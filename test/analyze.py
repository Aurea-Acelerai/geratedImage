#!/usr/bin/env python3
"""Junta a avaliação humana cega (blind/ratings.csv + blind/key.json) com o log do teste (log.json).

  python analyze.py out/<timestamp>

Mostra por braço: nota humana média, % que aprovaria para o cliente, nota do critic, gerações por peça.
A decisão do teste usa a nota humana. O critic entra só para medir se ele concorda com as pessoas.
"""
import csv, json, pathlib, statistics, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from critic import pearson

NOMES = {"A": "A  Image API crua", "B": "B  nosso harness (hex)", "N": "N  nosso harness (cores por nome)", "C": "C  Responses API nativa"}


def main(d):
    d = pathlib.Path(d)
    log = json.loads((d / "log.json").read_text(encoding="utf-8"))
    key = json.loads((d / "blind" / "key.json").read_text(encoding="utf-8"))
    info = {(str(r["case"]), arm): v for r in log for arm, v in r.get("arms", {}).items() if "score" in v}
    rows = []
    for r in csv.DictReader(open(d / "blind" / "ratings.csv", encoding="utf-8")):
        if not r["nota_humana_0_10"].strip():
            continue
        k = key[r["arquivo"]]
        i = info.get((str(k["case"]), k["arm"]), {})
        rows.append({"arm": k["arm"], "case": str(k["case"]), "human": float(r["nota_humana_0_10"]),
                     "ok": r["aprovaria_para_cliente_sim_nao"].strip().lower() in ("sim", "s", "yes"),
                     "critic": i.get("score"), "gens": i.get("generations", 1)})
    if not rows:
        sys.exit("Nenhuma nota humana preenchida em blind/ratings.csv.")
    print(f"{len(rows)} imagens avaliadas\n")
    print(f"{'braço':36} {'n':>3} {'humano':>7} {'aprova':>7} {'critic':>7} {'ger./peça':>10}")
    for arm in "ABNC":
        rs = [x for x in rows if x["arm"] == arm]
        if not rs:
            continue
        cr = [x["critic"] for x in rs if x["critic"] is not None]
        print(f"{NOMES[arm]:36} {len(rs):>3} {statistics.mean(x['human'] for x in rs):>7.2f} "
              f"{100 * sum(x['ok'] for x in rs) / len(rs):>6.0f}% {statistics.mean(cr) if cr else float('nan'):>7.2f} "
              f"{statistics.mean(x['gens'] for x in rs):>10.1f}")
    print("\nPor caso (nota humana média):")
    cases = sorted({x["case"] for x in rows})
    print(f"{'caso':8}" + "".join(f"{a:>8}" for a in "ABNC"))
    for c in cases:
        line = f"{c:8}"
        for arm in "ABNC":
            rs = [x["human"] for x in rows if x["case"] == c and x["arm"] == arm]
            line += f"{statistics.mean(rs):>8.1f}" if rs else f"{'-':>8}"
        print(line)
    pairs = [(x["critic"], x["human"]) for x in rows if x["critic"] is not None]
    if len(pairs) > 2:
        print(f"\nConcordância critic x humano (correlação): {pearson([p[0] for p in pairs], [p[1] for p in pairs])}")
        fa = sum(1 for x in rows if x["critic"] is not None and x["critic"] >= 8 and not x["ok"])
        print(f"Peças que o critic aprovaria (>= 8) e o humano reprovou: {fa} de {sum(1 for x in rows if not x['ok'])} reprovadas")
    print("\nLembrete: B e N otimizam contra o critic; a comparação justa é pela nota humana.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
