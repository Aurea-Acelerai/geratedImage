"""Regressão de projetos (pastas de conversas), lista global, cliente automático e provedor de banco (FAKE local).
Sobe o chat (--mock) e um Supabase falso em portas livres, com dados temporários e fictícios (C12): python3 e2e_projects.py"""
import http.client, json, os, pathlib, re, socket, subprocess, sys, tempfile, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import client_provider as cp
import critic, run_comparison as rc

KEY = "chave-de-leitura-falsa-9f3a"
KEY2 = "segredo-da-edge-falso-77c1"
CPF, MAIL, TEL = "123.456.789-09", "dona.boreal@example.com", "(11) 91234-5678"
A, B, D, E = ("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "44444444-4444-4444-8444-444444444444",
              "55555555-5555-4555-8555-555555555555")
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
PII = dict(cpf=CPF, email=MAIL, telefone=TEL, endereco_completo="Rua Falsa 1", valortotalcompra=9999)
# o que o banco devolve (a view já só traz clientes ELEGÍVEIS; o inelegível "Loja Inelegível" simplesmente não existe aqui).
# As linhas trazem colunas de PII de propósito: o provedor tem que descartá-las.
CLIENTES = {
    A: dict(cliente_id=A, compra_id="aaaaaaa2-0000-4000-8000-000000000002", nome_exibicao="Estúdio Boreal", nome_origem="brand_display_name", pessoa_fisica=False, setor="arquitetura",
            subsegmento="residencial", paleta=["#222222", "#ffffff"], tipografia="Inter", tom="acolhedor", publico_alvo="famílias", descricao_marca="feito com calma",
            site_url="https://exemplo.test", instagram_handle="boreal", tem_identidade=True, tone_local_wins=None, **PII),
    B: dict(cliente_id=B, compra_id="bbbbbbb1-0000-4000-8000-000000000001", nome_exibicao="Padaria Sol", nome_origem="nome_fantasia", pessoa_fisica=False, setor="alimentação",
            subsegmento=None, paleta=["#ffaa00"], tipografia=None, tom=None, publico_alvo=None, descricao_marca=None, site_url=None, instagram_handle=None, tem_identidade=True, **PII),
    D: dict(cliente_id=D, compra_id="ddddddd1-0000-4000-8000-000000000001", nome_exibicao="Maria Souza", nome_origem="nome", pessoa_fisica=True, setor="consultoria",
            subsegmento=None, paleta=["#123456"], tipografia=None, tom=None, publico_alvo=None, descricao_marca=None, site_url=None, instagram_handle=None, tem_identidade=True, **PII),
    E: dict(cliente_id=E, compra_id="eeeeeee1-0000-4000-8000-000000000001", nome_exibicao="Vazia Sem Marca", nome_origem="nome_fantasia", pessoa_fisica=False, setor="varejo",
            subsegmento=None, paleta=None, tipografia=None, tom=None, publico_alvo=None, descricao_marca=None, site_url=None, instagram_handle=None, tem_identidade=False, **PII),
}
LOGOS = {A: [dict(item_id="l0000001-0000-4000-8000-000000000001", storage_path=f"{A}/logo.png", mime_type="image/png", ativo=True, ordem=0)],
         B: [dict(item_id="l0000002-0000-4000-8000-000000000002", storage_path=f"{B}/logo.svg", mime_type="image/svg+xml", ativo=True, ordem=0)]}
FAKE = {"down": False, "redirect": None, "log": []}
ATTACK = []  # o que o "host de destino" de um redirecionamento recebeu


class FakeSupabase(BaseHTTPRequestHandler):
    """Imita o contrato chat_design: funções STABLE por GET (PostgREST), a view de logos e a Edge Function que devolve bytes."""
    def _go(self):
        u = urllib.parse.urlparse(self.path); q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n) if n else b""
        FAKE["log"].append((self.command, u.path, q, self.headers.get("apikey")))
        if FAKE["redirect"]:
            self.send_response(302); self.send_header("Location", FAKE["redirect"] + "/roubo"); self.send_header("Content-Length", "0"); self.end_headers(); return
        if u.path == "/functions/v1/chat-design-asset":
            if self.headers.get("x-chat-design-key") != KEY2 or self.command != "POST":
                return self._out(401, {"message": "no"})
            path = json.loads(body)["storage_path"]
            if path.endswith("/falso.png"):  # HTML rotulado como PNG
                return self._raw(200, b"<html><script>alert(1)</script></html>", "image/png")
            return self._raw(200, b"<svg/>" if path.endswith(".svg") else PNG, "image/svg+xml" if path.endswith(".svg") else "image/png")
        if self.headers.get("apikey") != KEY or self.headers.get("Accept-Profile") != "chat_design" or self.command != "GET":
            return self._out(401, {"message": "no"})
        if FAKE["down"]:
            return self._out(503, {"message": "down"})
        if u.path == "/rest/v1/rpc/buscar_cliente_chat":
            term = q.get("q", "").lower()
            rows = [{k: r[k] for k in ("cliente_id", "nome_exibicao", "nome_origem", "pessoa_fisica", "setor", "tem_identidade")} for r in CLIENTES.values() if term in r["nome_exibicao"].lower()]
            return self._out(200, rows[:min(int(q.get("limite", 20)), 50)])
        if u.path == "/rest/v1/rpc/carregar_cliente_chat":
            return self._out(200, [CLIENTES[q["p_cliente_id"]]] if q.get("p_cliente_id") in CLIENTES else [])
        if u.path == "/rest/v1/vw_chat_logos_cliente":
            return self._out(200, LOGOS.get(q.get("cliente_id", "").removeprefix("eq."), []))
        self._out(404, {})

    do_GET = do_POST = do_DELETE = do_PUT = do_PATCH = _go

    def _raw(self, code, data, ctype):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def _out(self, code, body): self._raw(code, json.dumps(body).encode(), "application/json")

    def log_message(self, *a): pass


class Attacker(BaseHTTPRequestHandler):
    def _go(self):
        ATTACK.append({k.lower(): v for k, v in self.headers.items()}); self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"[]")
    do_GET = do_POST = _go
    def log_message(self, *a): pass


def seed71(data_dir):
    """Cliente '71' do teste, FICTÍCIO e criado aqui (hermético: nunca lê test/client_71.json nem test/clients do repositório).
    A PII fictícia é proposital: serve para provar que ela não chega ao prompt."""
    d = pathlib.Path(data_dir) / "clients" / "71"; d.mkdir(parents=True, exist_ok=True)
    (d / "client.json").write_text(json.dumps({"id": 71, "name": "Marca Fictícia 71 (teste)", "sector": "praia fictícia", "audience": "publico ficticio setenta",
                                               "tone": "tom ficticio", "palette": ["#0B3C5D", "#F2A541"], "typography": "tipografia ficticia", "image_style": "estilo ficticio de teste",
                                               "approved_references": [], "deliveries_last_30d": 3, "cpf": "000.111.222-33", "email": "dono71@example.com", "observacoes": "segredo-do-71"}))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


FPORT, PORT, PORT2, PORT3 = free_port(), free_port(), free_port(), free_port()
fake = ThreadingHTTPServer(("127.0.0.1", FPORT), FakeSupabase); threading.Thread(target=fake.serve_forever, daemon=True).start()
APORT = free_port(); attacker = ThreadingHTTPServer(("127.0.0.1", APORT), Attacker); threading.Thread(target=attacker.serve_forever, daemon=True).start()
tmp = tempfile.TemporaryDirectory(); DATA = pathlib.Path(tmp.name); tmp2 = tempfile.TemporaryDirectory(); tmp3 = tempfile.TemporaryDirectory()
seed71(DATA); seed71(tmp2.name); seed71(tmp3.name)
base_env = {k: v for k, v in os.environ.items() if not k.startswith(("SUPABASE_", "CHAT_DB", "CHAT_DESIGN"))}
procs = [subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(PORT), "--mock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          env={**base_env, "CHAT_DATA_DIR": tmp.name, "OPENAI_API_KEY": "fake", "SUPABASE_URL": f"http://127.0.0.1:{FPORT}", "SUPABASE_READ_KEY": KEY, "CHAT_DB_ENABLED": "1", "CHAT_DESIGN_ASSET_KEY": KEY2, "CHAT_TEST_LOG_PROMPT": "1"}),
         subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(PORT2), "--mock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          env={**base_env, "CHAT_DATA_DIR": tmp2.name, "OPENAI_API_KEY": "fake"}),
         subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(PORT3), "--mock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          env={**base_env, "CHAT_DATA_DIR": tmp3.name, "OPENAI_API_KEY": "fake", "SUPABASE_URL": f"http://127.0.0.1:{FPORT}", "SUPABASE_READ_KEY": KEY})]


def req(method, path, body=None, port=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port or PORT, timeout=15)
    c.request(method, path, None if body is None else json.dumps(body), {"Content-Type": "application/json", **(headers or {})})
    r = c.getresponse(); raw = r.read()
    return r.status, (json.loads(raw) if raw else None)


def chat(text, conv=None, scope=None, port=None, **extra):
    body = {"text": text, "size": "1024x1024", **extra}
    if conv: body["conv"] = conv
    if scope: body["scope"] = scope
    st, j = req("POST", "/api/chat", body, port)
    if st != 200: return st, j, []
    steps, since = [], 0
    for _ in range(100):
        time.sleep(0.3); _, p = req("POST", "/api/job", {"id": j["job"], "since": since}, port); steps += [x["text"] for x in p["steps"]]; since = p["next"]
        if p["status"] != "running": return 200, p, steps
    sys.exit("job não terminou")


def fetch_status(path):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10); c.request("GET", path); return c.getresponse().status
def convs(q="", port=None): return req("GET", "/api/convs" + q, None, port)[1]
def item(cid, scope=None, q=""): return next((c for c in convs(q)["convs"] if c["id"] == cid and (scope is None or c["scope"] == scope)), None)
def state(cid, scope): return req("POST", "/api/conv", {"scope": scope, "conv": cid})[1]
def save_client(cid, **kw): return req("POST", "/api/client/save", {"id": cid, "client": {"id": cid, **kw}})
ok = lambda c, m: print(("OK   " if c else "FALHA"), m) or (c or sys.exit(1))

try:
    for port in (PORT, PORT2, PORT3):
        for _ in range(50):
            try: req("GET", "/api/state", None, port); break
            except Exception: time.sleep(0.2)
        else: sys.exit("o servidor do chat não subiu")

    # ================= unidade: lista permitida e casamento =================
    leaked = cp.safe_context({"name": "Marca X", "sector": "moda", "palette": ["#fff", "vermelho"], **PII, "cnpj": "12.345.678/0001-99", "observacoes": "ligue 11 99999-8888", "tone": f"fale com {MAIL}"})
    ok(set(leaked) <= set(cp.CONTEXT_FIELDS) and not any(k in leaked for k in ("cpf", "email", "telefone", "endereco_completo", "valortotalcompra", "cnpj", "observacoes")), "allowlist: CPF, e-mail, telefone, endereço, financeiro e texto livre ficam de fora")
    ok(leaked["palette"] == ["#fff"] and MAIL not in json.dumps(leaked) and "[dado pessoal removido]" in leaked["tone"], "allowlist: paleta validada e e-mail dentro de campo permitido é removido")
    ok(cp.safe_context("x") == {} and cp.safe_context({"name": ["a"]}) == {"name": "['a']"}, "allowlist: entrada estranha não derruba")

    for frase in ("ligue (11) 91234-5678", "ligue (11)91234-5678", "ligue 11 3456-7890", "ligue 11912345678", "ligue +55 11 91234-5678", "CEP 01310-100", f"fale com {MAIL}", f"CPF {CPF}", "CNPJ 12.345.678/0001-99"):
        for campo in ("brand_description", "tone"):
            out = cp.safe_context({campo: frase})[campo]
            ok("[dado pessoal removido]" in out and not re.search(r"91234|3456-7890|11912345678|01310|@|123\.456|12\.345", out), f"PII em campo permitido ({campo}) sai redigida: {frase!r}")
    ok(cp.safe_context({"tone": "calmo e solar, desde 2024"})["tone"] == "calmo e solar, desde 2024", "texto normal não é redigido")
    # o prompt (run_comparison) e o critic aplicam a lista permitida SOZINHOS, mesmo recebendo o JSON cru
    raw = {"name": "Marca Y", "palette": ["#fff"], "cpf": CPF, "email": MAIL, "telefone": TEL, "observacoes": "segredo-interno", "tone": "ligue (11) 91234-5678"}
    pr_txt = rc.mode_instructions(raw, "marca")
    ok("Marca Y" in pr_txt and not any(x in pr_txt for x in (CPF, MAIL, TEL, "segredo-interno", "91234", '"cpf"')), "run_comparison.mode_instructions: campo fora da lista não chega ao prompt")
    seen = {}
    def fake_vlm(system, user, images): seen["u"] = user; return json.dumps({"scores": {"a": 1}})
    critic.review(fake_vlm, "briefing", raw, "pedido", [])
    ok("Marca Y" in seen["u"] and not any(x in seen["u"] for x in (CPF, MAIL, TEL, "segredo-interno", "91234")), "critic.review: campo fora da lista não chega ao prompt do critic")
    # A2: host esperado, sem credencial na URL, http só para localhost
    def env_prov(url, **env):
        old = {k: os.environ.get(k) for k in ("SUPABASE_URL", "SUPABASE_READ_KEY", "CHAT_DB_ENABLED", "CHAT_DB_HOST")}
        os.environ.update({"SUPABASE_URL": url, "SUPABASE_READ_KEY": "k", "CHAT_DB_ENABLED": "1", **env})
        for k in ("CHAT_DB_HOST",):
            if k not in env: os.environ.pop(k, None)
        try: return cp.SupabaseClientProvider.from_env()
        finally:
            for k, v in old.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v
    ok(env_prov("https://abc.supabase.co") is not None and env_prov("https://db.corp.test", CHAT_DB_HOST="db.corp.test") is not None and env_prov("http://127.0.0.1:9") is not None, "from_env: .supabase.co, CHAT_DB_HOST e localhost (http) são aceitos")
    for bad in ("https://evil.example", "https://abc.supabase.co.evil.example", "http://abc.supabase.co", "http://evil.example", "https://user:pw@abc.supabase.co", "https://abc.supabase.co?x=1", "ftp://abc.supabase.co", "https://notsupabase.co"):
        ok(env_prov(bad) is None, f"from_env recusa {bad}")
    ok(env_prov("https://abc.supabase.co", CHAT_DB_HOST="outro.test") is None, "CHAT_DB_HOST definido: só esse host vale")

    # ================= conversas: escopo neutro, antigas e lista global =================
    st, p, steps = chat("um banner de natal sem cliente", conv="g1")
    ok(st == 200 and p["status"] == "done", "conversa sem cliente (escopo neutro) roda")
    g = item("g1")
    ok(g and g["scope"] == "_geral" and g["client"] is None and g["client_name"] is None and g["project"] is None, "sem cliente: scope _geral, client/client_name/project nulos")
    ok((DATA / "conversations" / "_geral" / "g1.json").exists() and any((DATA / "chat_out" / "_geral").glob("*")), "gravada em conversations/_geral e imagem em chat_out/_geral")
    st, p, _ = chat("pedido da conversa antiga", conv="leg1", client="71")
    ok(st == 200 and p["status"] == "done" and (DATA / "conversations" / "71" / "leg1.json").exists(), "fluxo antigo (client=71) segue funcionando, na pasta do cliente")
    l1 = item("leg1")
    ok(l1["scope"] == "71" and l1["client"] == "71" and l1["client_name"].startswith("Marca Fictícia 71"), "conversa antiga: scope=client=71 e nome do cliente")
    old = {"id": "antiga", "client": "71", "created": "2026-01-01 10:00:00", "turns": [{"n": 1, "t": "10:00:00", "request": "peça de 2026", "resolved": "peça de 2026", "intent": "new"}], "carry": [], "files": []}
    (DATA / "conversations" / "71" / "antiga.json").write_text(json.dumps(old))
    ok(item("antiga")["title"] == "peça de 2026" and state("antiga", "71")["client"]["id"] == "71", "arquivo no formato antigo (sem scope/project) aparece e abre")
    ok(req("POST", "/api/conv", {"client": "71", "conv": "antiga"})[1]["turns"][0]["request"] == "peça de 2026", "{client, conv} continua abrindo conversa antiga")
    ok({c["id"] for c in convs("?client=71")["convs"]} >= {"leg1", "antiga"} and all(c["scope"] == "71" for c in convs("?client=71")["convs"]), "?client= filtra por pasta, como antes")
    ok("g1" in {c["id"] for c in convs("?scope=_geral")["convs"]} and "leg1" not in {c["id"] for c in convs("?scope=_geral")["convs"]}, "?scope=_geral filtra o escopo neutro")
    chat("mesmo id em outra pasta", conv="leg1", scope="_geral")
    ok(item("leg1", "_geral") and item("leg1", "71"), "mesmo id em duas pastas: os dois aparecem, com scope diferente")
    ok(req("POST", "/api/conv/rename", {"scope": "_geral", "conv": "leg1", "title": "só a geral"})[0] == 200 and item("leg1", "71")["title"] != "só a geral" and item("leg1", "_geral")["title"] == "só a geral", "rename por {scope, conv} mexe só na pasta indicada")
    ok(req("POST", "/api/conv/delete", {"scope": "_geral", "conv": "leg1"})[0] == 200 and item("leg1", "71") and not item("leg1", "_geral"), "delete por {scope, conv} só apaga a da pasta indicada")
    ok(req("POST", "/api/conv/rename", {"client": "71", "conv": "antiga", "title": "renomeada"})[0] == 200, "{client, conv} continua valendo em rename")

    # ================= projetos =================
    st, pr = req("POST", "/api/project", {"name": "  Campanhas  "})
    ok(st == 200 and pr["name"] == "Campanhas" and re.fullmatch(r"p[0-9a-f]{8}", pr["id"]), f"criar projeto: {pr}")
    P1 = pr["id"]
    st, d = req("POST", "/api/project", {"name": "campanhas"})
    ok(st == 200 and d["name"] == "campanhas (2)" and d["id"] != P1, "nome duplicado (sem caixa) ganha sufixo")
    P2 = d["id"]
    for bad in ("", "   ", "x" * 61, None, 7, ["a"]):
        ok(req("POST", "/api/project", {"name": bad})[0] == 400, f"nome inválido {str(bad)[:8]!r} -> 400")
    ok(req("POST", "/api/project", {"name": "y" * 60})[0] == 200, "nome com 60 chars aceito")
    ok(req("POST", "/api/project", {})[0] == 400, "sem nome -> 400")
    ok(req("POST", "/api/project/rename", {"id": P2, "name": "Campanhas"})[1]["name"] == "Campanhas (2)", "renomear para nome já usado também ganha sufixo")
    ok(req("POST", "/api/project/rename", {"id": P2, "name": "Natal"}) == (200, {"id": P2, "name": "Natal"}), "renomear projeto")
    ok(req("POST", "/api/project/rename", {"id": P2, "name": ""})[0] == 400 and req("POST", "/api/project/rename", {"id": "p00000000", "name": "x"})[0] == 404, "rename: nome vazio 400, projeto inexistente 404")
    ps = req("GET", "/api/projects")[1]["projects"]
    ok({"Campanhas", "Natal"} <= {p["name"] for p in ps} and all(set(p) == {"id", "name", "updated", "count"} for p in ps), "GET /api/projects: contrato")
    ok(req("POST", "/api/conv/move", {"scope": "_geral", "conv": "g1", "project": P1}) == (200, {"ok": True}), "mover conversa para o projeto")
    ok(req("POST", "/api/conv/move", {"client": "71", "conv": "leg1", "project": P1})[0] == 200, "mover com {client, conv} (fluxo antigo)")
    ok(item("g1")["project"] == P1 and item("leg1", "71")["project"] == P1, "lista global traz o project de cada conversa")
    ok(next(p for p in req("GET", "/api/projects")[1]["projects"] if p["id"] == P1)["count"] == 2, "projeto conta 2 conversas")
    t0 = item("g1")["updated"]; time.sleep(1.1); req("POST", "/api/conv/move", {"scope": "_geral", "conv": "g1", "project": P2}); req("POST", "/api/conv/move", {"scope": "_geral", "conv": "g1", "project": P1})
    ok(item("g1")["updated"] == t0, "mover não muda a ordem do histórico (updated preservado)")
    ok(req("POST", "/api/conv/move", {"scope": "_geral", "conv": "g1", "project": "p00000000"})[0] == 404, "mover para projeto inexistente -> 404")
    ok(req("POST", "/api/conv/move", {"scope": "_geral", "conv": "naoexiste", "project": P1})[0] == 404, "mover conversa inexistente -> 404")
    before = json.loads((DATA / "conversations" / "_geral" / "g1.json").read_text())
    for bad in ("../x", "%2e%2e", "a/b", "P1", "", "p1 ", "..", "p1\x00"):
        for ep, body in (("/api/project/rename", {"id": bad, "name": "x"}), ("/api/project/delete", {"id": bad}), ("/api/conv/move", {"scope": "_geral", "conv": "g1", "project": bad or "  "})):
            ok(req("POST", ep, body)[0] in (400, 404), f"{ep} id malicioso {bad!r} rejeitado")
    for bad in ("../71", "..", "a/b", "_GERAL", ""):
        for ep, extra in (("/api/conv/move", {"project": P1}), ("/api/conv/client", {"client_id": None}), ("/api/conv/rename", {"title": "x"}), ("/api/conv/delete", {})):
            ok(req("POST", ep, {"scope": bad, "conv": "g1", **extra})[0] in (400, 404), f"{ep} scope malicioso {bad!r} rejeitado")
    ok(json.loads((DATA / "conversations" / "_geral" / "g1.json").read_text()) == before, "ids maliciosos não alteraram nenhuma conversa")
    pj = DATA / "projects.json"; good = pj.read_text(); pj.write_text("{quebrado")
    st, e = req("GET", "/api/projects")
    ok(st == 500 and "projects.json" in e["error"] and req("POST", "/api/project", {"name": "x"})[0] == 500, "projects.json corrompido: erro explícito, não vira 'nenhum projeto'")
    ok(pj.read_text() == "{quebrado", "o arquivo corrompido não é sobrescrito"); pj.write_text(good)
    for ep, body in (("/api/project", {"name": "hack"}), ("/api/project/rename", {"id": P1, "name": "hack"}), ("/api/project/delete", {"id": P1}),
                     ("/api/conv/move", {"scope": "_geral", "conv": "g1", "project": None}), ("/api/conv/client", {"scope": "_geral", "conv": "g1", "client_id": None})):
        ok(req("POST", ep, body, headers={"Origin": "http://evil.example"})[0] == 403, f"{ep}: Origin externo -> 403")
    ok(item("g1")["project"] == P1 and any(p["id"] == P1 for p in req("GET", "/api/projects")[1]["projects"]), "403 não alterou nada")
    before_files = sorted(p.name for p in DATA.rglob("*.json") if "conversations" in str(p))
    r = req("POST", "/api/project/delete", {"id": P1})
    ok(r == (200, {"ok": True, "released": 2}), f"excluir projeto libera as 2 conversas: {r}")
    ok(sorted(p.name for p in DATA.rglob("*.json") if "conversations" in str(p)) == before_files, "excluir projeto NÃO apagou nenhuma conversa")
    ok(item("g1")["project"] is None and item("leg1", "71")["project"] is None, "conversas voltam para 'sem projeto'")
    ok("project" not in json.loads((DATA / "conversations" / "_geral" / "g1.json").read_text()) and P1 not in pj.read_text(), "o campo project sai do arquivo e o projeto sai do projects.json")
    ok(req("POST", "/api/project/delete", {"id": P1})[0] == 404, "excluir de novo -> 404")
    ok(req("POST", "/api/conv/move", {"scope": "_geral", "conv": "g1", "project": None})[0] == 200, "mover para 'sem projeto' (null)")

    # ================= A4: ids reservados; A5: projects.json corrompido não derruba a lista =================
    for bad in ("_geral", "_Geral", "_x"):
        ok(req("POST", "/api/client/new", {"name": bad})[0] == 400 and req("POST", "/api/client/save", {"id": bad, "client": {"name": "x"}})[0] == 400, f"cliente {bad!r}: criar e salvar -> 400 (id reservado)")
    ok(not (DATA / "clients" / "_geral" / "client.json").exists() and "_geral" not in [c["id"] for c in req("GET", "/api/state")[1]["clients"]], "nenhum cliente _geral existe nem aparece no estado")
    pj = DATA / "projects.json"; good = pj.read_text(); pj.write_text("{quebrado")
    st, lst = req("GET", "/api/convs")
    ok(st == 200 and "projects_error" in lst and lst["convs"] and all(c["project"] is None for c in lst["convs"]), "lista de conversas sobrevive a projects.json corrompido (project nulo + projects_error)")
    ok(req("GET", "/api/projects")[0] == 500, "as rotas de projetos continuam 500 explícito"); pj.write_text(good)
    ok("projects_error" not in req("GET", "/api/convs")[1], "projects.json saudável: sem projects_error")

    # ================= cliente automático: provedor local =================
    save_client("padaria-lua", name="Padaria Lua", sector="padaria", aliases=["pães da lua"], cpf=CPF, email=MAIL, palette=["#aa0000"])
    save_client("cafe-aurora", name="Café Aurora", sector="cafeteria", tone="calmo")
    ok(req("GET", "/api/state")[1]["client_sources"] == ["local", "banco"] and req("GET", "/api/state", None, PORT2)[1]["client_sources"] == ["local"], "origens: com env local+banco; sem env só local (banco desabilitado)")
    st, p, steps = chat("faça um post para a CAFE aurora de lançamento", conv="d1")
    ok(st == 200 and p["status"] == "done" and "Cliente identificado: Café Aurora (fonte: local)" in steps, "detecta sem acento/caixa e emite 'Cliente identificado: ... (fonte: local)'")
    s = state("d1", "_geral")
    ok(s["client"] == {"id": "cafe-aurora", "name": "Café Aurora", "source": "local", "compra_id": None} and s["scope"] == "_geral", "estado da conversa traz client {id,name,source}")
    ok(item("d1")["client"] == "cafe-aurora" and item("d1")["client_name"] == "Café Aurora" and item("d1")["scope"] == "_geral", "lista traz client/client_name e a conversa segue na pasta _geral")
    st, p, steps = chat("mude a cor do fundo", conv="d1", scope="_geral")
    ok(st == 200 and p["status"] == "done" and not any("Cliente identificado" in x for x in steps) and state("d1", "_geral")["client"]["id"] == "cafe-aurora", "turnos seguintes seguem com o cliente e editam a imagem gerada antes")
    st, p, steps = chat("banner da Padaria Lua e do Café Aurora", conv="d2")
    txt = p["message"].get("text")
    ok(st == 200 and p["message"]["kind"] == "text" and txt in ("Qual cliente: Padaria Lua ou Café Aurora?", "Qual cliente: Café Aurora ou Padaria Lua?"), f"ambíguo: pergunta curta, sem escolher ({txt})")
    ok(state("d2", "_geral")["client"] is None and item("d2")["count"] == 1, "ambíguo: conversa sem cliente e o turno da pergunta registrado")
    st, p, steps = chat("só o Café Aurora", conv="d2", scope="_geral")
    ok(state("d2", "_geral")["client"]["id"] == "cafe-aurora", "resposta à pergunta resolve o cliente")
    st, p, steps = chat("um cartaz para a padaria luanda", conv="d3")
    ok(p["status"] == "done" and state("d3", "_geral")["client"] is None and not any("Cliente identificado" in x for x in steps), "palavra inteira: 'luanda' não casa com 'Padaria Lua'; sem match segue sem cliente")
    st, p, steps = chat("pães da lua em promoção", conv="d4")
    ok(state("d4", "_geral")["client"]["id"] == "padaria-lua", "apelido (aliases) também casa")
    def prompts_of(fn):
        ev = DATA / "logs" / "events.jsonl"; n0 = len(ev.read_text().splitlines()) if ev.exists() else 0
        fn(); return [json.loads(l)["system"] for l in ev.read_text().splitlines()[n0:] if '"prompt_ctx"' in l]
    save_client("tel-ok", name="Tel Ok", brand_description="ligue (11) 91234-5678 para falar", cpf=CPF, observacoes="segredo-interno", email=MAIL, palette=["#00ff00"])
    pp = prompts_of(lambda: chat("post para Tel Ok", conv="pr1", mode="marca"))
    ok(pp and "Tel Ok" in pp[0] and not any(x in pp[0] for x in (CPF, MAIL, "segredo-interno", "91234")) and "[dado pessoal removido]" in pp[0], "prompt real da conversa (mock): contexto do cliente sem campo fora da lista e com telefone redigido")
    pp = prompts_of(lambda: chat("banner de verão", conv="pr2", client="71", auto_client=True, mode="marca"))
    ok(pp and not any(x in pp[0] for x in ("Marca Fictícia 71", "praia fictícia", "publico ficticio setenta", "#0B3C5D", "segredo-do-71", "000.111.222-33")), "auto_client + 71 legado: NENHUM dado do 71 chega ao prompt")
    pp = prompts_of(lambda: chat("banner de verão", conv="pr3", client="71", mode="marca"))
    ok(pp and "Marca Fictícia 71" in pp[0] and "praia fictícia" in pp[0] and "segredo-do-71" not in pp[0] and "000.111.222-33" not in pp[0], "controle: sem auto_client o 71 legado continua no prompt (o teste enxerga o contexto)")
    # troca e remoção manual
    ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "d3", "client_id": "padaria-lua"})[0] == 200 and state("d3", "_geral")["client"]["id"] == "padaria-lua", "troca manual: define o cliente")
    chat("agora para o Café Aurora", conv="d3", scope="_geral")
    ok(state("d3", "_geral")["client"]["id"] == "padaria-lua", "escolha manual não é desfeita pela detecção automática")
    ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "d3", "client_id": "cafe-aurora"})[1]["client"]["name"] == "Café Aurora" and state("d3", "_geral")["client"]["id"] == "cafe-aurora", "troca de um cliente por outro")
    ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "d3", "client_id": None}) == (200, {"ok": True, "client": None}) and state("d3", "_geral")["client"] is None, "remoção manual")
    chat("de novo o Café Aurora", conv="d3", scope="_geral")
    ok(state("d3", "_geral")["client"] is None and item("d3")["client"] is None, "depois de remover, a detecção não recoloca o cliente")
    ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "d3", "client_id": "nao-existe"})[0] == 404, "cliente inexistente -> 404")
    ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "naoexiste", "client_id": "cafe-aurora"})[1].get("pending") is True and not (DATA / "conversations" / "_geral" / "naoexiste.json").exists(), "conversa inexistente: pending, sem criar arquivo")
    for bad in ("../x", "..", "a/b", "CAFE-AURORA", ""):
        ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "d3", "client_id": bad})[0] == 400, f"client_id malicioso {bad!r} -> 400")
    # biblioteca: imagem anexada antes de o cliente ser conhecido acompanha a conversa
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    _, a = req("POST", "/api/asset", {"client": "_geral", "conv": "d5", "kind": "referencia", "name": "ref.png", "mime": "image/png", "b64": png}); aid = a["asset"]["id"]
    st, p, steps = chat("post do Café Aurora com a referência", conv="d5", asset_ids=[aid])
    ok(st == 200 and p["status"] == "done" and "Cliente identificado: Café Aurora (fonte: local)" in steps, "primeira mensagem com anexo detecta o cliente")
    lib = json.loads((DATA / "clients" / "cafe-aurora" / "assets.json").read_text())
    ok(any(x["id"] == aid for x in lib) and (DATA / "clients" / "cafe-aurora" / "assets" / next(x["file"] for x in lib if x["id"] == aid)).exists(), "o anexo foi copiado para a biblioteca do cliente (a original fica)")
    ok(not any("apagada da biblioteca" in x for x in p["message"].get("avisos", [])) and state("d5", "_geral")["files"] == [aid], "anexo não vira 'apagado' depois da detecção")

    # ================= biblioteca neutra _geral e isolamento do 71 =================
    ok(req("POST", "/api/client", {"id": "_geral"}) == (200, {"id": "_geral", "client": None, "assets": req("POST", "/api/client", {"id": "_geral"})[1]["assets"]}), "POST /api/client {id:_geral}: {client:null, assets} sem criar cliente")
    _, up = req("POST", "/api/asset", {"client": "_geral", "conv": "iso1", "kind": "referencia", "name": "neutra.png", "mime": "image/png", "b64": png}); gid = up["asset"]["id"]
    _, up71 = req("POST", "/api/asset", {"client": "71", "kind": "referencia", "name": "praia71.png", "mime": "image/png", "b64": png, "alias": "praia"}); a71 = up71["asset"]["id"]
    lib_g = req("POST", "/api/client", {"id": "_geral"})[1]["assets"]
    mine = next((x for x in lib_g if x["id"] == gid), None)
    ok(mine and a71 not in [x["id"] for x in lib_g] and mine["url"].startswith("/files/_geral/assets/") and http.client.HTTPConnection("127.0.0.1", PORT).request("GET", mine["url"]) is None and fetch_status(mine["url"]) == 200, "upload em _geral aparece na biblioteca neutra (sem nada do 71) e o arquivo é servido")
    ok(not (DATA / "clients" / "_geral" / "client.json").exists() and "_geral" not in [c["id"] for c in req("GET", "/api/state")[1]["clients"]], "nenhum client.json em clients/_geral")
    ok(req("POST", "/api/asset/kind", {"client": "_geral", "conv": "iso1", "id": gid, "kind": "logo"})[0] == 200 and next(x for x in req("POST", "/api/client", {"id": "_geral"})[1]["assets"] if x["id"] == gid)["kind"] == "logo", "/api/asset/kind em _geral")
    ok(req("POST", "/api/asset/alias", {"client": "_geral", "conv": "iso1", "id": gid, "alias": "neutra"})[0] == 200 and next(x for x in req("POST", "/api/client", {"id": "_geral"})[1]["assets"] if x["id"] == gid)["alias"] == "neutra", "/api/asset/alias em _geral")
    ok(req("POST", "/api/client/save", {"id": "_geral", "client": {"name": "x"}})[0] == 400, "A4 continua: não dá para salvar CLIENTE _geral")
    # conversa sem cliente + anexo + auto_client + 71 legado: nada do 71
    st, p, steps = chat("foto da praia", conv="iso1", client="71", auto_client=True, asset_ids=[gid])
    ok(st == 200 and p["status"] == "done" and state("iso1", "_geral")["files"] == [gid] and state("iso1", "_geral")["client"] is None, "auto_client + anexo da biblioteca neutra: a conversa usa só o anexo _geral")
    ok(not any("praia71" in x for x in steps) and not any("automaticamente" in x for x in steps), "o apelido 'praia' do 71 NÃO é anexado automaticamente")
    st, e = chat("foto", conv="iso2", client="71", auto_client=True, asset_ids=[a71])[:2]
    ok(st == 409 and not (DATA / "conversations" / "_geral" / "iso2.json").exists(), "pedir um asset do 71 numa conversa sem cliente: 409, nada usado")
    # detecção na mensagem seguinte: o anexo é COPIADO para o cliente certo; o 71 não recebe nada
    ids71 = lambda: sorted(x["id"] for x in json.loads((DATA / "clients" / "71" / "assets.json").read_text()))
    before71 = ids71()
    st, p, steps = chat("agora para o Café Aurora", conv="iso1", scope="_geral", client="71", auto_client=True)
    ok(state("iso1", "_geral")["client"]["id"] == "cafe-aurora", "mensagem seguinte cita o cliente: detectado")
    ok(gid in [x["id"] for x in json.loads((DATA / "clients" / "cafe-aurora" / "assets.json").read_text())] and ids71() == before71, "anexo copiado para a biblioteca do cliente certo; o 71 não recebeu nada")
    ok(gid in [x["id"] for x in req("POST", "/api/client", {"id": "_geral"})[1]["assets"]], "a cópia não apaga o original da biblioteca neutra")

    # ================= N2: anexos neutros POR CONVERSA =================
    up = lambda conv, name, alias: req("POST", "/api/asset", {"client": "_geral", **({"conv": conv} if conv else {}), "kind": "referencia", "name": name, "mime": "image/png", "b64": png, "alias": alias})
    x1 = up("na1", "um.png", "gatoum")[1]["asset"]["id"]; x2 = up("na2", "dois.png", "gatodois")[1]["asset"]["id"]; xold = up(None, "antigo.png", "gatoantigo")[1]["asset"]["id"]
    listc = lambda conv: [a["id"] for a in req("POST", "/api/client", {"id": "_geral", **({"conv": conv} if conv else {})})[1]["assets"]]
    ok(listc("na1") == [x1] and listc("na2") == [x2], "listagem por conversa: cada uma vê só os seus anexos")
    ok({x1, x2, xold} <= set(listc(None)), "sem conv: lista todos (compatibilidade), inclusive o antigo sem dono")
    ok(xold not in listc("na1") and (DATA / "clients" / "_geral" / "assets").exists(), "anexo antigo sem dono fica fora das listas por conversa e continua no disco")
    ok(req("POST", "/api/asset", {"client": "_geral", "conv": "../x", "kind": "referencia", "name": "a.png", "mime": "image/png", "b64": png})[0] == 400 and req("POST", "/api/client", {"id": "_geral", "conv": "../x"})[0] == 400, "conv malicioso no upload e na listagem -> 400")
    st, p, steps = chat("usa o gatoum e o gatodois e o gatoantigo", conv="na1", asset_ids=[x1])
    ok(st == 200 and p["status"] == "done" and state("na1", "_geral")["files"] == [x1] and any("um.png" in z for z in steps) and not any(("dois.png" in z or "antigo.png" in z) for z in steps), "auto-anexo por apelido só considera os anexos da própria conversa")
    st, p, steps = chat("de novo", conv="na1", scope="_geral")
    ok(state("na1", "_geral")["files"] == [x1] and not any(("dois.png" in z or "antigo.png" in z) for z in steps), "a 2ª mensagem não leva anexo de outra conversa")
    ok(chat("com a do vizinho", conv="na1", scope="_geral", asset_ids=[x2])[0] == 409, "asset_ids de outra conversa -> 409")
    st, p, steps = chat("agora para o Café Aurora", conv="na1", scope="_geral")
    cafe_ids = [x["id"] for x in json.loads((DATA / "clients" / "cafe-aurora" / "assets.json").read_text())]
    ok(x1 in cafe_ids and x2 not in cafe_ids and xold not in cafe_ids, "ao detectar o cliente, migrate_assets copia só os anexos DA conversa")
    # ================= N4: /api/conv/files como o front chama (scope + conv) =================
    f1 = up("fl1", "f1.png", "fumum")[1]["asset"]["id"]; f2 = up("fl2", "f2.png", "fumdois")[1]["asset"]["id"]
    chat("conversa sem cliente para fixar", conv="fl1")
    r = req("POST", "/api/conv/files", {"scope": "_geral", "conv": "fl1", "add": [f1], "drop": []})
    ok(r == (200, {"files": [f1]}) and state("fl1", "_geral")["files"] == [f1], "conv/files com {scope, conv} em conversa existente sem cliente: lista gravada no servidor")
    ok(json.loads((DATA / "conversations" / "_geral" / "fl1.json").read_text())["files"] == [f1], "...e no arquivo da conversa")
    ok(req("POST", "/api/conv/files", {"scope": "_geral", "conv": "fl1", "add": [f2]})[0] == 409 and state("fl1", "_geral")["files"] == [f1], "anexo de OUTRA conversa -> 409 e nada gravado")
    ok(req("POST", "/api/conv/files", {"scope": "_geral", "conv": "fl1", "add": [], "drop": [f1]}) == (200, {"files": []}), "drop remove da lista")
    ok(req("POST", "/api/conv/files", {"client": "_geral", "conv": "fl1", "add": [f1]}) == (200, {"files": [f1]}), "{client, conv} continua compatível")
    chat("conversa com cliente detectado: Café Aurora", conv="fl3")
    cafe_lib = [a["id"] for a in json.loads((DATA / "clients" / "cafe-aurora" / "assets.json").read_text())]
    ok(cafe_lib and state("fl3", "_geral")["client"]["id"] == "cafe-aurora", "conversa com cliente detectado existe")
    r = req("POST", "/api/conv/files", {"scope": "_geral", "conv": "fl3", "add": [cafe_lib[0]], "drop": []})
    ok(r == (200, {"files": [cafe_lib[0]]}) and state("fl3", "_geral")["files"] == [cafe_lib[0]], "conv/files com {scope, conv} em conversa COM cliente detectado grava a lista")
    for bad in ("../x", "a/b", ""):
        ok(req("POST", "/api/conv/files", {"scope": bad, "conv": "fl1", "add": []})[0] in (400, 404) and req("POST", "/api/conv/files", {"scope": "_geral", "conv": bad, "add": []})[0] in (400, 404), f"conv/files com id malicioso {bad!r} rejeitado")
    # ================= N3: delete/kind/alias na biblioteca neutra exigem o dono =================
    g1 = up("own1", "o1.png", "donoum")[1]["asset"]["id"]
    snap = (DATA / "clients" / "_geral" / "assets.json").read_text()
    for ep, extra in (("/api/asset/delete", {}), ("/api/asset/kind", {"kind": "logo"}), ("/api/asset/alias", {"alias": "hack"})):
        ok(req("POST", ep, {"client": "_geral", "id": g1, **extra})[0] == 400, f"{ep} em _geral sem conv -> 400")
        ok(req("POST", ep, {"client": "_geral", "conv": "own2", "id": g1, **extra})[0] == 404, f"{ep} com conv de OUTRO dono -> 404")
        ok(req("POST", ep, {"client": "_geral", "conv": "../x", "id": g1, **extra})[0] == 400, f"{ep} com conv malicioso -> 400")
        ok(req("POST", ep, {"client": "_geral", "conv": "own1", "id": xold, **extra})[0] == 404, f"{ep} em asset sem dono -> 404")
    ok((DATA / "clients" / "_geral" / "assets.json").read_text() == snap and g1 in listc("own1"), "nada foi alterado pelas tentativas negadas")
    ok(req("POST", "/api/asset/alias", {"client": "_geral", "conv": "own1", "id": g1, "alias": "novo"})[0] == 200 and req("POST", "/api/asset/kind", {"client": "_geral", "conv": "own1", "id": g1, "kind": "logo"})[0] == 200, "o dono altera alias e tipo")
    ok(req("POST", "/api/asset/delete", {"client": "_geral", "conv": "own1", "id": g1})[0] == 200 and g1 not in listc("own1") and xold in listc(None), "o dono apaga o seu e o sem dono continua")

    # ================= N1: size auto na 2ª mensagem; erro interno neutro =================
    st, p, steps = chat("post para o Café Aurora", conv="sz1")
    st2, p2, _ = chat("mude a cor", conv="sz1", scope="_geral", size="auto")
    ok(st == 200 and p["status"] == "done" and st2 == 200 and p2["status"] == "done" and state("sz1", "_geral")["client"]["id"] == "cafe-aurora" and item("sz1")["count"] == 2, f"2 mensagens seguidas, a 2ª com size:auto e cliente detectado: {p2.get('error')}")
    st, p, steps = chat("pedido __boom__", conv="boom1")
    ok(st == 200 and p["status"] == "error" and p["error"] == "Não consegui concluir a imagem." and "ValueError" not in json.dumps(p["error"]), "erro interno: a mensagem visível é neutra, sem nome de exceção")
    ok(p["error_detail"].startswith("ValueError:") and "invalid literal" in p["error_detail"], "o detalhe técnico vai em error_detail")
    ok(any(json.loads(l).get("erro", "").startswith("ValueError") for l in (DATA / "logs" / "events.jsonl").read_text().splitlines() if '"erro"' in l), "o detalhe fica no log de eventos")

    # anexo na conversa nova + cliente ESCOLHIDO À MÃO antes do 1º envio: o servidor copia o anexo para o cliente e o usa
    _, up2 = req("POST", "/api/asset", {"client": "_geral", "conv": "man1", "kind": "referencia", "name": "manual.png", "mime": "image/png", "b64": png, "alias": "manualref"}); mid = up2["asset"]["id"]
    before71 = ids71()
    r = req("POST", "/api/conv/client", {"scope": "_geral", "conv": "man1", "client_id": "cafe-aurora"})
    ok(r[1].get("pending") is True and not (DATA / "conversations" / "_geral" / "man1.json").exists(), "escolha manual antes do 1º envio: pending, nada gravado")
    st, p, steps = chat("post com a referência", conv="man1", scope="_geral", client="cafe-aurora", auto_client=False, asset_ids=[mid])
    ok(st == 200 and p["status"] == "done" and any("manual.png" in x and "Imagens de entrada" in x for x in steps), f"o anexo vindo de _geral é USADO no 1º turno ({[x for x in steps if 'entrada' in x]})")
    lib_c = json.loads((DATA / "clients" / "cafe-aurora" / "assets.json").read_text())
    ok(mid in [x["id"] for x in lib_c] and (DATA / "clients" / "cafe-aurora" / "assets" / next(x["file"] for x in lib_c if x["id"] == mid)).exists(), "o anexo foi copiado para a biblioteca do cliente escolhido")
    ok(ids71() == before71 and state("man1", "_geral")["client"]["id"] == "cafe-aurora" and state("man1", "_geral")["files"] == [mid], "o 71 continua limpo e a conversa guarda cliente e anexo")
    ok(mid in [x["id"] for x in req("POST", "/api/client", {"id": "_geral"})[1]["assets"]], "o original fica na biblioteca neutra")

    # ================= cliente automático: provedor do banco (FAKE) =================
    ok(req("GET", "/api/state", None, PORT3)[1]["client_sources"] == ["local"], "env do banco SEM CHAT_DB_ENABLED=1: provedor desabilitado (fonte: local)")
    FAKE["log"].clear()
    st, p, steps = chat("logo novo para o estúdio boreal", conv="b1")
    ok(st == 200 and "Cliente identificado: Estúdio Boreal (fonte: banco)" in steps, "banco: detecta e informa 'fonte: banco'")
    sb = state("b1", "_geral")["client"]
    ok(sb["id"] == A and sb["source"] == "banco" and sb["compra_id"] == "aaaaaaa2-0000-4000-8000-000000000002", f"banco: cliente e compra vigente guardados na conversa: {sb}")
    chat("outra versão", conv="b1", scope="_geral")
    ok(state("b1", "_geral")["client"]["id"] == A, "turno seguinte reaproveita o cliente do banco")
    lib = json.loads((DATA / "clients" / A / "assets.json").read_text())
    ok(len(lib) == 1 and lib[0]["kind"] == "logo" and (DATA / "clients" / A / "assets" / lib[0]["file"]).read_bytes() == PNG, "logo do banco veio como BYTES pela Edge Function e ficou na biblioteca local do cliente")
    chat("outra versão ainda", conv="b1", scope="_geral")
    ok(len(json.loads((DATA / "clients" / A / "assets.json").read_text())) == 1, "logo não é baixado de novo a cada turno")
    st, p, steps = chat("cartaz da loja inelegível", conv="b2")
    ok(p["status"] == "done" and state("b2", "_geral")["client"] is None and not any("Cliente identificado" in x for x in steps), "cliente inelegível (fora da view) NÃO é reconhecido")
    st, p, steps = chat("cartaz da Padaria Sol", conv="b3")
    ok(state("b3", "_geral")["client"]["id"] == B and state("b3", "_geral")["client"]["source"] == "banco", "banco: match único de outro cliente")
    ok(any("não permitido" in a_ for a_ in p["message"].get("avisos", [])) and not (DATA / "clients" / B / "assets.json").exists(), "logo SVG do banco é recusado (aviso explícito) e não é guardado")
    save_client("padaria-sol-local", name="Padaria Sol")
    st, p, steps = chat("cartaz da Padaria Sol", conv="b4")
    ok(p["message"]["kind"] == "text" and p["message"]["text"].startswith("Qual cliente:") and state("b4", "_geral")["client"] is None, "mesmo nome em duas fontes: ambíguo, não escolhe")
    os.remove(DATA / "clients" / "padaria-sol-local" / "client.json")
    st, p, steps = chat("capa para Maria Souza", conv="b7")
    ok(any("pessoa física" in a_ for a_ in p["message"].get("avisos", [])) and state("b7", "_geral")["client"]["id"] == D, "pessoa física: reconhecida, com aviso de que o nome não vira marca")
    ctx_d = cp.SupabaseClientProvider(cp.HttpTransport(f"http://127.0.0.1:{FPORT}", KEY, KEY2)).load(D)
    ok("name" not in ctx_d and ctx_d["_pessoa_fisica"] is True and ctx_d["_display_name"] == "Maria Souza", "pessoa física: o nome não entra no contexto do prompt (só no chip)")
    st, p, steps = chat("banner da Vazia Sem Marca", conv="b8")
    ok(any("identidade de marca" in a_ for a_ in p["message"].get("avisos", [])), "cliente sem identidade: aviso 'indisponível', não 'sem cores' (C2)")
    ctx_e = cp.SupabaseClientProvider(cp.HttpTransport(f"http://127.0.0.1:{FPORT}", KEY, KEY2)).load(E)
    ok("palette" not in ctx_e and ctx_e["_sem_identidade"] is True, "sem identidade: paleta ausente (não lista vazia)")
    # banco prevalece; local só acrescenta o que falta
    merged = cp.merge_local({"name": "Banco", "tone": "do banco", "palette": None, "sector": ""}, {"name": "Local", "tone": "local", "palette": ["#010101"], "sector": "moda", "image_style": "minimalista", "cpf": CPF})
    ok(merged == {"name": "Banco", "tone": "do banco", "palette": ["#010101"], "sector": "moda", "image_style": "minimalista"}, "mescla: banco vence em conflito, local preenche o que o banco não tem, PII local cortada")
    # troca manual para cliente do banco
    r = req("POST", "/api/conv/client", {"scope": "_geral", "conv": "b4", "client_id": A})
    ok(r[0] == 200 and r[1]["client"]["source"] == "banco" and state("b4", "_geral")["client"]["compra_id"].startswith("aaaaaaa2"), "troca manual para cliente do banco")
    ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "b4", "client_id": "99999999-9999-4999-8999-999999999999"})[0] == 404, "cliente fora da view (inelegível/inexistente) -> 404")
    ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "b4", "client_id": A, "compra_id": "aaaaaaa1-0000-4000-8000-000000000001"})[0] == 400, "escolher outra compra: fora do contrato -> 400 claro")
    # ===== contrato com a UI =====
    st, cl = req("GET", "/api/clients?q=padaria")
    ok(st == 200 and {(c["name"], c["source"]) for c in cl["clients"]} == {("Padaria Lua", "local"), ("Padaria Sol", "banco")} and all(set(c) == {"id", "name", "source"} for c in cl["clients"]), f"GET /api/clients?q=: {cl}")
    ok(len(req("GET", "/api/clients")[1]["clients"]) >= 6, "GET /api/clients sem q lista tudo")
    st, c = req("POST", "/api/client", {"id": A})
    ok(st == 200 and c["source"] == "banco" and c["client"]["name"] == "Estúdio Boreal" and not any(k in c["client"] for k in ("cpf", "email", "telefone")) and c["assets"], "/api/client aceita id do banco: contexto filtrado + biblioteca local")
    ok(req("POST", "/api/client", {"id": "99999999-9999-4999-8999-999999999999"})[0] == 404, "/api/client: id desconhecido continua 404")
    ok(req("POST", "/api/client", {"id": "71"})[1]["client"]["id"] == 71, "/api/client: cliente local 71 como sempre")
    # auto_client: o 71 legado NÃO pode vazar
    st, p, steps = chat("banner de verão", conv="n1", client="71", auto_client=True, mode="marca")
    ok(st == 200 and p["status"] == "done" and state("n1", "_geral")["client"] is None and not (DATA / "conversations" / "71" / "n1.json").exists(), "auto_client=true + client legado 71: conversa fica em _geral, SEM cliente")
    ok(any("sem cliente identificado" in a_ for a_ in p["message"].get("avisos", [])), "modo marca sem cliente: aviso explícito, contexto do 71 NÃO usado")
    st, p, steps = chat("banner de verão", conv="n2", client="71", mode="marca")
    ok(not any("sem cliente identificado" in a_ for a_ in p["message"].get("avisos", [])) and state("n2", "71")["client"]["id"] == "71", "sem auto_client o fluxo antigo (client=71) continua valendo")
    st, p, steps = chat("post do estúdio boreal", conv="n3", client="71", auto_client=True)
    ok(state("n3", "_geral")["client"]["id"] == A and "Cliente identificado: Estúdio Boreal (fonte: banco)" in steps, "auto_client=true detecta pelo texto e ignora o 71 enviado")
    # conversa que ainda não existe: pending, nada gravado
    r = req("POST", "/api/conv/client", {"scope": "_geral", "conv": "novinha", "client_id": "cafe-aurora"})
    ok(r[0] == 200 and r[1]["pending"] is True and r[1]["client"]["id"] == "cafe-aurora" and not (DATA / "conversations" / "_geral" / "novinha.json").exists(), "conv/client em conversa nova: 200 pending, nada gravado")
    ok(req("POST", "/api/conv/client", {"scope": "_geral", "conv": "novinha", "client_id": "nao-existe"})[0] == 404, "pending também valida o cliente (404)")
    st, p, steps = chat("só um teste", conv="novinha", scope="_geral", client="cafe-aurora")
    ok(state("novinha", "_geral")["client"]["id"] == "cafe-aurora" and state("novinha", "_geral")["scope"] == "_geral", "o client do 1º /api/chat vale (escolha manual antes do 1º turno), na pasta _geral")
    st, p, steps = chat("outro", conv="novinha2", scope="_geral", client=A)
    ok(state("novinha2", "_geral")["client"]["source"] == "banco", "client do body pode ser um cliente do banco")
    # A7: assinatura dos bytes
    prov = cp.SupabaseClientProvider(cp.HttpTransport(f"http://127.0.0.1:{FPORT}", KEY, KEY2))
    for path, why in ((f"{A}/falso.png", "HTML rotulado como PNG"), (f"{A}/x.svg", "SVG")):
        try: prov.fetch_asset(path); ok(False, f"deveria recusar {why}")
        except cp.ProviderError as e: ok("recusado" in str(e), f"fetch_asset recusa {why}: {e}")
    ok(prov.fetch_asset(f"{A}/logo.png")[1] == "image/png", "fetch_asset aceita PNG verdadeiro")
    for bad in ("../x.png", "abc/logo.png", f"{A}/../x.png"):
        try: prov.fetch_asset(bad); ok(False, "deveria recusar caminho")
        except cp.ProviderError: ok(True, f"fetch_asset recusa caminho {bad!r}")
    # A1: redirecionamento nunca leva a chave a outro host
    FAKE["redirect"] = f"http://127.0.0.1:{APORT}"; ATTACK.clear()
    for label, call in (("rpc", lambda: prov.find("estudio")), ("get", lambda: prov.logos(A)), ("post_bytes", lambda: prov.fetch_asset(f"{A}/logo.png"))):
        try: call(); ok(False, f"{label}: deveria falhar no 302")
        except cp.ProviderError as e:
            ok("redirecionamento recusado" in str(e) and KEY not in str(e) and KEY2 not in str(e) and str(APORT) not in str(e) and str(FPORT) not in str(e), f"{label}: 3xx vira ProviderError sem URL nem chave ({e})")
    ok(ATTACK == [], f"o host do redirecionamento NÃO recebeu nenhuma requisição ({len(ATTACK)})")
    st, cl = req("GET", "/api/clients?q=padaria")
    ok(st == 200 and cl["errors"][0]["source"] == "banco" and KEY not in json.dumps(cl) and str(APORT) not in json.dumps(cl) and ATTACK == [], "servidor: /api/clients com 302 mostra erro explícito sem vazar nada")
    FAKE["redirect"] = None
    # A8: nome de pessoa física não é gravado
    cj = json.loads((DATA / "conversations" / "_geral" / "b7.json").read_text())
    ok(cj["client_name"] == "Cliente (pessoa física)" and item("b7")["client_name"] == "Cliente (pessoa física)" and state("b7", "_geral")["client"]["name"] == "Cliente (pessoa física)", "pessoa física: client_name genérico na conversa, na lista e no estado")
    evs = [json.loads(l) for l in (DATA / "logs" / "events.jsonl").read_text().splitlines()]
    ok(any("Cliente identificado: Cliente (pessoa física) (fonte: banco)" in e.get("text", "") for e in evs) and not any("Maria Souza" in e.get("text", "") for e in evs if e["kind"] == "step"), "pessoa física: o evento de progresso não traz o nome")
    ok("Maria Souza" not in json.dumps({k: v for k, v in cj.items() if k not in ("turns", "title")}), "pessoa física: o nome não está em nenhum campo da conversa além do que o usuário digitou (turns/title)")
    # banco fora do ar
    FAKE["down"] = True
    st, p, steps = chat("capa para o Estúdio Boreal", conv="b5")
    ok(st == 200 and p["status"] == "done" and any("banco" in x and "fora do ar" in x for x in steps) and state("b5", "_geral")["client"] is None, f"banco fora do ar: erro explícito no progresso e o chat segue ({[x for x in steps if 'banco' in x]})")
    ok(not any("não existe" in x for x in steps), "falha de banco nunca vira 'cliente não existe'")
    st, p, steps = chat("post para o Café Aurora", conv="b6")
    ok("Cliente identificado: Café Aurora (fonte: local)" in steps and any("fora do ar" in x for x in steps), "banco fora do ar: o provedor local continua reconhecendo (e o aviso aparece)")
    st, e = chat("mais uma", conv="b1", scope="_geral")[:2]
    ok(st == 502 and "banco indisponível" in e["error"], "conversa de cliente do banco com o banco fora: erro 502 explícito")
    st, e = req("POST", "/api/conv/client", {"scope": "_geral", "conv": "b6", "client_id": A})
    ok(st == 502 and "banco indisponível" in e["error"], "troca manual com banco fora: 502 explícito, não 404")
    st, e = req("POST", "/api/client", {"id": A})
    ok(st == 502 and "banco indisponível" in e["error"], "/api/client com banco fora: 502 explícito")
    st, cl = req("GET", "/api/clients?q=padaria")
    ok(st == 200 and any(c["source"] == "local" for c in cl["clients"]) and cl["errors"][0]["source"] == "banco", "/api/clients: fonte fora do ar vai em 'errors', as outras listam")
    FAKE["down"] = False
    # servidor sem env: banco desabilitado
    st, p, steps = chat("logo para o Estúdio Boreal", conv="s1", port=PORT2)
    ok(p["status"] == "done" and req("POST", "/api/conv", {"scope": "_geral", "conv": "s1"}, PORT2)[1]["client"] is None and not any("banco" in x for x in steps), "sem SUPABASE_*: banco desabilitado, sem erro, segue local")
    # segurança do acesso ao banco
    ok(FAKE["log"] and all(m == "GET" for m, k, *_ in FAKE["log"] if k.startswith("/rest/")), "banco REST: só GET")
    ok(all(m == "POST" for m, k, *_ in FAKE["log"] if k.startswith("/functions/")), "Edge Function: o único POST, só para baixar bytes")
    ok(all(k.startswith(("/rest/v1/rpc/buscar_cliente_chat", "/rest/v1/rpc/carregar_cliente_chat", "/rest/v1/vw_chat_logos_cliente", "/functions/v1/chat-design-asset")) for _, k, *_ in FAKE["log"]), "banco: só os objetos do contrato chat_design")
    ok(all("*" not in q.get("select", "") for _, _, q, _ in FAKE["log"]), "banco: nunca SELECT *")
    ctx = cp.SupabaseClientProvider(cp.HttpTransport(f"http://127.0.0.1:{FPORT}", KEY, KEY2)).load(A)
    ok({k for k in ctx if not k.startswith("_")} <= set(cp.CONTEXT_FIELDS) and ctx["palette"] == ["#222222", "#ffffff"], "load do banco: só campos permitidos")
    blob = "".join(p.read_text(errors="ignore") for p in DATA.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl"))
    bad = [(x, f.name) for f in DATA.rglob("*") if f.is_file() and f.suffix in (".json", ".jsonl") and not any(t in str(f) for t in ("padaria-lua", "tel-ok", "clients/71/client.json")) for x in (CPF, MAIL, TEL, "Rua Falsa", KEY, KEY2) if x in f.read_text(errors="ignore")]
    ok(not bad, f"{bad}: CPF, e-mail, telefone, endereço e as chaves não aparecem em nenhum arquivo gravado pelo chat (conversas, logs, biblioteca do banco); os client.json de teste (Padaria Lua, Tel Ok, 71) são a única fonte de PII proposital")
    ok(all(x not in json.dumps(req("POST", "/api/conv", {"scope": "_geral", "conv": "b1"})[1]) for x in (CPF, MAIL, KEY, KEY2)), "nem na resposta da API")
    print("\nTUDO OK")
finally:
    for pr in procs: pr.terminate()
    fake.shutdown(); attacker.shutdown(); tmp.cleanup(); tmp2.cleanup(); tmp3.cleanup()
