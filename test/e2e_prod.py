"""Endurecimento para produção: corpo inválido/gigante, cabeçalhos de segurança, métodos, formato/tamanho de imagem, prazo do pipeline,
job sem batimento e cache de modelos. Servidores próprios (--mock) em portas livres, dados temporários: python3 e2e_prod.py"""
import base64, http.client, json, os, pathlib, socket, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


P1, P2, P3, P4, FC = free_port(), free_port(), free_port(), free_port(), free_port()
tmps = [tempfile.TemporaryDirectory() for _ in range(4)]
D1, D2, D3, D4 = (pathlib.Path(t.name) for t in tmps)
def seed71(data_dir):  # cliente '71' FICTÍCIO criado aqui: o teste nunca lê test/client_71.json nem test/clients do repositório
    d = pathlib.Path(data_dir) / "clients" / "71"; d.mkdir(parents=True, exist_ok=True)
    (d / "client.json").write_text('{"id": 71, "name": "Marca Ficticia 71 (teste)", "sector": "praia ficticia", "palette": ["#0B3C5D"], "cpf": "000.111.222-33"}')
for _d in (D1, D2, D3, D4):
    seed71(_d)
base = {k: v for k, v in os.environ.items() if not k.startswith(("CHAT_", "VERCEL", "JOBS_INLINE"))}


def spawn(port, data, **env):
    return subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(port), "--mock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**base, "CHAT_DATA_DIR": str(data), "OPENAI_API_KEY": "fake", **env})


# Commons FALSO: devolve miniaturas no host real do Wikimedia, como a busca de verdade
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeCommons(BaseHTTPRequestHandler):
    def do_GET(self):
        pages = {"1": {"index": 1, "title": "File:Logo Teste.png", "imageinfo": [{"thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Logo_Teste.png/1024px-Logo_Teste.png",
                                                                                  "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Logo_Teste.png", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Logo_Teste.png",
                                                                                  "mime": "image/png", "width": 512, "height": 512}]},
                 "2": {"index": 2, "title": "File:Outro.svg", "imageinfo": [{"url": "https://upload.wikimedia.org/wikipedia/commons/c/cd/Outro.svg", "mime": "image/svg+xml"}]}}
        data = json.dumps({"query": {"pages": pages}}).encode(); self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *a): pass


fc = ThreadingHTTPServer(("127.0.0.1", FC), FakeCommons); threading.Thread(target=fc.serve_forever, daemon=True).start()
procs = [spawn(P1, D1, CHAT_MAX_BODY="200000", CHAT_MAX_RESPONSE="50000", COMMONS_API=f"http://127.0.0.1:{FC}/w/api.php", WEB_ALLOW_LOCAL="1"),
         spawn(P2, D2, JOBS_INLINE="1", CHAT_DEADLINE_S="14", CHAT_TEST_SLOW="5", CHAT_TEST_REJECT="1", CHAT_DEADLINE_MARGIN="1", CHAT_MIN_GEN_S="1"),
         spawn(P3, D3, CHAT_DEADLINE_S="3", CHAT_MIN_GEN_S="30"),
         spawn(P4, D4, JOBS_INLINE="1", CHAT_DEADLINE_S="8", CHAT_TEST_SLOW="9", CHAT_DEADLINE_MARGIN="1", CHAT_MIN_GEN_S="1")]


def raw(port, method, path, body=None, headers=None, send_body=True):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.putrequest(method, path)
    for k, v in (headers or {}).items():
        c.putheader(k, v)
    c.endheaders(body if (body is not None and send_body) else None)
    r = c.getresponse(); data = r.read()
    return r.status, dict(r.getheaders()), data


def post(port, path, body=None, **kw):
    data = json.dumps(body).encode() if not isinstance(body, bytes) else body
    h = {"Content-Type": "application/json", "Content-Length": str(len(data)), **kw.pop("headers", {})}
    return raw(port, "POST", path, data, h, **kw)


def j(resp): return json.loads(resp[2]) if resp[2] else None
ok = lambda c, m: print(("OK   " if c else "FALHA"), m) or (c or sys.exit(1))
events = lambda d: [json.loads(l) for l in (d / "logs" / "events.jsonl").read_text().splitlines()] if (d / "logs" / "events.jsonl").exists() else []

try:
    for port in (P1, P2, P3, P4):
        for _ in range(50):
            try: raw(port, "GET", "/api/state"); break
            except Exception: time.sleep(0.2)
        else: sys.exit("o servidor do chat não subiu")
    os.environ["CHAT_DATA_DIR"] = str(D1)  # o import em processo também grava só no diretório temporário
    import chat_server as cs  # em processo: funções puras e o cache de modelos
    vj = json.loads((ROOT.parent / "vercel.json").read_text())

    # ================= P1: corpo de POST =================
    n0 = len(events(D1))
    for label, body in (("JSON quebrado", b"{nao e json"), ("lista", b"[]"), ("string", b'"x"'), ("número", b"5"), ("UTF-8 inválido", b"\xff\xfe\x00{")):
        r = post(P1, "/api/conv", body)
        ok(r[0] == 400 and j(r) == {"error": "Corpo da requisição inválido."}, f"{label}: 400 sem error_detail")
    ok(len(events(D1)) == n0, "corpo malformado não grava evento por requisição (só contador)")
    for label, hdr in (("ausente", {}), ("negativo", {"Content-Length": "-5"}), ("inválido", {"Content-Length": "abc"})):
        c = http.client.HTTPConnection("127.0.0.1", P1, timeout=10); c.putrequest("POST", "/api/conv")
        for k, v in hdr.items(): c.putheader(k, v)
        c.endheaders(); r = c.getresponse(); body = json.loads(r.read())
        ok(r.status == 400 and body == {"error": "Corpo da requisição inválido."}, f"Content-Length {label}: 400")
    r = post(P1, "/api/conv", b"x", headers={"Content-Length": "300000"}, send_body=False)
    ok(r[0] == 413 and j(r)["error"] == "Arquivo grande demais para enviar (máx. ~4 MB). Reduza a imagem.", "Content-Length declarado acima do teto: 413 amigável, sem ler o corpo")
    ok(post(P1, "/api/conv", {"client": "71", "conv": "x"})[0] == 200, "corpo normal segue funcionando")
    ok(post(P1, "/api/job", {"id": "abc", "since": "abc"})[0] == 400, "valor inválido (since) -> 400, não 500")
    ok(post(P1, "/api/asset", {"client": "71", "kind": "referencia", "name": "a.png", "mime": "image/png", "b64": "!!não-é-base64!!"})[0] == 400, "b64 inválido -> 400, não 500")
    ok(post(P1, "/api/job", {"id": ["x"]})[0] == 404, "id de job de tipo errado -> 404")
    # error_detail só fora da Vercel / com CHAT_DEBUG
    os.environ.pop("VERCEL", None); os.environ.pop("CHAT_DEBUG", None)
    ok(cs.visible_detail("ValueError: x") == "ValueError: x", "fora da Vercel o detalhe técnico aparece")
    os.environ["VERCEL"] = "1"
    ok(cs.visible_detail("ValueError: x") is None, "na Vercel (VERCEL=1) o detalhe NÃO aparece")
    os.environ["CHAT_DEBUG"] = "1"
    ok(cs.visible_detail("ValueError: x") == "ValueError: x", "na Vercel com CHAT_DEBUG=1 aparece")
    os.environ.pop("VERCEL"); os.environ.pop("CHAT_DEBUG")
    os.environ["VERCEL"] = "1"; ok(cs.max_body() == 4_400_000, "teto de corpo na Vercel: 4,4 MB (abaixo dos 4,5 MB da plataforma)"); os.environ.pop("VERCEL")

    # ================= P2: cabeçalhos de segurança =================
    want = {"Content-Security-Policy": None, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=()"}
    vh = {h["key"]: h["value"] for h in vj["headers"][0]["headers"]}
    ok(vh == cs.SECURITY_HEADERS, "vercel.json e o servidor local usam exatamente os mesmos cabeçalhos")
    ok("'unsafe-eval'" not in vh["Content-Security-Policy"] and "frame-ancestors 'none'" in vh["Content-Security-Policy"] and "connect-src 'self'" in vh["Content-Security-Policy"], "CSP: sem unsafe-eval, frame-ancestors none, connect-src self")
    (D1 / "chat_out" / "_geral").mkdir(parents=True, exist_ok=True)
    (D1 / "chat_out" / "_geral" / "pq.png").write_bytes(b"\x89PNG\r\n\x1a\nxx")
    for path in ("/", "/brand/brand.css", "/api/state", "/files/_geral/out/pq.png", "/api/naoexiste", "/brand/../x"):
        st, h, _ = raw(P1, "GET", path)
        miss = [k for k in want if h.get(k) != (vh[k] if want[k] is None else want[k])]
        ok(not miss, f"GET {path} ({st}): cabeçalhos de segurança completos")
    st, h, _ = post(P1, "/api/conv", {"client": "71", "conv": "x"})[:3]
    ok(all(h.get(k) == vh[k] for k in want), "POST: cabeçalhos de segurança")

    # ================= P9: cache de /files/* =================
    imm = "private, max-age=31536000, immutable"
    for path in ("/files/_geral/out/pq.png",):
        ok(raw(P1, "GET", path)[1].get("Cache-Control") == imm, f"{path}: Cache-Control imutável e private")
    r = post(P1, "/api/asset", {"client": "_geral", "conv": "c1", "kind": "referencia", "name": "a.png", "mime": "image/png", "b64": base64.b64encode(b"\x89PNG\r\n\x1a\nxx").decode()})
    a1 = j(r)["asset"]
    ok(raw(P1, "GET", a1["url"])[1].get("Cache-Control") == imm, "anexo: Cache-Control imutável e private")
    post(P1, "/api/asset/delete", {"client": "_geral", "conv": "c1", "id": a1["id"]})
    a2 = j(post(P1, "/api/asset", {"client": "_geral", "conv": "c1", "kind": "referencia", "name": "a.png", "mime": "image/png", "b64": base64.b64encode(b"\x89PNG\r\n\x1a\nyy").decode()}))["asset"]
    ok(a2["id"] != a1["id"] and a2["url"] != a1["url"], "anexo apagado e recriado ganha id/URL novos (nunca reutiliza o nome em cache)")
    for path in ("/", "/api/state", "/api/naoexiste", "/files/_geral/out/naoexiste.png"):
        ok(raw(P1, "GET", path)[1].get("Cache-Control") == "no-store", f"{path}: continua no-store")
    ok(post(P1, "/api/conv", {"client": "71", "conv": "x"})[1].get("Cache-Control") == "no-store" and raw(P1, "GET", "/brand/brand.css")[1].get("Cache-Control") == "no-cache", "POST /api/* no-store; /brand no-cache")

    # ================= B1: a CSP cobre as miniaturas da busca na web =================
    import urllib.parse as up
    srch = j(post(P1, "/api/websearch", {"q": "logo teste"}))
    hosts = {up.urlparse(r["url"]).scheme + "://" + up.urlparse(r["url"]).hostname for r in srch["results"]}
    img_src = [t for d in vh["Content-Security-Policy"].split(";") if d.strip().startswith("img-src") for t in d.split()[1:]]
    ok(hosts == {"https://upload.wikimedia.org"} and len(srch["results"]) == 2, f"busca devolve miniaturas do Wikimedia: {hosts}")
    ok(all(h in img_src for h in hosts), "CSP img-src cobre o host de cada miniatura devolvida pela busca")
    ok("img-src" in cs.SECURITY_HEADERS["Content-Security-Policy"] and "https://upload.wikimedia.org" in cs.SECURITY_HEADERS["Content-Security-Policy"], "o servidor local também")
    idx = open(ROOT / "chat" / "index.html", encoding="utf-8").read()
    import re as _re
    ext_hosts = set(_re.findall(r"""(?:src|href)=["'](https?://[^"'$\s]+)""", idx)) | set(_re.findall(r"url\((https?://[^)'\"]+)", idx))
    ok(not [h for h in ext_hosts if "w3.org" not in h], f"o front não referencia outro host externo de imagem/estilo ({sorted(ext_hosts)})")

    # ================= D1: timeout de CADA chamada respeita o prazo =================
    t = time.time()
    st, h, body = post(P4, "/api/chat", {"client": "71", "conv": "to1", "text": "banner lento", "size": "1024x1024"})
    r = json.loads(body); dur = time.time() - t
    ok(r["status"] == "error" and r["error"] == "A geração demorou demais. Tente de novo." and dur < 9.3, f"chamada lenta é cortada pelo prazo, não passa dele ({dur:.1f}s < 9,8s sem corte)")
    ok(any(e["kind"] == "timeout" and e["etapa"] == "imagem" and e["s"] <= 7.1 for e in events(D4)), "timeout da imagem = prazo restante menos a margem")
    os.environ.pop("CHAT_MIN_GEN_S", None); os.environ["VERCEL"] = "1"; ok(cs.min_gen_s() == 90.0, "Vercel: mínimo de 90 s para começar a 1ª imagem"); os.environ.pop("VERCEL"); ok(cs.min_gen_s() == 45.0, "local: 45 s")

    # ================= P3: métodos =================
    for m in ("OPTIONS", "PUT", "DELETE", "PATCH"):
        for path in ("/api/state", "/", "/api/chat"):
            st, h, body = raw(P1, m, path, b"" if m != "OPTIONS" else None, {"Content-Length": "0"} if m != "OPTIONS" else {})
            ok(st == 405 and h.get("Allow") == "GET, HEAD, POST" and json.loads(body) == {"error": "Método não permitido."} and b"<html" not in body.lower(), f"{m} {path} -> 405 JSON com Allow")
    st, h, body = raw(P1, "TRACE", "/api/state")
    ok(st == 501 and body.startswith(b"{") and b"<html" not in body.lower(), "método desconhecido (TRACE): JSON, não HTML do stdlib")

    # ================= P5/P6: formato e tamanho da imagem =================
    for k in ("CHAT_IMAGE_FORMAT",): os.environ.pop(k, None)
    ok(cs.pick_output_format("1536x1024", "high") == ("webp", 85) and cs.pick_output_format("1024x1536", "high")[0] == "webp", "1536x1024 em qualidade alta: pede webp (PNG estouraria os 4,5 MB)")
    ok(cs.pick_output_format("1024x1024", "low") == ("png", None) and cs.pick_output_format("1024x1024", "medium")[0] == "png", "tamanho/qualidade menores: continua PNG")
    ok(cs.pick_output_format("1536x1024", "high", has_mask=True) == ("png", None), "edição localizada (máscara) fica PNG")
    ok(cs.pick_output_format("auto", "high")[0] == "png", "size auto não quebra")
    os.environ["CHAT_IMAGE_FORMAT"] = "jpeg"; ok(cs.pick_output_format("1024x1024", "low") == ("jpeg", 85), "CHAT_IMAGE_FORMAT força o formato"); os.environ.pop("CHAT_IMAGE_FORMAT")
    ok(cs.out_mime("a/b.webp") == "image/webp" and cs.out_mime("x.jpg") == "image/jpeg" and cs.out_mime("x.png") == "image/png" and cs.out_mime("x.svg") == "image/svg+xml", "a imagem anterior (edição) é lida com o mime do formato dela")
    sent = {}
    def fake_post(path, body): sent.update(body); return {"data": [{"b64_json": base64.b64encode(b"RIFF\x10\x00\x00\x00WEBPVP8 ").decode()}]}
    cs.MOCK = False; real = cs.ui.openai_post; cs.ui.openai_post = fake_post
    try:
        b64, ext = cs.make_image("p", "1536x1024", "high", [], "gpt-image-1")
        ok(ext == "webp" and sent.get("output_format") == "webp" and sent.get("output_compression") == 85, "make_image: pede webp e a extensão vem dos bytes recebidos")
        sent.clear(); b64, ext = cs.make_image("p", "1024x1024", "low", [], "gpt-image-1")
        ok(ext == "webp" and "output_format" not in sent, "tamanho pequeno: não pede formato; a extensão continua vindo dos bytes (aqui webp)")
    finally:
        cs.ui.openai_post = real; cs.MOCK = True
    (D1 / "chat_out" / "_geral" / "g.webp").write_bytes(b"RIFF\x10\x00\x00\x00WEBPVP8 ")
    (D1 / "chat_out" / "_geral" / "g.jpg").write_bytes(b"\xff\xd8\xff\xe0abc")
    st, h, _ = raw(P1, "GET", "/files/_geral/out/g.webp"); ok(st == 200 and h["Content-Type"] == "image/webp", "/files serve webp com o content-type certo")
    st, h, _ = raw(P1, "GET", "/files/_geral/out/g.jpg"); ok(st == 200 and h["Content-Type"] == "image/jpeg", "/files serve jpeg com o content-type certo")
    (D1 / "chat_out" / "_geral" / "grande.png").write_bytes(b"\x89PNG\r\n\x1a\n" + os.urandom(120000))
    st, h, body = raw(P1, "GET", "/files/_geral/out/grande.png")
    ok(st in (200, 413) and b"<html" not in body[:200].lower() and (h.get("X-Image-Reduced") == "1" if st == 200 else h.get("X-Image-Too-Large") == "1" and "grande demais" in json.loads(body)["error"]),
       f"imagem acima do limite de resposta: versão reduzida ou 413 em JSON, nunca 500/HTML ({st})")
    ok(raw(P1, "GET", "/files/_geral/out/pq.png")[0] == 200, "imagem pequena segue 200")

    # ================= P7: prazo do pipeline =================
    t = time.time()
    st, h, body = post(P2, "/api/chat", {"client": "71", "conv": "dl1", "text": "banner de teste", "size": "1024x1024", "mode": "livre"})
    r = json.loads(body); dur = time.time() - t
    msg = r.get("message") or {}
    ok(st == 200 and r["status"] == "done" and msg.get("kind") == "image" and msg.get("generations") == 1, f"prazo: entrega a imagem já gerada, job concluído ({dur:.0f}s, gerações {msg.get('generations')})")
    ok("Entreguei a melhor versão que deu tempo de fazer." in msg.get("avisos", []), f"prazo: aviso amigável ao usuário ({msg.get('avisos')} | passos: {[x['text'][:50] for x in r.get('steps', [])] if 'steps' in r else [e.get('text', e['kind'])[:50] for e in events(D2)][-14:]})")
    ok(any(e["kind"] == "prazo" and e.get("etapa") == "antes da correção" for e in events(D2)), "prazo: registrado no log")
    ok(all(e["s"] <= e["restante"] for e in events(D2) if e["kind"] == "timeout") and any(e["kind"] == "timeout" for e in events(D2)), "cada chamada (imagem e critic) tem timeout <= tempo restante do prazo")
    st, h, body = post(P3, "/api/chat", {"client": "71", "conv": "dl2", "text": "banner de teste", "size": "1024x1024"})
    jid = json.loads(body)["job"]
    for _ in range(50):
        time.sleep(0.3); jr = j(post(P3, "/api/job", {"id": jid, "since": 0}))
        if jr["status"] != "running": break
    ok(jr["status"] == "error" and jr["error"] == "A geração demorou demais. Tente de novo.", "nem a 1ª imagem cabe no prazo: erro neutro (a tela oferece Tentar de novo)")
    ok(any(e["kind"] == "prazo" and e.get("etapa") == "antes da 1ª imagem" for e in events(D3)), "...e fica no log")
    cs.os.environ.pop("CHAT_MAX_CYCLES", None); ok(cs.max_cycles() == cs.critic.MAX_CYCLES, "local: MAX_CYCLES da rubrica")
    os.environ["VERCEL"] = "1"; ok(cs.max_cycles() == 1 and cs.deadline_s() == 270.0, "Vercel: 1 correção e prazo de 270 s por padrão"); os.environ["CHAT_MAX_CYCLES"] = "2"
    ok(cs.max_cycles() == 2, "CHAT_MAX_CYCLES sobrescreve"); os.environ.pop("VERCEL"); os.environ.pop("CHAT_MAX_CYCLES")
    # job sem batimento
    (D2 / "jobs").mkdir(parents=True, exist_ok=True)
    now = time.time()
    (D2 / "jobs" / "aaaaaaaaaa.json").write_text(json.dumps({"id": "aaaaaaaaaa", "status": "running", "steps": [], "message": None, "error": None, "t0": now - 1000, "hb": now - 1000}))
    (D2 / "jobs" / "bbbbbbbbbb.json").write_text(json.dumps({"id": "bbbbbbbbbb", "status": "running", "steps": [], "message": None, "error": None, "t0": now - 30, "hb": now - 5}))
    r = j(post(P2, "/api/job", {"id": "aaaaaaaaaa"}))
    ok(r["status"] == "error" and r["error"] == "A geração demorou demais. Tente de novo.", "job running sem batimento além de prazo+60 s: erro neutro, não 'running' eterno")
    ok(j(post(P2, "/api/job", {"id": "bbbbbbbbbb"}))["status"] == "running", "job com batimento recente continua running")

    # ================= P8: cache da lista de modelos =================
    calls = []
    def fake_get(path, timeout=30): calls.append(path); return {"data": [{"id": "gpt-image-2.5-sunburst"}, {"id": "gpt-5.5"}]}
    cs.MOCK = False; os.environ["OPENAI_API_KEY"] = "sk-" + "a" * 30; realg = cs.openai_get; cs.openai_get = fake_get
    cs.MODELS_CACHE.update(t=0.0, key=None, val=None)
    try:
        a = cs.api_models({}); b = cs.api_models({})
        ok(len(calls) == 1 and a == b and a["ok"], "api_models: a 2ª chamada vem do cache (1 chamada à OpenAI)")
        cs.MODELS_TTL = 0.05; time.sleep(0.1); cs.api_models({})
        ok(len(calls) == 2, "TTL vencido: consulta de novo"); cs.MODELS_TTL = 600.0
        n = len(calls); cs.api_setkey({"key": "sk-" + "b" * 30}); n2 = len(calls)
        cs.api_models({})
        ok(len(calls) == n2 + 1, "trocar a chave (setkey) invalida o cache")
        os.environ["OPENAI_API_KEY"] = "sk-" + "c" * 30; cs.api_models({})
        ok(len(calls) == n2 + 2, "chave diferente nunca usa o cache de outra")
    finally:
        cs.openai_get = realg; cs.MOCK = True
    print("\nTUDO OK")
finally:
    for p in procs: p.terminate()
    fc.shutdown()
    for t in tmps: t.cleanup()
