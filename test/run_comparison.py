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
sys.path.insert(0, str(ROOT))
import skills_router  # skills de design escolhidas por pedido (skills/design-*)
import checks  # regras de design (docs/08) e checagens por código
import critic  # rubrica, limiar e prompt do critic: prompts/rubric.json e prompts/critic.system.md
from critic import MAX_CYCLES, PASS_SCORE, WEIGHTS, decide, weighted


PROFILE_PATH = ROOT.parent / "prompts" / "profiles" / os.environ.get("IMAGE_PROFILE", "openai-gpt-image-2.5.md")


def load_system_prompt(client_ctx, agency="Aurea Tech", request=None, size=None, has_inputs=False):
    txt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    profile = PROFILE_PATH.read_text(encoding="utf-8")
    return (txt.replace("{{client_context_json}}", json.dumps(client_ctx, ensure_ascii=False, indent=2))
               .replace("{{agency_name}}", agency)
               .replace("{{design_fundamentals}}", checks.design_fundamentals())
               .replace("{{design_skills}}", skills_router.render(skills_router.select(request, size, has_inputs)) if request and os.getenv("DESIGN_SKILLS", "on") != "off" else "")
               .replace("{{image_tool_profile}}", profile))


def naive_prompt(client_ctx, request):
    # Imita o workflow atual: template fixo + JSON do cliente.
    return f"{request}. Cliente: {client_ctx.get('name')}. Cores: {', '.join(client_ctx.get('palette', []))}."


def save_png(b64, path):
    path.write_bytes(base64.b64decode(b64))


def self_test():
    critic.self_test()
    checks.self_test()
    skills_router.self_test()
    sp = load_system_prompt({"name": "x"})
    assert "E1." in sp and "agent:start" not in sp, "regras de design não chegaram ao system prompt"
    sk = load_system_prompt({"name": "x"}, request="banner de promoção para stories", size="1536x1024")
    assert 'skill name="design-tipografia-texto"' in sk and 'skill name="design-formato-canal"' in sk and "{{design_skills}}" not in sk
    assert "<skill" not in sp, "sem pedido não há skills roteadas"
    os.environ["DESIGN_SKILLS"] = "off"
    try:
        assert "<skill" not in load_system_prompt({"name": "x"}, request="banner de promoção", size="1536x1024")
    finally:
        del os.environ["DESIGN_SKILLS"]
    assert all(v not in sp for v in ("{{client_context_json}}", "{{agency_name}}", "{{image_tool_profile}}", "{{design_fundamentals}}", "{{design_skills}}")), "variável sem preencher"


def run_case(client, case, client_ctx, out, args):
    image_model = os.getenv("IMAGE_MODEL", "gpt-image-2.5-sunburst")
    text_model = os.getenv("TEXT_MODEL", "gpt-5.5")
    resp_model = os.getenv("RESPONSES_MODEL", "gpt-5.5")
    size = case.get("size") or os.getenv("IMAGE_SIZE", "1024x1024")
    quality = os.getenv("IMAGE_QUALITY", "medium")
    request = case["request"]
    system = load_system_prompt(client_ctx, request=request, size=size)
    skill_notes = skills_router.review_notes(skills_router.select(request, size))
    arms = getattr(args, "arms", "ABC") if args else "ABC"
    res = {"case": case["id"], "request": request, "size": size, "image_model": image_model, "arms": {}}

    def gen(prompt):
        t0 = time.time()
        r = client.images.generate(model=image_model, prompt=prompt, size=size, quality=quality, n=1)
        return r.data[0].b64_json, round(time.time() - t0, 1)

    vlm = critic.openai_vlm(client, os.getenv("CRITIC_MODEL", text_model))  # trocar de backend = outro adaptador

    def review(b64, briefing):
        rv = critic.review(vlm, briefing, client_ctx, request, [("Imagem avaliada", b64)], notes=skill_notes)
        return checks.apply(rv, b64, size)  # vetos por código valem para todos os braços

    pa = naive_prompt(client_ctx, request)

    def arm_raw():  # A: Image API crua
        b64, secs = gen(pa)
        rv = review(b64, pa)
        save_png(b64, out / f"case{case['id']}_A.png")
        return {"prompt": pa, "seconds": secs, "generations": 1, "score": decide(rv)[0], "veto": rv.get("veto"), "review": rv}

    def arm_harness(tag, color_names=False):  # B: harness; N: igual, com cores por nome em vez de hex
        extra = ("\nNo prompt final descreva as cores pelo NOME (ex.: deep navy blue, warm amber, cream), "
                 "sem códigos hex.") if color_names else ""

        def write_briefing(feedback=None, prev=None):
            user = f"Pedido: {request}\n{extra}"
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
        save_png(best[1], out / f"case{case['id']}_{tag}.png")
        return {"cycles": cycles, "generations": len(cycles), "seconds": round(total_secs, 1),
                "score": best[0], "veto": best[2].get("veto"), "review": best[2]}

    def arm_native():  # C: Responses API (reescrita nativa da OpenAI)
        t0 = time.time()
        r = client.responses.create(model=resp_model, input=pa, tools=[{
            "type": "image_generation", "model": image_model, "quality": quality, "size": size, "action": "generate"}])
        calls = [o for o in r.output if o.type == "image_generation_call"]
        if not calls:
            return {"error": "sem image_generation_call", "text": getattr(r, "output_text", "")}
        b64 = calls[0].result
        rv = review(b64, pa)
        save_png(b64, out / f"case{case['id']}_C.png")
        return {"prompt": pa, "revised_prompt": getattr(calls[0], "revised_prompt", None), "generations": 1,
                "seconds": round(time.time() - t0, 1), "score": decide(rv)[0], "veto": rv.get("veto"), "review": rv}

    runners = {"A": arm_raw, "B": lambda: arm_harness("B"), "N": lambda: arm_harness("N", True), "C": arm_native}
    for tag in arms:
        try:  # um braço que falha não derruba os outros nem apaga o que já foi gerado
            res["arms"][tag] = runners[tag]()
        except Exception as e:
            res["arms"][tag] = {"error": f"{type(e).__name__}: {e}"}
            print(f"  braço {tag} do caso {case['id']} falhou: {type(e).__name__}: {e}")
    return res


def write_report(out, results):
    """report.html (com os braços, para você) e blind/ (sem os braços, para a avaliação humana cega)."""
    import shutil
    rows = []
    for r in results:
        arms = r["arms"]
        figs = "".join(f"<figure><img src='case{r['case']}_{k}.png' width=300><figcaption>{k} nota {arms[k].get('score')} "
                       f"({arms[k].get('seconds')}s, {arms[k].get('generations')} ger.)</figcaption></figure>"
                       for k in "ABNC" if k in arms and "score" in arms[k])
        rows.append(f"<h3>Caso {r['case']}: {r['request']}</h3><div style='display:flex;gap:12px'>{figs}</div>")
    (out / "report.html").write_text("<meta charset=utf-8><h1>Relatório (identifica os braços; não use para a avaliação cega)</h1>"
                                     + "".join(rows) + "<pre>" + json.dumps(results, ensure_ascii=False, indent=2) + "</pre>",
                                     encoding="utf-8")
    blind = out / "blind"
    blind.mkdir(exist_ok=True)
    items = [(r["case"], k) for r in results for k in "ABNC" if k in r["arms"] and "score" in r["arms"][k]]
    random.shuffle(items)
    key, figs = {}, []
    for i, (case_id, arm) in enumerate(items, 1):
        name = f"img{i:03d}.png"
        shutil.copy(out / f"case{case_id}_{arm}.png", blind / name)
        key[name] = {"case": case_id, "arm": arm}
        figs.append(f"<figure><img src='{name}' width=420><figcaption>{name}</figcaption></figure>")
    (blind / "key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")  # não abra antes de avaliar
    pedidos = {r["case"]: r["request"] for r in results}
    (blind / "avaliar.html").write_text("<meta charset=utf-8><h1>Avaliação cega</h1><p>Preencha ratings.csv. Não abra key.json.</p>"
                                        "<div style='display:flex;flex-wrap:wrap;gap:12px'>" + "".join(figs) + "</div>"
                                        + "<h3>Pedidos</h3><ul>" + "".join(f"<li>Caso {c}: {t}</li>" for c, t in pedidos.items()) + "</ul>",
                                        encoding="utf-8")
    with open(blind / "ratings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["arquivo", "caso", "nota_humana_0_10", "aprovaria_para_cliente_sim_nao", "comentario"])
        for name in sorted(key):
            w.writerow([name, key[name]["case"], "", "", ""])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default=str(ROOT / "client_71.json"))
    ap.add_argument("--cases", default=str(ROOT / "eval_set.json"))
    ap.add_argument("--case", type=int, help="id de um caso")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--repeats", type=int, default=1, help="repetições por caso (mede consistência)")
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--arms", default="ABC", help="braços a rodar: A crua, B harness, N harness com cores por nome, C nativo (ex.: AB, ABNC)")
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
