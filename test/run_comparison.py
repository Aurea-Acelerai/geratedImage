#!/usr/bin/env python3
"""Teste A/B/C de geração de imagem. Mesmo modelo de imagem nos três braços; muda só a orquestração.

  A  Image API crua: template fixo + JSON do cliente (o que o Robocop faz hoje)
  B  Nosso harness: briefing do diretor de arte -> Image API -> critic -> até 2 correções
  C  Responses API com a ferramenta nativa image_generation (a OpenAI reescreve o prompt;
     guardamos o revised_prompt). Mesmo prompt cru do braço A.

Todos os braços são avaliados pela mesma rubrica (critic). O critic é um LLM: use também
a avaliação humana cega (report.html gera a planilha ratings.csv).

Uso:
  pip install openai
  export OPENAI_API_KEY=...        # a organização pode precisar de verificação para modelos de imagem
  python run_comparison.py --dry-run
  python run_comparison.py --case 1
  python run_comparison.py --all --repeats 3

Variáveis: IMAGE_MODEL (gpt-image-2.5-sunburst), TEXT_MODEL (gpt-5.5), RESPONSES_MODEL (gpt-5.5),
           IMAGE_QUALITY (medium), IMAGE_SIZE (1024x1024)
Os nomes de modelo seguem a documentação da OpenAI de nov/2026; confirme na sua conta.
"""
import argparse, base64, csv, json, os, pathlib, random, sys, time

ROOT = pathlib.Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = ROOT.parent / "prompts" / "designer-imagegen.system.md"
MAX_CYCLES = 2
PASS_SCORE = 8.0

RUBRIC = """Avalie a imagem contra o briefing e a marca. Responda SOMENTE JSON:
{"scores":{"subject":0-10,"style":0-10,"composition":0-10,"color_contrast":0-10,"text":0-10,"defects":0-10,"format":0-10,"binding_count":0-10},
 "veto":[subset de: logo_inventado, watermark, texto_indevido, pessoa_real_sem_referencia, dado_inventado],
 "issues":[problemas objetivos],
 "fix":"UMA mudança curta para o próximo prompt"}
binding_count = cada cor/objeto/propriedade ligado ao elemento certo, contagens corretas, negações respeitadas.
Se não houver texto pedido, text=10 desde que não exista texto indevido. Confira o texto letra por letra.
Seja rigoroso: aspecto lavado, baixo contraste ou foco difuso derrubam color_contrast."""

WEIGHTS = {"subject": 2, "style": 1, "composition": 1, "color_contrast": 2, "text": 2,
           "defects": 1, "format": 0.5, "binding_count": 1}


def load_system_prompt(client_ctx, agency="Aurea Tech"):
    txt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (txt.replace("{{client_context_json}}", json.dumps(client_ctx, ensure_ascii=False, indent=2))
               .replace("{{agency_name}}", agency))


def weighted(scores):
    tot = sum(WEIGHTS.values())
    return round(sum(float(scores.get(k, 0)) * w for k, w in WEIGHTS.items()) / tot, 2)


def decide(review):
    """Aprova com nota >= PASS_SCORE e sem veto."""
    s = weighted(review.get("scores", {}))
    return s, (s >= PASS_SCORE and not review.get("veto"))


def naive_prompt(client_ctx, request):
    # Imita o workflow atual: template fixo + JSON do cliente.
    return f"{request}. Cliente: {client_ctx.get('name')}. Cores: {', '.join(client_ctx.get('palette', []))}."


def save_png(b64, path):
    path.write_bytes(base64.b64decode(b64))


def self_test():
    ok = {"scores": {k: 9 for k in WEIGHTS}, "veto": []}
    assert decide(ok) == (9.0, True)
    assert decide({"scores": {k: 10 for k in WEIGHTS}, "veto": ["watermark"]})[1] is False
    assert decide({"scores": {k: 5 for k in WEIGHTS}, "veto": []})[1] is False
    assert decide({"scores": {k: 8 for k in WEIGHTS}, "veto": []})[1] is True
    assert decide({"scores": {}, "veto": []})[0] == 0.0
    sp = load_system_prompt({"name": "x"})
    assert "{{client_context_json}}" not in sp and "{{agency_name}}" not in sp, "variável sem preencher"


def run_case(client, case, client_ctx, out, args):
    image_model = os.getenv("IMAGE_MODEL", "gpt-image-2.5-sunburst")
    text_model = os.getenv("TEXT_MODEL", "gpt-5.5")
    resp_model = os.getenv("RESPONSES_MODEL", "gpt-5.5")
    size = case.get("size") or os.getenv("IMAGE_SIZE", "1024x1024")
    quality = os.getenv("IMAGE_QUALITY", "medium")
    request = case["request"]
    system = load_system_prompt(client_ctx)
    res = {"case": case["id"], "request": request, "size": size, "image_model": image_model, "arms": {}}

    def gen(prompt):
        t0 = time.time()
        r = client.images.generate(model=image_model, prompt=prompt, size=size, quality=quality, n=1)
        return r.data[0].b64_json, round(time.time() - t0, 1)

    def review(b64, briefing):
        r = client.chat.completions.create(model=text_model, response_format={"type": "json_object"}, messages=[
            {"role": "system", "content": RUBRIC},
            {"role": "user", "content": [
                {"type": "text", "text": f"Briefing:\n{briefing}\n\nMarca:\n{json.dumps(client_ctx, ensure_ascii=False)}\n\nCaso: {request}"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}])
        return json.loads(r.choices[0].message.content)

    # ---- A: crua
    pa = naive_prompt(client_ctx, request)
    b64, secs = gen(pa)
    rv = review(b64, pa)
    save_png(b64, out / f"case{case['id']}_A.png")
    res["arms"]["A"] = {"prompt": pa, "seconds": secs, "score": decide(rv)[0], "veto": rv.get("veto"), "review": rv}

    # ---- B: harness
    def write_briefing(feedback=None, prev=None):
        user = f"Pedido: {request}\n"
        if feedback:
            user += f"\nA versão anterior foi reprovada. Prompt anterior:\n{prev}\n\nCorrija APENAS isto: {feedback}\nRepita as invariantes."
        user += '\n\nResponda SOMENTE JSON: {"use_case":"...","role":"hero|cell","prompt":"<prompt final em inglês no schema>"}'
        r = client.chat.completions.create(model=text_model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                           response_format={"type": "json_object"})
        return json.loads(r.choices[0].message.content)

    brief = write_briefing()
    cycles, best, total_secs = [], None, 0.0
    for cycle in range(MAX_CYCLES + 1):
        b64, secs = gen(brief["prompt"])
        total_secs += secs
        rv = review(b64, brief["prompt"])
        s, ok = decide(rv)
        cycles.append({"cycle": cycle, "prompt": brief["prompt"], "score": s, "approved": ok, "seconds": secs, "review": rv})
        if best is None or s > best[0]:
            best = (s, b64, rv)
        if ok or cycle == MAX_CYCLES:
            break
        brief = write_briefing(rv.get("fix"), brief["prompt"])
    save_png(best[1], out / f"case{case['id']}_B.png")
    res["arms"]["B"] = {"cycles": cycles, "generations": len(cycles), "seconds": round(total_secs, 1),
                        "score": best[0], "veto": best[2].get("veto"), "review": best[2]}

    # ---- C: Responses API (reescrita nativa da OpenAI)
    t0 = time.time()
    r = client.responses.create(model=resp_model, input=pa, tools=[{
        "type": "image_generation", "model": image_model, "quality": quality, "size": size, "action": "generate"}])
    calls = [o for o in r.output if o.type == "image_generation_call"]
    if calls:
        b64 = calls[0].result
        rv = review(b64, pa)
        save_png(b64, out / f"case{case['id']}_C.png")
        res["arms"]["C"] = {"prompt": pa, "revised_prompt": getattr(calls[0], "revised_prompt", None),
                            "seconds": round(time.time() - t0, 1), "score": decide(rv)[0], "veto": rv.get("veto"), "review": rv}
    else:
        res["arms"]["C"] = {"error": "sem image_generation_call", "text": getattr(r, "output_text", "")}
    return res


def write_report(out, results):
    rows = []
    for r in results:
        arms = r["arms"]
        figs = "".join(f"<figure><img src='case{r['case']}_{k}.png' width=300><figcaption>{k} nota {arms[k].get('score')} "
                       f"({arms[k].get('seconds')}s)</figcaption></figure>" for k in "ABC" if k in arms and "score" in arms[k])
        rows.append(f"<h3>Caso {r['case']}: {r['request']}</h3><div style='display:flex;gap:12px'>{figs}</div>")
    (out / "report.html").write_text("<meta charset=utf-8><h1>A vs B vs C</h1>" + "".join(rows) +
                                     "<pre>" + json.dumps(results, ensure_ascii=False, indent=2) + "</pre>", encoding="utf-8")
    # planilha para avaliação humana cega (ordem embaralhada, sem revelar o braço)
    with open(out / "ratings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arquivo", "nota_humana_0_10", "aprovaria_para_cliente_sim_nao", "comentario"])
        files = [f"case{r['case']}_{k}.png" for r in results for k in "ABC" if k in r["arms"] and "score" in r["arms"][k]]
        random.shuffle(files)
        for name in files:
            w.writerow([name, "", "", ""])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default=str(ROOT / "client_71.json"))
    ap.add_argument("--cases", default=str(ROOT / "eval_set.json"))
    ap.add_argument("--case", type=int, help="id de um caso")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--repeats", type=int, default=1, help="repetições por caso (mede consistência)")
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    self_test()
    client_ctx = json.loads(pathlib.Path(a.client).read_text(encoding="utf-8"))
    cases = json.loads(pathlib.Path(a.cases).read_text(encoding="utf-8"))
    if a.case:
        cases = [c for c in cases if c["id"] == a.case]
    elif not a.all:
        cases = cases[:1]
    out = pathlib.Path(a.out) / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    if a.dry_run:
        for c in cases:
            print(f"[A] caso {c['id']}: {naive_prompt(client_ctx, c['request'])}")
        print(f"[B] system prompt: {len(load_system_prompt(client_ctx))} caracteres; {len(cases)} caso(s)")
        print("[C] Responses API: model=%s, ferramenta image_generation(%s)" % (os.getenv("RESPONSES_MODEL", "gpt-5.5"), os.getenv("IMAGE_MODEL", "gpt-image-2.5-sunburst")))
        print("dry-run OK (nenhuma API chamada).")
        return

    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Defina OPENAI_API_KEY (ou use --dry-run).")
    from openai import OpenAI
    client = OpenAI()
    results = []
    for c in cases:
        for rep in range(a.repeats):
            cc = dict(c, id=c["id"] if a.repeats == 1 else f"{c['id']}r{rep + 1}")
            try:
                results.append(run_case(client, cc, client_ctx, out, a))
                print("caso", cc["id"], {k: v.get("score") for k, v in results[-1]["arms"].items()})
            except Exception as e:  # não derruba o lote; erros de moderação não devem ser repetidos às cegas
                print("caso", cc["id"], "falhou:", type(e).__name__, e)
                results.append({"case": cc["id"], "request": c["request"], "arms": {}, "error": str(e)})
    (out / "log.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(out, [r for r in results if r["arms"]])
    print("Pronto:", out / "report.html")


if __name__ == "__main__":
    main()
