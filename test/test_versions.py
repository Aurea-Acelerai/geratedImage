#!/usr/bin/env python3
"""Testes de versions.py (pai/filho de imagens). Sem rede e sem custo.

  cd test && python3 -I test_versions.py
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import store as st  # noqa: E402
import versions as vs  # noqa: E402

N = {"ok": 0}


def ok(cond, msg):
    print(("OK   " if cond else "FALHA"), msg)
    if not cond:
        sys.exit(1)
    N["ok"] += 1


def raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False


def rec(i, parent=None, **kw):
    return {"id": i, "parent_id": parent, "model": "m", "size": "1024x1024", "prompt_sha": vs.sha12("p" + i), **kw}


def test_base_of():
    ok(vs.base_of([]) == {"kind": None, "image_id": None, "asset_id": None, "ambiguous": False}, "sem entradas: sem base")
    ok(vs.base_of([{"kind": "logo", "id": "a1"}])["kind"] is None, "logo não é base")
    b = vs.base_of([{"kind": "logo"}, {"kind": "alvo", "src_image_id": "img1", "name": "img1.png"}])
    ok(b["kind"] == "generated" and b["image_id"] == "img1" and b["asset_id"] is None and not b["ambiguous"], "alvo vindo de imagem gerada: pai = a imagem")
    b = vs.base_of([{"kind": "alvo", "id": "asset9", "name": "foto.png"}])
    ok(b["kind"] == "attachment" and b["asset_id"] == "asset9" and b["image_id"] is None, "alvo anexado: sem pai gerado, guarda o asset")
    b = vs.base_of([{"kind": "variacao", "src_image_id": "v1"}])
    ok(b["kind"] == "generated" and b["image_id"] == "v1", "variação também tem pai")
    ok(vs.base_of([{"kind": "alvo", "src_image_id": "a"}, {"kind": "variacao", "src_image_id": "b"}])["ambiguous"], "duas bases são marcadas como ambíguas")


def test_log(make_store):
    s = make_store()
    log = vs.VersionLog(lambda: s)
    r = log.add("cli1", rec("a1", model="gpt-image-2.5-sunburst"))
    ok(r["created"] and log.get("cli1", "a1")["model"] == "gpt-image-2.5-sunburst", f"[{s.name}] grava e lê o registro")
    ok(log.get("cli1", "naoexiste") is None and log.get("outro", "a1") is None, f"[{s.name}] inexistente e outro escopo não aparecem")
    ok(raises(lambda: log.add("cli1", rec("a1"))), f"[{s.name}] id repetido é recusado")
    ok(raises(lambda: log.add("cli1", rec("a2", parent="a2"))), f"[{s.name}] auto-pai é recusado")
    for bad_scope, bad_id in (("../x", "a9"), ("cli1", "../a9"), ("cli1", ""), ("", "a9"), ("cli 1", "a9"), ("cli1", "A9")):
        ok(raises(lambda: log.add(bad_scope, rec(bad_id))), f"[{s.name}] id/escopo hostil é recusado ({bad_scope!r}, {bad_id!r})")
    ok(not any(".." in k for k in s.list("")), f"[{s.name}] nada foi gravado fora de versions/")
    ok(raises(lambda: log.add("cli1", rec("a3", parent="../../etc"))), f"[{s.name}] pai com formato inválido é recusado")
    log.add("cli1", rec("b1", parent="a1", intent="edit"))
    log.add("cli1", rec("c1", parent="b1", intent="edit"))
    log.add("cli1", rec("b2", parent="a1", intent="variation"))
    ok(log.children("cli1", "a1") == ["b1", "b2"] and log.children("cli1", "b1") == ["c1"] and log.children("cli1", "c1") == [], f"[{s.name}] filhos listados")
    ok(log.lineage("cli1", "c1") == {"chain": ["a1", "b1", "c1"], "complete": True, "reason": None}, f"[{s.name}] genealogia da raiz até a imagem")
    ok(log.lineage("cli1", "a1")["chain"] == ["a1"] and log.lineage("cli1", "a1")["complete"], f"[{s.name}] raiz tem cadeia de 1")
    l = log.lineage("cli1", "zz")
    ok(l["chain"] == [] and not l["complete"] and "sem registro" in l["reason"], f"[{s.name}] imagem sem registro: cadeia vazia e motivo")
    log.add("cli1", rec("d1", parent="perdido1"))
    l = log.lineage("cli1", "d1")
    ok(l["chain"] == ["d1"] and not l["complete"] and "perdido1" in l["reason"], f"[{s.name}] pai sem registro: cadeia parcial, incompleta e com o id que falta")
    # ciclo forçado por escrita direta (o add recusa auto-pai, mas arquivo corrompido pode existir)
    s.write_text("versions/cli1/e1.json", json.dumps(rec("e1", parent="e2")))
    s.write_text("versions/cli1/e2.json", json.dumps(rec("e2", parent="e1")))
    l = log.lineage("cli1", "e1")
    ok(not l["complete"] and "ciclo" in l["reason"], f"[{s.name}] ciclo detectado, sem laço infinito")
    log.update("cli1", "c1", score=9.0, approved=True)
    ok(log.get("cli1", "c1")["score"] == 9.0 and log.get("cli1", "c1")["parent_id"] == "b1", f"[{s.name}] update acrescenta nota sem mexer no pai")
    ok(raises(lambda: log.update("cli1", "c1", parent_id="a1")) and raises(lambda: log.update("cli1", "c1", id="x")), f"[{s.name}] update não troca id nem pai")
    ok(raises(lambda: log.update("cli1", "nao1", score=1), KeyError), f"[{s.name}] update de inexistente falha")
    s.write_text("versions/cli1/lixo.json", "{não é json")
    ok(log.children("cli1", "a1") == ["b1", "b2"], f"[{s.name}] arquivo corrompido não derruba children")
    ok("PROMPT" not in json.dumps(log.get("cli1", "a1")) and "bytes" not in json.dumps(log.get("cli1", "a1")), f"[{s.name}] registro guarda hash, não prompt nem bytes")
    ok(len(vs.sha12("x")) == 12 and vs.sha12("x") == vs.sha12("x") and vs.sha12("x") != vs.sha12("y"), "sha12 estável e distinto")


def main():
    import tempfile
    print("== base_of")
    test_base_of()
    print("== VersionLog")
    test_log(lambda: st.MemoryStore())
    tmp = tempfile.mkdtemp()
    test_log(lambda: st.FileStore(tmp))
    print(f"\nTUDO OK ({N['ok']} verificações)")


if __name__ == "__main__":
    main()
