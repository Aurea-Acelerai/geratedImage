#!/usr/bin/env python3
"""Chat de teste no estilo ChatGPT para o designer-imagegen.

  python3 chat_server.py              # http://127.0.0.1:8766  (usa OPENAI_API_KEY)
  python3 chat_server.py --mock       # sem API: imagens e revisões falsas, só para ver a interface

Sem dependências (só stdlib). Por cliente, em test/clients/<id>/: client.json e assets/ (logo, referências,
peças, produtos enviados pela interface). As imagens geradas ficam em test/chat_out/<id>/.

Cada mensagem passa pelo mesmo pipeline do teste A/B/C: system prompt do designer (com as regras de
docs/08) -> briefing -> imagem (edição se houver imagens de entrada) -> checagens por código ->
critic (rubrica v3) -> até 2 correções. Sem OPENAI_API_KEY, se o CLI `claude` existir, só o briefing é gerado.

Limite conhecido: logo e texto exato deveriam ser compostos por código (compose_text_overlay, ainda não existe).
Aqui o logo vai como imagem de entrada e o critic reprova se for redesenhado (veto logo_inventado).
"""
import argparse, base64, getpass, ipaddress, json, mimetypes, os, pathlib, random, re, shutil, socket, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import checks, critic, regionedit, skills_router  # noqa: E402
import run_comparison as rc  # noqa: E402
import ui_server as ui  # noqa: E402  (openai_post, ApiError, env_models)

# CHAT_DATA_DIR separa os dados do uso real dos dos testes automáticos (nunca apague a pasta de uso)
DATA = pathlib.Path(os.getenv("CHAT_DATA_DIR") or ROOT)
CLIENTS, OUT = DATA / "clients", DATA / "chat_out"
LOG_DIR = DATA / "logs"
MOCK = False
LOG_LOCK = threading.Lock()
KEYCHAIN_SERVICE = "geratedimage-openai"
COMMONS_API = os.getenv("COMMONS_API", "https://commons.wikimedia.org/w/api.php")
WEB_UA = "geratedimage-prototype/0.1 (uso local de teste)"
WEB_ALLOW_LOCAL = os.getenv("WEB_ALLOW_LOCAL") == "1"  # só para testes automáticos (servidor falso em 127.0.0.1)
GENERIC_ALIAS = {"logo", "foto", "imagem", "image", "img", "screenshot", "captura", "tela", "produto", "pessoa", "referencia", "peca",
                 "copy", "novo", "final", "versao", "whatsapp", "download", "photo", "picture", "untitled"}
CONV_LOCK = threading.Lock()  # duas tarefas da mesma conversa não podem se sobrescrever
CONV_BUSY = {}  # (cliente, conversa) -> nº de tarefas em andamento; protegido por CONV_LOCK. Excluir uma conversa ocupada seria desfeito pelo record()
FIDELITY_REJECTED = set()  # modelos que recusaram input_fidelity (não insiste a cada tentativa)
FIDELITY_MSG = "O modelo de imagem não aceitou input_fidelity=high; usei sem ele. A fidelidade ao rosto, logo ou produto de referência pode cair."
MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/svg+xml": "svg"}
KIND_ROLE = {
    "referencia": "REFERÊNCIA de estilo, cena ou assunto: inspire-se, não copie",
    "pessoa": "FOTO de pessoa real com autorização: é a IDENTIDADE a preservar (mesmo rosto, cabelo e traços); nunca substitua por sósia ou modelo genérico",
    "logo": "LOGO oficial do cliente: deve aparecer idêntico, nunca redesenhado nem alterado",
    "peca": "PEÇA já entregue ao cliente: mantenha o mesmo estilo e a mesma linguagem visual",
    "produto": "PRODUTO do cliente: deve aparecer fiel ao original (forma, cor, rótulo)",
}
SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}  # "auto": acompanha o alvo da edição (sem alvo, 1024x1024)


def log_event(kind, **fields):
    """Uma linha JSON por evento em logs/events.jsonl. Nunca derruba o chat. Não registra chaves nem imagens."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"t": time.strftime("%H:%M:%S"), "kind": kind, **fields}, ensure_ascii=False)
        with LOG_LOCK, open(LOG_DIR / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


def slug(s):
    s = re.sub(r"[^a-z0-9_-]", "", str(s).lower())
    if not s:
        raise ui.ApiError(400, "id de cliente inválido")
    return s


def cdir(cid):
    d = CLIENTS / slug(cid)
    (d / "assets").mkdir(parents=True, exist_ok=True)
    if not (d / "client.json").exists() and cid == "71":
        shutil.copy(ROOT / "client_71.json", d / "client.json")
    return d


def load_client(cid):
    p = cdir(cid) / "client.json"
    if not p.exists():
        raise ui.ApiError(404, f"cliente {cid} não existe")
    return json.loads(p.read_text(encoding="utf-8"))


def load_assets(cid):
    p = cdir(cid) / "assets.json"
    assets = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    for a in assets:  # imagens anteriores aos apelidos ganham um a partir do nome do arquivo ('rodrigo.webp' -> 'rodrigo')
        a.setdefault("alias", derive_alias(a.get("name", "")))
    return assets


def with_urls(cid, assets):
    return [dict(a, url=f"/files/{slug(cid)}/assets/{a['file']}") for a in assets]


# ---------- OpenAI (JSON, multipart) ----------
def openai_multipart(path, fields, files, timeout=300):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ui.ApiError(400, "Defina OPENAI_API_KEY antes de iniciar o servidor (ou use --mock).")
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for name, fname, mime, data in files:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'
                     f'Content-Type: {mime}\r\n\r\n'.encode() + data + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(ui.OPENAI + path, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(raw)["error"]["message"]
        except Exception:
            msg = raw[:500]
        raise ui.ApiError(502, f"OpenAI {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise ui.ApiError(502, f"Falha de rede: {e.reason}")


def sniff_mime(b64):
    return {"iVBOR": "image/png", "/9j/4": "image/jpeg", "UklGR": "image/webp"}.get(b64[:5], "image/png")


def data_url(inp):
    return f"data:{inp['mime']};base64,{base64.b64encode(inp['bytes']).decode()}"


# ---------- etapas ----------
def build_user(text, size, history, inputs, feedback=None, prev=None, memory="", intent="new", original=None, library=""):
    u = f"Pedido atual (já resolvido com o contexto da conversa): {text}\n"
    if original and original.strip() != text.strip():
        u += f"Mensagem original do usuário: {original}\n"
    u += f"Contêiner/tamanho: {size}\n"
    if intent == "edit":
        u += ("Intenção: EDIÇÃO da Image 1 (o alvo de edição): escreva 'change only X; keep everything else unchanged' e repita as invariantes "
              "(rosto, pose, enquadramento, fundo, texto).\n")
    elif intent == "variation":
        u += "Intenção: VARIAÇÃO da Image 1: mantenha o conceito, a pessoa/produto/marca e o estilo; mude só o que o pedido indicar.\n"
    if library:
        u += "\nImagens da biblioteca do cliente que NÃO estão anexadas a este pedido: " + library + "\n"
    if memory:
        u += "\n" + memory + "\n"
    elif history:
        u += "\nConversa até aqui (mais antiga primeiro):\n" + "\n".join(
            f"- {'Usuário' if h.get('role') == 'user' else 'Designer'}: {str(h.get('text', ''))[:400]}" for h in history[-6:]) + "\n"
    if inputs:
        u += "\nImagens de entrada, na ordem:\n" + "\n".join(f"Image {i + 1}: {x['role_text']}" for i, x in enumerate(inputs)) + "\n"
        u += "Cite cada imagem pelo número no prompt final (Input images) e diga o que deve ficar idêntico.\n"
    if feedback:
        u += (f"\nA versão anterior foi reprovada. Prompt anterior:\n{prev}\n\nCorrija APENAS isto: {feedback}\n"
              "Repita as invariantes.")
    u += ('\n\nO assunto e a cena do **pedido atual** são exigências literais: preserve-os no prompt final e não reaproveite a cena de '
          'pedidos anteriores (a menos que o pedido atual seja uma edição da imagem anterior).\n'
          'Se o pedido não disser o que deve aparecer (sem assunto), ou se faltar uma referência obrigatória (pessoa nomeada sem foto), '
          'responda SOMENTE {"question":"<uma pergunta curta em português>","search":[{"q":"<consulta curta>","kind":"logo|pessoa|produto|referencia"}]} '
          '(o campo search é opcional: use-o quando a resposta é uma imagem que dá para buscar na web, como um logo ou a foto de uma pessoa pública).\n'
          'Caso contrário responda SOMENTE JSON: {"use_case":"...","role":"hero|cell","prompt":"<prompt final em inglês no schema>","note":"<aviso curto ao usuário, opcional: ex. falta a oferta, será composta depois>"}')
    return u


def write_briefing(ctx, text, size, history, inputs, feedback=None, prev=None, model=None, provider="openai", mode="livre", use_skills=True,
                   memory="", intent="new", original=None, library=""):
    if MOCK:
        time.sleep(0.5)
        if re.search(r"\bperguntar\b", text):
            return {"question": "(mock) Qual é a oferta da peça?"}
        return {"use_case": "ads-marketing", "role": "cell",
                "prompt": f"Use case: ads-marketing\nPrimary request: {text}\n"
                          + (f"Style/medium: {ctx.get('image_style', '')}\nColor palette: {', '.join(ctx.get('palette', []))}\n" if mode == "marca" else "")
                          + f"Input images: {len(inputs)}"
                          + (f"\n[mock: corrigido -> {feedback}]" if feedback else "")}
    system = rc.load_system_prompt(ctx, request=text, size=size, has_inputs=bool(inputs), mode=mode, use_skills=use_skills)
    user = build_user(text, size, history, inputs, feedback, prev, memory, intent, original, library)
    if provider == "claude":
        import run_briefings_claude as rbc
        return rbc.briefing(user, ctx, "sonnet", size, mode=mode, use_skills=use_skills, tail="")
    # o designer enxerga até 6 imagens de até 5 MB (token e limite); o modelo de imagem recebe todas
    seen = [x for x in inputs if len(x["bytes"]) <= 5 * 1024 * 1024 and x["mime"] in ("image/png", "image/jpeg", "image/webp")][:6]
    skipped = [x["name"] for x in inputs if x not in seen]
    if skipped:
        user += "\n(Imagens não anexadas a este briefing por tamanho ou formato, mas enviadas ao modelo de imagem: " + ", ".join(skipped) + ")"
    content = [{"type": "text", "text": user}]
    for x in seen:
        content.append({"type": "image_url", "image_url": {"url": data_url(x)}})
    r = ui.openai_post("/chat/completions", {
        "model": model or ui.env_models()["text_model"], "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]})
    return json.loads(r["choices"][0]["message"]["content"])


def make_image(prompt, size, quality, inputs, model, fidelity=None, notes=None, mask=None):
    if MOCK:
        time.sleep(0.8)
        w, h = (int(x) for x in size.split("x"))
        hue = random.randint(0, 360)
        svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'><rect width='100%' height='100%' "
               f"fill='hsl({hue},55%,52%)'/><text x='50%' y='42%' font-size='{w // 14}' fill='white' text-anchor='middle' font-weight='bold'>"
               f"DEMONSTRAÇÃO</text><text x='50%' y='52%' font-size='{w // 26}' fill='white' text-anchor='middle'>"
               f"imagem FALSA: a OpenAI não foi chamada</text><text x='50%' y='60%' font-size='{w // 34}' fill='white' text-anchor='middle'>"
               f"para imagens reais rode ./run_chat.sh com a chave ({len(inputs)} entrada(s))</text></svg>")
        return base64.b64encode(svg.encode()).decode(), "svg"
    if inputs:
        files = [("image[]", f"in{i}.{MIME_EXT.get(x['mime'], 'png')}", x["mime"], x["bytes"]) for i, x in enumerate(inputs)]
        if mask:  # a máscara vale para a primeira imagem (o alvo); transparente = onde o modelo pode editar
            files.append(("mask", "mask.png", "image/png", mask))
        fields = {"model": model, "prompt": prompt, "size": size, "quality": quality, "n": 1}
        if fidelity and model in FIDELITY_REJECTED:
            fidelity = None
            if notes is not None and FIDELITY_MSG not in notes:
                notes.append(FIDELITY_MSG)
        if fidelity:
            fields["input_fidelity"] = fidelity  # alta fidelidade preserva rosto, logo e produto das imagens de entrada
        try:
            r = openai_multipart("/images/edits", fields, files)
        except ui.ApiError as e:
            if fidelity and "input_fidelity" in str(e):  # o modelo não aceita o parâmetro: repete sem ele e avisa
                fields.pop("input_fidelity")
                FIDELITY_REJECTED.add(model)
                if notes is not None and FIDELITY_MSG not in notes:
                    notes.append(FIDELITY_MSG)
                r = openai_multipart("/images/edits", fields, files)
            else:
                raise
    else:
        r = ui.openai_post("/images/generations", {"model": model, "prompt": prompt, "size": size, "quality": quality, "n": 1})
    return r["data"][0]["b64_json"], "png"


def do_review(ctx, text, briefing, b64, ext, size, inputs, model, notes="", packs=None):
    if MOCK:
        time.sleep(0.4)
        rv = {"scores": {k: random.randint(6, 10) for k in critic.weights_for(packs)}, "veto": random.choice([[], [], [], ["logo_inventado"]]),
              "issues": [{"criterion": "composition", "evidence": "(mock) exemplo", "severity": "baixa"}],
              "fix": "(mock) aumentar contraste do primeiro plano"}
    else:
        def vlm(system, user_text, images):
            content = [{"type": "text", "text": user_text}]
            for label, im in images:
                content += [{"type": "text", "text": label}, {"type": "image_url", "image_url": {"url": f"data:{sniff_mime(im)};base64,{im}"}}]
            r = ui.openai_post("/chat/completions", {"model": model, "response_format": {"type": "json_object"},
                                                     "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]})
            return r["choices"][0]["message"]["content"]
        imgs = [("Imagem avaliada", b64)]
        for x in inputs:
            imgs.append((f"Referência fornecida ({x['kind']}): {x['name']}", base64.b64encode(x["bytes"]).decode()))
        rv = critic.review(vlm, briefing, ctx, text, imgs, notes=notes, packs=packs)
    if ext == "png":
        rv = checks.apply(rv, b64, size)
    s, ok = critic.decide(rv, packs=packs)
    return rv, s, ok


def find_out(cid, mid):
    mid = re.sub(r"[^a-z0-9]", "", mid)
    for p in (OUT / slug(cid)).glob(f"{mid}.*"):
        return p
    raise ui.ApiError(404, "imagem a editar não encontrada")


def collect_inputs(cid, edit_of, asset_ids):
    inputs = []
    if edit_of:
        p = find_out(cid, edit_of)
        mime = "image/svg+xml" if p.suffix == ".svg" else "image/png"
        inputs.append(dict(kind="alvo", name=p.name, mime=mime, bytes=p.read_bytes(),
                           role_text="ALVO DE EDIÇÃO: peça gerada anteriormente; mude só o que o pedido atual pede e mantenha o resto idêntico"))
    by_id = {a["id"]: a for a in load_assets(cid)}
    missing = [aid for aid in asset_ids if aid not in by_id]
    if missing:
        raise ui.ApiError(409, f"Uma imagem fixada não existe mais na biblioteca ({', '.join(missing)}). Remova-a da conversa (×) e envie de novo: "
                               "sem ela a imagem sairia sem a referência.")
    for aid in asset_ids:
        a = by_id[aid]
        p = cdir(cid) / "assets" / a["file"]
        if not p.exists():
            raise ui.ApiError(409, f"O arquivo de '{a['name']}' sumiu da biblioteca. Envie a imagem de novo.")
        inputs.append(dict(id=a["id"], kind=a["kind"], name=a["name"], mime=a["mime"], bytes=p.read_bytes(),
                           role_text=f"{KIND_ROLE.get(a['kind'], 'imagem do cliente')} (arquivo: {a['name']})"))
    return inputs


# ---------- handlers ----------
def api_state(_):
    CLIENTS.mkdir(exist_ok=True)
    cdir("71")
    clients = []
    for d in sorted(CLIENTS.iterdir()):
        if (d / "client.json").exists():
            clients.append({"id": d.name, "name": json.loads((d / "client.json").read_text(encoding="utf-8")).get("name", d.name)})
    return {"mock": MOCK, "has_key": bool(os.getenv("OPENAI_API_KEY")), "has_claude": shutil.which("claude") is not None,
            **ui.env_models(), "pass_score": critic.PASS_SCORE, "max_cycles": critic.MAX_CYCLES, "clients": clients,
            "kinds": list(KIND_ROLE), "sizes": sorted(SIZES), "web_search": True}


def api_client(b):
    cid = b["id"]
    return {"id": slug(cid), "client": load_client(cid), "assets": with_urls(cid, load_assets(cid))}


def api_client_new(b):
    name = str(b.get("name", "")).strip()[:80]
    if len(name) < 2:
        raise ui.ApiError(400, "dê um nome ao cliente")
    base = slug(re.sub(r"\s+", "-", skills_router.norm(name))) if re.search(r"[a-z0-9]", skills_router.norm(name)) else "cliente"
    cid, n = base, 2
    while (CLIENTS / cid / "client.json").exists():
        cid, n = f"{base}-{n}", n + 1
    d = cdir(cid)
    ctx = {"id": cid, "name": name, "sector": str(b.get("sector", ""))[:120], "audience": "", "tone": "", "palette": [], "typography": "",
           "image_style": "", "approved_references": []}
    (d / "client.json").write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event("cliente_novo", id=cid)
    return {"id": cid, "client": ctx}


def api_client_save(b):
    d = cdir(b["id"])
    (d / "client.json").write_text(json.dumps(b["client"], ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "id": slug(b["id"])}


def api_asset(b):
    cid, mime = b["client"], b.get("mime", "")
    if mime not in MIME_EXT:
        raise ui.ApiError(400, "formato não suportado (use PNG, JPG, WEBP ou SVG)")
    if mime == "image/svg+xml" and not MOCK:
        raise ui.ApiError(400, "SVG não é aceito pela API de imagem: converta a logo para PNG (fundo transparente) antes de enviar.")
    if b.get("kind") not in KIND_ROLE:
        raise ui.ApiError(400, f"tipo inválido; use um de {list(KIND_ROLE)}")
    return {"asset": store_asset(cid, b["kind"], b.get("name"), mime, base64.b64decode(b["b64"]), b.get("alias"))}


def derive_alias(name):
    """Apelido a partir do nome do arquivo ('rodrigo.webp' -> 'rodrigo'); vazio se só tiver palavras genéricas."""
    stem = re.sub(r"[_\-.]+", " ", os.path.splitext(os.path.basename(name or ""))[0]).lower()
    words = [w for w in re.findall(r"[a-zà-ú0-9]+", stem) if not w.isdigit() and len(w) >= 3 and skills_router.norm(w) not in GENERIC_ALIAS]
    return " ".join(words)[:60]


def store_asset(cid, kind, name, mime, data, alias=None, extra=None):
    if len(data) > 20 * 1024 * 1024:
        raise ui.ApiError(400, "arquivo maior que 20 MB")
    aid = uuid.uuid4().hex[:8]
    clean = re.sub(r"[\x00-\x1f\x7f]", " ", os.path.basename(name or f"{aid}.{MIME_EXT[mime]}"))[:80]
    a = {"id": aid, "kind": kind, "name": clean, "alias": re.sub(r"[\x00-\x1f\x7f]", " ", (alias if alias is not None else derive_alias(clean)))[:60].strip(),
         "file": f"{aid}.{MIME_EXT[mime]}", "mime": mime, **(extra or {})}
    (cdir(cid) / "assets" / a["file"]).write_bytes(data)
    assets = load_assets(cid) + [a]
    (cdir(cid) / "assets.json").write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
    return with_urls(cid, [a])[0]


def api_asset_alias(b):
    cid = b["client"]
    assets = load_assets(cid)
    hit = [a for a in assets if a["id"] == b["id"]]
    if not hit:
        raise ui.ApiError(404, "imagem não encontrada na biblioteca")
    hit[0]["alias"] = re.sub(r"[\x00-\x1f\x7f]", " ", str(b.get("alias", "")))[:60].strip()
    (cdir(cid) / "assets.json").write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "alias": hit[0]["alias"]}


def alias_matches(text, assets):
    """Imagens da biblioteca cujo apelido aparece no texto (palavra inteira): 'rodrigo faro' casa com o apelido 'rodrigo'."""
    t = " " + skills_router.norm(text) + " "
    out = []
    for a in assets:
        al = skills_router.norm(a.get("alias") or "").strip()
        if not al:
            continue
        whole = lambda w: re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", t)
        if whole(al) or (len(al.split()) > 1 and all(whole(w) for w in al.split())):
            out.append(a)
    return out


def resolve_files(cid, conv, b, text):
    """Arquivos da CONVERSA (como no ChatGPT): o que já estava na conversa + o que a tela mandou + o que o texto cita pelo nome."""
    assets = load_assets(cid)
    by_id = {a["id"]: a for a in assets}
    ids, stale = [], []
    for i in conv.get("files", []):
        (ids if i in by_id else stale).append(i)
    for i in b.get("asset_ids") or []:
        if i not in ids:
            ids.append(i)  # id inexistente cai no erro 409 de collect_inputs
    auto = []
    for a in alias_matches(text, assets):
        if a["id"] not in ids:
            ids.append(a["id"])
            auto.append(a)
    return ids, auto, stale


def api_conv_files(b):
    """Fixa ou solta imagens na conversa (fica no servidor: recarregar a página não perde)."""
    with CONV_LOCK:
        conv = load_conv(b["client"], b.get("conv") or "x")
        files = [i for i in conv.get("files", []) if i not in set(b.get("drop") or [])]
        for i in b.get("add") or []:
            if i not in files:
                files.append(i)
        conv["files"] = files
        save_conv(conv)
    return {"files": files}


def api_asset_delete(b):
    cid = b["client"]
    assets = load_assets(cid)
    gone = [a for a in assets if a["id"] == b["id"]]
    for a in gone:
        (cdir(cid) / "assets" / a["file"]).unlink(missing_ok=True)
    (cdir(cid) / "assets.json").write_text(json.dumps([a for a in assets if a["id"] != b["id"]], ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


def openai_get(path, timeout=30):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ui.ApiError(400, "Sem OPENAI_API_KEY.")
    req = urllib.request.Request(ui.OPENAI + path, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(raw)["error"]["message"]
        except Exception:
            msg = raw[:300]
        raise ui.ApiError(502, f"OpenAI {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise ui.ApiError(502, f"Falha de rede: {e.reason}")


def api_models(_):
    """Confere a chave e os modelos da conta. Nunca derruba a tela: devolve o diagnóstico."""
    em = ui.env_models()
    if MOCK:
        return {"ok": True, "image_models": [em["image_model"]], "text_models": [em["text_model"]], "notes": ["modo mock"]}
    if not os.getenv("OPENAI_API_KEY"):
        return {"ok": False, "image_models": [], "text_models": [], "notes": ["Sem OPENAI_API_KEY: só o briefing sai (via Claude, se instalado)."]}
    try:
        ids = sorted(m["id"] for m in openai_get("/models").get("data", []))
    except ui.ApiError as e:
        return {"ok": False, "image_models": [], "text_models": [], "notes": [str(e)]}
    image = [i for i in ids if "image" in i]
    text = [i for i in ids if i.startswith(("gpt-", "o1", "o3", "o4", "chatgpt")) and "image" not in i and "audio" not in i
            and "realtime" not in i and "tts" not in i and "transcribe" not in i]
    notes = []
    if em["image_model"] not in ids:
        notes.append(f"O modelo de imagem '{em['image_model']}' não aparece na sua conta. Escolha outro na lista ou defina IMAGE_MODEL.")
    if em["text_model"] not in ids:
        notes.append(f"O modelo de texto '{em['text_model']}' não aparece na sua conta. Escolha outro na lista ou defina TEXT_MODEL.")
    if not image:
        notes.append("Nenhum modelo de imagem listado: a organização pode precisar de verificação para gerar imagens.")
    return {"ok": not notes, "image_models": image, "text_models": text, "notes": notes}


# ---------- chave da OpenAI pelo navegador (nunca passa pelo chat nem por arquivo do repositório) ----------
def load_key_from_keychain():
    if os.getenv("OPENAI_API_KEY") or sys.platform != "darwin":
        return False
    try:
        r = subprocess.run(["security", "find-generic-password", "-a", getpass.getuser(), "-s", KEYCHAIN_SERVICE, "-w"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            os.environ["OPENAI_API_KEY"] = r.stdout.strip()
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def api_setkey(b):
    key = str(b.get("key", "")).strip()
    if not re.fullmatch(r"sk-[A-Za-z0-9_\-]{20,}", key):
        raise ui.ApiError(400, "Isso não parece uma chave da OpenAI (começa com sk- e é longa).")
    old = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = key
    try:
        openai_get("/models")
    except ui.ApiError as e:
        if old is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = old
        raise ui.ApiError(400, f"A OpenAI não aceitou a chave: {e}")
    saved = False
    if b.get("save") and sys.platform == "darwin":
        try:  # a chave aparece por um instante na lista de processos; em troca, não digita de novo nunca mais
            subprocess.run(["security", "add-generic-password", "-a", getpass.getuser(), "-s", KEYCHAIN_SERVICE, "-U", "-w", key],
                           capture_output=True, timeout=15, check=True)
            saved = True
        except Exception:  # noqa: BLE001
            saved = False
    log_event("chave", definida=True, guardada_no_keychain=saved)  # nunca a chave
    return {"ok": True, "saved": saved}


# ---------- busca de imagens na web (logos, pessoas públicas, produtos): fonte aberta, o usuário escolhe ----------
class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _check_url(url):
    u = urllib.parse.urlparse(url)
    if WEB_ALLOW_LOCAL:
        if u.scheme not in ("http", "https") or not u.hostname:
            raise ui.ApiError(400, "link inválido")
        return
    if u.scheme != "https" or not u.hostname:
        raise ui.ApiError(400, "só são aceitos links https de imagem")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 443)
    except OSError:
        raise ui.ApiError(400, "não consegui resolver o endereço do link")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ui.ApiError(400, "endereço não permitido (rede interna)")


def fetch_image(url, limit=15 * 1024 * 1024):
    """Baixa uma imagem com limites: https, fora de rede interna, até 15 MB, só PNG/JPEG/WEBP (confere o conteúdo, não só o cabeçalho)."""
    _check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": WEB_UA})
    try:
        with urllib.request.build_opener(_SafeRedirect).open(req, timeout=25) as r:
            data = r.read(limit + 1)
    except urllib.error.URLError as e:
        raise ui.ApiError(502, f"Não consegui baixar a imagem: {getattr(e, 'reason', e)}")
    if len(data) > limit:
        raise ui.ApiError(400, "imagem maior que 15 MB")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return data, "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data, "image/webp"
    raise ui.ApiError(400, "o link não é uma imagem PNG, JPEG ou WEBP")


def _plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def api_websearch(b):
    q = str(b.get("q", "")).strip()[:120]
    if len(q) < 2:
        raise ui.ApiError(400, "digite o que buscar (ex.: logo CVC)")
    params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": "6", "gsrsearch": f"{q} filetype:bitmap|drawing",
              "gsrlimit": "14", "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata", "iiurlwidth": "1024"}
    req = urllib.request.Request(COMMONS_API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": WEB_UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        raise ui.ApiError(502, f"A busca na web falhou: {e}")
    out = []
    for p in sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata") or {}
        if ii.get("mime") not in ("image/png", "image/jpeg", "image/webp", "image/svg+xml"):
            continue
        out.append({"title": p.get("title", "").replace("File:", "", 1), "url": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl"),
                    "license": _plain((em.get("LicenseShortName") or {}).get("value")) or "licença não informada",
                    "author": _plain((em.get("Artist") or {}).get("value"))[:80], "mime": ii.get("mime"), "w": ii.get("width"), "h": ii.get("height")})
    return {"results": out[:8], "source": "Wikimedia Commons",
            "aviso": "São candidatos, não confirmações: confira se é a marca ou pessoa certa e a licença. O direito de uso é responsabilidade de quem publica."}


def api_webadd(b):
    kind = b.get("kind") if b.get("kind") in KIND_ROLE else "referencia"
    data, mime = fetch_image(str(b.get("url", "")))
    ext = MIME_EXT[mime]
    name = (str(b.get("name") or "imagem-web").strip() or "imagem-web")[:60]
    if not name.lower().endswith("." + ext):
        name = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", name) + "." + ext
    extra = {"origem": "web", "pagina": str(b.get("page") or "")[:300], "licenca": str(b.get("license") or "")[:80]}
    return {"asset": store_asset(b["client"], kind, name, mime, data, b.get("alias"), extra)}


# ---------- jobs (a geração leva minutos: o navegador acompanha por polling) ----------
JOBS = {}


def start_job(fn, meta=None):
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "status": "running", "steps": [], "message": None, "error": None, "t0": time.time()}
    for old in sorted(JOBS.values(), key=lambda j: j["t0"])[:-40]:
        JOBS.pop(old["id"], None)
    JOBS[jid] = job
    log_event("start", job=jid, **(meta or {}))

    def emit(text, **extra):
        step = {"t": round(time.time() - job["t0"], 1), "text": text, **extra}
        job["steps"].append(step)
        log_event("step", job=jid, t=step["t"], text=text, **{k: v for k, v in extra.items() if k in ("image_url", "prompt")})

    def runner():
        try:
            job["message"] = fn(emit)
            job["status"] = "done"
            m = job["message"] or {}
            log_event("done", job=jid, tipo=m.get("kind"), intent=m.get("intent"), packs=m.get("packs"), score=m.get("score"),
                      approved=m.get("approved"), veto=m.get("veto"), avisos=m.get("avisos"), resolved=m.get("resolved"),
                      image=m.get("id"), pergunta=m.get("text") if m.get("kind") == "text" else None, segundos=m.get("seconds"))
        except ui.ApiError as e:
            msg = str(e)
            if re.search(r"safety|moderation|content[_ ]policy|blocked", msg, re.I):
                msg += " | Dica: a OpenAI pode bloquear pedidos com pessoas reais ou conteúdo sensível. Reescreva sem o nome da pessoa ou use outra foto de referência."
            job["status"], job["error"] = "error", msg
            log_event("erro", job=jid, erro=msg)
        except Exception as e:  # noqa: BLE001
            job["status"], job["error"] = "error", f"{type(e).__name__}: {e}"
            log_event("erro", job=jid, erro=job["error"])

    threading.Thread(target=runner, daemon=True).start()
    return jid


def api_job(b):
    job = JOBS.get(b.get("id"))
    if not job:
        raise ui.ApiError(404, "tarefa não encontrada (o servidor foi reiniciado?)")
    since = int(b.get("since") or 0)
    return {"status": job["status"], "steps": job["steps"][since:], "next": len(job["steps"]),
            "message": job["message"], "error": job["error"], "elapsed": round(time.time() - job["t0"], 1)}


def api_chat(b):
    """Valida na hora (falha rápido) e roda o pipeline numa tarefa em segundo plano."""
    cid, text = b["client"], (b.get("text") or "").strip()
    if not text:
        raise ui.ApiError(400, "mensagem vazia")
    ctx = load_client(cid)
    conv = load_conv(cid, b.get("conv") or uuid.uuid4().hex[:10])
    b["conv"] = conv["id"]
    files, auto, stale = resolve_files(cid, conv, b, text)
    inputs = collect_inputs(cid, b.get("edit_of"), files)
    if not MOCK and not os.getenv("OPENAI_API_KEY") and not shutil.which("claude"):
        raise ui.ApiError(400, "Sem OPENAI_API_KEY e sem o CLI claude: nada a executar.")
    provider_now = "mock" if MOCK else ("openai" if os.getenv("OPENAI_API_KEY") else "claude-cli (SEM chave: nenhuma imagem é gerada)")
    meta = {"provedor": provider_now, "client": cid, "conv": b.get("conv"), "texto": text, "modo": b.get("mode") or "livre", "tamanho": b.get("size"),
            "qualidade": b.get("quality"), "anexos": [{"tipo": x["kind"], "nome": x["name"]} for x in inputs], "auto_anexados": [a["name"] for a in auto], "edit_of": b.get("edit_of"),
            "melhorias": {"designer": (b.get("improve") or {}).get("designer", True), "skills": (b.get("improve") or {}).get("skills", True),
                          "critic": b.get("review", True), "comparar": (b.get("improve") or {}).get("compare_raw", False)},
            "modelos": {"imagem": b.get("image_model"), "texto": b.get("text_model")}}
    key = (slug(cid), conv["id"])
    with CONV_LOCK:
        CONV_BUSY[key] = CONV_BUSY.get(key, 0) + 1

    def task(emit):
        try:
            return run_chat(b, emit, cid, text, ctx, inputs, files, auto, stale)
        finally:
            with CONV_LOCK:
                CONV_BUSY[key] -= 1
                if not CONV_BUSY[key]:
                    del CONV_BUSY[key]
    return {"job": start_job(task, meta)}


# ---------- memória da conversa (em disco; sobrevive a reinício e a atualizar a página) ----------
CONV_DIR = DATA / "conversations"
MEMORY_PROMPT_PATH = ROOT.parent / "prompts" / "memory.system.md"
IDENTITY_KINDS = ("pessoa", "logo", "produto")
EDIT_WORDS = re.compile(r"\b(mude|muda|troque|troca|tire|tira|remova|remove|adicione|coloque|agora|mais|menos|deixe|deixa|altere|ajuste)\b", re.I)


def conv_path(cid, conv_id):
    return CONV_DIR / slug(cid) / f"{slug(conv_id)}.json"


def load_conv(cid, conv_id):
    p = conv_path(cid, conv_id)
    if p.exists():
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            c.setdefault("files", [])
            return c
        except json.JSONDecodeError:  # arquivo corrompido: guarda a cópia e recomeça, em vez de travar a conversa
            p.rename(p.with_name(p.name + f".corrompido-{int(time.time())}"))
    return {"id": slug(conv_id), "client": slug(cid), "created": time.strftime("%Y-%m-%d %H:%M:%S"), "turns": [], "carry": [], "files": []}


def save_conv(conv):
    p = conv_path(conv["client"], conv["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def last_image(cid, conv):
    for t in reversed(conv["turns"]):
        if t.get("image_id"):
            try:
                p = find_out(cid, t["image_id"])
                if p.suffix == ".svg" and not MOCK:  # imagem falsa de um teste mock: a API real não aceita SVG
                    return None, None
                return p, t["image_id"]
            except ui.ApiError:
                return None, None
    return None, None


def memory_text(conv, files_desc=""):
    """O que o designer e o resolvedor 'lembram': a transcrição inteira, os arquivos da conversa e os detalhes recentes."""
    turns = conv["turns"]
    if not turns and not conv["carry"] and not files_desc:
        return ""
    L = ["Memória da conversa. Tudo o que foi dito, anexado e gerado nesta conversa continua valendo: não peça de novo o que já está aqui."]
    if files_desc:
        L.append("Arquivos da conversa (já anexados; valem em todos os pedidos até o usuário remover): " + files_desc)
    if turns:
        L.append("Transcrição (mais antigo primeiro):")
        if len(turns) > 40:
            L.append(f"(... {len(turns) - 40} turnos mais antigos omitidos)")
        for t in turns[-40:]:
            L.append(f'[{t["n"]}] Usuário: {t["request"][:300]}')
            if t.get("question"):
                L.append(f'     Designer: perguntou "{t["question"][:200]}" (sem imagem)')
            else:
                L.append(f'     Designer: gerou a imagem {t["image_id"]} ({"aprovada" if t["approved"] else "reprovada"}, nota {t["score"]}); briefing: {t["briefing"][:160]}')
        L.append("Detalhes dos últimos turnos:")
        recent = turns[-3:]
        for i, t in enumerate(recent):
            lim = 1500 if i == len(recent) - 1 else 500  # o último pedido vai quase inteiro: é dele que o resolvedor parte
            if t.get("question"):
                L.append(f'{t["n"]}. Pedido: {t["resolved"][:lim]} | o designer PERGUNTOU: "{t["question"]}" (sem imagem)')
            else:
                L.append(f'{t["n"]}. Pedido: {t["resolved"][:lim]} | intenção: {t["intent"]} | resultado: imagem {t["image_id"]} '
                         f'(nota {t["score"]}, {"aprovada" if t["approved"] else "reprovada"}) | briefing final: {t["briefing"][:600]}')
    if conv["carry"]:
        L.append("Instruções duradouras do usuário: " + "; ".join(conv["carry"]))
    last = turns[-1] if turns else None
    if last and last.get("question"):
        L.append(f'PERGUNTA PENDENTE: o último turno terminou numa pergunta do designer; a nova mensagem provavelmente a responde '
                 f'(pedido original: {last["resolved"][:1500]}; intenção original: {last["intent"]})')
    return "\n".join(L)


def resolve_turn(conv, text, avail, model, provider, has_files=False):
    """Entende a mensagem no contexto (como o ChatGPT): devolve intenção e um pedido autossuficiente. Nunca derruba o fluxo."""
    triv = {"intent": "new", "request": text, "use_last_image": False, "carry": list(conv["carry"])}
    if provider != "openai" or not (conv["turns"] or conv["carry"] or has_files):
        return triv, None
    mem = memory_text(conv)
    last = conv["turns"][-1] if conv["turns"] else None
    if MOCK:
        if last is None:
            m = re.search(r"([^,;|]+?) \(referencia\) \[id (\w+)\]", avail)
            if m and "referencia" in skills_router.norm(text) and EDIT_WORDS.search(text):
                return {**triv, "intent": "edit", "request": text, "edit_target": m.group(2)}, None
            return triv, None
        if last.get("question"):
            li = last.get("intent", "new")
            return {**triv, "intent": li, "request": f'{last["resolved"]} {text}', "use_last_image": li in ("edit", "variation")}, None
        if EDIT_WORDS.search(text):
            m = re.search(r"([^,;|]+?) \(referencia\) \[id (\w+)\]", avail)
            if m and "referencia" in skills_router.norm(text):
                return {**triv, "intent": "edit", "request": f'{last["resolved"]}; {text}', "edit_target": m.group(2)}, None
            return {**triv, "intent": "edit", "request": f'{last["resolved"]}; {text}', "use_last_image": True}, None
        return triv, None
    user = f"{mem}\n\nImagens disponíveis agora: {avail}\n\nNova mensagem do usuário: {text}"
    try:
        r = ui.openai_post("/chat/completions", {"model": model, "response_format": {"type": "json_object"},
                                                 "messages": [{"role": "system", "content": MEMORY_PROMPT_PATH.read_text(encoding="utf-8")},
                                                              {"role": "user", "content": user}]})
        out = json.loads(r["choices"][0]["message"]["content"])
        if out.get("intent") not in ("new", "edit", "variation") or not str(out.get("request", "")).strip():
            raise ValueError("resposta do resolvedor inválida")
        carry = [str(c)[:160] for c in (out.get("carry") or []) if str(c).strip()][:8]
        return {"intent": out["intent"], "request": str(out["request"]).strip(),
                "use_last_image": bool(out.get("use_last_image")) and out["intent"] in ("edit", "variation"),
                "edit_target": (str(out["edit_target"]).strip() if out.get("edit_target") and out["intent"] == "edit" else None),
                "scope": (out.get("scope") if out["intent"] == "edit" and out.get("scope") in ("local", "extend", "global") else None),
                "carry": carry or list(conv["carry"])}, None
    except Exception as e:  # noqa: BLE001
        return triv, f"não consegui resolver o contexto ({type(e).__name__}); usei a sua mensagem como está"


def api_clientlog(b):
    """Erros do navegador (JavaScript, rede) vão para o mesmo registro, para serem vistos e corrigidos."""
    log_event("ui", tipo=str(b.get("kind", ""))[:30], mensagem=str(b.get("message", ""))[:600])
    return {"ok": True}


def _strict_id(v, what):
    """Id de cliente/conversa para operações que removem ou alteram: aceita só o que o slug() deixaria intacto.
    O slug() sozinho apagaria os caracteres ruins e acertaria OUTRA conversa ('../abc' viraria 'abc')."""
    if not isinstance(v, str) or v != slug(v):
        raise ui.ApiError(400, f"id de {what} inválido")
    return v


def _conv_title(c):
    t = c.get("title")
    if isinstance(t, str) and t.strip():
        return t.strip()
    first = next((str(x.get("request") or "").strip() for x in c.get("turns", []) if isinstance(x, dict) and x.get("request")), "")
    return (first[:60].rstrip() + "…") if len(first) > 60 else first


def list_convs(cid):
    """Histórico do cliente, do mais recente ao mais antigo. Arquivo ilegível não derruba a lista: é contado em 'skipped'."""
    d = CONV_DIR / _strict_id(cid, "cliente")
    convs, skipped = [], 0
    for p in (d.glob("*.json") if d.is_dir() else []):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            turns = c["turns"]
            if not isinstance(turns, list):
                raise ValueError("turns")
            mtime = p.stat().st_mtime
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            skipped += 1
            log_event("conv_list_skipped", client=d.name, file=p.name)
            continue
        if turns:  # conversa sem mensagens não entra no histórico
            convs.append({"id": p.stem, "title": _conv_title(c), "updated": int(mtime), "count": len(turns), "_m": mtime})
    convs.sort(key=lambda x: x.pop("_m"), reverse=True)
    return {"convs": convs, "skipped": skipped}


def _existing_conv_path(b):
    p = conv_path(_strict_id(b["client"], "cliente"), _strict_id(b["conv"], "conversa"))
    if not p.is_file():
        raise ui.ApiError(404, "conversa não encontrada")
    return p


def api_conv_delete(b):
    with CONV_LOCK:
        p = _existing_conv_path(b)
        if CONV_BUSY.get((p.parent.name, p.stem)):
            raise ui.ApiError(409, "a conversa ainda está gerando uma resposta; espere terminar para excluir")
        p.unlink()  # só o JSON da conversa; imagens de saída e biblioteca ficam
    return {"ok": True}


def api_conv_rename(b):
    title = b["title"]
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
        raise ui.ApiError(400, "título deve ter de 1 a 80 caracteres")
    with CONV_LOCK:
        p = _existing_conv_path(b)
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            c = None
        if not isinstance(c, dict):
            raise ui.ApiError(422, "conversa ilegível; não dá para renomear")
        st = p.stat()
        c["title"] = title.strip()
        tmp = p.with_name(p.name + f".{uuid.uuid4().hex[:6]}.tmp")  # grava no caminho já validado, não no id de dentro do arquivo
        tmp.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
        os.utime(p, (st.st_atime, st.st_mtime))  # renomear não é atividade: não muda a ordem do histórico
    return {"ok": True}


def api_conv(b):
    return load_conv(b["client"], b.get("conv") or "x")


def api_asset_kind(b):
    cid = b["client"]
    if b.get("kind") not in KIND_ROLE:
        raise ui.ApiError(400, f"tipo inválido; use um de {list(KIND_ROLE)}")
    assets = load_assets(cid)
    hit = [a for a in assets if a["id"] == b["id"]]
    if not hit:
        raise ui.ApiError(404, "imagem não encontrada na biblioteca")
    hit[0]["kind"] = b["kind"]
    (cdir(cid) / "assets.json").write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


def run_chat(b, emit, cid, text, ctx, inputs, files=None, auto=None, stale=None):
    size = b.get("size") if b.get("size") in SIZES else "auto"
    quality = b.get("quality") or ui.env_models()["quality"]
    em = ui.env_models()
    text_model, image_model = b.get("text_model") or em["text_model"], b.get("image_model") or em["image_model"]
    history = b.get("history") or []
    provider = "claude" if (not MOCK and not os.getenv("OPENAI_API_KEY")) else "openai"
    mode = "marca" if b.get("mode") == "marca" else "livre"
    imp = {"designer": True, "skills": True, "review": b.get("review", True), "compare_raw": False, **(b.get("improve") or {})}
    ctx_eff = ctx if mode == "marca" else {}
    ctx_critic = ctx if mode == "marca" else {"modo": "livre (sem marca do cliente): julgue assunto, estilo e paleta só pelo pedido e pelo briefing"}
    t0 = time.time()
    avisos = []
    files, auto, stale = list(files or []), list(auto or []), list(stale or [])
    if stale:
        avisos.append("Uma imagem que estava na conversa foi apagada da biblioteca e saiu dela.")
    if auto:
        emit("Anexei automaticamente pelo nome: " + ", ".join(f"{a['name']} ({a['kind']})" for a in auto) + ". Para tirar, clique no × do anexo.")

    # --- memória: entender a mensagem no contexto da conversa ---
    conv = load_conv(cid, b.get("conv") or uuid.uuid4().hex[:10])
    lastp, last_id = last_image(cid, conv)
    avail = (f"última imagem gerada (id {last_id}); " if last_id else "nenhuma imagem gerada ainda; ") + \
            ("fixadas na conversa: " + ", ".join(f"{x['name']} ({x['kind']})" + (f" [id {x['id']}]" if x.get("id") else "") for x in inputs if x["kind"] not in ("alvo",)) if inputs else "nenhuma imagem fixada")
    edit_turn = next((t for t in conv["turns"] if t.get("image_id") == b.get("edit_of")), None) if b.get("edit_of") else None
    if edit_turn:
        avail += (f" | ATENÇÃO: o usuário escolheu EDITAR a imagem do turno {edit_turn['n']} (id {edit_turn['image_id']}), que pode NÃO ser a última; "
                  f"o pedido daquele turno foi: {edit_turn['resolved'][:600]}")
    resolved, warn = resolve_turn(conv, text, avail, text_model, provider, has_files=bool(inputs))
    if warn:
        avisos.append(warn)
    text_eff, intent = resolved["request"], resolved["intent"]
    if b.get("edit_of") and intent == "new":
        intent = "edit"  # o botão "Editar esta imagem" vale mais que a leitura do resolvedor
    et = resolved.get("edit_target")
    if et and str(et).lower() != "last" and not any(x["kind"] == "alvo" for x in inputs):
        q = skills_router.norm(str(et))
        hit = next((x for x in inputs if x.get("id") and (x["id"] == et or skills_router.norm(x["name"]) == q or q in skills_router.norm(x["name"]))), None)
        if hit:  # o usuário falou de uma imagem ANEXADA ("a foto de referência"): ela é o alvo, não a última gerada
            intent = "edit"
            tgt = dict(hit, kind="alvo", role_text=f"ALVO DE EDIÇÃO: a imagem anexada '{hit['name']}'; mude só o que o pedido atual pede "
                                                   "(por exemplo, trocar a pessoa pela da imagem de identidade) e mantenha o resto idêntico: layout, textos, logo, produtos, selos e fundo")
            inputs = [tgt] + [x for x in inputs if x is not hit]
            emit(f"Alvo da edição: a imagem anexada «{hit['name']}» (não a última gerada).")
    if resolved["use_last_image"] and lastp and not any(x["kind"] == "alvo" for x in inputs):
        role = ("ALVO DE EDIÇÃO: a última imagem gerada; mude só o que o pedido atual pede e mantenha o resto idêntico" if intent == "edit"
                else "IMAGEM-BASE da variação: mantenha o conceito, a pessoa/produto/marca e o estilo; mude só o que o pedido indicar")
        inputs = [dict(kind="alvo" if intent == "edit" else "variacao", name=lastp.name, mime="image/svg+xml" if lastp.suffix == ".svg" else "image/png",
                       bytes=lastp.read_bytes(), role_text=role)] + list(inputs)
    if size == "auto" and not any(x["kind"] in ("alvo", "variacao") for x in inputs):
        size = "1024x1024"  # sem alvo não há proporção a acompanhar
    if intent in ("edit", "variation") and not any(x["kind"] in ("alvo", "variacao") for x in inputs):
        intent = "new"
        avisos.append("Não encontrei a imagem anterior para editar; gerei do zero com o pedido resolvido.")
    # edição localizada / extensão de fundo: o modelo só mexe numa região e o original volta idêntico por código
    region, alvo_in = None, next((x for x in inputs if x["kind"] == "alvo"), None)
    if (alvo_in and intent == "edit" and resolved.get("scope") in ("local", "extend") and imp.get("region", True)
            and regionedit.available() and not MOCK and provider == "openai"):
        try:
            if resolved["scope"] == "extend":
                out_size = size if size in ("1024x1536", "1536x1024", "1024x1024") else "1024x1536"
                ow, oh = (int(v) for v in out_size.split("x"))
                canvas, mask_png, rorig, place = regionedit.make_extend(alvo_in["bytes"], ow, oh)
                region = {"mode": "extend", "canvas": canvas, "mask": mask_png, "rorig": rorig, "place": place, "size": (ow, oh)}
                size = out_size
                emit(f"Extensão de fundo: a peça original fica intacta no centro e o modelo só preenche as faixas novas ({out_size}).")
            else:
                def chat_json(system, user_text, data_url):
                    r = ui.openai_post("/chat/completions", {"model": text_model, "response_format": {"type": "json_object"},
                                                             "messages": [{"role": "system", "content": system},
                                                                          {"role": "user", "content": [{"type": "text", "text": user_text},
                                                                                                       {"type": "image_url", "image_url": {"url": data_url}}]}]})
                    return r["choices"][0]["message"]["content"]
                regs = regionedit.locate(chat_json, alvo_in["bytes"], alvo_in["mime"], text_eff)
                ow, oh = regionedit.open_rgb(alvo_in["bytes"]).size
                boxes = regionedit.to_px(regs, ow, oh)
                region = {"mode": "local", "mask": regionedit.local_mask_png((ow, oh), boxes), "boxes": boxes, "orig": alvo_in["bytes"]}
                emit("Edição localizada: " + "; ".join(f"{lbl or 'região'} {[round(v, 2) for v in box]}" for lbl, box in regs) + ". Fora disso o original volta idêntico.")
        except Exception as e:  # noqa: BLE001
            region = None
            avisos.append(f"Não consegui limitar a edição a uma região ({type(e).__name__}: {str(e)[:90]}); editei a imagem inteira.")
    pinned_ids = {x.get("id") for x in inputs}
    suggest = [{"id": a["id"], "name": a["name"], "kind": a["kind"]} for a in load_assets(cid) if a["kind"] in IDENTITY_KINDS and a["id"] not in pinned_ids]
    library = ", ".join(f"{s['name']} ({s['kind']})" for s in suggest)
    lib = {a["id"]: a for a in load_assets(cid)}
    files_desc = ", ".join(f"{lib[i]['name']} ({lib[i]['kind']}" + (f"; apelido: {lib[i]['alias']}" if lib[i].get("alias") else "") + ")" for i in files if i in lib)
    memory = memory_text(conv, files_desc)
    if region:
        memory += ("\n" if memory else "") + (
            "Modo da edição: LOCALIZADA com máscara. O modelo de imagem só pode alterar a região mascarada (transparente) da Image 1; todo o resto da Image 1 "
            "volta idêntico por código. Descreva SOMENTE o que deve aparecer dentro dessa região, no mesmo estilo, luz e escala do entorno, e escreva "
            "'keep everything outside the masked area unchanged'." if region["mode"] == "local" else
            "Modo da edição: EXTENSÃO DE FUNDO. A peça original está no centro da Image 1 e volta idêntica por código; o modelo só preenche as faixas vazias "
            "em cima e embaixo. Descreva apenas a continuação natural do fundo (mesma luz, bokeh e cor), SEM objetos, pessoas ou texto novos.")
    if conv["turns"] or text_eff != text:
        emit(f"Memória: entendi como {'edição da imagem anterior' if intent == 'edit' else 'variação' if intent == 'variation' else 'pedido novo'}"
             + (f" · pedido resolvido: «{text_eff[:220]}»" if text_eff != text else ""))

    used = skills_router.select(text_eff, size, bool(inputs)) if (imp["designer"] and imp["skills"]) else []
    notes = skills_router.review_notes(used)
    packs = skills_router.packs_for(text_eff, size, bool(inputs), mode, bool(b.get("edit_of")) or intent in ("edit", "variation"),
                                    [x["kind"] for x in inputs])
    on = [k for k, label in (("designer", "briefing do designer"), ("skills", "skills de design"), ("review", "critic"), ("compare_raw", "comparação com o GPT puro")) if imp.get(k)]
    emit("Critic (modelo da OpenAI como juiz): critérios da base" + "".join(f" + {p}" for p in packs) + (" (imagem livre: sem critérios de marketing)" if not packs else ""))
    emit(f"Modo {'com marca do cliente' if mode == 'marca' else 'livre (sem marca)'} · melhorias ligadas: " + (", ".join(on) or "nenhuma (seu texto vai direto ao modelo)"))
    if used:
        emit("Skills de design aplicadas: " + ", ".join(s.replace("design-", "") for s in used))
    if inputs:
        emit("Imagens de entrada: " + ", ".join(f"{x['kind']} {x['name']}" for x in inputs))

    def record(**turn):
        with CONV_LOCK:  # relê do disco: outra tarefa da mesma conversa pode ter gravado um turno enquanto esta rodava
            fresh = load_conv(cid, conv["id"])
            fresh["turns"].append({"n": len(fresh["turns"]) + 1, "t": time.strftime("%H:%M:%S"), "request": text, "resolved": text_eff,
                                   "intent": intent, **turn})
            fresh["carry"] = resolved["carry"]
            fresh["files"] = files
            save_conv(fresh)

    if imp["designer"]:
        emit(f"O designer está escrevendo o briefing ({'OpenAI, modelo ' + text_model if provider == 'openai' and not MOCK else 'DEMONSTRAÇÃO, sem API' if MOCK else 'Claude CLI: SEM chave da OpenAI'})…")
        brief = write_briefing(ctx_eff, text_eff, size, history, inputs, model=text_model, provider=provider, mode=mode, use_skills=imp["skills"],
                               memory=memory, intent=intent, original=text, library=library)
        if brief.get("question"):
            record(question=brief["question"])
            sw = [{"q": str(s["q"])[:120], "kind": s.get("kind") if s.get("kind") in KIND_ROLE else "referencia"}
                  for s in (brief.get("search") or []) if isinstance(s, dict) and s.get("q")][:3]
            about_image = bool(re.search(r"foto|imagem|refer[eê]ncia|logo|arquivo|anex|pessoa|produto|marca", brief["question"], re.I))
            return {"role": "assistant", "kind": "text", "text": brief["question"], "conv": conv["id"], "suggest": suggest if about_image else [],
                    "suggest_web": sw if about_image else [], "files": files}
        if provider == "claude":
            return {"role": "assistant", "kind": "text", "briefing_only": True,
                    "text": "Sem OPENAI_API_KEY: gerei só o briefing, sem imagem.\n\n" + brief.get("prompt", "")}
        if brief.get("note"):
            avisos.append(str(brief["note"])[:300])
        emit("Briefing pronto.", prompt=brief["prompt"])
    else:
        if provider == "claude":
            return {"role": "assistant", "kind": "text", "text": "Sem OPENAI_API_KEY não há como gerar a imagem."}
        brief = {"prompt": text_eff}
        emit("Sem briefing do designer: o seu texto vai direto ao modelo de imagem.")
    do_rev = bool(imp["review"])
    max_cycle = critic.MAX_CYCLES if imp["designer"] else 0
    fidelity = "high" if any(x["kind"] in IDENTITY_KINDS + ("alvo", "variacao") for x in inputs) else None
    mid = re.sub(r"[^a-z0-9]", "", time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4])
    (OUT / slug(cid)).mkdir(parents=True, exist_ok=True)
    cycles, best = [], None
    for cycle in range(max_cycle + 1):
        how = "editando com as imagens de entrada" if inputs else "gerando"
        emit(f"Tentativa {cycle + 1}: {how} (OpenAI Images, modelo {image_model}, {size}, {quality}" + (", fidelidade alta" if fidelity and image_model not in FIDELITY_REJECTED else "") + ")…")
        tg = time.time()
        call_inputs, mask_png = inputs, None
        if region:
            mask_png = region["mask"]
            if region["mode"] == "extend":
                call_inputs = [dict(alvo_in, bytes=region["canvas"], mime="image/png")] + [x for x in inputs if x is not alvo_in]
        b64, ext = make_image(brief["prompt"], size, quality, call_inputs, image_model, fidelity, avisos, mask=mask_png)
        gid = f"{mid}c{cycle}"
        if region:  # guarda o que o modelo gerou e entrega o original recomposto
            raw = base64.b64decode(b64)
            (OUT / slug(cid) / f"{gid}raw.png").write_bytes(raw)
            fin = (regionedit.composite_local(region["orig"], raw, region["boxes"]) if region["mode"] == "local"
                   else regionedit.composite_extend(raw, region["rorig"], region["place"], region["size"]))
            b64, ext = base64.b64encode(fin).decode(), "png"
            emit("Original recolado fora da região editada (pixels idênticos).")
        (OUT / slug(cid) / f"{gid}.{ext}").write_bytes(base64.b64decode(b64))
        url = f"/files/{slug(cid)}/out/{gid}.{ext}"
        emit(f"Imagem da tentativa {cycle + 1} pronta em {round(time.time() - tg)}s.", image_url=url)
        entry = {"cycle": cycle, "prompt": brief["prompt"], "id": gid, "url": url}
        if do_rev:
            emit(f"O critic está revisando ({'OpenAI, modelo ' + (b.get('critic_model') or text_model) if not MOCK else 'DEMONSTRAÇÃO'})…")
            rv, s, ok = do_review(ctx_critic, text_eff, brief["prompt"], b64, ext, size, inputs, b.get("critic_model") or text_model, notes, packs)
            entry.update(score=s, approved=ok, veto=rv.get("veto", []), fix=rv.get("fix"), review=rv)
            emit(f"Nota {s}: {'aprovada' if ok else 'reprovada'}" + (f" · vetos: {', '.join(rv.get('veto', []))}" if rv.get("veto") else "")
                 + (f" · correção: {rv.get('fix')}" if not ok and rv.get("fix") else ""))
        else:
            rv, s, ok = None, None, None
        cycles.append(entry)
        if best is None or (s or 0) > (best["score"] or 0):
            best = {"score": s, "entry": entry, "rv": rv, "ok": ok}
        if not do_rev or ok or cycle == max_cycle:
            break
        emit("Corrigindo o briefing com a sugestão do critic…")
        brief = write_briefing(ctx_eff, text_eff, size, history, inputs, feedback=rv.get("fix"), prev=brief["prompt"],
                               model=text_model, provider=provider, mode=mode, use_skills=imp["skills"], memory=memory, intent=intent, original=text, library=library)
        if brief.get("question"):
            break
    e = best["entry"]
    if "identidade_divergente" in ((best["rv"] or {}).get("veto") or []):
        avisos.append("A imagem NÃO manteve a identidade da referência (pessoa, produto ou logo): não use como se fosse. Confira a foto anexada e o tipo dela; "
                      "a API de imagem pode não preservar o rosto de uma pessoa real.")
    msg = {"role": "assistant", "kind": "image", "id": e["id"], "url": e["url"], "score": best["score"], "approved": best["ok"],
           "veto": (best["rv"] or {}).get("veto", []), "review": best["rv"], "prompt": e["prompt"], "request": text, "resolved": text_eff,
           "intent": intent, "conv": conv["id"], "files": files, "falha_identidade": "identidade_divergente" in ((best["rv"] or {}).get("veto") or []), "avisos": avisos, "cycles": cycles, "skills": used, "packs": packs, "mode": mode, "improve": imp,
           "generations": len(cycles), "seconds": round(time.time() - t0, 1), "size": size,
           "inputs": [{"kind": x["kind"], "name": x["name"]} for x in inputs]}
    record(briefing=e["prompt"], image_id=e["id"], score=best["score"], approved=bool(best["ok"]),
           inputs=[{"kind": x["kind"], "name": x["name"]} for x in inputs], mode=mode, packs=packs)
    if imp["compare_raw"]:
        emit("Gerando a versão do GPT puro (o seu texto, sem a aplicação) para comparar…")
        tr = time.time()
        b64, ext = make_image(text_eff, size, quality, inputs, image_model, fidelity, avisos)
        rid = f"{mid}raw"
        (OUT / slug(cid) / f"{rid}.{ext}").write_bytes(base64.b64decode(b64))
        raw = {"id": rid, "url": f"/files/{slug(cid)}/out/{rid}.{ext}", "prompt": text_eff}
        emit(f"Versão do GPT puro pronta em {round(time.time() - tr)}s.", image_url=raw["url"])
        if do_rev:
            emit("O critic está revisando a versão pura (mesma régua)…")
            rv2, s2, ok2 = do_review(ctx_critic, text_eff, text_eff, b64, ext, size, inputs, b.get("critic_model") or text_model, "", packs)
            raw.update(score=s2, approved=ok2, veto=rv2.get("veto", []))
            emit(f"GPT puro: nota {s2}{' · vetos: ' + ', '.join(rv2.get('veto', [])) if rv2.get('veto') else ''}")
        msg["raw"] = raw
    return msg


POST = {"/api/client": api_client, "/api/client/save": api_client_save, "/api/client/new": api_client_new, "/api/asset": api_asset,
        "/api/asset/delete": api_asset_delete, "/api/asset/kind": api_asset_kind, "/api/chat": api_chat, "/api/job": api_job,
        "/api/conv": api_conv, "/api/conv/delete": api_conv_delete, "/api/conv/rename": api_conv_rename, "/api/clientlog": api_clientlog, "/api/conv/files": api_conv_files,
        "/api/asset/alias": api_asset_alias, "/api/setkey": api_setkey, "/api/websearch": api_websearch, "/api/webadd": api_webadd}


BRAND_EXT = {".css", ".png"}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", cache="no-store"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(data)

    def _brand(self, raw_path):
        """GET /brand/<arquivo>: estáticos da marca em chat/brand, só extensões da allowlist, sem sair da pasta."""
        base = (ROOT / "chat" / "brand").resolve()
        name = raw_path[len("/brand/"):]
        # nome simples + extensão da allowlist; resolve()/is_relative_to barra o que sobrar (ex.: link simbólico para fora da pasta)
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or pathlib.Path(name).suffix.lower() not in BRAND_EXT:
            return self._send(404, {"error": "não encontrado"})
        p = (base / name).resolve()
        if not p.is_relative_to(base) or not p.is_file():
            return self._send(404, {"error": "não encontrado"})
        ctype = "text/css" if p.suffix.lower() == ".css" else (mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        self._send(200, p.read_bytes(), ctype, cache="no-cache")

    def do_HEAD(self):
        self._head_only = True
        self.do_GET()

    def _local_only(self):
        """Só aceita o próprio navegador: Host e Origin precisam ser 127.0.0.1 ou localhost. Bloqueia páginas de outros sites
        que tentariam gastar a chave ou mexer na biblioteca (CSRF) e DNS rebinding."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ("127.0.0.1", "localhost"):
            return False
        org = self.headers.get("Origin")
        return not org or urllib.parse.urlparse(org).hostname in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._local_only():
            return self._send(403, {"error": "acesso negado: só o navegador local pode usar este chat"})
        path = urllib.parse.urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._send(200, (ROOT / "chat" / "index.html").read_bytes(), "text/html")
            if path.startswith("/brand/"):
                return self._brand(path)
            if path == "/api/state":
                return self._send(200, api_state({}))
            if path == "/api/models":
                return self._send(200, api_models({}))
            if path == "/api/convs":
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                return self._send(200, list_convs((q.get("client") or [""])[0]))
            m = re.fullmatch(r"/files/([a-z0-9_-]+)/(assets|out)/([A-Za-z0-9._-]+)", path)
            if m:
                base = (CLIENTS / m.group(1) / "assets") if m.group(2) == "assets" else (OUT / m.group(1))
                p = (base / m.group(3)).resolve()
                if base.resolve() in p.parents and p.is_file():
                    return self._send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream")
            self._send(404, {"error": "não encontrado"})
        except ui.ApiError as e:
            self._send(e.status, {"error": str(e)})

    def do_POST(self):
        if not self._local_only():
            return self._send(403, {"error": "acesso negado: só o navegador local pode usar este chat"})
        fn = POST.get(self.path)
        if not fn:
            return self._send(404, {"error": "não encontrado"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self._send(200, fn(body))
        except ui.ApiError as e:
            self._send(e.status, {"error": str(e)})
        except KeyError as e:
            self._send(400, {"error": f"campo ausente: {e}"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def main():
    global MOCK
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--mock", action="store_true", help="não chama a API; dados falsos para ver a interface")
    a = ap.parse_args()
    MOCK = a.mock
    rc.self_test()
    cdir("71")
    if not MOCK and load_key_from_keychain():
        print("Chave da OpenAI lida do Keychain do Mac.")
    print(f"Chat em http://127.0.0.1:{a.port}  ({'MOCK' if MOCK else 'OPENAI_API_KEY ' + ('definida' if os.getenv('OPENAI_API_KEY') else 'NÃO definida')})")
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as e:
        sys.exit(f"Não consegui abrir a porta {a.port} ({e.strerror}). Já tem um chat rodando? Feche-o ou use --port {a.port + 1}.")
    srv.serve_forever()


if __name__ == "__main__":
    main()
