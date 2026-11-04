#!/usr/bin/env python3
"""Critic de imagem nosso: rubrica em prompts/rubric.json, prompt em prompts/critic.system.md.

O critic é independente de fornecedor: `review()` recebe uma função `vlm(system, texto, imagens) -> str`.
`openai_vlm()` é um adaptador; para outro backend, escreva outro adaptador com a mesma assinatura.

Uso:
  python critic.py --self-test                      # sem API
  python critic.py --calibrate calibration/labels.csv --dry-run
  OPENAI_API_KEY=... python critic.py --calibrate calibration/labels.csv
"""
import argparse, base64, csv, json, os, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent
RUBRIC_PATH = ROOT.parent / "prompts" / "rubric.json"
CRITIC_PROMPT_PATH = ROOT.parent / "prompts" / "critic.system.md"

RUBRIC = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
WEIGHTS = {c["key"]: c["weight"] for c in RUBRIC["criteria"]}
VETOS = [v["key"] for v in RUBRIC["vetos"]]
PASS_SCORE = RUBRIC["pass_score"]
MAX_CYCLES = RUBRIC["max_cycles"]


def render_rubric():
    lines = ["Critérios (nota 0 a 10; peso entre parênteses):"]
    lines += [f"- `{c['key']}` (peso {c['weight']}): {c['description']}" for c in RUBRIC["criteria"]]
    lines += ["", "Vetos (qualquer um reprova a peça, mesmo com nota alta):"]
    lines += [f"- `{v['key']}`: {v['description']}" for v in RUBRIC["vetos"]]
    lines += ["", f"Aprovação: nota ponderada >= {PASS_SCORE} e nenhum veto."]
    return "\n".join(lines)


def critic_system_prompt():
    return CRITIC_PROMPT_PATH.read_text(encoding="utf-8").replace("{{rubric}}", render_rubric())


def weighted(scores):
    """Média ponderada 0-10. Critério ausente conta 0 (omitir não ajuda); `null` explícito sai do cálculo."""
    used = {k: w for k, w in WEIGHTS.items() if not (k in scores and scores[k] is None)}
    tot = sum(used.values())
    if not tot:
        return 0.0
    def num(v):
        try:
            return max(0.0, min(10.0, float(v)))
        except (TypeError, ValueError):
            return 0.0
    return round(sum(num(scores.get(k, 0)) * w for k, w in used.items()) / tot, 2)


def decide(review, pass_score=None):
    """Aprova com nota >= pass_score e sem veto."""
    s = weighted(review.get("scores", {}))
    return s, (s >= (PASS_SCORE if pass_score is None else pass_score) and not review.get("veto"))


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("o critic não devolveu JSON")
        return json.loads(m.group(0))


def review(vlm, briefing, client_ctx, request, images, retries=1):
    """images: lista de (rótulo, base64 png). Falha explícita se o JSON for inválido: nunca aprova por omissão."""
    user = (f"Pedido original: {request}\n\nBriefing enviado ao modelo de imagem:\n{briefing}\n\n"
            f"Contexto da marca:\n{json.dumps(client_ctx, ensure_ascii=False)}")
    last = None
    for _ in range(retries + 1):
        try:
            rv = parse_json(vlm(critic_system_prompt(), user, images))
            if not isinstance(rv.get("scores"), dict):
                raise ValueError("JSON sem 'scores'")
            rv.setdefault("veto", [])
            return rv
        except (ValueError, json.JSONDecodeError) as e:
            last = e
    raise ValueError(f"critic inválido após {retries + 1} tentativas: {last}")


def openai_vlm(client, model):
    def call(system, user_text, images):
        content = [{"type": "text", "text": user_text}]
        for label, b64 in images:
            content += [{"type": "text", "text": label},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]
        r = client.chat.completions.create(model=model, response_format={"type": "json_object"},
                                           messages=[{"role": "system", "content": system},
                                                     {"role": "user", "content": content}])
        return r.choices[0].message.content
    return call


# ---------- calibração contra avaliação humana ----------

def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return None if not sx or not sy else round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 3)


def calibration_report(rows):
    """rows: lista de dicts com critic_score, critic_veto (bool), human_score, human_ok (bool)."""
    xs = [r["critic_score"] for r in rows]
    ys = [r["human_score"] for r in rows]
    out = {"n": len(rows), "correlacao": pearson(xs, ys),
           "erro_medio_abs": round(sum(abs(x - y) for x, y in zip(xs, ys)) / len(rows), 2) if rows else None,
           "limiares": []}
    t = 5.0
    while t <= 9.5:
        fa = sum(1 for r in rows if r["critic_score"] >= t and not r["critic_veto"] and not r["human_ok"])
        fr = sum(1 for r in rows if (r["critic_score"] < t or r["critic_veto"]) and r["human_ok"])
        ok = sum(1 for r in rows if r["human_ok"])
        bad = len(rows) - ok
        out["limiares"].append({"limiar": t, "falsa_aprovacao": fa, "de": bad, "falsa_reprovacao": fr, "de_aprovadas": ok})
        t += 0.5
    return out


def calibrate(path, vlm, client_ctx):
    base = pathlib.Path(path).parent
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        img = base / r["imagem"]
        b64 = base64.b64encode(img.read_bytes()).decode()
        rv = review(vlm, r.get("briefing", ""), client_ctx, r.get("pedido", ""), [("Imagem avaliada", b64)])
        s, _ = decide(rv)
        rows.append({"imagem": r["imagem"], "critic_score": s, "critic_veto": bool(rv.get("veto")),
                     "human_score": float(r["nota_humana_0_10"]),
                     "human_ok": r["aprovaria_para_cliente_sim_nao"].strip().lower() in ("sim", "s", "yes")})
    return calibration_report(rows)


def self_test():
    ok = {"scores": {k: 9 for k in WEIGHTS}, "veto": []}
    assert decide(ok) == (9.0, True)
    assert decide({"scores": {k: 10 for k in WEIGHTS}, "veto": ["watermark"]})[1] is False
    assert decide({"scores": {k: 5 for k in WEIGHTS}, "veto": []})[1] is False
    assert decide({"scores": {k: 8 for k in WEIGHTS}, "veto": []})[1] is True
    assert decide({"scores": {}, "veto": []})[0] == 0.0
    # null sai do cálculo; critério ausente conta zero
    sc = {k: 9 for k in WEIGHTS}
    sc["text"] = None
    assert weighted(sc) == 9.0
    del sc["subject"]
    assert weighted(sc) < 9.0
    # a rubrica renderizada traz todos os critérios e vetos, e o prompt não deixa variável aberta
    p = critic_system_prompt()
    assert "{{rubric}}" not in p and all(f"`{k}`" in p for k in list(WEIGHTS) + VETOS)
    # parsing tolerante a cerca de código, e falha explícita em texto sem JSON
    assert parse_json('```json\n{"scores":{"subject":9}}\n```')["scores"]["subject"] == 9
    try:
        review(lambda s, u, i: "sem json", "b", {}, "r", [], retries=0)
        raise AssertionError("deveria falhar")
    except ValueError:
        pass
    # calibração: critic concorda com humano -> sem falsa aprovação no limiar 8
    rows = [dict(critic_score=9, critic_veto=False, human_score=9, human_ok=True),
            dict(critic_score=4, critic_veto=False, human_score=3, human_ok=False),
            dict(critic_score=9, critic_veto=False, human_score=4, human_ok=False)]
    rep = calibration_report(rows)
    lim8 = next(x for x in rep["limiares"] if x["limiar"] == 8.0)
    assert lim8["falsa_aprovacao"] == 1 and lim8["falsa_reprovacao"] == 0
    print("critic self-test ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--calibrate", help="CSV de exemplos rotulados por humanos (ver calibration/README.md)")
    ap.add_argument("--client", default=str(ROOT / "client_71.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    self_test()
    if not a.calibrate:
        return
    n = sum(1 for _ in csv.DictReader(open(a.calibrate, encoding="utf-8")))
    if a.dry_run:
        print(f"critic: prompt de {len(critic_system_prompt())} caracteres; {n} exemplo(s) para calibrar. dry-run OK.")
        return
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Defina OPENAI_API_KEY (ou use --dry-run), ou escreva um adaptador vlm para o seu backend.")
    from openai import OpenAI
    vlm = openai_vlm(OpenAI(), os.getenv("CRITIC_MODEL", os.getenv("TEXT_MODEL", "gpt-5.5")))
    rep = calibrate(a.calibrate, vlm, json.loads(pathlib.Path(a.client).read_text(encoding="utf-8")))
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print("\nEscolha o menor limiar com 0 falsa_aprovacao que ainda mantenha poucas falsas reprovações.")


if __name__ == "__main__":
    main()
