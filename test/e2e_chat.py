#!/usr/bin/env python3
"""Teste de ponta a ponta do chat contra a OpenAI falsa (fake_openai.py). Sem chave, sem custo.

  python3 e2e_chat.py

Sobe a OpenAI falsa e o chat em portas livres, com uma pasta de dados TEMPORÁRIA (CHAT_DATA_DIR): nunca toca em
test/clients nem test/chat_out, que guardam o seu uso real. Prova que o nosso código monta as requisições, trata as
respostas e respeita modos e melhorias; não valida a semântica da API real.
"""
import base64, json, os, pathlib, socket, struct, subprocess, sys, tempfile, time, urllib.error, urllib.request, zlib

ROOT = pathlib.Path(__file__).resolve().parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


FAKE, CHAT = free_port(), free_port()
tmp = tempfile.TemporaryDirectory()
procs = [subprocess.Popen([sys.executable, str(ROOT / "fake_openai.py"), "--port", str(FAKE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
         subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(CHAT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          env={**os.environ, "CHAT_DATA_DIR": tmp.name, "OPENAI_API_KEY": "fake", "OPENAI_BASE_URL": f"http://127.0.0.1:{FAKE}/v1"})]
try:
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CHAT}/api/state", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        sys.exit("o servidor do chat não subiu")

    def call(base, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{base}{path}", data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    def png(w,h):
        raw=b"".join(b"\x00"+b"\x80"*w for _ in range(h)); c=lambda t,d: struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
        return b"\x89PNG\r\n\x1a\n"+c(b"IHDR",struct.pack(">IIBBBBB",w,h,8,0,0,0,0))+c(b"IDAT",zlib.compress(raw))+c(b"IEND",b"")
    def run(body):
        st, j = call(CHAT, "/api/chat", body); assert st == 200, (st, j)
        steps, since = [], 0
        for _ in range(200):
            time.sleep(0.4); _, p = call(CHAT, "/api/job", {"id": j["job"], "since": since}); since = p["next"]; steps += p["steps"]
            if p["status"] != "running": return p, steps
        raise SystemExit("timeout")
    ok = lambda c, m: print(("OK   " if c else "FALHA"), m) or (c or sys.exit(1))

    st, m = call(CHAT, "/api/models"); print("models:", m)
    ok(m["ok"] and "gpt-image-2.5-sunburst" in m["image_models"] and "gpt-5.5" in m["text_models"] and "whisper-1" not in m["text_models"], "lista de modelos filtrada e sem avisos")
    _, a = call(CHAT, "/api/asset", {"client": "71", "kind": "logo", "name": "logo.png", "mime": "image/png", "b64": base64.b64encode(png(64, 64)).decode()}); aid = a["asset"]["id"]
    st, e = call(CHAT, "/api/asset", {"client": "71", "kind": "logo", "name": "l.svg", "mime": "image/svg+xml", "b64": "AA=="}); ok(st == 400 and "SVG" in e["error"], "SVG recusado no modo real")

    # 1) com logo: briefing vê a imagem, edição multipart, reprova no 1º ciclo e aprova no 2º
    p, steps = run({"client": "71", "text": "banner de promocao de verao com a nossa logo", "asset_ids": [aid], "size": "1536x1024", "quality": "low"})
    msg = p["message"]; print("passos:", [s["text"][:60] for s in steps])
    ok(p["status"] == "done" and msg["kind"] == "image", "job terminou com imagem")
    ok(msg["generations"] == 2 and msg["approved"] and msg["score"] >= 8, f"correção funcionou: 2 gerações, nota {msg['score']}")
    ok(len(msg["cycles"]) == 2 and msg["cycles"][0]["approved"] is False and msg["cycles"][0]["fix"], "ciclo 1 reprovado com correção")
    ok(all(c["url"] for c in msg["cycles"]) and msg["id"] == msg["cycles"][1]["id"], "cada tentativa salvou sua imagem; a melhor é a final")
    ok(any(s.get("image_url") for s in steps), "progresso mostra imagem intermediária")
    ok("design-tipografia-texto" in msg["skills"], "skills roteadas no caminho real")
    _, s = call(FAKE, "/__stats")
    ok(s["edits"] == 2 and s["edit_images"] == [1, 1] and s["generations"] == 0, f"usou /images/edits com a logo (image[]={s['edit_images']})")
    ok(s["writer_images"][0] == 1, "o designer recebeu a logo como imagem")
    ok(s["critic_images"][0] == 2, "o critic recebeu a imagem gerada + a logo de referência")
    ok([a for a in s["auth"] if a] == ["Bearer fake"], "autenticação enviada em todas as chamadas à API")
    ok("quality" in s["edit_fields"][0] and "prompt" in s["edit_fields"][0], "campos do multipart")

    # 2) edição da imagem anterior (alvo) + sem logo
    p, _ = run({"client": "71", "text": "deixe mais quente", "edit_of": msg["id"], "history": [{"role": "user", "text": "banner"}], "review": False})
    m2 = p["message"]; ok(m2["kind"] == "image" and m2["score"] is None and m2["inputs"][0]["kind"] == "alvo", "edição usa a imagem anterior como alvo, sem revisão")
    _, s = call(FAKE, "/__stats"); ok(s["edits"] == 3, "mais uma chamada de edição")
    ok("Conversa até aqui" in s["last_writer_user"] and "ALVO DE EDIÇÃO" in s["last_writer_user"], "histórico e alvo no briefing")

    # 3) sem imagens: /images/generations
    p, _ = run({"client": "71", "text": "paisagem de praia", "review": False}); ok(p["message"]["kind"] == "image", "geração sem entradas")
    _, s = call(FAKE, "/__stats"); ok(s["generations"] == 1, "usou /images/generations")

    # 4) tamanho errado: veto por código mesmo com nota alta
    p, _ = run({"client": "71", "text": "banner wrongsize", "size": "1024x1024"}); m3 = p["message"]
    ok("formato_incorreto" in m3["veto"] and m3["approved"] is False, f"veto formato_incorreto aplicado (vetos {m3['veto']})")

    # 5) pergunta do designer
    p, _ = run({"client": "71", "text": "preciso perguntar algo"}); ok(p["message"]["kind"] == "text" and "oferta" in p["message"]["text"].lower(), "designer pergunta quando falta a oferta")
    # 6) validações síncronas
    ok(call(CHAT, "/api/chat", {"client": "71", "text": " "})[0] == 400, "mensagem vazia recusada na hora")
    ok(call(CHAT, "/api/chat", {"client": "71", "text": "x", "edit_of": "naoexiste"})[0] == 404, "alvo inexistente recusado na hora")
    ok(call(CHAT, "/api/job", {"id": "nada"})[0] == 404, "job inexistente")

    # 7) modos, melhorias independentes e comparação com o GPT puro
    p, _ = run({"client": "71", "text": "um gato astronauta numa estacao espacial", "review": False}); m = p["message"]
    _, s = call(FAKE, "/__stats"); sysm = s["writer_systems"][-1]
    ok(sysm["livre"] and not sysm["marca"] and not sysm["setor_no_prompt"], f"modo livre (padrão): nada do cliente no system prompt {sysm}")
    ok(m["mode"] == "livre" and "design-estrategia" not in m["skills"], f"imagem livre não carrega a skill de estratégia de marketing ({m['skills']})")
    p, _ = run({"client": "71", "text": "banner de black friday", "mode": "marca", "review": False}); m = p["message"]
    _, s = call(FAKE, "/__stats"); sysm = s["writer_systems"][-1]
    ok(sysm["marca"] and sysm["setor_no_prompt"] and m["mode"] == "marca", "modo com marca carrega o cliente")
    ok("design-estrategia" in m["skills"], "peça de marketing carrega a skill de estratégia")
    n_writers = s["chat_writer"]
    p, steps = run({"client": "71", "text": "garrafa de vidro ambar sobre marmore preto", "improve": {"designer": False}, "review": False}); m = p["message"]
    _, s = call(FAKE, "/__stats")
    ok(s["chat_writer"] == n_writers, "designer desligado: nenhuma chamada ao redator de briefing")
    ok(s["image_prompts"][-1] == "garrafa de vidro ambar sobre marmore preto", "o texto do usuário vai EXATAMENTE ao modelo de imagem")
    ok(m["skills"] == [] and m["generations"] == 1 and m["prompt"] == m["request"], "sem designer: sem skills, 1 geração, prompt = pedido")
    p, steps = run({"client": "71", "text": "retrato de senhora idosa rindo", "improve": {"compare_raw": True}}); m = p["message"]
    _, s = call(FAKE, "/__stats")
    ok(m.get("raw") and m["raw"]["url"] and m["raw"].get("score") is not None, "comparação: GPT puro gerado e avaliado na mesma régua")
    ok(s["image_prompts"][-1] == "retrato de senhora idosa rindo", "a versão pura usa só o texto do usuário")
    ok(any("GPT puro" in x["text"] for x in steps), "progresso informa a versão pura")
    pa = run({"client": "71", "text": "gato astronauta", "review": False})[0]["message"]["prompt"]
    pb = run({"client": "71", "text": "garrafa de vidro", "review": False})[0]["message"]["prompt"]
    ok(pa != pb and "gato" in pa.lower() and "garrafa" in pb.lower() and "praia" not in (pa + pb).lower(), "pedidos diferentes geram briefings diferentes, sem cena do cliente")

    print("\nTUDO OK")
finally:
    for p in procs:
        p.terminate()
    tmp.cleanup()
