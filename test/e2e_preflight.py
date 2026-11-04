#!/usr/bin/env python3
"""E2E do preflight e do escalonamento do Runner contra a OpenAI falsa. Sem chave real, sem custo.

  python3 e2e_preflight.py

Cenário A: orçamento da sessão = 0. O preflight tem que barrar ANTES do briefing pago e de qualquer imagem
           (a OpenAI falsa conta as chamadas: 0 redator de briefing, 0 gerações).
Cenários C, D, E (texto): 429 transitório nas chamadas de texto é repetido e a tarefa conclui; orçamento de texto da
           sessão = 0 ou da tarefa = 1 interrompe a tarefa com mensagem clara (nem o briefing nem a imagem acontecem).
Cenário B: orçamento da tarefa = 1. O preflight limita o laço a 1 geração; o critic reprova (a falsa reprova o 1º
           review) e o resultado sai ESCALONADO para revisão humana, sem 2ª geração.
"""
import json, os, pathlib, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(port, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def ok(c, m):
    print(("OK   " if c else "FALHA"), m)
    if not c:
        sys.exit(1)


class Stack:
    def __init__(self, fake_delay=0, **env):
        self.fake, self.chat = free_port(), free_port()
        self.tmp = tempfile.TemporaryDirectory()
        e = {**os.environ, "CHAT_DATA_DIR": self.tmp.name, "OPENAI_API_KEY": "fake", "OPENAI_BASE_URL": f"http://127.0.0.1:{self.fake}/v1", **env}
        self.procs = [subprocess.Popen([sys.executable, str(ROOT / "fake_openai.py"), "--port", str(self.fake), "--delay", str(fake_delay)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
                      subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(self.chat)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=e)]
        for port, path in ((self.fake, "/__stats"), (self.chat, "/api/state")):
            for _ in range(60):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1)
                    break
                except Exception:
                    time.sleep(0.2)
            else:
                sys.exit("servidor não subiu")

    def run(self, body):
        st, j = call(self.chat, "/api/chat", body)
        assert st == 200, (st, j)
        since, steps = 0, []
        for _ in range(200):
            time.sleep(0.3)
            _, p = call(self.chat, "/api/job", {"id": j["job"], "since": since})
            since = p["next"]
            steps += p["steps"]
            if p["status"] != "running":
                return p, steps
        sys.exit("timeout")

    def events(self):
        p = os.path.join(self.tmp.name, "logs", "events.jsonl")
        return [json.loads(x) for x in open(p, encoding="utf-8").read().splitlines() if x.strip()] if os.path.exists(p) else []

    def stats(self):
        return call(self.fake, "/__stats")[1]

    def close(self):
        for p in self.procs:
            p.terminate()
        self.tmp.cleanup()


def main():
    print("== A: sessão sem orçamento")
    a = Stack(IMAGE_BUDGET_SESSION="0")
    try:
        p, steps = a.run({"client": "71", "text": "paisagem de praia", "review": False})
        s = a.stats()
        ok(p["status"] == "error" and "Pré-checagem falhou" in p["error"] and "orçamento da sessão esgotado" in p["error"], f"job termina em erro claro: {p['error'][:90]}")
        ok(s["chat_writer"] == 0, "o redator de briefing (chamada paga de texto) NÃO foi chamado")
        ok(s["generations"] == 0 and s["edits"] == 0, "nenhuma imagem foi gerada")
        ok(not any("Pré-checagem ok" in x["text"] for x in steps), "não anunciou pré-checagem ok")
    finally:
        a.close()
    print("== B: orçamento da tarefa = 1")
    b = Stack(IMAGE_BUDGET_TASK="1")
    try:
        p, steps = b.run({"client": "71", "text": "banner de promocao de verao"})
        m, s = p["message"], b.stats()
        ok(p["status"] == "done" and m["kind"] == "image", "job termina com imagem")
        ok(m["generations"] == 1 and s["generations"] == 1, "o laço foi limitado a 1 geração (sem reparo)")
        ok(m["approved"] is False, "a falsa reprova o 1º review: a imagem não foi aprovada")
        ok(any("Escalado para revisão humana" in x and "orçamento de chamadas limitou o plano a 1 geração" in x for x in m["avisos"]), f"escalonamento explicado ao usuário: {[x for x in m['avisos'] if 'Escalado' in x]}")
        ok(any("orçamento da tarefa permite só 1" in x for x in m["avisos"]), "o preflight avisou que o orçamento limitou o plano")
        ok(m["preflight"] and "parametros" in m["preflight"] and "credencial" in m["preflight"], f"resposta registra as checagens feitas: {m['preflight']}")
        ok(len(m["trace"]) == 1 and m["trace"][0]["decision"] == "escalate" and m["trace"][0]["attempts"] == 1 and m["trace"][0]["score"] is not None,
           "trace da execução vem na resposta: decisão, tentativas e nota")
        ok(any("Pré-checagem ok" in x["text"] for x in steps), "o passo 'Pré-checagem ok' aparece no progresso")
    finally:
        b.close()
    print("== C: 429 transitório no texto")
    c = Stack()
    try:
        p, steps = c.run({"client": "71", "text": "banner flaky429 de verao", "review": False})
        s = c.stats()
        ok(p["status"] == "done" and p["message"]["kind"] == "image", "a tarefa conclui com imagem apesar do 429 nas chamadas de texto")
        ok(s["injected"] >= 2, f"houve falhas de texto injetadas e repetidas ({s['injected']} no total)")
        ok(not [a for a in p["message"]["avisos"] if "não consegui resolver o contexto" in a], "o resolvedor se recuperou: sem aviso de contexto degradado")
    finally:
        c.close()
    print("== D: orçamento de texto da sessão = 0")
    d = Stack(TEXT_BUDGET_SESSION="0")
    try:
        p, steps = d.run({"client": "71", "text": "paisagem de praia", "review": False})
        s = d.stats()
        ok(p["status"] == "error" and "texto da sessão" in p["error"] and "esgotado" in p["error"], f"job para com erro claro: {p['error'][:90]}")
        ok(s["chat_writer"] == 0 and s["generations"] == 0 and s["edits"] == 0 and s["resolver_users"] == [], "nenhuma chamada de texto nem de imagem chegou à OpenAI")
    finally:
        d.close()
    print("== E: orçamento de texto da tarefa = 1")
    e = Stack(TEXT_BUDGET_TASK="1")
    try:
        p, steps = e.run({"client": "71", "text": "paisagem de praia", "review": False})
        s = e.stats()
        ok(p["status"] == "error" and "texto da tarefa" in p["error"], f"job para quando a 2ª chamada de texto excede a tarefa: {p['error'][:90]}")
        ok(len(s["resolver_users"]) == 1 and s["chat_writer"] == 0 and s["generations"] == 0, "o resolvedor usou a única chamada; o briefing e a imagem não aconteceram")
    finally:
        e.close()
    print("== F: com prazo ativo, orçamento de texto esgotado no critic ainda para a tarefa")
    f = Stack(CHAT_DEADLINE_S="200", CHAT_MIN_GEN_S="1", TEXT_BUDGET_TASK="2")
    try:
        p, steps = f.run({"client": "71", "text": "paisagem de praia"})
        s = f.stats()
        ok(p["status"] == "error" and "texto da tarefa" in p["error"] and "esgotado" in p["error"],
           f"o critic sem orçamento NÃO é tratado como 'estourou o tempo': a tarefa para ({p['error'][:80]})")
        ok(s["generations"] + s["edits"] == 1 and s["chat_critic"] == 0, "a imagem foi gerada e o critic nem chegou à OpenAI")
    finally:
        f.close()
    print("== G: com prazo ativo e orçamento suficiente, o critic roda normalmente")
    g = Stack(CHAT_DEADLINE_S="200", CHAT_MIN_GEN_S="1")
    try:
        p, steps = g.run({"client": "71", "text": "paisagem de praia"})
        m = p["message"]
        ok(p["status"] == "done" and m["kind"] == "image" and m["score"] is not None and not any("Entreguei a melhor versão" in a for a in m["avisos"]),
           "com prazo folgado: imagem revisada, sem aviso de corte")
    finally:
        g.close()
    print("== H: sem tempo para o critic depois da imagem (prazo total)")
    h = Stack(fake_delay=6, CHAT_DEADLINE_S="12", CHAT_DEADLINE_MARGIN="4", CHAT_MIN_GEN_S="1")
    try:
        p, steps = h.run({"client": "71", "text": "paisagem de praia", "improve": {"compare_raw": True}})
        m, s = p["message"], h.stats()
        ok(p["status"] == "done" and m["kind"] == "image" and m["generations"] == 1 and m["score"] is None, f"imagem entregue SEM nota ({m['generations']} geração)")
        ok("Entreguei a melhor versão que deu tempo de fazer." in m["avisos"], "aviso amigável do prazo")
        ok(not any("Escalado" in a for a in m["avisos"]), "corte por prazo NÃO é rotulado como escalonamento para revisão humana")
        ok(s["chat_critic"] == 0, "o critic não foi chamado")
        ok(any(e["kind"] == "prazo" and e.get("etapa") == "antes do critic" for e in h.events()), "registrado no log: prazo, etapa 'antes do critic'")
        ok("raw" not in m and s["generations"] + s["edits"] == 1, "a comparação 'GPT puro' não roda depois de um corte (nem gasta a 2ª imagem)")
    finally:
        h.close()
    print("== I: revisou, mas não cabe outra volta (prazo total)")
    # janela do prazo D (g = geração ~2 s, p = trabalho antes dela ~0,2 s, r = revisão ~0,3 s, M = margem 4 s):
    #   revisa se D >= 1,6g + p + M (~7,4 s);  NÃO repara se D < 2,15g + p + 2,15r + M (~9,2 s)  ->  D = 8,3 s fica no meio
    i = Stack(fake_delay=2, CHAT_DEADLINE_S="8.3", CHAT_DEADLINE_MARGIN="4", CHAT_MIN_GEN_S="1")
    try:
        p, steps = i.run({"client": "71", "text": "paisagem de praia"})
        m, s = p["message"], i.stats()
        ok(p["status"] == "done" and m["generations"] == 1 and m["approved"] is False and m["score"] is not None, f"1 geração revisada e reprovada (nota {m['score']}), sem reparo")
        ok(s["chat_critic"] == 1, "o critic foi chamado uma vez")
        ok("Entreguei a melhor versão que deu tempo de fazer." in m["avisos"] and not any("Escalado" in a for a in m["avisos"]), "corte por prazo: só o aviso do prazo, sem 'escalado'")
        ok(m["trace"][-1]["decision"] == "stop" and "prazo" in m["trace"][-1]["reason"], f"trace: decisão stop por prazo ({m['trace'][-1]['reason'][:50]})")
        ok(any(e["kind"] == "prazo" and e.get("etapa") == "antes da correção" for e in i.events()), "registrado no log: prazo, etapa 'antes da correção'")
    finally:
        i.close()
    print("== J: CHAT_MAX_CYCLES chega ao laço")
    j = Stack(CHAT_MAX_CYCLES="0")
    try:
        p, steps = j.run({"client": "71", "text": "paisagem de praia"})
        m = p["message"]
        ok(m["generations"] == 1 and m["approved"] is False, "CHAT_MAX_CYCLES=0: uma geração, mesmo com o critic reprovando")
        ok(any("Escalado para revisão humana" in a and "limite de 0 reparo" in a for a in m["avisos"]), "...e escalona com o motivo certo")
    finally:
        j.close()
    print("\nTUDO OK")


if __name__ == "__main__":
    main()
