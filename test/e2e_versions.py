#!/usr/bin/env python3
"""E2E das versões de imagem (pai/filho) contra a OpenAI falsa. Sem chave real, sem custo.

  python3 e2e_versions.py

Prova que cada geração grava um registro com modelo, parâmetros e versão do prompt; que "Editar esta imagem" e "mude só a cor"
(sem botão, pela última imagem) resolvem a base ANTES da chamada e gravam o pai certo; e que a genealogia sai por /api/lineage.
"""
import sys

from e2e_preflight import Stack, call, ok


def lineage(stack, iid, client="71"):
    return call(stack.chat, "/api/lineage", {"client": client, "id": iid})


def main():
    s = Stack()
    try:
        print("== do zero, edição pelo botão e 'mude só a cor' pela última imagem")
        p, _ = s.run({"client": "71", "text": "banner de promocao de verao", "review": False})
        m1 = p["message"]
        ok(p["status"] == "done" and m1["kind"] == "image" and m1["parent_id"] is None, "imagem do zero: sem pai")
        conv = m1["conv"]
        st, r1 = lineage(s, m1["id"])
        rec1 = r1["record"]
        ok(st == 200 and rec1["parent_id"] is None and rec1["base_kind"] is None and rec1["op"] == "generate", "registro 1: geração sem base")
        ok(rec1["model"] == "gpt-image-2.5-sunburst" and rec1["size"] and rec1["quality"] and rec1["conv"] == conv and rec1["intent"] == "new", f"registro 1 guarda modelo, tamanho, qualidade, conversa e intenção ({rec1['model']}, {rec1['size']})")
        ok(len(rec1["prompt_sha"]) == 12 and len(rec1["prompt_version"]) == 12 and rec1["mid"], "registro 1 guarda hash do briefing e versão do system prompt")
        ok("prompt" not in rec1 and "bytes" not in rec1 and "b64" not in str(rec1), "registro não guarda prompt, bytes nem imagem")

        p, _ = s.run({"client": "71", "text": "deixe mais quente", "edit_of": m1["id"], "conv": conv, "review": False})
        m2 = p["message"]
        ok(m2["kind"] == "image" and m2["parent_id"] == m1["id"], "edição pelo botão: o pai é a imagem escolhida")
        _, r2 = lineage(s, m2["id"])
        ok(r2["record"]["parent_id"] == m1["id"] and r2["record"]["base_kind"] == "generated" and r2["record"]["op"] == "edit" and r2["record"]["intent"] == "edit", "registro 2: edição, base gerada")
        ok(r2["record"]["fidelity"] == "high" and r2["record"]["inputs"][0]["kind"] == "alvo", "registro 2: fidelidade alta e o alvo nas entradas")

        p, _ = s.run({"client": "71", "text": "mude só a cor do fundo", "conv": conv, "review": False})
        m3 = p["message"]
        ok(m3["kind"] == "image" and m3["intent"] == "edit" and m3["parent_id"] == m2["id"], f"'mude só a cor' sem botão: base resolvida pela ÚLTIMA imagem (pai {m3['parent_id']} = {m2['id']})")
        _, r3 = lineage(s, m3["id"])
        ok(r3["lineage"] == {"chain": [m1["id"], m2["id"], m3["id"]], "complete": True, "reason": None}, "genealogia da imagem 3: raiz, edição 1, edição 2")
        ok(r3["children"] == [], "a última imagem não tem filhos")
        _, r1b = lineage(s, m1["id"])
        ok(r1b["children"] == [m2["id"]], "a raiz lista só o filho direto")
        st = s.stats()
        ok(st["edits"] == 2 and st["generations"] == 1, "a base foi enviada de verdade: 1 geração + 2 edições na OpenAI falsa")

        print("== ciclos de revisão e erros")
        p, _ = s.run({"client": "71", "text": "outro banner para a campanha de inverno"})
        m4 = p["message"]
        ok(len(m4["cycles"]) == 2, "a falsa reprova o 1º review e aprova o 2º (2 ciclos)")
        recs = [lineage(s, c["id"])[1]["record"] for c in m4["cycles"]]
        ok(recs[0]["approved"] is False and recs[1]["approved"] is True and recs[0]["score"] < recs[1]["score"], f"cada ciclo guarda nota e aprovação ({recs[0]['score']} -> {recs[1]['score']})")
        ok(recs[0]["parent_id"] is None and recs[1]["parent_id"] is None, "ciclos de uma geração do zero ficam sem pai")
        ok([r["cycle"] for r in recs] == [0, 1] and recs[0]["mid"] == recs[1]["mid"], "ciclos numerados e ligados à mesma execução")
        ok(call(s.chat, "/api/lineage", {"client": "71", "id": "naoexiste1"})[0] == 404, "imagem sem registro: 404")
        for bad in ("../x", "A B", "", None, 7, "x" * 70):
            ok(call(s.chat, "/api/lineage", {"client": "71", "id": bad})[0] == 400, f"id inválido {bad!r}: 400")
        ok(call(s.chat, "/api/lineage", {"client": "../71", "id": m1["id"]})[0] == 400, "escopo hostil: 400")
        ok(call(s.chat, "/api/lineage", {"client": "outro", "id": m1["id"]})[0] == 404, "o mesmo id em outro escopo não aparece")
    finally:
        s.close()
    print("\nTUDO OK")


if __name__ == "__main__":
    sys.exit(main())
