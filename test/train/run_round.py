#!/usr/bin/env python3
"""Executa uma rodada de treino: roda as tarefas de train/tasks.json pelo PRÓPRIO chat (mesmo pipeline do usuário),
guarda as imagens e um resumo, e conta quantas imagens foram geradas (custo). Só stdlib.

  python3 train/run_round.py --round 1                # as 3 tarefas
  python3 train/run_round.py --round 1 --tasks T1,T2  # só algumas
  python3 train/run_round.py --round 1 --budget 6     # para quando passar de 6 imagens geradas nesta rodada

Pré-requisito: servidor de TREINO no ar, com pasta de dados própria (nunca a de uso real):
  cd test && CHAT_DATA_DIR=$PWD/train_data python3 chat_server.py --port 8770
Saída: test/train_out/round_<N>/<tarefa>.png (final), <tarefa>_c<k>.png (tentativas), <tarefa>.json (resumo e passos).
"""
import argparse, base64, json, mimetypes, pathlib, shutil, sys, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "train_data"
OUT = ROOT / "train_out"
SPEC = json.loads((ROOT / "train" / "tasks.json").read_text(encoding="utf-8"))
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def call(port, path, body=None, timeout=60):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def ensure_client(port):
    st, state = call(port, "/api/state")
    hit = [c for c in state["clients"] if c["name"] == SPEC["client"]["name"]]
    if hit:
        cid = hit[0]["id"]
    else:
        st, r = call(port, "/api/client/new", {"name": SPEC["client"]["name"], "sector": SPEC["client"]["sector"]})
        cid = r["id"]
    ctx = {"id": cid, **SPEC["client"]}
    call(port, "/api/client/save", {"id": cid, "client": ctx})
    return cid


def ensure_assets(port, cid):
    st, cur = call(port, "/api/client", {"id": cid})
    have = {a["name"]: a for a in cur["assets"]}
    ids = {}
    for key, a in SPEC["assets"].items():
        if a["name"] in have:
            ids[key] = have[a["name"]]["id"]
            continue
        p = DATA / a["file"]
        st, r = call(port, "/api/asset", {"client": cid, "kind": a["kind"], "name": a["name"], "mime": MIME[p.suffix.lower()],
                                          "b64": base64.b64encode(p.read_bytes()).decode(), "alias": a["alias"]})
        if st != 200:
            sys.exit(f"não consegui enviar {a['name']}: {r}")
        ids[key] = r["asset"]["id"]
    return ids


def run_task(port, cid, ids, task, rnd, quality, review):
    conv = f"tr{rnd}{task['id'].lower()}{int(time.time()) % 100000}"
    body = {"client": cid, "conv": conv, "text": task["text"], "asset_ids": [ids[k] for k in task["assets"]], "size": task["size"],
            "quality": quality, "review": review, "mode": "marca", "improve": {"compare_raw": False}}
    st, j = call(port, "/api/chat", body)
    if st != 200:
        return {"task": task["id"], "erro": j.get("error", st)}
    job, since, steps, t0 = j["job"], 0, [], time.time()
    while time.time() - t0 < 420:
        time.sleep(2)
        st, p = call(port, "/api/job", {"id": job, "since": since})
        since = p["next"]
        steps += [s["text"] for s in p["steps"]]
        if p["status"] != "running":
            if p["status"] == "error":
                return {"task": task["id"], "erro": p["error"], "steps": steps}
            return {"task": task["id"], "message": p["message"], "steps": steps, "segundos": round(time.time() - t0)}
    return {"task": task["id"], "erro": "tempo esgotado (420 s)", "steps": steps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--tasks", default=",".join(t["id"] for t in SPEC["tasks"]))
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--quality", default="medium")
    ap.add_argument("--no-review", action="store_true")
    ap.add_argument("--budget", type=int, default=12, help="máximo de imagens geradas nesta rodada")
    a = ap.parse_args()
    cid = ensure_client(a.port)
    ids = ensure_assets(a.port, cid)
    outdir = OUT / f"round_{a.round}"
    outdir.mkdir(parents=True, exist_ok=True)
    total = 0
    for t in [t for t in SPEC["tasks"] if t["id"] in a.tasks.split(",")]:
        if total >= a.budget:
            print(f"{t['id']}: pulada (orçamento de {a.budget} imagens atingido)")
            continue
        res = run_task(a.port, cid, ids, t, a.round, a.quality, not a.no_review)
        (outdir / f"{t['id']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        if "message" not in res:
            print(f"{t['id']}: ERRO {res.get('erro')}")
            continue
        m = res["message"]
        total += m.get("generations", 1)
        for c in m.get("cycles", []):
            src = DATA / "chat_out" / cid / pathlib.Path(c["url"]).name
            if src.exists():
                shutil.copy(src, outdir / f"{t['id']}_c{c['cycle']}{src.suffix}")
        fin = DATA / "chat_out" / cid / pathlib.Path(m["url"]).name
        if fin.exists():
            shutil.copy(fin, outdir / f"{t['id']}{fin.suffix}")
        print(f"{t['id']} {t['title']}: nota {m.get('score')} {'APROVADA' if m.get('approved') else 'REPROVADA'} | vetos {m.get('veto')} | "
              f"{m.get('generations')} geração(ões) | {res['segundos']}s | alvo/entradas {[(i['kind'], i['name'][:22]) for i in m.get('inputs', [])]} | tamanho {m.get('size')}")
        for av in m.get("avisos") or []:
            print(f"    aviso: {av[:160]}")
    print(f"imagens geradas nesta rodada: {total}  (arquivos em {outdir})")


if __name__ == "__main__":
    main()
