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
import argparse, base64, getpass, ipaddress, json, mimetypes, os, pathlib, posixpath, random, re, shutil, socket, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import checks, client_provider, critic, regionedit, research, skills_router  # noqa: E402
import store as store_mod  # noqa: E402  (Store: FileStore/MemoryStore/BlobStore)
import run_comparison as rc  # noqa: E402
import ui_server as ui  # noqa: E402  (openai_post, ApiError, env_models)

# CHAT_DATA_DIR separa os dados do uso real dos dos testes automáticos (nunca apague a pasta de uso)
DATA = pathlib.Path(os.getenv("CHAT_DATA_DIR") or ROOT)
# Tudo o que o servidor guarda passa pelo Store (test/store.py). Chaves: clients/<id>/client.json, clients/<id>/assets.json,
# clients/<id>/assets/<arquivo>, chat_out/<id>/<imagem>, conversations/<id>/<conv>.json, logs/events.jsonl, jobs/<id>.json.
# Backend: STORE=file|memory|blob; sem STORE, blob se BLOB_READ_WRITE_TOKEN existir, senão disco em DATA (comportamento de sempre).
STORE = None
_SEEDED = set()
MOCK = False
# Vercel: a função serverless some quando responde, então o pipeline roda DENTRO da requisição e o estado vai para o Store.
JOBS_INLINE = os.getenv("JOBS_INLINE") == "1" or bool(os.getenv("VERCEL"))


def vercel_mode():
    """Lido a cada requisição (e não na importação) para que os testes possam ligar e desligar."""
    return bool(os.getenv("VERCEL"))


def get_store():
    global STORE
    if STORE is None:
        try:
            STORE = store_mod.make_store(DATA)
        except ModuleNotFoundError as e:
            raise ui.ApiError(500, f"Backend de armazenamento indisponível ({e}). Na Vercel, instale as dependências de requirements.txt.")
        except ValueError as e:
            raise ui.ApiError(500, str(e))
        if vercel_mode() and STORE.name == "file":
            STORE = None
            raise ui.ApiError(500, "Na Vercel o disco não guarda nada entre chamadas: defina BLOB_READ_WRITE_TOKEN (Vercel Blob) no projeto.")
    return STORE


def set_store(s):
    """Troca o backend (testes). Zera o cache de semeadura do cliente 71."""
    global STORE
    STORE = s
    _SEEDED.clear()
KEYCHAIN_SERVICE = "geratedimage-openai"
COMMONS_API = os.getenv("COMMONS_API", "https://commons.wikimedia.org/w/api.php")
WEB_UA = "geratedimage-prototype/0.1 (uso local de teste)"
WEB_ALLOW_LOCAL = os.getenv("WEB_ALLOW_LOCAL") == "1"  # só para testes automáticos (servidor falso em 127.0.0.1)
GENERIC_ALIAS = {"logo", "foto", "imagem", "image", "img", "screenshot", "captura", "tela", "produto", "pessoa", "referencia", "peca",
                 "copy", "novo", "final", "versao", "whatsapp", "download", "photo", "picture", "untitled"}
CONV_LOCK = threading.Lock()  # duas tarefas da mesma conversa não podem se sobrescrever
GERAL = "_geral"  # escopo neutro: conversa que ainda não tem cliente (o cliente é detectado pelo texto)
PROJECT_LOCK = threading.Lock()  # ordem das travas: PROJECT_LOCK antes de CONV_LOCK
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
        line = json.dumps({"t": time.strftime("%H:%M:%S"), "kind": kind, **fields}, ensure_ascii=False)
        get_store().append_line("logs/events.jsonl", line)
    except Exception:  # noqa: BLE001
        pass


def slug(s):
    s = re.sub(r"[^a-z0-9_-]", "", str(s).lower())
    if not s:
        raise ui.ApiError(400, "id de cliente inválido")
    return s


def cdir(cid):
    """Prefixo do cliente no Store ('clients/<id>'); semeia o cliente de exemplo 71 na primeira vez."""
    d = f"clients/{slug(cid)}"
    if cid == "71" and (id(get_store()), "71") not in _SEEDED:
        if not get_store().exists(f"{d}/client.json"):
            get_store().write_bytes(f"{d}/client.json", (ROOT / "client_71.json").read_bytes())
        _SEEDED.add((id(get_store()), "71"))
    return d


def read_json(key):
    return json.loads(get_store().read_text(key))


def write_json(key, obj):
    get_store().write_text(key, json.dumps(obj, ensure_ascii=False, indent=2), "application/json")


def load_client(cid):
    k = cdir(cid) + "/client.json"
    if not get_store().exists(k):
        raise ui.ApiError(404, f"cliente {cid} não existe")
    return read_json(k)


def load_assets(cid):
    k = cdir(cid) + "/assets.json"
    assets = read_json(k) if get_store().exists(k) else []
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
    for k in get_store().list(f"chat_out/{slug(cid)}/"):
        if posixpath.basename(k).startswith(mid + "."):
            return k
    raise ui.ApiError(404, "imagem a editar não encontrada")


def collect_inputs(cid, edit_of, asset_ids, scope=None):
    inputs = []
    if edit_of:
        k = find_out(scope or cid, edit_of)
        mime = "image/svg+xml" if k.endswith(".svg") else "image/png"
        inputs.append(dict(kind="alvo", name=posixpath.basename(k), mime=mime, bytes=get_store().read_bytes(k),
                           role_text="ALVO DE EDIÇÃO: peça gerada anteriormente; mude só o que o pedido atual pede e mantenha o resto idêntico"))
    by_id = {a["id"]: a for a in load_assets(cid)}
    missing = [aid for aid in asset_ids if aid not in by_id]
    if missing:
        raise ui.ApiError(409, f"Uma imagem fixada não existe mais na biblioteca ({', '.join(missing)}). Remova-a da conversa (×) e envie de novo: "
                               "sem ela a imagem sairia sem a referência.")
    for aid in asset_ids:
        a = by_id[aid]
        k = f"{cdir(cid)}/assets/{a['file']}"
        if not get_store().exists(k):
            raise ui.ApiError(409, f"O arquivo de '{a['name']}' sumiu da biblioteca. Envie a imagem de novo.")
        inputs.append(dict(id=a["id"], kind=a["kind"], name=a["name"], mime=a["mime"], bytes=get_store().read_bytes(k),
                           role_text=f"{KIND_ROLE.get(a['kind'], 'imagem do cliente')} (arquivo: {a['name']})"))
    return inputs


# ---------- handlers ----------
def api_state(_):
    cdir("71")
    clients = []
    ids = sorted({k.split("/")[1] for k in get_store().list("clients/") if k.count("/") == 2 and k.endswith("/client.json")})
    for i in ids:
        clients.append({"id": i, "name": read_json(f"clients/{i}/client.json").get("name", i)})
    return {"mock": MOCK, "has_key": bool(os.getenv("OPENAI_API_KEY")), "has_claude": shutil.which("claude") is not None,
            **ui.env_models(), "pass_score": critic.PASS_SCORE, "max_cycles": critic.MAX_CYCLES, "clients": clients,
            "client_sources": [p.name for p in client_providers()], "kinds": list(KIND_ROLE), "sizes": sorted(SIZES), "web_search": True}


def api_client(b):
    cid = b["id"]
    if get_store().exists(cdir(cid) + "/client.json"):
        return {"id": slug(cid), "client": load_client(cid), "assets": with_urls(cid, load_assets(cid))}
    info = _lookup_client(_strict_id(cid, "cliente"))  # id que vem do banco: contexto pela lista permitida + biblioteca local do cliente
    ctx = {k: v for k, v in _provider(info["source"]).load(info["id"]).items() if not k.startswith("_")}
    return {"id": slug(cid), "client": ctx, "assets": with_urls(cid, load_assets(cid)), "source": info["source"]}


def api_client_new(b):
    name = str(b.get("name", "")).strip()[:80]
    if len(name) < 2:
        raise ui.ApiError(400, "dê um nome ao cliente")
    base = slug(re.sub(r"\s+", "-", skills_router.norm(name))) if re.search(r"[a-z0-9]", skills_router.norm(name)) else "cliente"
    cid, n = base, 2
    while get_store().exists(f"clients/{cid}/client.json"):
        cid, n = f"{base}-{n}", n + 1
    d = cdir(cid)
    ctx = {"id": cid, "name": name, "sector": str(b.get("sector", ""))[:120], "audience": "", "tone": "", "palette": [], "typography": "",
           "image_style": "", "approved_references": []}
    write_json(f"{d}/client.json", ctx)
    log_event("cliente_novo", id=cid)
    return {"id": cid, "client": ctx}


def api_client_save(b):
    d = cdir(b["id"])
    write_json(f"{d}/client.json", b["client"])
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
    get_store().write_bytes(f"{cdir(cid)}/assets/{a['file']}", data, mime)
    assets = load_assets(cid) + [a]
    write_json(f"{cdir(cid)}/assets.json", assets)
    return with_urls(cid, [a])[0]


def api_asset_alias(b):
    cid = b["client"]
    assets = load_assets(cid)
    hit = [a for a in assets if a["id"] == b["id"]]
    if not hit:
        raise ui.ApiError(404, "imagem não encontrada na biblioteca")
    hit[0]["alias"] = re.sub(r"[\x00-\x1f\x7f]", " ", str(b.get("alias", "")))[:60].strip()
    write_json(f"{cdir(cid)}/assets.json", assets)
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
        get_store().delete(f"{cdir(cid)}/assets/{a['file']}")
    write_json(f"{cdir(cid)}/assets.json", [a for a in assets if a["id"] != b["id"]])
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
    if os.getenv("OPENAI_API_KEY") or sys.platform != "darwin" or vercel_mode():
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
    if vercel_mode():
        raise ui.ApiError(403, "Na Vercel a chave não pode ser definida pela página: defina OPENAI_API_KEY nas variáveis de ambiente do projeto (Settings > Environment Variables) e faça um novo deploy.")
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
# Modo local (padrão): dicionário em memória + thread em segundo plano.
# Modo inline (JOBS_INLINE=1, ou VERCEL definido): o pipeline roda DENTRO da requisição de /api/chat (a função fica viva até
# terminar) e o estado da tarefa vai para o Store (jobs/<id>.json); /api/job lê do Store, então qualquer instância responde.
JOBS = {}
JOB_ID = re.compile(r"[a-f0-9]{10}")


def start_job(fn, meta=None):
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "status": "running", "steps": [], "message": None, "error": None, "t0": time.time()}
    if not JOBS_INLINE:
        for old in sorted(JOBS.values(), key=lambda j: j["t0"])[:-40]:
            JOBS.pop(old["id"], None)
        JOBS[jid] = job
    log_event("start", job=jid, **(meta or {}))

    def save():
        if JOBS_INLINE:
            try:
                write_json(f"jobs/{jid}.json", job)
            except Exception as e:  # noqa: BLE001  (não derruba o pipeline; o log registra)
                log_event("erro", job=jid, erro=f"não consegui gravar o estado da tarefa: {type(e).__name__}")

    def emit(text, **extra):
        step = {"t": round(time.time() - job["t0"], 1), "text": text, **extra}
        job["steps"].append(step)
        log_event("step", job=jid, t=step["t"], text=text, **{k: v for k, v in extra.items() if k in ("image_url", "prompt")})
        save()

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

    if JOBS_INLINE:
        save()
        try:
            runner()
        finally:
            job["t1"] = time.time()  # congela o "elapsed" depois de terminar (quem consulta de outra instância vê o tempo real da tarefa)
            save()
        return jid
    threading.Thread(target=runner, daemon=True).start()
    return jid


def api_job(b):
    jid = b.get("id")
    if JOBS_INLINE:
        if not isinstance(jid, str) or not JOB_ID.fullmatch(jid) or not get_store().exists(f"jobs/{jid}.json"):
            raise ui.ApiError(404, "tarefa não encontrada")
        job = read_json(f"jobs/{jid}.json")
    else:
        job = JOBS.get(jid)
    if not job:
        raise ui.ApiError(404, "tarefa não encontrada (o servidor foi reiniciado?)")
    since = int(b.get("since") or 0)
    return {"status": job["status"], "steps": job["steps"][since:], "next": len(job["steps"]),
            "message": job["message"], "error": job["error"], "elapsed": round(job.get("t1", time.time()) - job["t0"], 1)}


def client_providers():
    """Fontes de cliente. O banco só entra se SUPABASE_URL e SUPABASE_READ_KEY existirem (somente leitura, só no servidor)."""
    ids = lambda: sorted({k.split("/")[1] for k in get_store().list("clients/") if k.count("/") == 2 and k.endswith("/client.json")} - {GERAL})
    def read(i):
        k = f"clients/{slug(i)}/client.json"
        if not get_store().exists(k):
            raise FileNotFoundError(k)
        return read_json(k)
    ps = [client_provider.LocalClientProvider(ids, read)]
    db = client_provider.SupabaseClientProvider.from_env()
    return ps + ([db] if db else [])


def _conv_client_id(conv, scope):
    """Cliente da conversa: o campo 'client' (None = sem cliente); conversa antiga sem o campo usa a pasta onde está."""
    if "client" in conv:
        return conv["client"] if isinstance(conv["client"], str) and conv["client"] else None
    return None if scope == GERAL else scope


def _provider(source):
    return next((p for p in client_providers() if p.name == source), None)


def client_ctx(conv, cl):
    """Contexto do cliente da conversa, SEMPRE pela lista permitida (as chaves '_x' são metadados internos, tiradas antes do prompt).
    Banco fora do ar é erro explícito, nunca 'sem cliente'. Cliente do banco: o banco prevalece, a edição local só acrescenta o que falta."""
    src = conv.get("client_source") or "local"
    pv = _provider(src)
    if pv is None:
        raise ui.ApiError(503, f"A fonte de clientes '{src}' não está habilitada neste servidor (CHAT_DB_ENABLED, SUPABASE_URL e SUPABASE_READ_KEY).")
    try:
        ctx = pv.load(cl)
    except client_provider.NotFound:
        raise ui.ApiError(404, f"cliente {cl} não existe na fonte '{src}'")
    except client_provider.ProviderError as e:
        raise ui.ApiError(502, str(e))
    if src == "banco" and get_store().exists(f"clients/{slug(cl)}/client.json"):
        meta = {k: v for k, v in ctx.items() if k.startswith("_")}
        ctx = {**client_provider.merge_local({k: v for k, v in ctx.items() if not k.startswith("_")}, read_json(f"clients/{slug(cl)}/client.json")), **meta}
    return ctx


def _lookup_client(cid):
    """Acha o cliente nas fontes (local, depois banco). Falha de fonte é erro explícito (502), nunca 'não existe'."""
    errs = []
    for pv in client_providers():
        try:
            ctx = pv.load(cid)
            return {"id": cid, "name": ctx.get("name") or ctx.get("_display_name") or cid, "source": pv.name, "compra_id": ctx.get("_compra_id") or None, "name_origin": ctx.get("_name_origin"),
                    "pessoa_fisica": ctx.get("_pessoa_fisica")}
        except client_provider.NotFound:
            continue
        except client_provider.ProviderError as e:
            errs.append(str(e))
    if errs:
        raise ui.ApiError(502, "; ".join(errs))
    raise ui.ApiError(404, "cliente não encontrado")


def sync_banco_logos(cl):
    """Traz para a biblioteca local do cliente os logos ativos do banco (bytes pela Edge Function; nunca URL). -> lista de avisos."""
    pv, warns = _provider("banco"), []
    if pv is None:
        return warns
    try:
        have = {a.get("db_item_id") for a in load_assets(cl)}
        for row in pv.logos(cl):
            if row.get("item_id") in have:
                continue
            data, mime = pv.fetch_asset(row["storage_path"])
            store_asset(cl, "logo", "logo." + client_provider.SupabaseClientProvider.ASSET_MIME[mime], mime, data, alias="logo", extra={"db_item_id": row.get("item_id")})
    except (client_provider.ProviderError, client_provider.NotFound) as e:
        warns.append(f"Logo do banco não carregado: {e}")
    return warns


def migrate_assets(src, dst, ids):
    """Copia (não move) para a biblioteca do cliente as imagens que a conversa anexou antes de o cliente ser conhecido."""
    if src == dst or not ids:
        return
    have = {a["id"] for a in load_assets(dst)}
    moved = [a for a in load_assets(src) if a["id"] in ids and a["id"] not in have]
    for a in moved:
        k = f"{cdir(src)}/assets/{a['file']}"
        if get_store().exists(k):
            get_store().write_bytes(f"{cdir(dst)}/assets/{a['file']}", get_store().read_bytes(k), a.get("mime"))
    ok = [a for a in moved if get_store().exists(f"{cdir(dst)}/assets/{a['file']}")]
    if ok:
        write_json(f"{cdir(dst)}/assets.json", load_assets(dst) + ok)


def _apply_client(scope, conv_id, info, locked=False):
    """Grava o cliente na conversa (campos aditivos; a conversa continua na mesma pasta)."""
    with CONV_LOCK:
        c = load_conv(scope, conv_id)
        c.update(client=info["id"] if info else None, client_name=info["name"] if info else None, client_source=info["source"] if info else None)
        if info and info.get("compra_id"):
            c["compra_id"] = info["compra_id"]
        else:
            c.pop("compra_id", None)
        if locked:
            c["client_locked"] = True
        save_conv(c)


def api_chat(b):
    """Valida na hora (falha rápido) e roda o pipeline numa tarefa em segundo plano (ou inline, ver JOBS_INLINE)."""
    text = (b.get("text") or "").strip()
    if not text:
        raise ui.ApiError(400, "mensagem vazia")
    if b.get("auto_client"):  # a tela diz que a conversa não tem cliente: o 'client' legado que vem junto é ignorado (nunca vale por engano)
        b = {k: v for k, v in b.items() if k != "client"}
    scope = _scope_of(b, default=GERAL)
    conv = load_conv(scope, b.get("conv") or uuid.uuid4().hex[:10])
    b["conv"] = conv["id"]
    cl, detect, ctx, cmeta = _conv_client_id(conv, scope), None, {}, {}
    explicit = b.get("client")
    if cl is None and not conv.get("client_locked") and isinstance(explicit, str) and explicit and explicit != GERAL:
        cl = _strict_id(explicit, "cliente")  # a tela escolheu o cliente (fluxo antigo, ou escolha manual antes do 1º turno)
        info = _lookup_client(cl)
        conv["client_source"] = info["source"]
        detect = {"status": "match", "client": info, "errors": [], "explicit": True}
    elif cl is None and not conv.get("client_locked"):
        detect = client_provider.resolve(text, client_providers())
        if detect["status"] == "match":
            cl = detect["client"]["id"]
            conv["client_source"] = detect["client"]["source"]
    if cl is not None:
        ctx = client_ctx(conv, cl)
        cmeta = {k[1:]: ctx.pop(k) for k in [k for k in ctx if k.startswith("_")]}
        if detect and detect["status"] == "match":
            detect["client"]["compra_id"] = cmeta.get("compra_id") or None
            detect["client"]["name_origin"] = cmeta.get("name_origin")
            detect["client"]["pessoa_fisica"] = cmeta.get("pessoa_fisica")
        if detect and detect["status"] == "match" and scope != cl:
            migrate_assets(scope, cl, set(conv.get("files", [])) | set(b.get("asset_ids") or []))
    lib = cl or scope  # biblioteca de imagens: a do cliente, se já o conhecemos; imagens GERADAS ficam sempre na pasta da conversa
    files, auto, stale = resolve_files(lib, conv, b, text)
    inputs = collect_inputs(lib, b.get("edit_of"), files, scope)
    if not MOCK and not os.getenv("OPENAI_API_KEY") and not shutil.which("claude"):
        raise ui.ApiError(400, "Sem OPENAI_API_KEY e sem o CLI claude: nada a executar.")
    provider_now = "mock" if MOCK else ("openai" if os.getenv("OPENAI_API_KEY") else "claude-cli (SEM chave: nenhuma imagem é gerada)")
    meta = {"provedor": provider_now, "client": cl, "scope": scope, "conv": b.get("conv"), "texto": text, "modo": b.get("mode") or "livre", "tamanho": b.get("size"),
            "qualidade": b.get("quality"), "anexos": [{"tipo": x["kind"], "nome": x["name"]} for x in inputs], "auto_anexados": [a["name"] for a in auto], "edit_of": b.get("edit_of"),
            "melhorias": {"designer": (b.get("improve") or {}).get("designer", True), "skills": (b.get("improve") or {}).get("skills", True),
                          "critic": b.get("review", True), "comparar": (b.get("improve") or {}).get("compare_raw", False)},
            "modelos": {"imagem": b.get("image_model"), "texto": b.get("text_model")}}
    key = (scope, conv["id"])
    with CONV_LOCK:
        CONV_BUSY[key] = CONV_BUSY.get(key, 0) + 1

    def task(emit):
        try:
            return run_chat(b, emit, lib, text, ctx, inputs, files, auto, stale, scope=scope, detect=detect, client_meta=cmeta)
        finally:
            with CONV_LOCK:
                CONV_BUSY[key] -= 1
                if not CONV_BUSY[key]:
                    del CONV_BUSY[key]
    jid = start_job(task, meta)
    if JOBS_INLINE:  # já terminou: devolve o resultado junto; a interface ainda consulta /api/job e recebe o mesmo estado
        j = api_job({"id": jid})
        return {"job": jid, "status": j["status"], "message": j["message"], "error": j["error"]}
    return {"job": jid}


# ---------- memória da conversa (em disco; sobrevive a reinício e a atualizar a página) ----------
MEMORY_PROMPT_PATH = ROOT.parent / "prompts" / "memory.system.md"
IDENTITY_KINDS = ("pessoa", "logo", "produto")
EDIT_WORDS = re.compile(r"\b(mude|muda|troque|troca|tire|tira|remova|remove|adicione|coloque|agora|mais|menos|deixe|deixa|altere|ajuste)\b", re.I)


def conv_path(cid, conv_id):
    """Chave da conversa no Store."""
    return f"conversations/{slug(cid)}/{slug(conv_id)}.json"


def load_conv(cid, conv_id):
    p = conv_path(cid, conv_id)
    if get_store().exists(p):
        try:
            c = read_json(p)
            c.setdefault("files", [])
            c.setdefault("scope", slug(cid))
            return c
        except json.JSONDecodeError:  # arquivo corrompido: guarda a cópia e recomeça, em vez de travar a conversa
            get_store().rename(p, p + f".corrompido-{int(time.time())}")
    return {"id": slug(conv_id), "client": None if slug(cid) == GERAL else slug(cid), "scope": slug(cid), "created": time.strftime("%Y-%m-%d %H:%M:%S"), "turns": [], "carry": [], "files": []}


def save_conv(conv):
    write_json(conv_path(conv.get("scope") or conv["client"], conv["id"]), conv)  # o FileStore troca de forma atômica (arquivo temporário + replace)


def last_image(cid, conv):
    for t in reversed(conv["turns"]):
        if t.get("image_id"):
            try:
                p = find_out(cid, t["image_id"])
                if p.endswith(".svg") and not MOCK:  # imagem falsa de um teste mock: a API real não aceita SVG
                    return None, None
                return p, t["image_id"]
            except ui.ApiError:
                return None, None
    return None, None


def memory_text(conv, files_desc=""):
    """O que o designer e o resolvedor 'lembram': a transcrição inteira, os arquivos da conversa e os detalhes recentes."""
    turns = conv["turns"]
    if not turns and not conv["carry"] and not files_desc and not conv.get("brand_brief"):
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
    if conv.get("brand_brief"):
        bb = conv["brand_brief"]
        L.append("Pesquisa da marca já feita nesta conversa (não pesquise de novo; fontes: " + ", ".join(s["url"] for s in bb.get("sources", [])[:4]) + "): "
                 + json.dumps(bb.get("brief", {}), ensure_ascii=False)[:1500])
    if conv["carry"]:
        L.append("Instruções duradouras do usuário: " + "; ".join(conv["carry"]))
    last = turns[-1] if turns else None
    if last and last.get("question"):
        L.append(f'PERGUNTA PENDENTE: o último turno terminou numa pergunta do designer; a nova mensagem provavelmente a responde '
                 f'(pedido original: {last["resolved"][:1500]}; intenção original: {last["intent"]})')
    return "\n".join(L)


def infer_size(text):
    """Formato pelo pedido quando está em 'auto' e não há alvo: banner/capa = horizontal; story/reels = vertical."""
    t = skills_router.norm(text)
    if re.search(r"\b(story|stories|reels|vertical|9:16|tiktok)\b", t):
        return "1024x1536"
    if re.search(r"\b(banner|banners|capa|youtube|thumbnail|horizontal|paisagem|16:9|cabecalho|outdoor|landscape)\b", t):
        return "1536x1024"
    return "1024x1024"


def fetch_text(url, limit=2 * 1024 * 1024):
    """Baixa uma página HTML com as mesmas travas dos downloads de imagem."""
    _check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": WEB_UA, "Accept": "text/html"})
    try:
        with urllib.request.build_opener(_SafeRedirect).open(req, timeout=20) as r:
            return r.read(limit).decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise ui.ApiError(502, f"Não consegui abrir a página: {getattr(e, 'reason', e)}")


def resolve_turn(conv, text, avail, model, provider, has_files=False):
    """Entende a mensagem no contexto (como o ChatGPT): devolve intenção e um pedido autossuficiente. Nunca derruba o fluxo."""
    triv = {"intent": "new", "request": text, "use_last_image": False, "carry": list(conv["carry"])}
    if provider != "openai":
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
                "research": (str(out["research"]).strip()[:160] if out.get("research") else None),
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


def _scope_of(b, default=None):
    """Pasta da conversa: 'scope' (qualquer escopo, inclusive _geral) ou 'client' (conversas antigas: pasta = cliente)."""
    v = b.get("scope") if b.get("scope") is not None else b.get("client")
    if v is None:
        if default is not None:
            return default
        raise KeyError("scope")
    return _strict_id(v, "escopo")


def _scan_convs(scope=None):
    """Percorre as conversas de um escopo ou de todos. Arquivo ilegível é contado em 'skipped' (e registrado), nunca engolido."""
    found, skipped = [], 0
    pre = f"conversations/{scope}/" if scope else "conversations/"
    for k in get_store().list(pre):
        parts = k[len("conversations/"):].split("/")
        if len(parts) != 2 or not parts[1].endswith(".json"):  # só os JSON diretos de cada pasta
            continue
        try:
            c = read_json(k)
            if not isinstance(c.get("turns"), list):
                raise ValueError("turns")
            found.append((parts[0], parts[1][:-len(".json")], c, get_store().mtime(k)))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            skipped += 1
            log_event("conv_list_skipped", scope=parts[0], file=parts[1])
    return found, skipped


def _client_name(cl, cache):
    if cl not in cache:
        try:
            cache[cl] = str(read_json(f"clients/{slug(cl)}/client.json").get("name") or cl)
        except (OSError, ValueError, ui.ApiError):
            cache[cl] = cl  # sem nome à mão: mostra o id, não esconde o cliente
    return cache[cl]


def _conv_item(scope, cid, c, mtime, project_ids, names):
    cl = _conv_client_id(c, scope)
    name = (c.get("client_name") or _client_name(cl, names)) if cl else None
    return {"id": cid, "title": _conv_title(c), "updated": int(mtime), "count": len(c["turns"]), "scope": scope, "client": cl, "client_name": name,
            "project": c.get("project") if c.get("project") in project_ids else None, "_m": mtime}


def list_convs(scope=None):
    """Histórico do mais recente ao mais antigo. Sem escopo: todas as conversas de todas as pastas."""
    scope = _strict_id(scope, "escopo") if scope is not None else None
    found, skipped = _scan_convs(scope)
    pids, names = {p["id"] for p in read_projects()}, {}
    convs = [_conv_item(sc, cid, c, m, pids, names) for sc, cid, c, m in found if c["turns"]]  # conversa sem mensagens não entra
    convs.sort(key=lambda x: x.pop("_m"), reverse=True)
    return {"convs": convs, "skipped": skipped}


def _existing_conv_path(b):
    p = conv_path(_scope_of(b), _strict_id(b["conv"], "conversa"))
    if not get_store().exists(p):
        raise ui.ApiError(404, "conversa não encontrada")
    return p


def _edit_conv(b, mutate):
    """Altera campos de uma conversa que já existe, no caminho validado, sem mudar a ordem do histórico (mtime preservado)."""
    with CONV_LOCK:
        p = _existing_conv_path(b)
        try:
            c = read_json(p)
        except ValueError:
            c = None
        if not isinstance(c, dict):
            raise ui.ApiError(422, "conversa ilegível; não dá para alterar")
        t0 = get_store().mtime(p)
        mutate(c)
        get_store().write_bytes(p, json.dumps(c, ensure_ascii=False, indent=2).encode("utf-8"), "application/json")
        get_store().set_mtime(p, t0)
        return c


def api_conv_delete(b):
    with CONV_LOCK:
        p = _existing_conv_path(b)
        if CONV_BUSY.get((_scope_of(b), slug(b["conv"]))):
            raise ui.ApiError(409, "a conversa ainda está gerando uma resposta; espere terminar para excluir")
        get_store().delete(p)  # só o JSON da conversa; imagens de saída e biblioteca ficam
    return {"ok": True}


def api_conv_rename(b):
    title = b["title"]
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
        raise ui.ApiError(400, "título deve ter de 1 a 80 caracteres")
    _edit_conv(b, lambda c: c.update(title=title.strip()))
    return {"ok": True}


def conv_client_info(c, scope):
    cl = _conv_client_id(c, scope)
    if not cl:
        return None
    return {"id": cl, "name": c.get("client_name") or _client_name(cl, {}), "source": c.get("client_source") or "local", "compra_id": c.get("compra_id")}


def api_conv(b):
    scope = _scope_of(b)
    c = load_conv(scope, b.get("conv") or "x")
    return dict(c, client=conv_client_info(c, scope), scope=scope, project=c.get("project"))


def api_conv_client(b):
    """O usuário troca ou remove o cliente da conversa; daí em diante a detecção automática não mexe mais nela.
    Conversa que ainda não existe no servidor (sem turnos): 200 com "pending": true e NADA é gravado; o client_id vale
    quando o primeiro /api/chat da conversa mandar `client` no body (com o mesmo `scope`)."""
    scope, cid = _scope_of(b), _strict_id(b["conv"], "conversa")
    if b.get("compra_id") is not None:
        raise ui.ApiError(400, "trocar a compra não é suportado pelo contrato do banco (só a compra vigente)")
    new = b.get("client_id")
    exists = get_store().exists(conv_path(scope, cid))
    if new is None:
        if exists:
            _edit_conv(b, lambda c: (c.update(client=None, client_name=None, client_source=None, client_locked=True), c.pop("compra_id", None)))
        return {"ok": True, "client": None, **({} if exists else {"pending": True})}
    info = _lookup_client(_strict_id(new, "cliente"))
    out = {"id": info["id"], "name": info["name"], "source": info["source"], "compra_id": info["compra_id"]}
    if not exists:
        return {"ok": True, "client": out, "pending": True}
    c = _edit_conv(b, lambda c: (c.update(client=info["id"], client_name=info["name"], client_source=info["source"], client_locked=True),
                                 c.update(compra_id=info["compra_id"]) if info["compra_id"] else c.pop("compra_id", None)))
    migrate_assets(scope, info["id"], set(c.get("files", [])))
    resp = {"ok": True, "client": out}
    if info["source"] == "banco":
        warns = sync_banco_logos(info["id"])
        if warns:
            resp["warnings"] = warns
    return resp


def api_clients(q):
    """GET /api/clients?q=: clientes de todas as fontes (o chip e o seletor manual). Fonte fora do ar vai em 'errors'."""
    out, errors = [], []
    for pv in client_providers():
        try:
            out += [{"id": c["id"], "name": c["name"], "source": pv.name} for c in pv.find(q or "", 50)]
        except client_provider.ProviderError as e:
            errors.append({"source": pv.name, "error": str(e)})
    out.sort(key=lambda c: client_provider.norm(c["name"]))
    return {"clients": out[:50], **({"errors": errors} if errors else {})}


# ---------- projetos: pastas que agrupam conversas (DATA/projects.json; a conversa guarda só o campo 'project') ----------
def read_projects():
    k = "projects.json"
    if not get_store().exists(k):
        return []
    try:
        ps = read_json(k)["projects"]
        assert isinstance(ps, list) and all(isinstance(p, dict) and isinstance(p.get("id"), str) and isinstance(p.get("name"), str) for p in ps)
    except (ValueError, KeyError, TypeError, AssertionError):
        raise ui.ApiError(500, "projects.json ilegível: não vou tratar como 'nenhum projeto'. Corrija ou restaure o arquivo.")
    return ps


def _project_name(v, taken):
    if not isinstance(v, str) or not 1 <= len(v.strip()) <= 60:
        raise ui.ApiError(400, "nome do projeto deve ter de 1 a 60 caracteres")
    base, name, n = v.strip(), v.strip(), 2
    low = {t.lower() for t in taken}
    while name.lower() in low:
        name, n = f"{base} ({n})", n + 1
    return name


def api_projects(_):
    projects = read_projects()
    found, _skipped = _scan_convs()
    out = []
    for p in projects:
        mine = [(c, m) for _, _, c, m in found if c.get("project") == p["id"] and c["turns"]]
        out.append({"id": p["id"], "name": p["name"], "updated": int(max([p.get("updated", 0)] + [m for _, m in mine])), "count": len(mine)})
    out.sort(key=lambda x: x["updated"], reverse=True)
    return {"projects": out}


def api_project_create(b):
    with PROJECT_LOCK:
        ps = read_projects()
        p = {"id": "p" + uuid.uuid4().hex[:8], "name": _project_name(b["name"], [x["name"] for x in ps]), "updated": int(time.time())}
        write_json("projects.json", {"projects": ps + [p]})
    return {"id": p["id"], "name": p["name"]}


def _project_index(ps, pid):
    pid = _strict_id(pid, "projeto")
    i = next((i for i, p in enumerate(ps) if p["id"] == pid), None)
    if i is None:
        raise ui.ApiError(404, "projeto não encontrado")
    return pid, i


def api_project_rename(b):
    with PROJECT_LOCK:
        ps = read_projects()
        pid, i = _project_index(ps, b["id"])
        ps[i] = dict(ps[i], name=_project_name(b["name"], [p["name"] for j, p in enumerate(ps) if j != i]), updated=int(time.time()))
        write_json("projects.json", {"projects": ps})
    return {"id": pid, "name": ps[i]["name"]}


def api_project_delete(b):
    """Apaga só a pasta: as conversas dela voltam para 'sem projeto'. Nunca apaga conversa."""
    with PROJECT_LOCK:
        ps = read_projects()
        pid, i = _project_index(ps, b["id"])
        released = 0
        with CONV_LOCK:
            for sc, cid, c, _m in _scan_convs()[0]:
                if c.get("project") == pid:
                    c.pop("project")
                    k = conv_path(sc, cid)
                    t0 = get_store().mtime(k)
                    get_store().write_bytes(k, json.dumps(c, ensure_ascii=False, indent=2).encode("utf-8"), "application/json")
                    get_store().set_mtime(k, t0)
                    released += 1
        write_json("projects.json", {"projects": ps[:i] + ps[i + 1:]})
    return {"ok": True, "released": released}


def api_conv_move(b):
    pid = b.get("project")
    if pid is not None:
        pid = _strict_id(pid, "projeto")
        if not any(p["id"] == pid for p in read_projects()):
            raise ui.ApiError(404, "projeto não encontrado")
    _edit_conv(b, lambda c: c.update(project=pid) if pid else c.pop("project", None))
    return {"ok": True}


def api_asset_kind(b):
    cid = b["client"]
    if b.get("kind") not in KIND_ROLE:
        raise ui.ApiError(400, f"tipo inválido; use um de {list(KIND_ROLE)}")
    assets = load_assets(cid)
    hit = [a for a in assets if a["id"] == b["id"]]
    if not hit:
        raise ui.ApiError(404, "imagem não encontrada na biblioteca")
    hit[0]["kind"] = b["kind"]
    write_json(f"{cdir(cid)}/assets.json", assets)
    return {"ok": True}


def run_chat(b, emit, cid, text, ctx, inputs, files=None, auto=None, stale=None, scope=None, detect=None, client_meta=None):
    """cid = biblioteca de imagens (cliente, ou a pasta da conversa se ainda não há cliente); scope = pasta da conversa e das imagens geradas."""
    scope = scope or cid
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

    # --- cliente automático: o que o texto citou (ou o que a tela escolheu) vira o cliente da conversa ---
    if detect:
        for e in detect.get("errors", []):
            emit(f"Fonte de clientes '{e['source']}' fora do ar: {e['error']}. Segui com as outras fontes; o cliente pode não ter sido reconhecido.")
        if detect["status"] == "match":
            info = detect["client"]
            if not detect.get("explicit"):
                emit(f"Cliente identificado: {info['name']} (fonte: {info['source']})")
            _apply_client(scope, b["conv"], info)
            if info["source"] == "banco":
                if info.get("pessoa_fisica") is True:
                    avisos.append("Este cliente é pessoa física: o nome dele não foi usado como marca. Descreva a marca no pedido.")
                elif info.get("pessoa_fisica") is None and info.get("name_origin") == "nome":
                    avisos.append("O nome deste cliente veio do cadastro civil e pode ser de pessoa física; confira antes de usar como marca.")
                avisos.extend(sync_banco_logos(info["id"]))
        elif detect["status"] == "ambiguous":
            q = detect["question"]
            with CONV_LOCK:
                fresh = load_conv(scope, b["conv"])
                fresh["turns"].append({"n": len(fresh["turns"]) + 1, "t": time.strftime("%H:%M:%S"), "request": text, "resolved": text, "intent": "new", "question": q})
                save_conv(fresh)
            return {"role": "assistant", "kind": "text", "text": q, "conv": b["conv"], "suggest": [], "suggest_web": [], "files": files}
    if (client_meta or {}).get("sem_identidade"):
        avisos.append("Este cliente ainda não tem identidade de marca cadastrada: paleta, tipografia e estilo estão indisponíveis (não é 'sem cores').")
    if mode == "marca" and not ctx:
        avisos.append("Modo marca sem cliente identificado: gerei sem a identidade da marca. Cite o cliente no texto ou escolha-o no chip.")

    # --- memória: entender a mensagem no contexto da conversa ---
    conv = load_conv(scope, b.get("conv") or uuid.uuid4().hex[:10])
    lastp, last_id = last_image(scope, conv)
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
        inputs = [dict(kind="alvo" if intent == "edit" else "variacao", name=posixpath.basename(lastp), mime="image/svg+xml" if lastp.endswith(".svg") else "image/png",
                       bytes=get_store().read_bytes(lastp), role_text=role)] + list(inputs)
    if size == "auto" and not any(x["kind"] in ("alvo", "variacao") for x in inputs):
        size = infer_size(text_eff)  # sem alvo não há proporção a acompanhar: o formato vem do pedido
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
    # pesquisa na web (como o ChatGPT faz antes de desenhar): só com marca real e fatos que não se inventam
    brand_brief, rq, no_logo = conv.get("brand_brief"), resolved.get("research"), None
    if rq and imp.get("research", True) and provider == "openai" and not MOCK and not (
            brand_brief and skills_router.norm(brand_brief.get("query", "")) == skills_router.norm(rq)):
        emit(f"Pesquisando na web: «{rq}» (busca da OpenAI, modelo {text_model})…")
        tr0 = time.time()
        try:
            brief_r, srcs = research.brand_research(ui.openai_post, rq, text_model)
            brand_brief = {"query": rq, "brief": brief_r, "sources": srcs}
            emit(f"Pesquisa pronta em {round(time.time() - tr0)}s: slogan «{brief_r.get('slogan')}», {len(brief_r.get('ofertas_vigentes', []))} oferta(s) vigente(s), "
                 f"{len(srcs)} fonte(s): " + ", ".join(urllib.parse.urlparse(s["url"]).netloc for s in srcs[:4]))
            if not srcs and brief_r.get("ofertas_vigentes"):  # oferta sem fonte citada não é fato: descarta
                brief_r["ofertas_vigentes"] = []
                avisos.append("A pesquisa não trouxe fontes citáveis; descartei as ofertas encontradas (não publico preço ou condição sem fonte).")
            brand = str(brief_r.get("marca") or "").strip()
            if brand and not any(x["kind"] == "logo" for x in inputs):
                got, why = None, []
                cands = [("site da marca", brief_r.get("logo_url"))]
                for label, lu in cands + [("página oficial", "PAGE"), ("Wikimedia Commons", "COMMONS")]:
                    try:
                        if lu == "PAGE":
                            lu = brief_r.get("site_oficial") and research.find_logo_url(fetch_text(brief_r["site_oficial"]), brief_r["site_oficial"])
                        elif lu == "COMMONS":
                            res = api_websearch({"q": f"logo {brand}"})["results"]
                            lu = next((r["url"] for r in res if r.get("mime") != "image/svg+xml" and "logo" in r["title"].lower()), None)
                        if not lu:
                            continue
                        data, mime = fetch_image(lu)
                        got = (data, mime, label, lu)
                        break
                    except Exception as e:  # noqa: BLE001
                        why.append(f"{label}: {str(e)[:60]}")
                if got:
                    data, mime, label, lu = got
                    asset = store_asset(cid, "logo", f"logo {brand}.{MIME_EXT[mime]}", mime, data, brand,
                                        {"origem": "web", "pagina": str(lu)[:300], "licenca": "da pesquisa na web; confirmar o direito de uso"})
                    files.append(asset["id"])
                    inputs.append(dict(id=asset["id"], kind="logo", name=asset["name"], mime=mime, bytes=data,
                                       role_text=f"{KIND_ROLE['logo']} (arquivo: {asset['name']}; baixado de: {label})"))
                    emit(f"Logo da marca baixado ({label}) e anexado: {asset['name']}.")
                else:
                    no_logo = brand
                    emit("Não achei um logo utilizável na web" + (f" ({'; '.join(why)})" if why else "") + ".")
                    avisos.append(f"Não consegui um logo oficial de {brand}; a peça sai sem logo desenhado. Envie o logo oficial para colocá-lo fiel.")
        except Exception as e:  # noqa: BLE001
            brand_brief = conv.get("brand_brief")
            avisos.append(f"A pesquisa na web não funcionou ({type(e).__name__}: {str(e)[:100]}); segui SEM fatos pesquisados e sem inventar slogan, oferta ou condição.")
    lib = {a["id"]: a for a in load_assets(cid)}
    files_desc = ", ".join(f"{lib[i]['name']} ({lib[i]['kind']}" + (f"; apelido: {lib[i]['alias']}" if lib[i].get("alias") else "") + ")" for i in files if i in lib)
    memory = memory_text(conv, files_desc)
    if no_logo:
        memory += ("\n" if memory else "") + (f"Logo oficial de {no_logo}: NÃO disponível mesmo após pesquisar na web. NÃO pergunte por ele e NÃO faça pergunta alguma sobre o logo: "
                                              "gere a peça já, com o nome da marca só como texto tipográfico simples (sem simular o logo) e as cores da pesquisa; o aviso ao usuário já foi dado.")
    if brand_brief and not conv.get("brand_brief"):  # pesquisa feita agora: o texto legível vai ao designer (depois vem da memória)
        memory += ("\n" if memory else "") + research.brief_text(brand_brief["brief"], brand_brief["sources"])
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
            fresh = load_conv(scope, conv["id"])
            fresh["turns"].append({"n": len(fresh["turns"]) + 1, "t": time.strftime("%H:%M:%S"), "request": text, "resolved": text_eff,
                                   "intent": intent, **turn})
            fresh["carry"] = resolved["carry"]
            fresh["files"] = files
            if brand_brief:
                fresh["brand_brief"] = brand_brief
            save_conv(fresh)

    if imp["designer"]:
        emit(f"O designer está escrevendo o briefing ({'OpenAI, modelo ' + text_model if provider == 'openai' and not MOCK else 'DEMONSTRAÇÃO, sem API' if MOCK else 'Claude CLI: SEM chave da OpenAI'})…")
        brief = write_briefing(ctx_eff, text_eff, size, history, inputs, model=text_model, provider=provider, mode=mode, use_skills=imp["skills"],
                               memory=memory, intent=intent, original=text, library=library)
        if brief.get("question") and not MOCK and provider == "openai" and imp.get("auto", True):
            # modo automático: o usuário quer que o app execute o que foi pedido, sem perguntas; decide a melhor suposição e avisa
            q0 = str(brief["question"])[:300]
            emit(f"O designer ia perguntar «{q0}»; modo automático: decidindo sozinho pela melhor suposição.")
            brief = write_briefing(ctx_eff, text_eff, size, history, inputs, model=text_model, provider=provider, mode=mode, use_skills=imp["skills"],
                                   memory=(memory + "\n" if memory else "") + f"MODO AUTOMÁTICO: o usuário não quer perguntas e quer que você execute o pedido já. A pergunta que você ia fazer era: «{q0}». "
                                   "NÃO devolva question. Adote a suposição mais razoável pelo pedido e pelo contexto (pessoa real citada sem foto: gere a peça SEM a pessoa e sem sósia; logo ou fato ausente: "
                                   "não invente, use a marca só como texto) e registre em `note` (uma frase) a suposição que adotou.",
                                   intent=intent, original=text, library=library)
            if not brief.get("question"):
                avisos.append(f"Não perguntei «{q0[:120]}»: segui pela melhor suposição" + (f" ({str(brief.get('note'))[:140]})" if brief.get("note") else "") + ".")
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
    max_cycle = (1 if region else critic.MAX_CYCLES) if imp["designer"] else 0  # com região, correções por texto quase nunca melhoram: no máximo 2 gerações
    fidelity = "high" if any(x["kind"] in IDENTITY_KINDS + ("alvo", "variacao") for x in inputs) else None
    mid = re.sub(r"[^a-z0-9]", "", time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4])
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
            get_store().write_bytes(f"chat_out/{slug(scope)}/{gid}raw.png", raw, "image/png")
            fin = (regionedit.composite_local(region["orig"], raw, region["boxes"]) if region["mode"] == "local"
                   else regionedit.composite_extend(raw, region["rorig"], region["place"], region["size"]))
            b64, ext = base64.b64encode(fin).decode(), "png"
            emit("Original recolado fora da região editada (pixels idênticos).")
        get_store().write_bytes(f"chat_out/{slug(scope)}/{gid}.{ext}", base64.b64decode(b64), "image/svg+xml" if ext == "svg" else "image/png")
        url = f"/files/{slug(scope)}/out/{gid}.{ext}"
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
           "intent": intent, "conv": conv["id"], "files": files, "fontes": (brand_brief or {}).get("sources", []), "pesquisa": (brand_brief or {}).get("query"), "falha_identidade": "identidade_divergente" in ((best["rv"] or {}).get("veto") or []), "avisos": avisos, "cycles": cycles, "skills": used, "packs": packs, "mode": mode, "improve": imp,
           "generations": len(cycles), "seconds": round(time.time() - t0, 1), "size": size,
           "inputs": [{"kind": x["kind"], "name": x["name"]} for x in inputs]}
    record(briefing=e["prompt"], image_id=e["id"], score=best["score"], approved=bool(best["ok"]),
           inputs=[{"kind": x["kind"], "name": x["name"]} for x in inputs], mode=mode, packs=packs)
    if imp["compare_raw"]:
        emit("Gerando a versão do GPT puro (o seu texto, sem a aplicação) para comparar…")
        tr = time.time()
        b64, ext = make_image(text_eff, size, quality, inputs, image_model, fidelity, avisos)
        rid = f"{mid}raw"
        get_store().write_bytes(f"chat_out/{slug(scope)}/{rid}.{ext}", base64.b64decode(b64), "image/svg+xml" if ext == "svg" else "image/png")
        raw = {"id": rid, "url": f"/files/{slug(scope)}/out/{rid}.{ext}", "prompt": text_eff}
        emit(f"Versão do GPT puro pronta em {round(time.time() - tr)}s.", image_url=raw["url"])
        if do_rev:
            emit("O critic está revisando a versão pura (mesma régua)…")
            rv2, s2, ok2 = do_review(ctx_critic, text_eff, text_eff, b64, ext, size, inputs, b.get("critic_model") or text_model, "", packs)
            raw.update(score=s2, approved=ok2, veto=rv2.get("veto", []))
            emit(f"GPT puro: nota {s2}{' · vetos: ' + ', '.join(rv2.get('veto', [])) if rv2.get('veto') else ''}")
        msg["raw"] = raw
    return msg


POST = {"/api/project": api_project_create, "/api/project/rename": api_project_rename, "/api/project/delete": api_project_delete,
        "/api/conv/move": api_conv_move, "/api/conv/client": api_conv_client, "/api/client": api_client, "/api/client/save": api_client_save, "/api/client/new": api_client_new, "/api/asset": api_asset,
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
        que tentariam gastar a chave ou mexer na biblioteca (CSRF) e DNS rebinding.
        Na Vercel (env VERCEL) o Host é o domínio do deploy e o login é a Deployment Protection da Vercel: aqui só resta a
        checagem de mesma origem (um Origin, se vier, precisa ser o próprio Host)."""
        if vercel_mode():
            org = self.headers.get("Origin")
            return not org or urllib.parse.urlparse(org).netloc.lower() == (self.headers.get("Host") or "").lower()
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
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True)
                return self._send(200, list_convs((q.get("client") or q.get("scope") or [""])[0] if ("client" in q or "scope" in q) else None))
            if path == "/api/clients":
                return self._send(200, api_clients((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q") or [""])[0]))
            if path == "/api/projects":
                return self._send(200, api_projects({}))
            m = re.fullmatch(r"/files/([a-z0-9_-]+)/(assets|out)/([A-Za-z0-9._-]+)", path)
            if m and m.group(3) not in (".", ".."):
                key = f"clients/{m.group(1)}/assets/{m.group(3)}" if m.group(2) == "assets" else f"chat_out/{m.group(1)}/{m.group(3)}"
                try:
                    data = get_store().read_bytes(key)
                except FileNotFoundError:
                    data = None
                if data is not None:
                    return self._send(200, data, mimetypes.guess_type(m.group(3))[0] or "application/octet-stream")
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
