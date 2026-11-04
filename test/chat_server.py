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
import argparse, base64, json, mimetypes, os, pathlib, random, re, shutil, sys, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import checks, critic, skills_router  # noqa: E402
import run_comparison as rc  # noqa: E402
import ui_server as ui  # noqa: E402  (openai_post, ApiError, env_models)

# CHAT_DATA_DIR separa os dados do uso real dos dos testes automáticos (nunca apague a pasta de uso)
DATA = pathlib.Path(os.getenv("CHAT_DATA_DIR") or ROOT)
CLIENTS, OUT = DATA / "clients", DATA / "chat_out"
MOCK = False
MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/svg+xml": "svg"}
KIND_ROLE = {
    "referencia": "REFERÊNCIA de estilo, cena ou assunto: inspire-se, não copie",
    "pessoa": "FOTO de pessoa real com autorização: é a IDENTIDADE a preservar (mesmo rosto, cabelo e traços); nunca substitua por sósia ou modelo genérico",
    "logo": "LOGO oficial do cliente: deve aparecer idêntico, nunca redesenhado nem alterado",
    "peca": "PEÇA já entregue ao cliente: mantenha o mesmo estilo e a mesma linguagem visual",
    "produto": "PRODUTO do cliente: deve aparecer fiel ao original (forma, cor, rótulo)",
}
SIZES = {"1024x1024", "1536x1024", "1024x1536"}


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
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


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
def build_user(text, size, history, inputs, feedback=None, prev=None, memory="", intent="new", original=None):
    u = f"Pedido atual (já resolvido com o contexto da conversa): {text}\n"
    if original and original.strip() != text.strip():
        u += f"Mensagem original do usuário: {original}\n"
    u += f"Contêiner/tamanho: {size}\n"
    if intent == "edit":
        u += ("Intenção: EDIÇÃO da Image 1 (a última imagem gerada): escreva 'change only X; keep everything else unchanged' e repita as invariantes "
              "(rosto, pose, enquadramento, fundo, texto).\n")
    elif intent == "variation":
        u += "Intenção: VARIAÇÃO da Image 1: mantenha o conceito, a pessoa/produto/marca e o estilo; mude só o que o pedido indicar.\n"
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
          'Se o pedido não disser o que deve aparecer (sem assunto), ou, numa peça de marketing, se faltar a oferta e não der para deduzir, '
          'responda SOMENTE {"question":"<uma pergunta curta em português>"}.\n'
          'Caso contrário responda SOMENTE JSON: {"use_case":"...","role":"hero|cell","prompt":"<prompt final em inglês no schema>"}')
    return u


def write_briefing(ctx, text, size, history, inputs, feedback=None, prev=None, model=None, provider="openai", mode="livre", use_skills=True,
                   memory="", intent="new", original=None):
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
    user = build_user(text, size, history, inputs, feedback, prev, memory, intent, original)
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


def make_image(prompt, size, quality, inputs, model, fidelity=None, notes=None):
    if MOCK:
        time.sleep(0.8)
        w, h = (int(x) for x in size.split("x"))
        hue = random.randint(0, 360)
        svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'><rect width='100%' height='100%' "
               f"fill='hsl({hue},55%,52%)'/><text x='50%' y='48%' font-size='{w // 16}' fill='white' text-anchor='middle'>"
               f"mock {size}</text><text x='50%' y='56%' font-size='{w // 28}' fill='white' text-anchor='middle'>"
               f"{len(inputs)} imagem(ns) de entrada</text></svg>")
        return base64.b64encode(svg.encode()).decode(), "svg"
    if inputs:
        files = [("image[]", f"in{i}.{MIME_EXT.get(x['mime'], 'png')}", x["mime"], x["bytes"]) for i, x in enumerate(inputs)]
        fields = {"model": model, "prompt": prompt, "size": size, "quality": quality, "n": 1}
        if fidelity:
            fields["input_fidelity"] = fidelity  # alta fidelidade preserva rosto, logo e produto das imagens de entrada
        try:
            r = openai_multipart("/images/edits", fields, files)
        except ui.ApiError as e:
            if fidelity and "input_fidelity" in str(e):  # o modelo não aceita o parâmetro: repete sem ele e avisa
                fields.pop("input_fidelity")
                if notes is not None:
                    notes.append("O modelo de imagem não aceitou input_fidelity=high; repeti sem ele. A fidelidade ao rosto, logo ou produto de referência pode cair.")
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
    for aid in asset_ids:
        a = by_id.get(aid)
        if not a:
            continue
        p = cdir(cid) / "assets" / a["file"]
        inputs.append(dict(kind=a["kind"], name=a["name"], mime=a["mime"], bytes=p.read_bytes(),
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
            "kinds": list(KIND_ROLE), "sizes": sorted(SIZES)}


def api_client(b):
    cid = b["id"]
    return {"id": slug(cid), "client": load_client(cid), "assets": with_urls(cid, load_assets(cid))}


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
    data = base64.b64decode(b["b64"])
    if len(data) > 20 * 1024 * 1024:
        raise ui.ApiError(400, "arquivo maior que 20 MB")
    aid = uuid.uuid4().hex[:8]
    a = {"id": aid, "kind": b["kind"], "name": os.path.basename(b.get("name") or f"{aid}.{MIME_EXT[mime]}"),
         "file": f"{aid}.{MIME_EXT[mime]}", "mime": mime}
    (cdir(cid) / "assets" / a["file"]).write_bytes(data)
    assets = load_assets(cid) + [a]
    (cdir(cid) / "assets.json").write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"asset": with_urls(cid, [a])[0]}


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


# ---------- jobs (a geração leva minutos: o navegador acompanha por polling) ----------
JOBS = {}


def start_job(fn):
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "status": "running", "steps": [], "message": None, "error": None, "t0": time.time()}
    for old in sorted(JOBS.values(), key=lambda j: j["t0"])[:-40]:
        JOBS.pop(old["id"], None)
    JOBS[jid] = job

    def emit(text, **extra):
        job["steps"].append({"t": round(time.time() - job["t0"], 1), "text": text, **extra})

    def runner():
        try:
            job["message"] = fn(emit)
            job["status"] = "done"
        except ui.ApiError as e:
            job["status"], job["error"] = "error", str(e)
        except Exception as e:  # noqa: BLE001
            job["status"], job["error"] = "error", f"{type(e).__name__}: {e}"

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
    inputs = collect_inputs(cid, b.get("edit_of"), b.get("asset_ids") or [])
    if not MOCK and not os.getenv("OPENAI_API_KEY") and not shutil.which("claude"):
        raise ui.ApiError(400, "Sem OPENAI_API_KEY e sem o CLI claude: nada a executar.")
    return {"job": start_job(lambda emit: run_chat(b, emit, cid, text, ctx, inputs))}


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
        return json.loads(p.read_text(encoding="utf-8"))
    return {"id": slug(conv_id), "client": slug(cid), "created": time.strftime("%Y-%m-%d %H:%M:%S"), "turns": [], "carry": []}


def save_conv(conv):
    p = conv_path(conv["client"], conv["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def last_image(cid, conv):
    for t in reversed(conv["turns"]):
        if t.get("image_id"):
            try:
                return find_out(cid, t["image_id"]), t["image_id"]
            except ui.ApiError:
                return None, None
    return None, None


def memory_text(conv):
    """O que o designer e o resolvedor 'lembram': pedidos, o que foi gerado e perguntas pendentes."""
    if not conv["turns"] and not conv["carry"]:
        return ""
    lines = ["Memória da conversa (mais antigo primeiro):"]
    for t in conv["turns"][-8:]:
        if t.get("question"):
            lines.append(f'{t["n"]}. Pedido: {t["resolved"][:300]} | o designer PERGUNTOU: "{t["question"]}" (sem imagem)')
        else:
            lines.append(f'{t["n"]}. Pedido: {t["resolved"][:300]} | intenção: {t["intent"]} | resultado: imagem {t["image_id"]} '
                         f'(nota {t["score"]}, {"aprovada" if t["approved"] else "reprovada"}) | briefing final: {t["briefing"][:600]}')
    if conv["carry"]:
        lines.append("Instruções duradouras do usuário: " + "; ".join(conv["carry"]))
    last = conv["turns"][-1] if conv["turns"] else None
    if last and last.get("question"):
        lines.append(f'PERGUNTA PENDENTE: o último turno terminou numa pergunta do designer; a nova mensagem provavelmente a responde '
                     f'(pedido original: {last["resolved"][:300]})')
    return "\n".join(lines)


def resolve_turn(conv, text, avail, model, provider):
    """Entende a mensagem no contexto (como o ChatGPT): devolve intenção e um pedido autossuficiente. Nunca derruba o fluxo."""
    triv = {"intent": "new", "request": text, "use_last_image": False, "carry": list(conv["carry"])}
    if provider != "openai" or not (conv["turns"] or conv["carry"]):
        return triv, None
    mem = memory_text(conv)
    last = conv["turns"][-1]
    if MOCK:
        if last.get("question"):
            return {**triv, "request": f'{last["resolved"]} {text}'}, None
        if EDIT_WORDS.search(text):
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
                "use_last_image": bool(out.get("use_last_image")) and out["intent"] in ("edit", "variation"), "carry": carry or list(conv["carry"])}, None
    except Exception as e:  # noqa: BLE001
        return triv, f"não consegui resolver o contexto ({type(e).__name__}); usei a sua mensagem como está"


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


def run_chat(b, emit, cid, text, ctx, inputs):
    size = b.get("size") if b.get("size") in SIZES else "1024x1024"
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

    # --- memória: entender a mensagem no contexto da conversa ---
    conv = load_conv(cid, b.get("conv") or uuid.uuid4().hex[:10])
    lastp, last_id = last_image(cid, conv)
    avail = (f"última imagem gerada (id {last_id}); " if last_id else "nenhuma imagem gerada ainda; ") + \
            ("fixadas na conversa: " + ", ".join(f"{x['name']} ({x['kind']})" for x in inputs if x["kind"] not in ("alvo",)) if inputs else "nenhuma imagem fixada")
    resolved, warn = resolve_turn(conv, text, avail, text_model, provider)
    if warn:
        avisos.append(warn)
    text_eff, intent = resolved["request"], resolved["intent"]
    if b.get("edit_of") and intent == "new":
        intent = "edit"  # o botão "Editar esta imagem" vale mais que a leitura do resolvedor
    if resolved["use_last_image"] and lastp and not any(x["kind"] == "alvo" for x in inputs):
        role = ("ALVO DE EDIÇÃO: a última imagem gerada; mude só o que o pedido atual pede e mantenha o resto idêntico" if intent == "edit"
                else "IMAGEM-BASE da variação: mantenha o conceito, a pessoa/produto/marca e o estilo; mude só o que o pedido indicar")
        inputs = [dict(kind="alvo" if intent == "edit" else "variacao", name=lastp.name, mime="image/svg+xml" if lastp.suffix == ".svg" else "image/png",
                       bytes=lastp.read_bytes(), role_text=role)] + list(inputs)
    memory = memory_text(conv)
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
        n = len(conv["turns"]) + 1
        conv["turns"].append({"n": n, "t": time.strftime("%H:%M:%S"), "request": text, "resolved": text_eff, "intent": intent, **turn})
        conv["carry"] = resolved["carry"]
        save_conv(conv)

    if imp["designer"]:
        emit("O designer está escrevendo o briefing…")
        brief = write_briefing(ctx_eff, text_eff, size, history, inputs, model=text_model, provider=provider, mode=mode, use_skills=imp["skills"],
                               memory=memory, intent=intent, original=text)
        if brief.get("question"):
            record(question=brief["question"])
            return {"role": "assistant", "kind": "text", "text": brief["question"], "conv": conv["id"]}
        if provider == "claude":
            return {"role": "assistant", "kind": "text", "briefing_only": True,
                    "text": "Sem OPENAI_API_KEY: gerei só o briefing, sem imagem.\n\n" + brief.get("prompt", "")}
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
        emit(f"Tentativa {cycle + 1}: {how} ({image_model}, {size}, {quality}" + (", fidelidade alta" if fidelity else "") + ")…")
        tg = time.time()
        b64, ext = make_image(brief["prompt"], size, quality, inputs, image_model, fidelity, avisos)
        gid = f"{mid}c{cycle}"
        (OUT / slug(cid) / f"{gid}.{ext}").write_bytes(base64.b64decode(b64))
        url = f"/files/{slug(cid)}/out/{gid}.{ext}"
        emit(f"Imagem da tentativa {cycle + 1} pronta em {round(time.time() - tg)}s.", image_url=url)
        entry = {"cycle": cycle, "prompt": brief["prompt"], "id": gid, "url": url}
        if do_rev:
            emit("O critic está revisando…")
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
                               model=text_model, provider=provider, mode=mode, use_skills=imp["skills"], memory=memory, intent=intent, original=text)
        if brief.get("question"):
            break
    e = best["entry"]
    if "identidade_divergente" in ((best["rv"] or {}).get("veto") or []):
        avisos.append("A imagem não manteve a identidade da referência (pessoa, produto ou logo). Confira a foto anexada e o tipo dela; "
                      "a API de imagem pode não preservar o rosto de uma pessoa real.")
    msg = {"role": "assistant", "kind": "image", "id": e["id"], "url": e["url"], "score": best["score"], "approved": best["ok"],
           "veto": (best["rv"] or {}).get("veto", []), "review": best["rv"], "prompt": e["prompt"], "request": text, "resolved": text_eff,
           "intent": intent, "conv": conv["id"], "avisos": avisos, "cycles": cycles, "skills": used, "packs": packs, "mode": mode, "improve": imp,
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


POST = {"/api/client": api_client, "/api/client/save": api_client_save, "/api/asset": api_asset,
        "/api/asset/delete": api_asset_delete, "/api/asset/kind": api_asset_kind, "/api/chat": api_chat, "/api/job": api_job,
        "/api/conv": api_conv}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._send(200, (ROOT / "chat" / "index.html").read_bytes(), "text/html")
            if path == "/api/state":
                return self._send(200, api_state({}))
            if path == "/api/models":
                return self._send(200, api_models({}))
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
    print(f"Chat em http://127.0.0.1:{a.port}  ({'MOCK' if MOCK else 'OPENAI_API_KEY ' + ('definida' if os.getenv('OPENAI_API_KEY') else 'NÃO definida')})")
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    except OSError as e:
        sys.exit(f"Não consegui abrir a porta {a.port} ({e.strerror}). Já tem um chat rodando? Feche-o ou use --port {a.port + 1}.")
    srv.serve_forever()


if __name__ == "__main__":
    main()
