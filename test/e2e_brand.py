"""Regressão da rota estática GET /brand/<arquivo> do chat_server (allowlist, path traversal, content-type).
Sobe uma instância própria em porta livre, sem chamar a OpenAI: python3 e2e_brand.py"""
import http.client, os, pathlib, re, shutil, socket, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parent
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]
tmp = tempfile.TemporaryDirectory()
proc = subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env={**os.environ, "CHAT_DATA_DIR": tmp.name, "OPENAI_API_KEY": "fake"})


def get(path, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    c.request(method, path)  # http.client não normaliza o caminho
    r = c.getresponse(); body = r.read()
    return r.status, r.getheader("Content-Type") or "", r.getheader("Cache-Control"), body


# sentinela FORA de chat/brand: um .png válido que só seria servido se a proteção de caminho falhasse
sent_dir = pathlib.Path(tempfile.mkdtemp(dir=ROOT, prefix="_sentinela_")); (sent_dir / "x.png").write_bytes(b"\x89PNG\r\n\x1a\nSENTINELA")
link = ROOT / "chat" / "brand" / "_link_fora.png"  # link simbólico dentro da pasta apontando para fora: só o resolve()/is_relative_to barra
link.symlink_to(sent_dir / "x.png")
ok = lambda c, m: print(("OK   " if c else "FALHA"), m) or (c or sys.exit(1))
try:
    for _ in range(50):
        try: get("/api/state"); break
        except Exception: time.sleep(0.2)
    else:
        sys.exit("o servidor do chat não subiu")
    st, ct, cc, _ = get("/brand/brand.css")
    ok(st == 200 and ct.startswith("text/css") and "utf-8" in ct and cc == "no-cache", "brand.css: 200 text/css, no-cache")
    html = get("/")[3].decode()
    ok(re.search(r'<link rel="stylesheet" href="/brand/[A-Za-z0-9._-]+\.css">', html), "HTML servido liga o stylesheet /brand/*.css")
    ok('<link rel="icon" href="/brand/favicon.png">' in html, "HTML servido liga o favicon")
    st, ct, _, body = get("/brand/logo-acelerai-white-sm.png")
    ok(st == 200 and ct == "image/png" and body[:8] == b"\x89PNG\r\n\x1a\n", "logo pequeno: 200 image/png")
    st, ct, _, body = get("/brand/logo-acelerai-white-sm.png", "HEAD")
    ok(st == 200 and ct == "image/png" and body == b"", "HEAD: 200 sem corpo")
    ok(get("/brand/favicon.png")[0] == 200, "favicon.png: 200")
    for bad in ("/brand/../chat_server.py", "/brand/%2e%2e/chat_server.py", "/brand/%2E%2E%2Fchat_server.py", "/brand/..%2fchat_server.py",
                "/brand/sub/../../chat_server.py", "/brand/%5c..%5cchat_server.py", "/brand/logo.png%00.css", "/brand/x.py", "/brand/chat_server.py",
                "/brand/", "/brand", "/brand/naoexiste.png", "/brand/%2e%2e", "/brand/.."):
        st = get(bad)[0]
        ok(st in (400, 404), f"{bad} -> {st}")
    ok(get("/brand/_link_fora.png")[0] == 404, "link simbólico para fora de chat/brand -> 404")
    for esc in (f"/brand/../{sent_dir.name}/x.png", f"/brand/%2e%2e/{sent_dir.name}/x.png", f"/brand/..%2f{sent_dir.name}%2fx.png",
                f"/brand/%2E%2E%2F{sent_dir.name}%2Fx.png", f"/brand/..%5c{sent_dir.name}%5cx.png"):
        st, _, _, body = get(esc)
        ok(st in (400, 404) and b"SENTINELA" not in body, f"sentinela fora da pasta inacessível: {esc} -> {st}")
    for gone in ("/brand/x.svg", "/brand/x.ico", "/brand/x.woff2"):
        ok(get(gone)[0] == 404, f"{gone} -> 404 (fora da allowlist)")
    ok(get("/brand/logo-acelerai-white-sm.png", "POST")[0] in (404, 501), "POST não é servido")
    print("\nTUDO OK")
finally:
    proc.terminate(); tmp.cleanup(); link.unlink(missing_ok=True); shutil.rmtree(sent_dir, ignore_errors=True)
