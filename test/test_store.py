#!/usr/bin/env python3
"""Teste de conformidade do Store: as MESMAS verificações rodam em FileStore, MemoryStore e BlobStore (SDK falso).

  cd test && python3 -I test_store.py
"""
import json, pathlib, sys, tempfile, threading, time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import store as st  # noqa: E402
from fake_blob import FakeBlobSDK  # noqa: E402

N = {"ok": 0}


def ok(cond, msg):
    print(("OK   " if cond else "FALHA"), msg)
    if not cond:
        sys.exit(1)
    N["ok"] += 1


def conformance(s):
    n = s.name
    ok(not s.exists("a/b.json"), f"[{n}] chave inexistente não existe")
    try:
        s.read_bytes("a/b.json"); ok(False, f"[{n}] ler inexistente deveria falhar")
    except FileNotFoundError:
        ok(True, f"[{n}] ler inexistente levanta FileNotFoundError")
    s.delete("a/nada.json"); ok(True, f"[{n}] apagar inexistente é silencioso")
    s.write_bytes("a/b.json", b'{"x": 1}'); s.write_bytes("a/c/d.png", b"\x89PNG\x00\xff")
    ok(s.read_bytes("a/b.json") == b'{"x": 1}' and s.read_text("a/b.json") == '{"x": 1}', f"[{n}] escrever e ler")
    ok(s.read_bytes("a/c/d.png") == b"\x89PNG\x00\xff", f"[{n}] bytes binários idênticos")
    s.write_bytes("a/b.json", b"novo"); ok(s.read_bytes("a/b.json") == b"novo", f"[{n}] sobrescrever")
    ok(s.exists("a/b.json") and s.exists("a/c/d.png"), f"[{n}] exists")
    s.write_text("a/t.txt", "acentuação ção"); ok(s.read_text("a/t.txt") == "acentuação ção", f"[{n}] texto UTF-8")
    ok(s.list("a/") == ["a/b.json", "a/c/d.png", "a/t.txt"], f"[{n}] list(prefixo/) recursivo e ordenado: {s.list('a/')}")
    ok(s.list("a/c/") == ["a/c/d.png"] and s.list("zzz/") == [], f"[{n}] list de subpasta e de prefixo vazio")
    s.write_bytes("ab/x.json", b"1"); ok(s.list("a/") == ["a/b.json", "a/c/d.png", "a/t.txt"], f"[{n}] 'a/' não pega 'ab/'")
    s.delete("a/b.json"); ok(not s.exists("a/b.json") and "a/b.json" not in s.list("a/"), f"[{n}] delete")
    # append: nunca perde linhas, nem em threads
    ths = [threading.Thread(target=lambda i=i: [s.append_line("logs/e.jsonl", json.dumps({"i": i, "j": j})) for j in range(5)]) for i in range(4)]
    [t.start() for t in ths]; [t.join() for t in ths]
    lines = s.read_text("logs/e.jsonl").splitlines()
    ok(len(lines) == 20 and len({l for l in lines}) == 20 and all(json.loads(l) for l in lines), f"[{n}] append_line: 20 linhas de 4 threads, nenhuma perdida")
    ok(s.exists("logs/e.jsonl"), f"[{n}] exists vale para chave de append")
    s.append_line("logs/novo.jsonl", "um"); s.append_line("logs/novo.jsonl", "dois")
    ok(s.read_text("logs/novo.jsonl") == "um\ndois\n", f"[{n}] append em chave nova, ordem preservada")
    # rename / mtime
    s.write_bytes("c/1.json", b"conteudo")
    s.rename("c/1.json", "c/1.json.corrompido-9")
    ok(not s.exists("c/1.json") and s.read_bytes("c/1.json.corrompido-9") == b"conteudo", f"[{n}] rename")
    s.write_bytes("c/old.json", b"1"); time.sleep(0.05); s.write_bytes("c/new.json", b"2")
    ok(s.mtime("c/new.json") > s.mtime("c/old.json"), f"[{n}] mtime cresce com a escrita")
    t_old = s.mtime("c/old.json"); time.sleep(0.05)
    s.write_bytes("c/old.json", b"1b"); s.set_mtime("c/old.json", t_old)
    ok(abs(s.mtime("c/old.json") - t_old) < 0.01 and s.mtime("c/old.json") < s.mtime("c/new.json"), f"[{n}] set_mtime preserva a ordem (renomear conversa)")
    time.sleep(0.05); s.write_bytes("c/old.json", b"1c")
    ok(s.mtime("c/old.json") > s.mtime("c/new.json"), f"[{n}] nova escrita depois de set_mtime volta a atualizar a data")
    try:
        s.mtime("c/nao.json"); ok(False, f"[{n}] mtime de inexistente")
    except FileNotFoundError:
        ok(True, f"[{n}] mtime de inexistente levanta FileNotFoundError")
    s.delete("c/old.json"); ok(not s.exists("c/old.json"), f"[{n}] delete limpa também o sidecar de mtime")
    ok(all(not k.startswith("_meta/") for k in s.list("")), f"[{n}] sidecars internos não aparecem em list")
    # chaves perigosas
    for bad in ("../x", "a/../../x", "/abs", "a//b", "", "a\\b", "a/./b"):
        try:
            s.write_bytes(bad, b"x"); ok(False, f"[{n}] chave {bad!r} deveria ser recusada")
        except ValueError:
            ok(True, f"[{n}] recusa chave {bad!r}")


def main():
    with tempfile.TemporaryDirectory() as d:
        fs = st.FileStore(d)
        conformance(fs)
        ok(not any(p.name.endswith(".tmp") for p in pathlib.Path(d).rglob("*")), "[file] nenhum .tmp sobra")
        ok(json.loads((pathlib.Path(d) / "logs" / "e.jsonl").read_text().splitlines()[0]) is not None, "[file] logs/e.jsonl é um arquivo comum de linhas")
    conformance(st.MemoryStore())
    sdk = FakeBlobSDK()
    bs = st.BlobStore(access="private", sdk=sdk)
    conformance(bs)
    ok(("put", "a/c/d.png") in sdk.calls, "[blob] usa put_blob com o pathname da chave")
    # BlobStore: acesso incompatível com a loja falha alto (a documentação exige access igual ao da loja)
    try:
        st.BlobStore(access="public", sdk=FakeBlobSDK("private")).write_bytes("x/y.json", b"1"); ok(False, "[blob] access errado deveria falhar")
    except Exception as e:  # noqa: BLE001
        ok("access" in str(e), "[blob] access diferente do da loja falha com erro claro")
    # leitura da própria escrita: a CDN pode atrasar; a instância enxerga o que acabou de gravar
    class Stale(FakeBlobSDK):
        def get_blob(self, pathname, *, access):
            r = super().get_blob(pathname, access=access)
            return type(r)(body=b"VELHO", metadata=r.metadata)
    b2 = st.BlobStore(access="private", sdk=Stale())
    b2.write_bytes("conversations/71/z.json", b'{"novo": true}')
    ok(b2.read_bytes("conversations/71/z.json") == b'{"novo": true}', "[blob] lê a própria escrita mesmo se a CDN devolver conteúdo velho")
    # seleção de backend
    import os
    for env, cls in (({"STORE": "memory"}, st.MemoryStore), ({"STORE": "file"}, st.FileStore), ({}, st.FileStore)):
        old = {k: os.environ.pop(k, None) for k in ("STORE", "BLOB_READ_WRITE_TOKEN")}
        os.environ.update(env)
        try:
            ok(isinstance(st.make_store("/tmp/x"), cls), f"make_store {env or 'sem env'} -> {cls.__name__}")
        finally:
            for k in ("STORE", "BLOB_READ_WRITE_TOKEN"):
                os.environ.pop(k, None)
            os.environ.update({k: v for k, v in old.items() if v is not None})
    try:
        os.environ["STORE"] = "xyz"; st.make_store("/tmp/x"); ok(False, "STORE inválido deveria falhar")
    except ValueError:
        ok(True, "STORE inválido é recusado")
    finally:
        os.environ.pop("STORE", None)
    print(f"\nTUDO OK ({N['ok']} verificações)")


if __name__ == "__main__":
    main()
