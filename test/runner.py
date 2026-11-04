#!/usr/bin/env python3
"""Runner: preflight leve + laço de execução com decisão de aceite, reparo ou escalonamento. Só stdlib.

Dois momentos de verificação, de propósito separados:
- ANTES de incorporar código: lint, testes e avaliações (test/run_tests.sh, CI). Nunca roda dentro de uma requisição.
- ANTES de cada geração (este módulo): preflight barato, sem rede e sem custo, que falha rápido com TODOS os problemas
  antes de gastar chamadas de texto ou de imagem: esquema, referências, imagem-base ambígua, parâmetros aceitos
  pelo modelo, credencial, orçamento e armazenamento gravável.
O adapter (provider.py) valida de novo a requisição exata imediatamente antes de cada chamada paga: o preflight não o
substitui, só adianta a falha. Não existe flag para pular o preflight.

O laço (run) recebe callbacks (gerar, revisar, revisar o briefing) para ficar testável sem HTTP. Decisões:
- aceita: o critic aprovou, ou a revisão está desligada;
- repara: reprovou, ainda há reparos, orçamento e a nota melhorou em relação à tentativa anterior;
- escalona (revisão humana): limite de reparos, orçamento esgotado ou ausência de progresso;
- para: o designer pediu esclarecimento em vez de um novo briefing.
"""
import time

BASE_KINDS = ("alvo", "variacao")
INTENTS = ("new", "edit", "variation")


class PreflightError(Exception):
    def __init__(self, problems, warnings=()):
        self.problems, self.warnings = list(problems), list(warnings)
        super().__init__("Pré-checagem falhou, nada foi gerado: " + "; ".join(self.problems))


class Decision:
    def __init__(self, action, reason=""):
        self.action, self.reason = action, reason

    def __repr__(self):
        return f"Decision({self.action!r}, {self.reason!r})"


class Runner:
    def __init__(self, images, session_budget=None, key_fn=None, storage_probe=None, clock=time.time, text_session_budget=None):
        self.images = images
        self.session_budget = session_budget
        self.text_session_budget = text_session_budget
        self.key_fn = key_fn
        self.storage_probe = storage_probe  # callable -> None (ok) ou texto do problema
        self.clock = clock

    # ---------- preflight ----------
    def preflight(self, *, model, size, quality, intent, inputs, mask=None, call_inputs=None, known_ids=None,
                  allowed_kinds=None, task_budget=None, planned_calls=1):
        """Levanta PreflightError com todos os problemas; devolve {"checks", "warnings", "allowed_calls"}."""
        problems, warnings, checks = [], [], []

        # 1. esquema
        before = len(problems)
        if not isinstance(model, str) or not model:
            problems.append("modelo de imagem ausente")
        if not isinstance(size, str) or not size:
            problems.append("tamanho ausente")
        if quality is not None and not isinstance(quality, str):
            problems.append("quality deve ser texto")
        if intent not in INTENTS:
            problems.append(f"intent inválida: {intent!r}")
        for i, x in enumerate(inputs or []):
            if not isinstance(x, dict) or not x.get("bytes") or not x.get("mime") or not x.get("kind"):
                problems.append(f"entrada {i}: faltam bytes, mime ou kind")
            elif allowed_kinds is not None and x["kind"] not in allowed_kinds:
                problems.append(f"entrada {i}: tipo de referência desconhecido ({x['kind']!r})")
        checks.append("esquema") if len(problems) == before else None

        # 2. referências existentes e autorizadas (só ids da biblioteca do escopo; a imagem anterior da conversa não tem id)
        before = len(problems)
        if known_ids is not None:
            for x in inputs or []:
                if isinstance(x, dict) and x.get("id") and x["id"] not in known_ids:
                    problems.append(f"referência '{x.get('name')}' não pertence à biblioteca deste escopo")
        checks.append("referencias") if len(problems) == before else None

        # 3. imagem-base: sem ambiguidade crítica
        before = len(problems)
        bases = [x for x in (inputs or []) if isinstance(x, dict) and x.get("kind") in BASE_KINDS]
        if len(bases) > 1:
            problems.append("mais de uma imagem-base (" + ", ".join(str(b.get("name")) for b in bases) + "): diga qual editar")
        if intent in ("edit", "variation") and not bases:
            problems.append("edição ou variação sem imagem-base")
        checks.append("imagem_base") if len(problems) == before else None

        # 4. credencial
        if self.key_fn is not None and not self.key_fn():
            problems.append("OPENAI_API_KEY ausente")
        else:
            checks.append("credencial")

        # 5. parâmetros aceitos (a mesma validação que o adapter fará antes de enviar)
        if isinstance(model, str) and model and isinstance(size, str) and size:
            ci = call_inputs if call_inputs is not None else (inputs or [])
            try:
                warnings.extend(self.images.validate_request("edit" if ci else "generate", model, size, quality, inputs=ci, mask=mask))
                checks.append("parametros")
            except Exception as e:  # noqa: BLE001  (ProviderError: o texto já lista todos os problemas)
                problems.extend(str(e).replace("Requisição inválida, nada foi enviado: ", "").split("; "))

        # 6. orçamento
        allowed = planned_calls
        sess = self.session_budget.remaining() if self.session_budget else None
        task = task_budget.remaining() if task_budget else None
        for name, left in (("da sessão", sess), ("da tarefa", task)):
            if left is not None:
                if left < 1:
                    problems.append(f"orçamento {name} esgotado")
                elif left < planned_calls:
                    warnings.append(f"orçamento {name} permite só {left} de {planned_calls} chamadas planejadas (repetições de rede também consomem)")
                allowed = min(allowed, left)
        if self.text_session_budget is not None and self.text_session_budget.remaining() is not None and self.text_session_budget.remaining() < 1:
            problems.append("orçamento de texto da sessão esgotado")  # o briefing e o critic precisam de chamadas de texto
        if not any("orçamento" in p for p in problems):
            checks.append("orcamento")

        # 7. armazenamento
        if self.storage_probe:
            why = self.storage_probe()
            if why:
                problems.append(f"armazenamento indisponível: {why}")
            else:
                checks.append("armazenamento")

        if problems:
            raise PreflightError(problems, warnings)
        return {"checks": checks, "warnings": warnings, "allowed_calls": max(1, allowed)}

    # ---------- decisão e laço ----------
    @staticmethod
    def decide(cycles, max_repairs, calls_left=None, limit_reason=None):
        last = cycles[-1]
        if last.get("approved") is None or last["approved"]:
            return Decision("accept", "aprovada" if last.get("approved") else "revisão desligada")
        done = len(cycles) - 1
        if done >= max_repairs:
            return Decision("escalate", limit_reason or f"limite de {max_repairs} reparo(s) atingido")
        if calls_left is not None and calls_left < 1:
            return Decision("escalate", "orçamento de chamadas esgotado")
        if len(cycles) >= 2 and (last.get("score") or 0) <= (cycles[-2].get("score") or 0):
            return Decision("escalate", f"sem progresso (nota {last.get('score')} após {cycles[-2].get('score')})")
        return Decision("repair", "reprovada; há reparo, orçamento e tentativa anterior a superar")

    def run(self, brief, *, max_repairs, generate, review=None, revise=None, task_budget=None, reserve_calls=0, emit=None, limit_reason=None):
        """generate(cycle, brief) -> entry (dict com id/url/prompt…); review(entry, brief) -> (rv, score, ok) ou None;
        revise(brief, rv) -> novo brief (dict; 'question' interrompe). reserve_calls: chamadas guardadas para depois do laço.
        limit_reason: texto da escalada quando o limite de reparos foi imposto por fora (ex.: orçamento), não pela configuração."""
        cycles, best, trace, decision = [], None, [], None
        for cycle in range(max_repairs + 1):
            t0 = self.clock()
            entry = generate(cycle, brief)
            rv = None
            if review:
                rv, s, ok = review(entry, brief)
                entry.update(score=s, approved=ok, veto=rv.get("veto", []), fix=rv.get("fix"), review=rv)
            cycles.append(entry)
            if best is None or (entry.get("score") or 0) > (best["score"] or 0):
                best = {"score": entry.get("score"), "entry": entry, "rv": rv, "ok": entry.get("approved")}
            left = None if task_budget is None or task_budget.remaining() is None else task_budget.remaining() - reserve_calls
            decision = self.decide(cycles, max_repairs, left, limit_reason)
            trace.append({"cycle": cycle, "id": entry.get("id"), "score": entry.get("score"), "approved": entry.get("approved"),
                          "decision": decision.action, "reason": decision.reason, "seconds": round(self.clock() - t0, 2),
                          **{k: v for k, v in (entry.get("meta") or {}).items() if k in ("request_id", "attempts", "ms", "usage")}})
            if decision.action != "repair":
                break
            if emit:
                emit("Corrigindo o briefing com a sugestão do critic…")
            new = revise(brief, rv) if revise else None
            if not new or new.get("question"):
                decision = Decision("stop", "o designer pediu esclarecimento em vez de um novo briefing; mantive a melhor tentativa")
                trace[-1].update(decision=decision.action, reason=decision.reason)
                break
            brief = new
        return {"cycles": cycles, "best": best, "decision": decision, "trace": trace}
