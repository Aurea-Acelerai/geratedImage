#!/usr/bin/env python3
"""Testes de tools/obsidian_sync.py com um vault falso em pasta temporária (nunca toca no vault real).

  cd test && python3 -I test_obsidian_sync.py
"""
import contextlib, io, json, os, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "tools"))
import obsidian_sync as osy  # noqa: E402

N = {"ok": 0}


def ok(cond, msg):
    print(("OK   " if cond else "FALHA"), msg)
    if not cond:
        sys.exit(1)
    N["ok"] += 1


def run(vault, dest, entries, apply=False):
    tmp = pathlib.Path(tempfile.mkdtemp())
    cfg = tmp / "cfg.json"
    cfg.write_text(json.dumps({"dest": str(dest), "files": entries}))
    argv = ["--source", str(vault), "--config", str(cfg), "--dest", str(dest), "--json"] + (["--apply"] if apply else [])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = osy.main(argv)
    out = json.loads(buf.getvalue())
    return code, {x["dest"]: x for x in out["actions"]}, out


def tree(p):
    return sorted(str(x.relative_to(p)) for x in p.rglob("*")) if p.exists() else []


def main():
    base = pathlib.Path(tempfile.mkdtemp())
    vault, dest = base / "vault", base / "repo" / "origin"
    (vault / "Agentes").mkdir(parents=True)
    (vault / "Agentes" / "a.md").write_text("# Agente A\nv1\n", encoding="utf-8")
    (vault / "Agentes" / "b.md").write_text("# Agente B\n", encoding="utf-8")
    E = [{"src": "Agentes/a.md", "dest": "a.md"}, {"src": "Agentes/b.md", "dest": "b.md"}]

    print("== dry-run")
    code, acts, _ = run(vault, dest, E)
    ok(code == 0 and acts["a.md"]["action"] == "novo" and acts["b.md"]["action"] == "novo", "dry-run planeja 2 arquivos novos")
    ok(not dest.exists(), "dry-run não grava nada (nem a pasta de destino, manifesto ou log)")
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            osy.main(["--config", "x"])
        ok(False, "sem --source deveria falhar")
    except SystemExit as e:
        ok(e.code == 2, "--source é obrigatório (origem explícita)")

    print("== apply")
    code, acts, out = run(vault, dest, E, apply=True)
    ok(out["written"] == 2 and (dest / "a.md").read_text(encoding="utf-8") == "# Agente A\nv1\n", "apply copia os arquivos")
    man = json.loads((dest / "MANIFEST.json").read_text())
    ok(man["files"]["a.md"]["sha256"] == osy.sha256((vault / "Agentes" / "a.md").read_bytes()) and man["files"]["a.md"]["size"] == 14, "manifesto guarda sha256 e tamanho corretos")
    log = [json.loads(x) for x in (dest / "SYNC_LOG.jsonl").read_text().splitlines()]
    ok(len(log) == 2 and {x["action"] for x in log} == {"novo"} and log[0]["new_sha256"], "log registra cada ação com hashes")
    ok(str(vault) not in (dest / "MANIFEST.json").read_text() + (dest / "SYNC_LOG.jsonl").read_text(), "o caminho absoluto do vault não vai para manifesto nem log")
    ok(not [x for x in tree(dest) if x.endswith(".tmp")], "nenhum arquivo temporário sobra")
    code, acts, out = run(vault, dest, E, apply=True)
    ok(code == 0 and out["written"] == 0 and all(x["action"] == "sem_mudanca" for x in acts.values()), "segunda execução é idempotente")

    print("== atualização e conflitos")
    (vault / "Agentes" / "a.md").write_text("# Agente A\nv2\n", encoding="utf-8")
    code, acts, out = run(vault, dest, E)
    ok(acts["a.md"]["action"] == "atualizar" and (dest / "a.md").read_text(encoding="utf-8").endswith("v1\n"), "origem mudou e destino intacto: planeja atualizar, dry-run não grava")
    code, acts, out = run(vault, dest, E, apply=True)
    ok((dest / "a.md").read_text(encoding="utf-8").endswith("v2\n") and any(x["action"] == "atualizar" for x in map(json.loads, (dest / "SYNC_LOG.jsonl").read_text().splitlines())), "apply atualiza e registra")
    (dest / "a.md").write_text("# edição local\n", encoding="utf-8")
    (vault / "Agentes" / "a.md").write_text("# Agente A\nv3\n", encoding="utf-8")
    code, acts, out = run(vault, dest, E, apply=True)
    ok(code == 2 and acts["a.md"]["action"] == "conflito" and (dest / "a.md").read_text(encoding="utf-8") == "# edição local\n", "destino editado localmente: conflito, nada sobrescrito")
    ok(json.loads((dest / "MANIFEST.json").read_text())["files"]["a.md"]["sha256"] != osy.sha256(b"# Agente A\nv3\n"), "manifesto não avança sobre conflito")
    (dest / "b.md").unlink()
    code, acts, _ = run(vault, dest, E, apply=True)
    ok(acts["b.md"]["action"] == "conflito" and not (dest / "b.md").exists(), "destino apagado localmente: conflito, não recria em silêncio")
    (dest / "c.md").write_text("outro\n", encoding="utf-8")
    (vault / "Agentes" / "c.md").write_text("diferente\n", encoding="utf-8")
    code, acts, _ = run(vault, dest, E + [{"src": "Agentes/c.md", "dest": "c.md"}], apply=True)
    ok(acts["c.md"]["action"] == "conflito" and (dest / "c.md").read_text() == "outro\n", "destino fora do manifesto com conteúdo diferente: conflito")
    (vault / "Agentes" / "d.md").write_text("igual\n", encoding="utf-8")
    (dest / "d.md").write_text("igual\n", encoding="utf-8")
    code, acts, _ = run(vault, dest, [{"src": "Agentes/d.md", "dest": "d.md"}], apply=True)
    ok(acts["d.md"]["action"] == "adotar" and "d.md" in json.loads((dest / "MANIFEST.json").read_text())["files"], "destino idêntico fora do manifesto é adotado sem reescrever")

    print("== nunca exclui")
    code, acts, _ = run(vault, dest, [{"src": "Agentes/d.md", "dest": "d.md"}], apply=True)
    ok(acts["a.md"]["action"] == "orfao" and (dest / "a.md").exists(), "arquivo fora da lista é órfão reportado, não excluído")
    (vault / "Agentes" / "d.md").unlink()
    code, acts, _ = run(vault, dest, [{"src": "Agentes/d.md", "dest": "d.md"}], apply=True)
    ok(code == 2 and acts["d.md"]["action"] == "origem_ausente" and (dest / "d.md").exists(), "origem removida: reporta, não exclui o destino")

    print("== contenção de caminho")
    outside = base / "fora.md"
    outside.write_text("segredo-nao-listado\n")
    (vault / "link.md").symlink_to(outside)
    (vault / "pasta_link").symlink_to(base)
    bad = [("../fora.md", "x1.md"), (str(outside), "x2.md"), ("Agentes/../../fora.md", "x3.md"), ("link.md", "x4.md"), ("pasta_link/fora.md", "x5.md"),
           ("Agentes/a.md", "../escapou.md"), ("Agentes/a.md", "sub/x.md"), ("Agentes/a.md", "/tmp/abs.md"), ("Agentes/a.md", ".oculto.md"), ("Agentes/a.md", "sem-extensao"),
           ("Agentes/a.md", ""), ("", "x6.md"), ("Agentes\\a.md", "x7.md")]
    code, acts, out = run(vault, dest, [{"src": s, "dest": d} for s, d in bad], apply=True)
    errs = [x for x in out["actions"] if x["action"] in ("erro", "origem_ausente")]
    ok(code == 2 and len(errs) == len(bad), f"{len(bad)} caminhos hostis ou inválidos recusados")
    ok(not (base / "escapou.md").exists() and not (base / "repo" / "escapou.md").exists() and not (dest / "sub").exists() and not pathlib.Path("/tmp/abs.md").exists(),
       "nada foi escrito fora da pasta de destino")
    ok(not any((dest / n).exists() for n in ("x1.md", "x2.md", "x3.md", "x4.md", "x5.md")), "nada do que está fora da origem foi copiado")
    (vault / "Agentes" / "t.txt").write_text("x")
    code, acts, _ = run(vault, dest, [{"src": "Agentes/t.txt", "dest": "t.md"}])
    ok(acts["t.md"]["action"] == "erro" and ".md" in acts["t.md"]["reason"], "só arquivos .md")
    (vault / "Agentes" / "grande.md").write_text("x" * (osy.MAX_BYTES + 1))
    code, acts, _ = run(vault, dest, [{"src": "Agentes/grande.md", "dest": "grande.md"}])
    ok(acts["grande.md"]["action"] == "erro" and "acima" in acts["grande.md"]["reason"], "arquivo acima do limite é recusado")
    (vault / "Agentes" / "bin.md").write_bytes(b"\xff\xfe\x00\x80")
    code, acts, _ = run(vault, dest, [{"src": "Agentes/bin.md", "dest": "bin.md"}])
    ok(acts["bin.md"]["action"] == "erro" and "UTF-8" in acts["bin.md"]["reason"], "arquivo que não é UTF-8 é recusado")

    print("== segredos")
    fake_jwt = "eyJ" + "A" * 30 + "." + "B" * 30 + "." + "C" * 20
    for label, body in (("jwt", f"token {fake_jwt}"), ("chave_sk", "key sk-" + "a" * 30), ("token_sbp", "sbp_" + "b" * 30), ("chave_privada", "-----BEGIN RSA PRIVATE KEY-----\nMARCADOR-UNICO-9")):
        (vault / "Agentes" / "s.md").write_text(body)
        code, acts, out = run(vault, dest, [{"src": "Agentes/s.md", "dest": "s.md"}], apply=True)
        ok(acts["s.md"]["action"] == "erro" and label in acts["s.md"]["reason"] and not (dest / "s.md").exists(), f"segredo ({label}) não é copiado")
        ok(body.split()[-1] not in json.dumps(out), f"o valor do segredo ({label}) não aparece no relatório")
    print(f"\nTUDO OK ({N['ok']} verificações)")


if __name__ == "__main__":
    main()
