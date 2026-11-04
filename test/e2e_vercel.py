#!/usr/bin/env python3
"""Simula LOCALMENTE a função da Vercel: api/index.py (class handler) sob um servidor HTTP comum, com VERCEL=1, JOBS_INLINE=1 e
STORE=memory, contra a OpenAI falsa. Sem chave, sem nuvem, sem custo.

  cd test && python3 -I e2e_vercel.py

O que prova: o handler importa de dentro de api/ com o sys.path ajustado; o fluxo estado -> cliente novo -> upload -> chat -> job ->
/files funciona só com Store em memória e tarefas inline; os guardas do modo Vercel (mesma origem, /api/setkey desligado) e o do modo
local (loopback) se comportam como combinado.
O que NÃO prova: o runtime real da Vercel (como ele chama a classe handler, o que acontece com o caminho da requisição depois do
rewrite, limites de tempo e de tamanho de corpo/resposta), nem o Vercel Blob real (aqui é MemoryStore).
"""
import base64, http.client, json, os, pathlib, socket, struct, subprocess, sys, time, urllib.error, urllib.request, zlib

ROOT = pathlib.Path(__file__).resolve().parent
API = ROOT.parent / "api"
LAUNCH = ("import sys; sys.path.insert(0, sys.argv[1]); import index; from http.server import ThreadingHTTPServer; "
          "ThreadingHTTPServer(('127.0.0.1', int(sys.argv[2])), index.handler).serve_forever()")
N = {"ok": 0}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ok(cond, msg):
    print(("OK   " if cond else "FALHA"), msg)
    if not cond:
        sys.exit(1)
    N["ok"] += 1


def png(w, h):
    raw = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    c = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + c(b"IDAT", zlib.compress(raw)) + c(b"IEND", b"")


FAKE = free_port()
procs = [subprocess.Popen([sys.executable, str(ROOT / "fake_openai.py"), "--port", str(FAKE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]


def spawn(extra):
    port = free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "BLOB_READ_WRITE_TOKEN", "STORE", "VERCEL", "JOBS_INLINE", "CHAT_DATA_DIR")}
    env.update({"OPENAI_API_KEY": "fake", "OPENAI_BASE_URL": f"http://127.0.0.1:{FAKE}/v1", **extra})
    p = subprocess.Popen([sys.executable, "-c", LAUNCH, str(API), str(port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    return port


def wait(port):
    for _ in range(100):
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            c.request("GET", "/nada")
            c.getresponse().read()
            return
        except OSError:
            time.sleep(0.2)
    sys.exit("o servidor não subiu")


def req(port, method, path, body=None, headers=None, raw=False):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    h = dict(headers or {})
    data = None if body is None else json.dumps(body).encode()
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    b = r.read()
    return r.status, (b if raw else (json.loads(b) if b[:1] in (b"{", b"[") else b)), r.getheader("Content-Type")


try:
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{FAKE}/__stats", timeout=1)
            break
        except Exception:
            time.sleep(0.2)

    # ---- modo Vercel: VERCEL=1, JOBS_INLINE=1, STORE=memory ----
    V = spawn({"VERCEL": "1", "JOBS_INLINE": "1", "STORE": "memory"})
    wait(V)
    HOST = "chat-preview-abc.vercel.app"
    same = {"Host": HOST, "Origin": f"https://{HOST}"}
    st, html, ct = req(V, "GET", "/", headers={"Host": HOST})
    ok(st == 200 and b"<html" in html.lower() and "text/html" in ct, "GET / serve a página (Host de domínio Vercel aceito, sem loopback)")
    st, state, _ = req(V, "GET", "/api/state", headers={"Host": HOST})
    ok(st == 200 and [c["id"] for c in state["clients"]] == ["71"] and state["has_key"], "GET /api/state: cliente 71 semeado no Store em memória")
    ok(req(V, "GET", "/api/state", headers={"Host": HOST, "Origin": "https://outro-site.example"})[0] == 403, "Origin diferente do Host é bloqueado (mesma origem)")
    ok(req(V, "POST", "/api/client", {"id": "71"}, {"Host": HOST, "Origin": "https://outro-site.example"})[0] == 403, "POST de outra origem é bloqueado")
    ok(req(V, "POST", "/api/client", {"id": "71"}, same)[0] == 200, "Origin igual ao Host passa")
    ok(req(V, "POST", "/api/client", {"id": "71"}, {"Host": HOST})[0] == 200, "sem Origin passa")
    st, e, _ = req(V, "POST", "/api/setkey", {"key": "sk-" + "x" * 30}, same)
    ok(st == 403 and "OPENAI_API_KEY" in e["error"], f"/api/setkey desligado com mensagem clara ({e['error'][:60]}...)")
    st, nc, _ = req(V, "POST", "/api/client/new", {"name": "Padaria Sol", "sector": "alimentos"}, same)
    ok(st == 200 and nc["id"] == "padaria-sol", "cliente novo")
    st, a, _ = req(V, "POST", "/api/asset", {"client": "padaria-sol", "kind": "logo", "name": "logo.png", "mime": "image/png", "b64": base64.b64encode(png(64, 64)).decode()}, same)
    ok(st == 200 and a["asset"]["url"].startswith("/files/padaria-sol/assets/"), "upload de logo")
    st, f, ct = req(V, "GET", a["asset"]["url"], headers={"Host": HOST}, raw=True)
    ok(st == 200 and f[:8] == b"\x89PNG\r\n\x1a\n" and ct == "image/png", "/files serve a logo do Store")
    st, j, _ = req(V, "POST", "/api/chat", {"client": "padaria-sol", "conv": "c1", "text": "banner de promocao de verao", "asset_ids": [a["asset"]["id"]], "size": "1536x1024", "quality": "low"}, same)
    ok(st == 200 and j["status"] == "done" and j["message"]["kind"] == "image" and j["message"]["approved"], f"/api/chat inline devolve a imagem pronta (nota {j['message']['score']})")
    st, p, _ = req(V, "POST", "/api/job", {"id": j["job"]}, same)
    ok(p["status"] == "done" and p["message"]["id"] == j["message"]["id"] and p["steps"], "/api/job responde pelo Store")
    st, img, ct = req(V, "GET", j["message"]["url"], headers={"Host": HOST}, raw=True)
    ok(st == 200 and img[:4] == b"\x89PNG", "/files/.../out serve a imagem gerada")
    st, cv, _ = req(V, "POST", "/api/conv", {"client": "padaria-sol", "conv": "c1"}, same)
    ok(len(cv["turns"]) == 1 and a["asset"]["id"] in cv["files"], "conversa gravada no Store")
    st, lst, _ = req(V, "GET", "/api/convs?client=padaria-sol", headers={"Host": HOST})
    ok(lst["convs"] and lst["convs"][0]["id"] == "c1" and lst["skipped"] == 0, "histórico lista a conversa")
    st, j2, _ = req(V, "POST", "/api/chat", {"client": "padaria-sol", "conv": "c1", "text": "deixe mais quente", "edit_of": j["message"]["id"], "review": False}, same)
    ok(j2["status"] == "done" and j2["message"]["intent"] == "edit", "edição da imagem anterior (lida do Store) funciona")
    ok(req(V, "GET", "/files/padaria-sol/out/..", headers={"Host": HOST})[0] == 404 and req(V, "GET", "/files/padaria-sol/assets/nao-existe.png", headers={"Host": HOST})[0] == 404, "/files: '..' e arquivo inexistente dão 404")
    ok(req(V, "POST", "/api/job", {"id": "nada"}, same)[0] == 404, "job desconhecido: 404")
    st, ev, _ = req(V, "POST", "/api/clientlog", {"kind": "js-error", "message": "x"}, same)
    ok(st == 200, "clientlog grava no Store")

    # ---- modo local (sem VERCEL): o guarda de loopback segue igual, /api/setkey funciona ----
    L = spawn({"STORE": "memory"})
    wait(L)
    ok(req(L, "GET", "/api/state")[0] == 200, "local: 127.0.0.1 aceito")
    ok(req(L, "GET", "/api/state", headers={"Host": HOST})[0] == 403, "local: Host de domínio estranho continua bloqueado")
    ok(req(L, "GET", "/api/state", headers={"Origin": "https://outro-site.example"})[0] == 403, "local: Origin estranho continua bloqueado")
    st, kr, _ = req(L, "POST", "/api/setkey", {"key": "sk-" + "x" * 30, "save": False})
    ok(st == 200 and kr["ok"], "local: /api/setkey continua funcionando")
    st, j3, _ = req(L, "POST", "/api/chat", {"client": "71", "text": "uma xicara de cafe", "review": False})
    ok(st == 200 and "status" not in j3 and "job" in j3, "local (sem JOBS_INLINE): /api/chat devolve só o id da tarefa")

    # ---- Vercel sem loja configurada: falha clara em vez de gravar em disco efêmero ----
    X = spawn({"VERCEL": "1"})
    wait(X)
    st, e, _ = req(X, "GET", "/api/state", headers={"Host": HOST})
    ok(st == 500 and "BLOB_READ_WRITE_TOKEN" in e["error"], "Vercel sem BLOB_READ_WRITE_TOKEN: erro claro, nenhum dado em disco")
    print(f"\nTUDO OK ({N['ok']} verificações)")
finally:
    for p in procs:
        p.terminate()
