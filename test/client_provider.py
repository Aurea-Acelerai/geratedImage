"""Clientes do chat: de onde vêm, como o texto do usuário é casado com um cliente e o que pode ir ao prompt.

- LocalClientProvider: os client.json que já existem (test/clients/<id>/client.json).
- SupabaseClientProvider: SOMENTE LEITURA, só no servidor, só pelas views propostas (docs/fontes-de-dados-clientes.md, seção 7.2).
  Fica DESLIGADO sem SUPABASE_URL e SUPABASE_READ_KEY. A chave só vai no cabeçalho da requisição: nunca em log, erro ou resposta.
- safe_context(): LISTA PERMITIDA de campos. Tudo o que vai ao prompt (run_comparison.py, critic.py) passa por ela.

Ligar CHAT_DB_ENABLED exige decisão humana (C13): expor o schema chat_design na API REST ou usar Postgres direto, ver
docs/proposta-acesso-leitura-chat.md. O transporte está isolado em Transport (get/rpc/post_bytes): trocar por um driver Postgres
não mexe no resto. Os nomes de objetos seguem o contrato dessa proposta (nada foi aplicado no banco).
"""
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

# Campos que podem ir ao prompt. Nunca CPF, telefone, e-mail, endereço, financeiro ou pagamento: o que não está aqui é descartado.
CONTEXT_FIELDS = ("id", "modo", "name", "sector", "audience", "tone", "palette", "typography", "image_style", "brand_description",
                  "site_url", "instagram_handle", "approved_references", "deliveries_last_30d")
_TEXT_FIELDS = {"id", "modo", "name", "sector", "audience", "tone", "typography", "image_style", "brand_description", "site_url", "instagram_handle"}
_PII = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.-]+"                                                    # e-mail
    r"|(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"                                   # CPF
    r"|(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)"                          # CNPJ
    r"|(?<!\d)(?:\+?55[\s.-]?)?(?:\(\d{2}\)|\d{2})[\s.-]?9?\d{4}[\s.-]?\d{4}(?!\d)"   # telefone: (11) 91234-5678, (11)91234-5678, 11 3456-7890
    r"|(?<!\d)\d{5}-\d{3}(?!\d)")                                                  # CEP
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _clean(v):
    v = str(v).strip()[:600]
    return "[dado pessoal removido]" if _PII.search(v) else v


def safe_context(raw):
    """Copia só os campos permitidos, com tipo checado; texto que parece CPF/CNPJ/telefone/e-mail é trocado por um aviso."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k in CONTEXT_FIELDS:
        v = raw.get(k)
        if v is None:
            continue
        if k in _TEXT_FIELDS:
            out[k] = _clean(v)
        elif k == "palette" and isinstance(v, list):
            out[k] = [c for c in v[:12] if isinstance(c, str) and _HEX.fullmatch(c)]
        elif k == "approved_references" and isinstance(v, list):
            out[k] = [_clean(x)[:200] for x in v[:20] if isinstance(x, str)]
        elif k == "deliveries_last_30d" and isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    return out


class ProviderError(Exception):
    """Falha ao consultar uma fonte. Nunca vira 'cliente não existe' (C2)."""


class NotFound(Exception):
    pass


class ClientProvider:
    name = "?"  # "local" | "banco": aparece em "(fonte: ...)"

    def list(self):  # -> [{"id","name","aliases":[...]}]
        raise NotImplementedError

    def load(self, cid, compra_id=None):  # -> contexto já filtrado por safe_context
        raise NotImplementedError

    def find(self, q, limit=20):  # -> [{"id","name",...}] cujo nome contém q (sem acento/caixa)
        n = norm(q or "")
        return [c for c in self.list() if n in norm(c["name"])][:limit]

    def search(self, text):
        """Candidatos citados no texto (palavra inteira, sem acento nem caixa)."""
        return _match(text, [dict(c, source=self.name) for c in self.list()])


class LocalClientProvider(ClientProvider):
    name = "local"

    def __init__(self, ids, read):
        self._ids, self._read = ids, read  # ids() -> [id]; read(id) -> dict do client.json (FileNotFoundError se não há)

    def list(self):
        out = []
        for i in self._ids():
            raw = self._read(i)
            out.append({"id": i, "name": str(raw.get("name") or i), "aliases": [a for a in (raw.get("aliases") or []) if isinstance(a, str)]
                        + [raw[k] for k in ("brand", "nome_fantasia", "brand_display_name") if isinstance(raw.get(k), str)]})
        return out

    def load(self, cid, compra_id=None):
        try:
            raw = self._read(cid)
        except FileNotFoundError:
            raise NotFound(cid)
        return safe_context(dict(raw, id=cid))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Nunca segue redirecionamento: o urllib reenviaria apikey/Authorization ao host de destino."""
    def redirect_request(self, *a, **k):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


class Transport:
    """Fala com o banco. Interface pequena para trocar PostgREST por um driver Postgres depois (get/rpc/post_bytes)."""
    MAX_BYTES = 10 * 1024 * 1024

    def get(self, path, params):  # -> lista de linhas (dict)
        raise NotImplementedError

    def rpc(self, fn, params):  # -> lista de linhas (dict)
        raise NotImplementedError

    def post_bytes(self, path, payload):  # -> (bytes, content-type)
        raise NotImplementedError


class HttpTransport(Transport):
    SCHEMA = "chat_design"

    def __init__(self, url, key, asset_key=None, timeout=5):
        self.url, self._key, self._asset_key, self.timeout = url.rstrip("/"), key, asset_key, timeout

    def _open(self, req):
        try:
            with _OPENER.open(req, timeout=self.timeout) as r:
                return r.read(self.MAX_BYTES + 1), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:  # mensagem sem URL nem chave
            raise ProviderError("banco indisponível (redirecionamento recusado)" if 300 <= e.code < 400 else f"banco indisponível (HTTP {e.code})")
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("banco indisponível (sem conexão ou tempo esgotado)")

    def _rows(self, url):
        raw, _ = self._open(urllib.request.Request(url, method="GET", headers={
            "apikey": self._key, "Authorization": f"Bearer {self._key}", "Accept": "application/json", "Accept-Profile": self.SCHEMA}))
        try:
            rows = json.loads(raw)
        except ValueError:
            raise ProviderError("banco indisponível (resposta inválida)")
        if not isinstance(rows, list):
            raise ProviderError("banco indisponível (resposta inesperada)")
        return [r for r in rows if isinstance(r, dict)]

    def get(self, path, params):
        return self._rows(f"{self.url}/rest/v1/{path}?" + urllib.parse.urlencode(params, safe=",."))

    def rpc(self, fn, params):
        return self._rows(f"{self.url}/rest/v1/rpc/{fn}?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}))

    def post_bytes(self, path, payload):
        if not self._asset_key:
            raise ProviderError("logo indisponível: falta CHAT_DESIGN_ASSET_KEY no servidor")
        return self._open(urllib.request.Request(f"{self.url}/functions/v1/{path}", method="POST", data=json.dumps(payload).encode(),
                                                 headers={"x-chat-design-key": self._asset_key, "Content-Type": "application/json"}))


def _magic(raw):
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


class SupabaseClientProvider(ClientProvider):
    """Contrato de docs/proposta-acesso-leitura-chat.md (schema chat_design, papel de leitura mínima). SOMENTE LEITURA.
    A elegibilidade (assinada e paga, não cancelada, não teste) é da view; este provedor não decide regra de negócio.
    DESABILITADO por padrão: precisa de SUPABASE_URL, SUPABASE_READ_KEY e CHAT_DB_ENABLED=1 (Q7 e Q8 pendentes)."""
    name = "banco"
    MAX_ASSET = 10 * 1024 * 1024
    ASSET_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}  # SVG recusado

    def __init__(self, transport):
        self.t = transport

    @classmethod
    def from_env(cls):
        url, key = os.getenv("SUPABASE_URL", "").strip(), os.getenv("SUPABASE_READ_KEY", "").strip()
        if os.getenv("CHAT_DB_ENABLED") != "1" or not url or not key:
            return None  # desligado: o chat segue com o provedor local ("fonte: local")
        try:
            p = urllib.parse.urlparse(url)
            host = (p.hostname or "").lower()
        except ValueError:
            return None
        local = p.scheme == "http" and host in ("127.0.0.1", "localhost")  # http só para o servidor falso dos testes
        expected = os.getenv("CHAT_DB_HOST", "").strip().lower()
        if p.username or p.password or p.query or p.fragment:
            return None  # credencial na URL, ou lixo na URL: recusa
        if not local and not (p.scheme == "https" and host and (host == expected or (not expected and host.endswith(".supabase.co")))):
            return None  # host inesperado: a chave nunca vai para ele
        return cls(HttpTransport(url, key, os.getenv("CHAT_DESIGN_ASSET_KEY", "").strip() or None))

    def find(self, q, limit=20):
        rows = self.t.rpc("buscar_cliente_chat", {"q": q, "limite": limit})
        return [{"id": str(r["cliente_id"]), "name": str(r["nome_exibicao"]), "aliases": [], "name_origin": r.get("nome_origem"), "pessoa_fisica": r.get("pessoa_fisica")}
                for r in rows if r.get("cliente_id") and r.get("nome_exibicao")]

    def list(self):
        return self.find(None, 50)

    def search(self, text):
        """A função só busca por trecho: consulta as palavras do texto (poucas) e confere palavra inteira aqui."""
        words = list(dict.fromkeys(w for w in norm(text).split() if len(w) >= 4))[:10]
        seen = {}
        for w in words:
            for c in self.find(w):
                seen[c["id"]] = dict(c, source=self.name)
        return _match(text, list(seen.values()))

    def load(self, cid, compra_id=None):
        if not re.fullmatch(r"[0-9a-fA-F-]{8,40}", str(cid)):
            raise NotFound(cid)
        rows = self.t.rpc("carregar_cliente_chat", {"p_cliente_id": cid})
        if not rows:
            raise NotFound(cid)  # 0 linhas = não elegível/inexistente (falha de rede é ProviderError, outra coisa)
        r = rows[0]
        ctx = safe_context({"id": str(cid), "name": r.get("nome_exibicao"), "sector": " / ".join(x for x in (r.get("setor"), r.get("subsegmento")) if x) or None,
                            "audience": r.get("publico_alvo"), "tone": r.get("tom"), "typography": r.get("tipografia"), "palette": r.get("paleta"),
                            "brand_description": r.get("descricao_marca"), "site_url": r.get("site_url"), "instagram_handle": r.get("instagram_handle")})
        ctx["_compra_id"] = str(r.get("compra_id") or "")
        ctx["_name_origin"] = r.get("nome_origem")
        ctx["_display_name"] = str(r.get("nome_exibicao") or "")  # só para a tela (chip); não vai ao prompt
        ctx["_pessoa_fisica"] = r.get("pessoa_fisica")  # True: o nome é de pessoa, não de marca; None = indeterminado
        if r.get("pessoa_fisica") is True:
            ctx.pop("name", None)  # nome de pessoa física nunca vai ao prompt como se fosse marca
        ctx["_sem_identidade"] = not r.get("paleta")  # marca ausente é "indisponível", nunca "sem cores" (C2)
        return ctx

    def logos(self, cid):
        """Logos ativos do cliente (caminhos no bucket) pela view; os bytes vêm de fetch_asset."""
        if not re.fullmatch(r"[0-9a-fA-F-]{8,40}", str(cid)):
            raise NotFound(cid)
        rows = self.t.get("vw_chat_logos_cliente", {"select": "item_id,storage_path,mime_type,ativo", "cliente_id": f"eq.{cid}", "tipo": "eq.logo", "order": "ordem", "limit": "3"})
        return [r for r in rows if r.get("ativo") and r.get("storage_path")]

    def fetch_asset(self, storage_path):
        """Bytes do logo pela Edge Function: valida caminho, tipo declarado, assinatura dos bytes e tamanho; nunca guarda URL."""
        if not re.fullmatch(r"[0-9a-fA-F-]{36}/[A-Za-z0-9_./-]+", str(storage_path)) or ".." in storage_path:
            raise ProviderError("logo indisponível: caminho inválido")
        raw, ctype = self.t.post_bytes("chat-design-asset", {"storage_path": storage_path})
        mime = ctype.split(";")[0].strip().lower()
        if mime not in self.ASSET_MIME:
            raise ProviderError(f"logo recusado: tipo {mime or 'desconhecido'} não permitido")
        if len(raw) > self.MAX_ASSET:
            raise ProviderError("logo recusado: maior que 10 MiB")
        if _magic(raw) != mime:
            raise ProviderError("logo recusado: o conteúdo não é a imagem declarada")
        return raw, mime


def merge_local(db_ctx, local_ctx):
    """Banco prevalece; a edição local só acrescenta o que o banco não tem (valor ausente ou vazio)."""
    out = dict(safe_context(local_ctx))
    out.update({k: v for k, v in db_ctx.items() if v not in (None, "", [])})
    return out


def _match(text, cands):
    """Candidatos cujo nome/apelido/marca aparece no texto como palavra inteira. Um nome que só existe dentro de outro nome
    mais longo também citado ('Sol' dentro de 'Padaria Sol') não conta."""
    t = f" {norm(text)} "
    hits = []
    for c in cands:
        for n in [c["name"], re.sub(r"\(.*?\)", " ", c["name"])] + list(c.get("aliases") or []):
            n = norm(n)
            if len(n) >= 3 and f" {n} " in t:
                hits.append((c, n))
    hits = [(c, n) for c, n in hits if not any(c2["id"] != c["id"] and n != n2 and f" {n} " in f" {n2} " for c2, n2 in hits)]
    out = {}
    for c, n in hits:
        out.setdefault((c["source"], c["id"]), c)
    return list(out.values())


def resolve(text, providers):
    """-> {"status": "match"|"ambiguous"|"none", "client": {...}, "question": str, "errors": [{"source","error"}]}.
    Empate ou ambiguidade NÃO escolhe; nenhum match não inventa; fonte que falhou é reportada, nunca vira 'sem cliente' calado."""
    found, errors = [], []
    for p in providers:
        try:
            found += p.search(text)
        except ProviderError as e:
            errors.append({"source": p.name, "error": str(e)})
    if len(found) == 1:
        return {"status": "match", "client": found[0], "errors": errors}
    if len(found) > 1:
        names = ["Cliente (pessoa física)" if c.get("pessoa_fisica") is True else c["name"] for c in found[:4]]  # nome de pessoa não vai para a conversa
        return {"status": "ambiguous", "candidates": found, "errors": errors,
                "question": "Qual cliente: " + ", ".join(names[:-1]) + (" ou " if len(names) > 1 else "") + names[-1] + "?"}
    return {"status": "none", "errors": errors}
