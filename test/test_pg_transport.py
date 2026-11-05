"""PgTransport / opção B: conexão direta SOMENTE LEITURA ao Postgres. 100% hermético: conexão falsa que registra o que foi executado.
Afirma comportamento (SQL enviado, parâmetros, transação de leitura, erros sem vazamento, recusa de DSN perigoso), não que um mock foi chamado."""
import datetime, os, pathlib, sys, uuid
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import client_provider as cp

fails = []
def ok(c, msg):
    print(("OK   " if c else "FALHA ") + msg)
    if not c: fails.append(msg)

class FakeCur:
    def __init__(self, conn): self.c, self.description, self._rows = conn, None, []
    def execute(self, sql, args=None):
        self.c.log.append((sql, args))
        if self.c.fail and not sql.startswith("set transaction"): raise RuntimeError("password authentication failed for user chat_design_ro host db.secret.supabase.co")
        if sql.startswith("select"):
            self.description, self._rows = self.c.result
    def fetchall(self): return self._rows
class FakeConn:
    def __init__(self, result=(None, []), fail=False): self.log, self.result, self.fail, self.closed, self.rolled = [], result, fail, False, False
    def cursor(self): return FakeCur(self)
    def rollback(self): self.rolled = True
    def close(self): self.closed = True

CID = uuid.UUID("c0000000-0000-0000-0000-00000000000a")
def mk(result=(None, []), fail=False, asset=None):
    c = FakeConn(result, fail); return c, cp.PgTransport(lambda: c, asset)

# 1) rpc: SQL fixo e parametrizado, transação READ ONLY primeiro, conexão encerrada, UUID/data viram texto
c, t = mk(([("cliente_id",), ("nome_exibicao",), ("atualizado_em",)], [(CID, "Marca A", datetime.datetime(2026, 1, 1))]))
rows = t.rpc("buscar_cliente_chat", {"q": "marca'; drop table x;--", "limite": 5})
ok(c.log[0][0] == "set transaction read only", "primeira instrução é transação READ ONLY")
ok(c.log[1] == ("select * from chat_design.buscar_cliente_chat(%s, %s)", ("marca'; drop table x;--", 5)), "SQL fixo; entrada do usuário só como parâmetro, nunca concatenada")
ok(rows == [{"cliente_id": str(CID), "nome_exibicao": "Marca A", "atualizado_em": "2026-01-01 00:00:00"}], "linhas viram dict com uuid/data em texto")
ok(c.closed and c.rolled, "transação revertida e conexão fechada")

# 2) logos
c, t = mk(([("item_id",), ("storage_path",), ("mime_type",), ("ativo",)], [(None, f"{CID}/logo.png", "image/png", True)]))
r = t.logos(CID)
ok(r[0]["storage_path"].endswith("logo.png") and c.log[1][1] == (str(CID),) and "tipo = 'logo'" in c.log[1][0] and "limit 3" in c.log[1][0], "logos: consulta fixa por cliente, no máximo 3")

# 3) allowlist: função desconhecida, get genérico e injeção por nome de função são recusados sem abrir conexão
c, t = mk()
for fn in ("pg_sleep", "buscar_cliente_chat; drop table clientes", "public.clientes", ""):
    try: t.rpc(fn, {}); ok(False, f"rpc {fn!r} deveria ser recusado")
    except cp.ProviderError: ok(not c.log, f"rpc {fn!r} recusado sem tocar no banco")
try: t.get("clientes", {}); ok(False, "get genérico deveria ser recusado")
except cp.ProviderError: ok(not c.log, "get genérico recusado")

# 4) falha do driver: mensagem neutra, sem host/usuário/senha, conexão fechada
c, t = mk(fail=True)
try: t.rpc("carregar_cliente_chat", {"p_cliente_id": str(CID)}); ok(False, "falha deveria virar ProviderError")
except cp.ProviderError as e:
    m = str(e); ok("secret" not in m and "chat_design_ro" not in m and "password" not in m, f"erro sem vazamento: {m!r}"); ok(c.closed, "conexão fechada após falha")
class PgErr(Exception): pass
def authfail(): raise PgErr({"S": "FATAL", "C": "28P01", "M": "password authentication failed for user chat_design_ro", "H": "hunter2@db.secret"})
try: cp.PgTransport(authfail).rpc("buscar_cliente_chat", {"q": "a", "limite": 1}); ok(False, "auth deveria falhar")
except cp.ProviderError as e: ok("28P01" in str(e) and "hunter2" not in str(e) and "secret" not in str(e) and "chat_design_ro" not in str(e), f"diagnóstico só com o código SQLSTATE: {e}")
def boom(): raise OSError("could not connect to server at db.secret.supabase.co:5432 with password hunter2")
try: cp.PgTransport(boom).rpc("buscar_cliente_chat", {"q": "a", "limite": 1}); ok(False, "falha de conexão deveria virar ProviderError")
except cp.ProviderError as e: ok("hunter2" not in str(e) and "secret" not in str(e), "falha de conexão também sem vazamento")

# 5) provedor completo sobre o transporte: elegível, não elegível e pessoa física
res = (["cliente_id","compra_id","nome_exibicao","nome_origem","pessoa_fisica","setor","subsegmento","paleta","tipografia","tom","publico_alvo","descricao_marca","site_url","instagram_handle","atualizado_em"],
       [(CID, uuid.uuid4(), "Marca A", "nome_fantasia", False, "Alimentação", None, ["#FF0000"], "Inter", "Calorosa", "Famílias", "Sabor de casa", "https://a.test", "@a", None)])
c, t = mk(([(n,) for n in res[0]], res[1])); prov = cp.SupabaseClientProvider(t)
ctx = prov.load(str(CID))
ok(ctx["name"] == "Marca A" and ctx["palette"] == ["#FF0000"] and ctx["_display_name"] == "Marca A", "load: contexto da marca vindo do Postgres")
c, t = mk(([(n,) for n in res[0]], [])); 
try: cp.SupabaseClientProvider(t).load(str(CID)); ok(False, "0 linhas deveria ser NotFound")
except cp.NotFound: ok(True, "0 linhas = não elegível (NotFound), diferente de falha de banco")

# 6) bytes de logo: sem asset configurado falha clara; com asset delega
c, t = mk()
try: t.post_bytes("chat-design-asset", {}); ok(False, "sem asset deveria falhar")
except cp.ProviderError as e: ok("CHAT_DESIGN_ASSET_KEY" in str(e), "sem Edge Function configurada: erro claro")
class FakeAsset:
    def post_bytes(self, p, pl): return (b"\x89PNG\r\n\x1a\nxxxx", "image/png")
c, t = mk(asset=FakeAsset())
raw, mime = cp.SupabaseClientProvider(t).fetch_asset(f"{CID}/logo.png")
ok(mime == "image/png" and raw.startswith(b"\x89PNG"), "bytes do logo pela função, validados por assinatura")

# 7) from_env: DSN seguro aceito; perigoso recusado
def env(**kv):
    old = {k: os.environ.get(k) for k in ("CHAT_DB_DSN","CHAT_DB_ENABLED","CHAT_DB_HOST","SUPABASE_URL","SUPABASE_READ_KEY","CHAT_DESIGN_ASSET_KEY")}
    for k in old: os.environ.pop(k, None)
    os.environ.update(kv)
    try: return cp.SupabaseClientProvider.from_env()
    finally:
        for k, v in old.items():
            os.environ.pop(k, None)
            if v is not None: os.environ[k] = v
GOOD = "postgresql://chat_design_ro.abcdefgh:s3nha%40x@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"
p = env(CHAT_DB_DSN=GOOD, CHAT_DB_ENABLED="1")
ok(p is not None and isinstance(p.t, cp.PgTransport), "DSN do papel chat_design_ro no pooler do Supabase é aceito")
ok(env(CHAT_DB_DSN=GOOD) is None, "sem CHAT_DB_ENABLED=1 fica desligado")
for bad in ("postgresql://postgres:x@db.abc.supabase.co:5432/postgres",                 # superusuário
            "postgresql://service_role:x@db.abc.supabase.co:5432/postgres",
            "postgresql://chat_design_ro:x@evil.example.com:5432/postgres",             # host fora da allowlist
            "postgresql://chat_design_ro@db.abc.supabase.co:5432/postgres",             # sem senha
            "postgresql://chat_design_ro:x@db.abc.supabase.co:5432/postgres?sslmode=disable",
            "mysql://chat_design_ro:x@db.abc.supabase.co/x", "lixo"):
    ok(env(CHAT_DB_DSN=bad, CHAT_DB_ENABLED="1") is None, f"DSN recusado: {bad.split('@')[-1][:40]}")
ok(env(CHAT_DB_DSN="postgresql://chat_design_ro:x@db.corp.test:5432/postgres", CHAT_DB_ENABLED="1", CHAT_DB_HOST="db.corp.test") is not None, "CHAT_DB_HOST permite host próprio")

# 8) driver ausente: erro neutro (o import é preguiçoso)
sys.modules["pg8000"] = None
try: cp._pg8000_connect("h", 5432, "chat_design_ro", "x", "postgres", True); ok(False, "sem driver deveria falhar")
except cp.ProviderError as e: ok("pg8000" in str(e), "sem pg8000 instalado: erro claro, sem derrubar o servidor")

# 9) TLS: a CA do Supabase está no repositório, é um certificado válido e entra no pacote da Vercel; verificação nunca desligada
import json, ssl as _ssl
ok(os.path.isfile(cp.SUPABASE_CA), "certificado raiz do Supabase está no repositório")
ctx = cp._tls_context("aws-0-sa-east-1.pooler.supabase.com")
ok(ctx.verify_mode == _ssl.CERT_REQUIRED and ctx.check_hostname, "contexto TLS do Supabase exige certificado e confere o nome do servidor")
ok(len(ctx.get_ca_certs()) == 1 and "Supabase Root 2021 CA" in str(ctx.get_ca_certs()[0].get("subject")), "confia só na CA do Supabase para hosts do Supabase")
c2 = cp._tls_context("db.corp.test"); ok(c2.verify_mode == _ssl.CERT_REQUIRED and c2.check_hostname, "host próprio também verifica certificado e nome")
inc = json.load(open(pathlib.Path(__file__).resolve().parent.parent / "vercel.json"))["functions"]["api/index.py"]["includeFiles"]
ok("test/supabase_ca_2021.pem" in inc, "vercel.json empacota o certificado na função")

print("TODOS OK" if not fails else f"{len(fails)} FALHA(S)")
sys.exit(1 if fails else 0)
