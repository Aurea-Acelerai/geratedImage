#!/usr/bin/env python3
"""Armazenamento do chat atrás de uma interface pequena (docs/12, passo 1).

Tudo o que o servidor guarda (clientes, biblioteca, imagens geradas, conversas, logs, estado das tarefas) passa por um
`Store`. Chaves são caminhos relativos com "/" (ex.: "clients/71/client.json", "chat_out/71/abc.png",
"conversations/71/x.json", "logs/events.jsonl", "jobs/<id>.json").

  FileStore(root)   disco local: o comportamento de sempre (padrão). Só stdlib.
  MemoryStore()     em memória: para testes (STORE=memory). Não sobrevive ao processo.
  BlobStore()       Vercel Blob (STORE=blob, ou automático quando BLOB_READ_WRITE_TOKEN existe). Usa o SDK oficial `vercel`.

Interface: read_bytes, write_bytes, exists, list(prefix), delete, append_line (pedidos no enunciado) e, além disso,
rename, mtime e set_mtime (o histórico de conversas ordena por data de modificação e o renomear não pode mudar a ordem).

O QUE NÃO FOI VERIFICADO CONTRA O SERVIÇO REAL (não havia loja Blob disponível; só a documentação e a leitura do código do SDK
`vercel` 0.12.x):
  * as chamadas do SDK (put_blob/get_blob/head_blob/query_blobs/delete_blob, API síncrona `vercel.blob.sync`) seguem a documentação
    e as assinaturas do pacote, mas nunca foram executadas aqui;
  * a loja precisa existir e ter acesso compatível com BLOB_ACCESS (padrão "private"; "public" tornaria as imagens acessíveis por URL);
  * leitura logo após escrita: a documentação diz que sobrescritas levam até ~60 s para atravessar o cache da CDN e o Python SDK
    não expõe `useCache=false`. Mitigação aqui: cache em memória das PRÓPRIAS escritas (mesma instância) e max-age curto
    (BLOB_MUTABLE_MAX_AGE, padrão 60). Outra instância ainda pode ler um JSON de conversa até ~60 s atrasado;
  * não há trava entre instâncias: duas mensagens simultâneas da mesma conversa em instâncias diferentes podem perder um turno
    (CONV_LOCK só vale dentro de um processo). `etag`/`if_match` do SDK permitiria resolver; não foi feito;
  * append_line no Blob grava um objeto por linha (<chave>.parts/<ns>-<rand>) e read_bytes(chave) os junta; custo: uma operação
    por evento de log;
  * limites de tamanho de corpo/resposta das funções da Vercel (4,5 MB, de memória, não confirmado na documentação consultada).
"""
import errno, json, os, pathlib, posixpath, secrets, threading, time, mimetypes


def _check_key(key):
    if not isinstance(key, str) or not key or "\x00" in key or "\\" in key or key.startswith("/"):
        raise ValueError(f"chave inválida: {key!r}")
    if any(seg in ("", ".", "..") for seg in key.rstrip("/").split("/")):
        raise ValueError(f"chave inválida: {key!r}")
    return key


def _check_prefix(prefix):
    if prefix == "":
        return ""
    if not isinstance(prefix, str) or "\x00" in prefix or "\\" in prefix or prefix.startswith("/"):
        raise ValueError(f"prefixo inválido: {prefix!r}")
    if any(seg in (".", "..") for seg in prefix.split("/")):
        raise ValueError(f"prefixo inválido: {prefix!r}")
    return prefix


class Store:
    """Contrato. read_bytes de chave inexistente levanta FileNotFoundError; delete de chave inexistente não faz nada."""
    name = "abstract"

    def read_bytes(self, key): raise NotImplementedError
    def write_bytes(self, key, data, content_type=None): raise NotImplementedError
    def exists(self, key): raise NotImplementedError
    def list(self, prefix=""): raise NotImplementedError          # chaves completas que começam com prefix, ordenadas
    def delete(self, key): raise NotImplementedError
    def append_line(self, key, line): raise NotImplementedError   # acrescenta line + "\n" (str); nunca perde linhas
    def rename(self, src, dst): raise NotImplementedError
    def mtime(self, key): raise NotImplementedError               # segundos desde a época; FileNotFoundError se não existe
    def set_mtime(self, key, t): raise NotImplementedError

    # atalhos de texto/JSON
    def read_text(self, key): return self.read_bytes(key).decode("utf-8")
    def write_text(self, key, text, content_type=None): self.write_bytes(key, text.encode("utf-8"), content_type)


class FileStore(Store):
    name = "file"

    def __init__(self, root):
        self.root = pathlib.Path(root)
        self._lock = threading.Lock()

    def _p(self, key):
        p = (self.root / _check_key(key)).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError(f"chave fora da raiz: {key!r}")
        return p

    def read_bytes(self, key):
        p = self._p(key)
        if not p.is_file():
            raise FileNotFoundError(errno.ENOENT, "não existe", key)
        return p.read_bytes()

    def write_bytes(self, key, data, content_type=None):
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".{secrets.token_hex(3)}.tmp")  # troca atômica: leitor nunca vê arquivo pela metade
        tmp.write_bytes(data)
        tmp.replace(p)

    def exists(self, key):
        return self._p(key).is_file()

    def list(self, prefix=""):
        _check_prefix(prefix)
        base = self.root / posixpath.dirname(prefix) if "/" in prefix else self.root
        out = []
        if base.is_dir():
            for dp, _dirs, files in os.walk(base):
                for f in files:
                    if f.endswith(".tmp"):
                        continue
                    k = pathlib.Path(dp, f).relative_to(self.root).as_posix()
                    if k.startswith(prefix):
                        out.append(k)
        return sorted(out)

    def delete(self, key):
        self._p(key).unlink(missing_ok=True)

    def append_line(self, key, line):
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def rename(self, src, dst):
        d = self._p(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        self._p(src).rename(d)

    def mtime(self, key):
        p = self._p(key)
        if not p.is_file():
            raise FileNotFoundError(errno.ENOENT, "não existe", key)
        return p.stat().st_mtime

    def set_mtime(self, key, t):
        p = self._p(key)
        st = p.stat()
        os.utime(p, (st.st_atime, t))


class MemoryStore(Store):
    """Mesmo contrato, em dicionário. Serve de fake do Blob nos testes de conformidade e no e2e (STORE=memory)."""
    name = "memory"

    def __init__(self):
        self._d = {}
        self._lock = threading.RLock()

    def read_bytes(self, key):
        with self._lock:
            if _check_key(key) not in self._d:
                raise FileNotFoundError(errno.ENOENT, "não existe", key)
            return self._d[key][0]

    def write_bytes(self, key, data, content_type=None):
        with self._lock:
            self._d[_check_key(key)] = (bytes(data), time.time())

    def exists(self, key):
        with self._lock:
            return _check_key(key) in self._d

    def list(self, prefix=""):
        _check_prefix(prefix)
        with self._lock:
            return sorted(k for k in self._d if k.startswith(prefix))

    def delete(self, key):
        with self._lock:
            self._d.pop(_check_key(key), None)

    def append_line(self, key, line):
        with self._lock:
            old = self._d.get(_check_key(key), (b"", 0))[0]
            self._d[key] = (old + line.encode("utf-8") + b"\n", time.time())

    def rename(self, src, dst):
        with self._lock:
            if _check_key(src) not in self._d:
                raise FileNotFoundError(errno.ENOENT, "não existe", src)
            self._d[_check_key(dst)] = self._d.pop(src)

    def mtime(self, key):
        with self._lock:
            if _check_key(key) not in self._d:
                raise FileNotFoundError(errno.ENOENT, "não existe", key)
            return self._d[key][1]

    def set_mtime(self, key, t):
        with self._lock:
            self._d[_check_key(key)] = (self._d[key][0], t)


class BlobStore(Store):
    """Vercel Blob pelo SDK oficial (`pip install vercel`), API SÍNCRONA (`vercel.blob.sync`): o servidor é síncrono e por
    threads, e a API assíncrona reaproveita uma sessão HTTP entre chamadas, o que não combina com um asyncio.run por chamada
    (cada um cria e fecha um laço de eventos). Credenciais: BLOB_READ_WRITE_TOKEN (o SDK lê do ambiente). Ver aviso no topo."""
    name = "blob"
    _META = "_meta/mtime/"   # sidecars de data de modificação (ver set_mtime)

    def __init__(self, access=None, sdk=None):
        self.access = access or os.getenv("BLOB_ACCESS") or "private"
        if sdk is None:
            from vercel.blob import sync as sdk  # noqa: PLC0415  (dependência só da Vercel; o modo local não precisa dela)
        self.sdk = sdk
        self.mutable_age = int(os.getenv("BLOB_MUTABLE_MAX_AGE") or 60)
        self._own = {}                      # chave -> (dados, instante): leitura da própria escrita (a CDN pode atrasar até ~60 s)
        self._own_lock = threading.Lock()
        self._own_ttl = max(self.mutable_age, 60) + 30

    # tipos mutáveis (JSON de estado, logs) recebem max-age curto; imagens e arquivos da biblioteca ficam com o padrão do serviço
    @staticmethod
    def _is_mutable(key):
        return key.endswith((".json", ".jsonl")) or ".parts/" in key

    def _not_found(self):
        return self.sdk.BlobNotFoundError

    def read_bytes(self, key):
        _check_key(key)
        with self._own_lock:
            hit = self._own.get(key)
            if hit and time.time() - hit[1] < self._own_ttl:
                return hit[0]
        try:
            return self.sdk.get_blob(key, access=self.access).body
        except self._not_found():
            parts = self._parts(key)
            if parts:
                return b"".join(self.sdk.get_blob(p, access=self.access).body for p in parts)
            raise FileNotFoundError(errno.ENOENT, "não existe", key)

    def write_bytes(self, key, data, content_type=None):
        _check_key(key)
        kw = {"cache_control_max_age": self.mutable_age} if self._is_mutable(key) else {}
        self.sdk.put_blob(key, bytes(data), access=self.access, content_type=content_type or mimetypes.guess_type(key)[0] or "application/octet-stream",
                          add_random_suffix=False, allow_overwrite=True, **kw)
        if self._is_mutable(key):
            with self._own_lock:
                self._own[key] = (bytes(data), time.time())

    def _head(self, key):
        try:
            return self.sdk.head_blob(key)
        except self._not_found():
            return None

    def _parts(self, key):
        return sorted(b.pathname for b in self.sdk.query_blobs(prefix=key + ".parts/"))

    def exists(self, key):
        _check_key(key)
        return self._head(key) is not None or bool(self._parts(key))

    def list(self, prefix=""):
        _check_prefix(prefix)
        names = {b.pathname for b in self.sdk.query_blobs(prefix=prefix or None)}
        names = {n for n in names if not n.startswith(self._META)}
        return sorted(n for n in names if n.startswith(prefix))

    def delete(self, key):
        _check_key(key)
        with self._own_lock:
            self._own.pop(key, None)
        self.sdk.delete_blob([key, self._META + key] + self._parts(key))  # inexistente é ignorado pelo serviço

    def append_line(self, key, line):
        _check_key(key)
        part = f"{key}.parts/{time.time_ns():020d}-{secrets.token_hex(3)}"
        self.sdk.put_blob(part, (line + "\n").encode("utf-8"), access=self.access, content_type="text/plain",
                          add_random_suffix=False, allow_overwrite=False, cache_control_max_age=self.mutable_age)

    def rename(self, src, dst):
        data = self.read_bytes(src)
        self.write_bytes(dst, data)
        self.delete(src)

    def mtime(self, key):
        h = self._head(_check_key(key))
        if h is None:
            raise FileNotFoundError(errno.ENOENT, "não existe", key)
        side = self._head(self._META + key)
        if side is not None and side.uploaded_at >= h.uploaded_at:  # sidecar gravado depois do conteúdo: vale o valor guardado
            try:
                return float(self.sdk.get_blob(self._META + key, access=self.access).body.decode())
            except Exception:  # noqa: BLE001
                pass
        return h.uploaded_at.timestamp()

    def set_mtime(self, key, t):
        _check_key(key)
        self.sdk.put_blob(self._META + key, repr(float(t)).encode(), access=self.access, content_type="text/plain",
                          add_random_suffix=False, allow_overwrite=True, cache_control_max_age=self.mutable_age)


def make_store(data_dir):
    """Escolha do backend: STORE=file|memory|blob; sem STORE, blob se BLOB_READ_WRITE_TOKEN existir, senão disco em data_dir."""
    kind = (os.getenv("STORE") or "").lower()
    if kind not in ("", "file", "memory", "blob"):
        raise ValueError(f"STORE inválido: {kind!r} (use file, memory ou blob)")
    if not kind:
        kind = "blob" if os.getenv("BLOB_READ_WRITE_TOKEN") else "file"
    if kind == "memory":
        return MemoryStore()
    if kind == "blob":
        return BlobStore()
    return FileStore(data_dir)
