#!/usr/bin/env python3
"""E2E do preflight e do escalonamento do Runner contra a OpenAI falsa. Sem chave real, sem custo.

  python3 e2e_preflight.py

Cenário A: orçamento da sessão = 0. O preflight tem que barrar ANTES do briefing pago e de qualquer imagem
           (a OpenAI falsa conta as chamadas: 0 redator de briefing, 0 gerações).
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
    def __init__(self, **env):
        self.fake, self.chat = free_port(), free_port()
        self.tmp = tempfile.TemporaryDirectory()
        e = {**os.environ, "CHAT_DATA_DIR": self.tmp.name, "OPENAI_API_KEY": "fake", "OPENAI_BASE_URL": f"http://127.0.0.1:{self.fake}/v1", **env}
        self.procs = [subprocess.Popen([sys.executable, str(ROOT / "fake_openai.py"), "--port", str(self.fake)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
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
    print("\nTUDO OK")


if __name__ == "__main__":
    main()
