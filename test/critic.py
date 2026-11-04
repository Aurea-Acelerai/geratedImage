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
BASE, PACKS = RUBRIC["base"], RUBRIC["packs"]
ALL_PACKS = list(PACKS)
PASS_SCORE = RUBRIC["pass_score"]
MAX_CYCLES = RUBRIC["max_cycles"]


def _packs(packs):
    """None = todos os pacotes (comportamento legado, usado no teste A/B/C). Lista = só esses pacotes."""
    if packs is None:
        return ALL_PACKS
    unknown = [p for p in packs if p not in PACKS]
    if unknown:
        raise ValueError(f"pacote(s) de rubrica desconhecido(s): {unknown}")
    return list(packs)


def criteria_for(packs=None):
    return list(BASE["criteria"]) + [c for p in _packs(packs) for c in PACKS[p]["criteria"]]


def vetos_for(packs=None):
    return list(BASE["vetos"]) + [v for p in _packs(packs) for v in PACKS[p]["vetos"]]


def weights_for(packs=None):
    return {c["key"]: c["weight"] for c in criteria_for(packs)}


WEIGHTS = weights_for(None)  # união de todos os pacotes
VETOS = [v["key"] for v in vetos_for(None)]


def render_rubric(packs=None):
    """O critic só vê os critérios e vetos que valem para esta peça: base + pacotes do caso de uso."""
    names = _packs(packs)
    lines = [f"Critérios que valem para esta peça (nota 0 a 10; peso entre parênteses). Pacotes ativos: base"
             + "".join(f", {p}" for p in names) + ". Não avalie nada fora desta lista.", ""]
    lines += [f"- `{c['key']}` (peso {c['weight']}): {c['description']}" for c in criteria_for(packs)]
    lines += ["", "Vetos (qualquer um reprova a peça, mesmo com nota alta):"]
    lines += [f"- `{v['key']}`: {v['description']}" for v in vetos_for(packs)]
    lines += ["", f"Aprovação: nota ponderada >= {PASS_SCORE} e nenhum veto."]
    return "\n".join(lines)


def critic_system_prompt(packs=None):
    return CRITIC_PROMPT_PATH.read_text(encoding="utf-8").replace("{{rubric}}", render_rubric(packs))


def weighted(scores, packs=None):
    """Média ponderada 0-10 só dos critérios dos pacotes ativos. Critério ausente conta 0 (omitir não ajuda);
    `null` explícito sai do cálculo; chave de outro pacote é ignorada."""
    weights = weights_for(packs)
    used = {k: w for k, w in weights.items() if not (k in scores and scores[k] is None)}
    tot = sum(used.values())
    if not tot:
        return 0.0
    def num(v):
        try:
            return max(0.0, min(10.0, float(v)))
        except (TypeError, ValueError):
            return 0.0
    return round(sum(num(scores.get(k, 0)) * w for k, w in used.items()) / tot, 2)


def decide(review, pass_score=None, packs=None):
    """Aprova com nota >= pass_score e sem veto. Vetos de OUTROS pacotes (que o critic nem recebeu) são ignorados;
    veto desconhecido é mantido (na dúvida, reprova)."""
    s = weighted(review.get("scores", {}), packs)
    active = {v["key"] for v in vetos_for(packs)}
    elsewhere = {v["key"] for v in vetos_for(None)} - active
    vetos = [v for v in review.get("veto", []) if v not in elsewhere]
    return s, (s >= (PASS_SCORE if pass_score is None else pass_score) and not vetos)


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("o critic não devolveu JSON")
        return json.loads(m.group(0))


def review(vlm, briefing, client_ctx, request, images, retries=1, notes="", packs=None):
    """images: lista de (rótulo, base64 png). Falha explícita se o JSON for inválido: nunca aprova por omissão."""
    user = (f"Pedido original: {request}\n\nBriefing enviado ao modelo de imagem:\n{briefing}\n\n"
            f"Contexto da marca:\n{json.dumps(client_ctx, ensure_ascii=False)}")
    if notes:  # checagens específicas das skills de design aplicadas a esta peça (skills_router.review_notes)
        user += f"\n\nChecagens específicas desta peça (skills de design aplicadas):\n{notes}"
    last = None
    for _ in range(retries + 1):
        try:
            rv = parse_json(vlm(critic_system_prompt(packs), user, images))
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
    # pacotes: imagem livre só é julgada pela base; marketing acrescenta hierarquia/CTA; vetos de outro pacote não valem
    free = weights_for([])
    assert set(free) == {c["key"] for c in BASE["criteria"]} and "hierarchy" not in free and "message_clarity" not in free
    assert {"hierarchy", "legibility_size", "message_clarity"} <= set(weights_for(["marketing"]))
    assert "brand_fit" in weights_for(["brand"]) and "text" in weights_for(["text"]) and "invariants" in weights_for(["edit"])
    sc_free = {k: 9 for k in free}
    assert decide({"scores": sc_free, "veto": []}, packs=[]) == (9.0, True)
    assert decide({"scores": sc_free, "veto": ["cta_vago"]}, packs=[])[1] is True      # veto de marketing não vale em imagem livre
    assert decide({"scores": sc_free, "veto": ["cta_vago"]}, packs=["marketing"])[1] is False
    assert decide({"scores": sc_free, "veto": ["veto_inexistente"]}, packs=[])[1] is False  # desconhecido reprova
    assert decide({"scores": sc_free, "veto": ["formato_incorreto"]}, packs=[])[1] is False  # veto por código é da base
    pf = critic_system_prompt([])
    assert "`hierarchy`" not in pf and "`cta_vago`" not in pf and "`subject`" in pf and "`watermark`" in pf
    pm = critic_system_prompt(["marketing", "brand"])
    assert "`hierarchy`" in pm and "`brand_fit`" in pm and "`logo_inventado`" in pm and "`text`" not in pm
    try:
        weights_for(["inexistente"])
        raise AssertionError("deveria falhar")
    except ValueError:
        pass
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
