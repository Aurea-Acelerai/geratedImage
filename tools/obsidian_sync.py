#!/usr/bin/env python3
"""Sincronização controlada Obsidian -> repositório (unidirecional). Só stdlib.

  python3 tools/obsidian_sync.py --source "/caminho/do/vault"            # dry-run (padrão): mostra o plano, não grava nada
  python3 tools/obsidian_sync.py --source "/caminho/do/vault" --apply    # grava o que é seguro

Regras:
- Origem explícita: --source é obrigatório (sem variável de ambiente nem caminho padrão).
- Só copia o que está listado em agents/obsidian-sync.json (lista de permissão, arquivo a arquivo, só .md).
- Manifesto (dest/MANIFEST.json) com sha256 de cada arquivo sincronizado. O caminho absoluto do vault nunca é gravado.
- Conflito nunca é resolvido em silêncio: arquivo de destino alterado localmente, destino que existe fora do manifesto
  com conteúdo diferente, ou destino apagado localmente => "conflito", nada é sobrescrito nem recriado.
- Nunca exclui: arquivo que saiu da lista ou sumiu da origem só é reportado ("órfão" / "origem ausente").
- Contenção de caminho: caminho de origem absoluto, com "..", symlink ou que resolva fora da origem é recusado;
  o nome de destino é um nome simples (sem diretórios) e confirmado dentro da pasta de destino.
- Arquivo com cara de segredo (JWT, chave sk-/sbp_/ghp_, chave privada…) não é copiado; só o NOME do padrão é reportado.
- Em --apply, cada ação vai para dest/SYNC_LOG.jsonl. Dry-run não grava nada (nem log).
- Código de saída: 0 sem conflito nem erro; 2 com conflito ou erro (as ações seguras ainda são aplicadas em --apply).
"""
import argparse, hashlib, json, os, re, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO / "agents" / "obsidian-sync.json"
MAX_BYTES = 256 * 1024
DEST_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.md$")
SECRET_PATTERNS = {
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}"),
    "chave_sk": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "token_sbp": re.compile(r"\bsbp_[A-Za-z0-9]{20,}"),
    "token_github": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "chave_aws": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "token_slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "chave_privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_manifest(dest):
    p = dest / "MANIFEST.json"
    if not p.exists():
        return {"version": 1, "files": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def safe_source(source_root, rel):
    """(Path, erro). Recusa absoluto, '..', symlink e qualquer caminho que resolva fora da origem."""
    if not rel or os.path.isabs(rel) or "\\" in rel or "\x00" in rel:
        return None, "caminho de origem inválido (vazio, absoluto ou com caractere proibido)"
    parts = Path(rel).parts
    if ".." in parts:
        return None, "caminho de origem com '..'"
    cur = source_root
    for part in parts:
        cur = cur / part
        if cur.is_symlink():
            return None, "caminho de origem passa por symlink"
    try:
        resolved = cur.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return None, "origem ausente"
    try:
        resolved.relative_to(source_root.resolve())
    except ValueError:
        return None, "caminho de origem resolve fora da pasta de origem"
    if not resolved.is_file():
        return None, "origem não é arquivo regular"
    return resolved, None


def plan(source_root, dest, entries):
    """Lista de ações. Cada uma: {action, dest, src, reason?, old_sha?, new_sha?, _data?}."""
    manifest = load_manifest(dest)
    mfiles = manifest["files"]
    dest_real = dest.resolve()
    out, listed = [], set()
    for e in entries:
        src_rel, name = e.get("src", ""), e.get("dest", "")
        item = {"dest": name, "src": src_rel}
        if not isinstance(name, str) or not DEST_NAME.match(name):
            out.append(dict(item, action="erro", reason="nome de destino inválido (use um nome simples terminado em .md, sem diretórios)"))
            continue
        listed.add(name)
        target = dest / name
        if target.parent.resolve() != dest_real:
            out.append(dict(item, action="erro", reason="destino fora da pasta de destino"))
            continue
        if target.is_symlink():
            out.append(dict(item, action="erro", reason="destino é symlink"))
            continue
        if not src_rel.lower().endswith(".md"):
            out.append(dict(item, action="erro", reason="só arquivos .md"))
            continue
        path, err = safe_source(source_root, src_rel)
        if err:
            out.append(dict(item, action="origem_ausente" if err == "origem ausente" else "erro", reason=err))
            continue
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            out.append(dict(item, action="erro", reason=f"origem com {len(data)} bytes, acima de {MAX_BYTES}"))
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            out.append(dict(item, action="erro", reason="origem não é UTF-8"))
            continue
        hits = [n for n, rx in SECRET_PATTERNS.items() if rx.search(text)]
        if hits:
            out.append(dict(item, action="erro", reason="possível segredo na origem (" + ", ".join(hits) + "); não copiado"))
            continue
        new_sha = sha256(data)
        item.update(new_sha=new_sha, _data=data)
        m = mfiles.get(name)
        if not target.exists():
            if m:
                out.append(dict(item, action="conflito", reason="destino apagado localmente; não recrio em silêncio", old_sha=m["sha256"]))
            else:
                out.append(dict(item, action="novo"))
            continue
        cur_sha = sha256(target.read_bytes())
        if not m:
            out.append(dict(item, action="adotar", old_sha=cur_sha) if cur_sha == new_sha else
                       dict(item, action="conflito", reason="destino existe fora do manifesto com conteúdo diferente", old_sha=cur_sha))
        elif cur_sha != m["sha256"]:
            out.append(dict(item, action="conflito", reason="destino alterado localmente desde a última sincronização", old_sha=cur_sha))
        elif new_sha == m["sha256"]:
            out.append(dict(item, action="sem_mudanca", old_sha=cur_sha))
        else:
            out.append(dict(item, action="atualizar", old_sha=cur_sha))
    for name in sorted(set(mfiles) - listed):
        out.append({"action": "orfao", "dest": name, "src": mfiles[name].get("src"), "reason": "fora da lista de sincronização; não excluo"})
    return out


def apply_plan(dest, actions):
    dest.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(dest)
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    log = []
    for a in actions:
        if a["action"] not in ("novo", "atualizar", "adotar"):
            continue
        target = dest / a["dest"]
        if a["action"] != "adotar":
            fd, tmp = tempfile.mkstemp(dir=str(dest), prefix=".sync-", suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(a["_data"])
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        manifest["files"][a["dest"]] = {"src": a["src"], "sha256": a["new_sha"], "size": len(a["_data"]), "synced_at": now}
        log.append({"t": now, "action": a["action"], "dest": a["dest"], "src": a["src"], "old_sha256": a.get("old_sha"), "new_sha256": a["new_sha"]})
    if log:
        (dest / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with open(dest / "SYNC_LOG.jsonl", "a", encoding="utf-8") as f:
            for line in log:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return log


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True, help="pasta do vault (explícita, sem padrão)")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--dest", default=None, help="pasta de destino (padrão: a do arquivo de configuração)")
    ap.add_argument("--apply", action="store_true", help="grava (sem isto é dry-run)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    source = Path(a.source).expanduser()
    if not source.is_dir():
        print(f"origem não é uma pasta: {source}", file=sys.stderr)
        return 2
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    dest_rel = a.dest or cfg["dest"]
    dest = Path(dest_rel) if os.path.isabs(dest_rel) else REPO / dest_rel
    actions = plan(source, dest, cfg["files"])
    written = apply_plan(dest, actions) if a.apply else []
    view = [{k: v for k, v in x.items() if not k.startswith("_")} for x in actions]
    if a.json:
        print(json.dumps({"mode": "apply" if a.apply else "dry-run", "actions": view, "written": len(written)}, ensure_ascii=False, indent=2))
    else:
        print(("APLICADO" if a.apply else "DRY-RUN (nada foi gravado)") + f" · {len(actions)} item(ns)")
        for x in view:
            print(f"  {x['action']:<14} {x['dest']}" + (f"  [{x['reason']}]" if x.get("reason") else ""))
    return 2 if any(x["action"] in ("conflito", "erro", "origem_ausente") for x in actions) else 0


if __name__ == "__main__":
    sys.exit(main())
