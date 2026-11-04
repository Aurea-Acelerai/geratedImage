#!/usr/bin/env python3
"""SDK `vercel.blob.sync` FALSO, em memória, só para testar o BlobStore sem loja real.

Imita APENAS o que a documentação e a leitura do pacote `vercel` 0.12 dizem: put_blob(pathname, body, *, access, content_type,
add_random_suffix, allow_overwrite, cache_control_max_age), get_blob(pathname, *, access) -> .body/.metadata, head_blob ->
.uploaded_at/.size/.etag, query_blobs(prefix=) iterador de .pathname, delete_blob(um ou lista), BlobNotFoundError. Não prova
nada sobre o serviço real (cache de CDN, limites, cobrança, erros de rede); prova a lógica do BlobStore em cima dessa interface.
"""
import datetime, hashlib, threading, time


class BlobError(Exception):
    pass


class BlobNotFoundError(BlobError, FileNotFoundError):
    pass


class _Obj:
    def __init__(self, body, ctype, t):
        self.body, self.content_type, self.uploaded_at = body, ctype, t
        self.size, self.etag = len(body), hashlib.md5(body).hexdigest()


class _R:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeBlobSDK:
    BlobNotFoundError = BlobNotFoundError
    BlobError = BlobError

    def __init__(self, access="private"):
        self.store_access = access
        self.objs = {}
        self.lock = threading.Lock()
        self.calls = []
        self._tick = 0.0

    def _now(self):  # relógio estritamente crescente: uploaded_at distingue escritas feitas em sequência
        self._tick = max(self._tick + 0.001, time.time())
        return datetime.datetime.fromtimestamp(self._tick, datetime.timezone.utc)

    def _acc(self, access):
        if access != self.store_access:
            raise BlobError(f"access={access!r} não bate com a loja ({self.store_access!r})")

    def put_blob(self, pathname, body, *, access, content_length=None, content_type=None, add_random_suffix=False,
                 allow_overwrite=False, cache_control_max_age=None):
        self._acc(access)
        assert isinstance(body, (bytes, bytearray, memoryview)), "o BlobStore deve enviar bytes"
        assert not add_random_suffix
        with self.lock:
            self.calls.append(("put", pathname))
            if pathname in self.objs and not allow_overwrite:
                raise BlobError("já existe e allow_overwrite=False")
            self.objs[pathname] = _Obj(bytes(body), content_type, self._now())
        return _R(pathname=pathname, url="https://fake/" + pathname)

    def get_blob(self, pathname, *, access):
        self._acc(access)
        with self.lock:
            self.calls.append(("get", pathname))
            if pathname not in self.objs:
                raise BlobNotFoundError(pathname)
            o = self.objs[pathname]
        return _R(body=o.body, metadata=_R(content_type=o.content_type))

    def head_blob(self, pathname):
        with self.lock:
            self.calls.append(("head", pathname))
            if pathname not in self.objs:
                raise BlobNotFoundError(pathname)
            o = self.objs[pathname]
        return _R(pathname=pathname, size=o.size, etag=o.etag, uploaded_at=o.uploaded_at, content_type=o.content_type)

    def query_blobs(self, *, prefix=None, page_size=None, cursor=None):
        with self.lock:
            self.calls.append(("list", prefix))
            items = [(k, o) for k, o in self.objs.items() if k.startswith(prefix or "")]
        return iter([_R(pathname=k, size=o.size, uploaded_at=o.uploaded_at, etag=o.etag) for k, o in sorted(items)])

    def delete_blob(self, target, *, if_match=None):
        with self.lock:
            for k in ([target] if isinstance(target, str) else list(target)):
                self.calls.append(("delete", k))
                self.objs.pop(k, None)
