#!/usr/bin/env python3
"""Testes do Runner (preflight e laço de decisão). Sem rede e sem custo.

  cd test && python3 -I test_runner.py

Preflight: afirma que TODOS os problemas saem juntos e que nenhuma chamada chegou ao transporte.
Laço: afirma quantas gerações ocorreram, qual tentativa foi a melhor e por que parou (aceite, reparo, escalonamento).
"""
import inspect, json, pathlib, struct, sys, zlib

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import provider as pv  # noqa: E402
import runner as rn  # noqa: E402

N = {"ok": 0}
MODEL = "gpt-image-2.5-sunburst"


def ok(cond, msg):
    print(("OK   " if cond else "FALHA"), msg)
    if not cond:
        sys.exit(1)
    N["ok"] += 1


def png(w=1024, h=1024, color_type=2):
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00")) + chunk(b"IEND", b"")


class Wire:
    calls = []

    def __call__(self, *a, **k):
        self.calls.append(a)
        raise AssertionError("o preflight não pode tocar na rede")


def make(session=None, key="k", probe=None):
    wire = Wire()
    wire.calls = []
    images = pv.OpenAIImages("http://x/v1", "k", transport=wire)
    return rn.Runner(images, session, key_fn=(lambda: key), storage_probe=probe), wire


def inp(kind="alvo", name="a.png", mime="image/png", data=None, id=None):
    return {"kind": kind, "name": name, "mime": mime, "bytes": data or png(), **({"id": id} if id else {})}


def base(**kw):
    d = dict(model=MODEL, size="1024x1024", quality="medium", intent="new", inputs=[])
    d.update(kw)
    return d


def problems(runner, **kw):
    try:
        runner.preflight(**kw)
    except rn.PreflightError as e:
        return e
    return None


def test_preflight():
    r, wire = make()
    rep = r.preflight(**base())
    ok(rep["checks"] == ["esquema", "referencias", "imagem_base", "credencial", "parametros", "orcamento"] and rep["allowed_calls"] == 1,
       "pedido válido passa as checagens aplicáveis (sem store a probar, o armazenamento não conta)")
    r, _ = make(probe=lambda: None)
    ok("armazenamento" in r.preflight(**base())["checks"], "com probe de armazenamento, ele entra nas checagens")
    e = problems(make()[0], **base(size="1000x1000"))
    ok(e and "múltiplos de 16" in str(e), "tamanho inválido para o modelo falha no preflight")
    e = problems(make(key=None)[0], **base())
    ok(e and "OPENAI_API_KEY" in str(e), "credencial ausente falha")
    e = problems(make()[0], **base(intent="edit", inputs=[inp("alvo"), inp("alvo", "b.png")]))
    ok(e and "mais de uma imagem-base" in str(e) and "a.png" in str(e) and "b.png" in str(e), "duas imagens-base são ambiguidade crítica")
    e = problems(make()[0], **base(intent="edit", inputs=[inp("alvo"), inp("variacao", "c.png")]))
    ok(e and "mais de uma imagem-base" in str(e), "alvo + variação também é ambíguo")
    e = problems(make()[0], **base(intent="edit", inputs=[inp("logo")]))
    ok(e and "sem imagem-base" in str(e), "edição sem imagem-base falha")
    e = problems(make()[0], **base(intent="remix"))
    ok(e and "intent inválida" in str(e), "intent desconhecida falha")
    e = problems(make()[0], **base(inputs=[inp("logo", id="x1")], known_ids={"x2"}))
    ok(e and "biblioteca" in str(e), "referência fora da biblioteca do escopo é recusada")
    r, _ = make()
    r.preflight(**base(inputs=[inp("logo", id="x1")], known_ids={"x1"}))
    r.preflight(**base(intent="edit", inputs=[inp("alvo")], known_ids=set()))
    ok(True, "referência da biblioteca passa; a imagem anterior (sem id) não exige biblioteca")
    e = problems(make()[0], **base(inputs=[inp("foto-secreta")], allowed_kinds={"logo", "alvo"}))
    ok(e and "desconhecido" in str(e), "tipo de referência fora da lista é recusado")
    e = problems(make()[0], **base(inputs=[{"kind": "logo", "name": "v.png", "mime": "image/png", "bytes": b""}]))
    ok(e and "faltam bytes" in str(e), "entrada sem bytes falha no esquema")
    e = problems(make()[0], **base(inputs=[inp("logo", mime="image/svg+xml", data=b"<svg/>")]))
    ok(e and "não suportado" in str(e), "SVG como entrada de edição falha em parâmetros (antes do briefing pago)")
    e = problems(make()[0], **base(intent="edit", inputs=[inp("alvo")], mask=png(color_type=2)))
    ok(e and "alfa" in str(e), "máscara sem canal alfa falha")
    e = problems(make()[0], **base(intent="edit", inputs=[inp("alvo", mime="image/jpeg", data=b"\xff\xd8\xff" + b"\x00" * 9)], mask=png(color_type=6)))
    ok(e and "mesmo formato" in str(e), "alvo JPEG com máscara PNG falha (a conversão deve ter ocorrido antes)")
    e = problems(make()[0], **base(size="1000x1000", intent="remix", quality="ultra"), )
    ok(e and len(e.problems) >= 3, f"vários problemas saem juntos ({len(e.problems)} listados)")
    ok(wire.calls == [] and make()[1].calls == [], "nenhum preflight tocou no transporte")
    e = problems(make(probe=lambda: "PermissionError")[0], **base())
    ok(e and "armazenamento indisponível" in str(e), "armazenamento sem gravação falha")
    ok(e.warnings == [] and isinstance(e.problems, list), "PreflightError expõe problemas e avisos")
    params = set(inspect.signature(rn.Runner.preflight).parameters)
    ok(not [p for p in params if any(w in p.lower() for w in ("skip", "force", "bypass", "ignore", "disable"))], "o preflight não tem flag para ser contornado")


def test_budget_preflight():
    sess = pv.Budget("sessão", 2)
    r, _ = make(session=sess)
    task = pv.Budget("tarefa", 8)
    rep = r.preflight(**base(task_budget=task, planned_calls=3))
    ok(rep["allowed_calls"] == 2 and any("sessão" in w and "2 de 3" in w for w in rep["warnings"]), "orçamento da sessão menor que o plano: limita e avisa")
    sess.reserve(); sess.reserve()
    e = problems(r, **base(task_budget=task))
    ok(e and "orçamento da sessão esgotado" in str(e), "sessão esgotada falha antes de qualquer chamada")
    t = pv.Budget("tarefa", 1)
    r2, _ = make()
    rep = r2.preflight(**base(task_budget=t, planned_calls=3))
    ok(rep["allowed_calls"] == 1 and rep["warnings"], "orçamento da tarefa menor que o plano: limita a 1 e avisa")
    t.reserve()
    ok("da tarefa esgotado" in str(problems(r2, **base(task_budget=t))), "tarefa esgotada falha")
    ok(pv.Budget("x", None).remaining() is None and pv.Budget("x", 3).remaining() == 3, "Budget.remaining: sem limite e com limite")


def entries(*scores):
    """review/generate falsos: notas na ordem; aprova a partir de 8."""
    it = iter(scores)
    st = {"gens": 0, "revs": 0, "revised": 0}

    def gen(cycle, brief):
        st["gens"] += 1
        return {"cycle": cycle, "prompt": brief["prompt"], "id": f"g{cycle}", "url": f"/u{cycle}", "meta": {"request_id": f"req{cycle}", "attempts": 1, "ms": 5, "usage": None}}

    def rev(entry, brief):
        st["revs"] += 1
        s = next(it)
        return {"veto": [], "fix": f"corrigir {entry['id']}"}, s, s >= 8

    def revise(brief, rv):
        st["revised"] += 1
        return {"prompt": brief["prompt"] + " +fix"}
    return gen, rev, revise, st


def test_loop():
    r, _ = make()
    gen, rev, revise, st = entries(9)
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen, review=rev, revise=revise)
    ok(st["gens"] == 1 and out["decision"].action == "accept" and out["best"]["ok"] is True and len(out["cycles"]) == 1, "aprovada de primeira: 1 geração, aceite")
    gen, rev, revise, st = entries()
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen, review=None, revise=revise)
    ok(st["gens"] == 1 and st["revs"] == 0 and out["decision"].action == "accept" and out["best"]["ok"] is None, "revisão desligada: 1 geração, aceite sem nota")
    gen, rev, revise, st = entries(6, 9)
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen, review=rev, revise=revise)
    ok(st["gens"] == 2 and st["revised"] == 1 and out["best"]["entry"]["id"] == "g1" and out["decision"].action == "accept", "reprova e melhora: 1 reparo e aceite da segunda")
    ok(out["cycles"][1]["prompt"] == "p +fix", "o reparo usou o briefing revisado")
    gen, rev, revise, st = entries(5, 6, 7)
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen, review=rev, revise=revise)
    ok(st["gens"] == 3 and out["decision"].action == "escalate" and "limite" in out["decision"].reason and out["best"]["entry"]["id"] == "g2",
       "melhora sempre mas não chega a 8: para no limite de reparos e escalona")
    gen, rev, revise, st = entries(6, 5, 9)
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen, review=rev, revise=revise)
    ok(st["gens"] == 2 and out["decision"].action == "escalate" and "sem progresso" in out["decision"].reason, "nota não melhorou: para sem gastar a 3ª geração")
    ok(out["best"]["entry"]["id"] == "g0", "a melhor tentativa (nota 6) é mantida, não a última (nota 5)")
    gen, rev, revise, st = entries(6, 6, 9)
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen, review=rev, revise=revise)
    ok(st["gens"] == 2 and "sem progresso" in out["decision"].reason, "nota igual também conta como sem progresso")
    ok(out["best"]["entry"]["id"] == "g0", "empate de nota: fica a primeira tentativa (a mais barata), não a última")
    gen, rev, revise, st = entries(4)
    out = r.run({"prompt": "p"}, max_repairs=0, generate=gen, review=rev, revise=revise, limit_reason="o orçamento limitou o plano")
    ok(out["decision"].reason == "o orçamento limitou o plano", "limit_reason substitui o texto do limite quando o limite veio de fora")
    gen, rev, revise, st = entries(4)
    out = r.run({"prompt": "p"}, max_repairs=0, generate=gen, review=rev, revise=revise)
    ok(st["gens"] == 1 and st["revised"] == 0 and out["decision"].action == "escalate", "max_repairs=0: nunca repara")


def test_loop_budget_and_questions():
    r, _ = make()
    t = pv.Budget("tarefa", 3)
    gen, rev, revise, st = entries(5, 6, 7)
    calls = []

    def gen2(cycle, brief):
        t.reserve()
        calls.append(cycle)
        return gen(cycle, brief)
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen2, review=rev, revise=revise, task_budget=t, reserve_calls=2)
    ok(len(calls) == 1 and out["decision"].action == "escalate" and "orçamento" in out["decision"].reason, "reserva de 2 chamadas para depois do laço: sobra 1, não repara")
    t = pv.Budget("tarefa", 2)
    gen, rev, revise, st = entries(5, 6, 7)

    def gen3(cycle, brief):
        t.reserve()
        return gen(cycle, brief)
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen3, review=rev, revise=revise, task_budget=t)
    ok(st["gens"] == 2 and "orçamento" in out["decision"].reason, "orçamento da tarefa acaba no meio: escalona em vez de estourar")
    gen, rev, revise, st = entries(5, 9)
    out = r.run({"prompt": "p"}, max_repairs=2, generate=gen, review=rev, revise=lambda b, rv: {"question": "qual logo?"})
    ok(st["gens"] == 1 and out["decision"].action == "stop" and "esclarecimento" in out["decision"].reason and out["best"]["entry"]["id"] == "g0",
       "designer pergunta em vez de revisar: para e mantém a melhor tentativa")
    out = r.run({"prompt": "p"}, max_repairs=2, generate=entries(5, 9)[0], review=entries(5, 9)[1], revise=lambda b, rv: None)
    ok(out["decision"].action == "stop", "revisão que devolve nada também para")
    msgs = []
    gen, rev, revise, st = entries(6, 9)
    r.run({"prompt": "p"}, max_repairs=2, generate=gen, review=rev, revise=revise, emit=msgs.append)
    ok(msgs == ["Corrigindo o briefing com a sugestão do critic…"], "emite o aviso de correção só quando repara")


def test_trace():
    r, _ = make()
    gen, rev, revise, st = entries(6, 9)
    out = r.run({"prompt": "PROMPT-SECRETO"}, max_repairs=2, generate=gen, review=rev, revise=revise)
    tr = out["trace"]
    ok(len(tr) == 2 and [t["decision"] for t in tr] == ["repair", "accept"], "trace tem uma linha por tentativa com a decisão")
    ok(tr[0]["request_id"] == "req0" and tr[1]["attempts"] == 1 and tr[0]["score"] == 6 and tr[1]["approved"] is True, "trace guarda request_id, tentativas e nota")
    ok("PROMPT-SECRETO" not in json.dumps(tr), "trace não contém prompt")
    ok(all(isinstance(t["seconds"], float) for t in tr), "trace mede o tempo de cada tentativa")


def main():
    for fn in (test_preflight, test_budget_preflight, test_loop, test_loop_budget_and_questions, test_trace):
        print(f"== {fn.__name__}")
        fn()
    print(f"\nTUDO OK ({N['ok']} verificações)")


if __name__ == "__main__":
    main()
