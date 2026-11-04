"""Regressão do histórico de conversas do chat_server: GET /api/convs, POST /api/conv/rename e /api/conv/delete.
Sobe uma instância própria (--mock) em porta livre, com dados temporários: python3 e2e_convs.py"""
import http.client, json, os, pathlib, socket, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parent
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); PORT = s.getsockname()[1]
tmp = tempfile.TemporaryDirectory(); DATA = pathlib.Path(tmp.name)
proc = subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(PORT), "--mock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env={**os.environ, "CHAT_DATA_DIR": tmp.name, "OPENAI_API_KEY": "fake"})


def req(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)  # http.client não normaliza o caminho
    c.request(method, path, None if body is None else json.dumps(body), {"Content-Type": "application/json"})
    r = c.getresponse(); raw = r.read()
    return r.status, (json.loads(raw) if raw else None)


ok = lambda c, m: print(("OK   " if c else "FALHA"), m) or (c or sys.exit(1))
listing = lambda cl="71": req("GET", f"/api/convs?client={cl}")
conv_dir = DATA / "conversations" / "71"


def chat(conv, text):
    st, j = req("POST", "/api/chat", {"client": "71", "conv": conv, "text": text, "size": "1024x1024"}); assert st == 200, (st, j)
    for _ in range(100):
        time.sleep(0.3); _, p = req("POST", "/api/job", {"id": j["job"], "since": 0})
        if p["status"] != "running": return p
    sys.exit("job não terminou")


try:
    for _ in range(50):
        try: req("GET", "/api/state"); break
        except Exception: time.sleep(0.2)
    else:
        sys.exit("o servidor do chat não subiu")

    # ---- vazio: cliente sem conversas ----
    ok(listing("nuncaexistiu")[1] == {"convs": [], "skipped": 0}, "cliente inexistente: lista vazia, skipped 0, sem erro")
    ok(not (DATA / "conversations" / "nuncaexistiu").exists(), "listar não cria pasta do cliente")

    # ---- conversas pelo fluxo real do mock ----
    long = "banner de promocao de verao " + "muito comprido " * 10
    for cid, text in (("ca", "primeiro pedido da conversa A"), ("cb", long), ("cc", "pedido da conversa C")):
        chat(cid, text); time.sleep(1.1)  # mtime em segundos: separa a ordem
    chat("ca", "agora mude a cor")  # A vira a mais recente e ganha 2 turnos
    st, body = listing()
    ids = [c["id"] for c in body["convs"]]
    ok(st == 200 and ids == ["ca", "cc", "cb"], f"ordem do mais recente ao mais antigo: {ids}")
    by = {c["id"]: c for c in body["convs"]}
    ok({"id", "title", "updated", "count"} <= set(by["ca"]) and body["skipped"] == 0, "contrato: campos do histórico (mais os aditivos de escopo/cliente/projeto) e skipped 0")
    ok(by["ca"]["title"] == "primeiro pedido da conversa A", "título = primeira mensagem do usuário")
    ok(len(by["cb"]["title"]) <= 61 and by["cb"]["title"].startswith("banner de promocao") and by["cb"]["title"].endswith("…"), "título longo truncado (~60)")
    ok(by["ca"]["count"] == len(req("POST", "/api/conv", {"client": "71", "conv": "ca"})[1]["turns"]) >= 2 and by["cc"]["count"] >= 1, "count = nº de mensagens da conversa")
    ok(all(isinstance(c["updated"], int) and abs(c["updated"] - time.time()) < 120 for c in body["convs"]), "updated em epoch segundos")

    # ---- conversa vazia e arquivo corrompido ----
    (conv_dir / "vazia.json").write_text(json.dumps({"id": "vazia", "client": "71", "turns": []}))
    (conv_dir / "quebrada.json").write_text("{isto nao e json")
    (conv_dir / "semturns.json").write_text(json.dumps({"id": "x"}))
    st, body = listing()
    ok([c["id"] for c in body["convs"]] == ["ca", "cc", "cb"], "conversa sem mensagens omitida")
    ok(st == 200 and body["skipped"] == 2, f"corrompido/sem campo 'turns' não derruba a lista e aparece em skipped ({body['skipped']})")
    ok((conv_dir / "quebrada.json").exists(), "listar não apaga nem renomeia o arquivo corrompido")
    (conv_dir / "quebrada.json").unlink(); (conv_dir / "semturns.json").unlink(); (conv_dir / "vazia.json").unlink()

    # ---- rename ----
    before = {c["id"]: c for c in listing()[1]["convs"]}
    raw_before = json.loads((conv_dir / "cc.json").read_text())
    ok(req("POST", "/api/conv/rename", {"client": "71", "conv": "cc", "title": "  Campanha Verão  "}) == (200, {"ok": True}), "rename: 200 {ok:true}")
    after = {c["id"]: c for c in listing()[1]["convs"]}
    ok(after["cc"]["title"] == "Campanha Verão", "título renomeado (strip) aparece na lista")
    ok(after["cc"]["updated"] == before["cc"]["updated"] and [c for c in after] == [c for c in before], "renomear não muda updated nem a ordem")
    raw_after = json.loads((conv_dir / "cc.json").read_text())
    ok({k: v for k, v in raw_after.items() if k != "title"} == raw_before and "title" not in raw_before, "formato aditivo: só o campo 'title' foi acrescentado")
    st, c = req("POST", "/api/conv", {"client": "71", "conv": "cc"})
    ok(st == 200 and c["turns"] == raw_before["turns"], "load_conv funciona com o campo title")
    chat("cc", "outra mensagem depois de renomear")
    st, c2 = req("POST", "/api/conv", {"client": "71", "conv": "cc"})
    ok(len(c2["turns"]) == len(raw_before["turns"]) + 1 and listing()[1]["convs"][0]["title"] == "Campanha Verão", "chat continua a conversa e preserva o título")
    ok(req("POST", "/api/conv/rename", {"client": "71", "conv": "ca", "title": "x" * 80})[0] == 200, "título com 80 chars aceito")
    for bad in ("", "   ", "x" * 81, None, 5, ["a"]):
        ok(req("POST", "/api/conv/rename", {"client": "71", "conv": "ca", "title": bad})[0] == 400, f"título inválido {str(bad)[:12]!r} -> 400")
    ok(req("POST", "/api/conv/rename", {"client": "71", "conv": "ca"})[0] == 400, "sem título -> 400")
    ok(req("POST", "/api/conv/rename", {"client": "71", "conv": "naoexiste", "title": "t"})[0] == 404, "rename de conversa inexistente -> 404")
    ok(not (conv_dir / "naoexiste.json").exists(), "rename inexistente não cria arquivo")
    (conv_dir / "quebrada.json").write_text("{x")
    ok(req("POST", "/api/conv/rename", {"client": "71", "conv": "quebrada", "title": "t"})[0] == 422 and (conv_dir / "quebrada.json").read_text() == "{x", "rename de arquivo ilegível -> 422 e não o sobrescreve")
    (conv_dir / "quebrada.json").unlink()

    # ---- ids maliciosos: nada fora da pasta pode ser tocado e nada é apagado "por aproximação" ----
    outside = DATA / "conversations" / "alvo.json"; outside.write_text(json.dumps({"turns": [{"request": "a"}]}))
    victim = DATA / "conversations" / "71" / "ca.json"
    other = DATA / "conversations" / "outro"; other.mkdir(); (other / "ca.json").write_text(json.dumps({"turns": [{"request": "de outro cliente"}]}))
    bads = ["../alvo", "../71/ca", "..", ".", "%2e%2e/alvo", "%2e%2e%2falvo", "a/b", "a\\b", "ca/", "/ca", "CA", "ca\x00", "ca.json", "ca ", "", "../../etc/passwd"]
    for ep, extra in (("/api/conv/delete", {}), ("/api/conv/rename", {"title": "pwn"})):
        for bad in bads:
            for body in ({"client": "71", "conv": bad}, {"client": bad, "conv": "ca"}):
                st, _ = req("POST", ep, {**body, **extra})
                ok(st in (400, 404), f"{ep} {json.dumps(body)} -> {st}")
    ok(outside.exists() and victim.exists() and (other / "ca.json").exists(), "nenhum arquivo fora do alvo foi apagado")
    ok(json.loads(outside.read_text())["turns"][0]["request"] == "a" and "title" not in json.loads((other / "ca.json").read_text()), "nenhum arquivo fora do alvo foi alterado")
    for bad in ("../71", "%2e%2e", "a/b", "", "71/../71", "71%00"):
        ok(req("GET", f"/api/convs?client={bad}")[0] in (400, 404), f"GET /api/convs?client={bad!r} rejeitado")
    ok(req("GET", "/api/convs")[0] == 200 and req("GET", "/api/convs?client=")[0] == 400, "GET sem client lista todos os escopos; client vazio -> 400")
    ok(req("POST", "/api/conv/delete", {"client": "71"})[0] == 400, "delete sem conv -> 400")

    # ---- delete: só o JSON da conversa, idempotência ----
    out_dir = DATA / "chat_out" / "71"; out_dir.mkdir(parents=True, exist_ok=True)
    imgs = [p for p in list((DATA / "chat_out").rglob("*")) + list((DATA / "clients").rglob("*")) if p.is_file()]
    snapshot = sorted(str(p) for p in imgs)
    ok(len(snapshot) > 0, f"há arquivos de imagem de saída/biblioteca para proteger ({len(snapshot)})")
    ok(req("POST", "/api/conv/delete", {"client": "71", "conv": "cb"}) == (200, {"ok": True}), "delete: 200 {ok:true}")
    ok(not (conv_dir / "cb.json").exists() and "cb" not in [c["id"] for c in listing()[1]["convs"]], "conversa some do disco e da lista")
    ok(sorted(str(p) for p in list((DATA / "chat_out").rglob("*")) + list((DATA / "clients").rglob("*")) if p.is_file()) == snapshot, "imagens de saída e biblioteca intactas")
    ok(req("POST", "/api/conv/delete", {"client": "71", "conv": "cb"})[0] == 404, "segundo delete -> 404 (idempotente, sem efeito)")
    ok(req("POST", "/api/conv/delete", {"client": "71", "conv": "naoexiste"})[0] == 404, "delete de inexistente -> 404")
    ok(req("POST", "/api/conv/delete", {"client": "nuncaexistiu", "conv": "ca"})[0] == 404, "delete em cliente inexistente -> 404")
    ok([c["id"] for c in listing()[1]["convs"]] == ["cc", "ca"] or sorted(c["id"] for c in listing()[1]["convs"]) == ["ca", "cc"], "as outras conversas seguem na lista")

    # ---- A1: excluir durante um job não ressuscita a conversa ----
    st, j = req("POST", "/api/chat", {"client": "71", "conv": "ca", "text": "mais uma alteração", "size": "1024x1024"}); assert st == 200
    st, e = req("POST", "/api/conv/delete", {"client": "71", "conv": "ca"})
    ok(st == 409 and "gerando" in e["error"] and victim.exists(), "delete com job em andamento -> 409 com mensagem clara e conversa intacta")
    for _ in range(100):
        time.sleep(0.3)
        if req("POST", "/api/job", {"id": j["job"], "since": 0})[1]["status"] != "running": break
    ok(req("POST", "/api/conv/delete", {"client": "71", "conv": "ca"}) == (200, {"ok": True}), "terminado o job, delete funciona")
    time.sleep(1.5)
    ok(not victim.exists() and "ca" not in [c["id"] for c in listing()[1]["convs"]], "a conversa excluída não reaparece depois do job")
    chat("novaid", "conversa nova depois da exclusão")
    ok("novaid" in [c["id"] for c in listing()[1]["convs"]], "conversa nova com outro id funciona")

    # ---- A2: rename grava só no arquivo alvo e trata JSON inesperado ----
    for name, content in (("lista", "[]"), ("numero", "5"), ("semchaves", '{"turns": [{"request": "x"}]}')):
        (conv_dir / f"{name}.json").write_text(content)
    ok(all(req("POST", "/api/conv/rename", {"client": "71", "conv": n, "title": "t"})[0] == (200 if n == "semchaves" else 422) for n in ("lista", "numero", "semchaves")),
       "JSON que não é objeto -> 422 (não 500); objeto sem client/id é renomeado")
    ok((conv_dir / "lista.json").read_text() == "[]" and (conv_dir / "numero.json").read_text() == "5", "422 não sobrescreve o arquivo")
    ok(json.loads((conv_dir / "semchaves.json").read_text())["title"] == "t" and sorted(p.name for p in conv_dir.glob("semchaves*")) == ["semchaves.json"], "sem chaves: título gravado no próprio arquivo, sem .tmp sobrando")
    (conv_dir / "alias.json").write_text(json.dumps({"id": "cc", "client": "outro", "turns": [{"request": "id interno aponta para cc"}]}))
    cc_before = (conv_dir / "cc.json").read_text(); outro_before = (other / "ca.json").read_text()
    ok(req("POST", "/api/conv/rename", {"client": "71", "conv": "alias", "title": "só o alias"})[0] == 200, "rename de arquivo com id interno diferente do nome")
    ok((conv_dir / "cc.json").read_text() == cc_before and (other / "ca.json").read_text() == outro_before and not (other / "cc.json").exists(), "o id/cliente de dentro do arquivo não redirecionam a escrita")
    ok(json.loads((conv_dir / "alias.json").read_text())["title"] == "só o alias", "só o arquivo alvo foi alterado")
    for n in ("lista", "numero", "semchaves", "alias"): (conv_dir / f"{n}.json").unlink()

    # ---- só o navegador local ----
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    c.request("POST", "/api/conv/delete", json.dumps({"client": "71", "conv": "cc"}), {"Origin": "http://evil.example"})
    ok(c.getresponse().status == 403 and (conv_dir / "cc.json").exists(), "POST com Origin externo -> 403 e nada apagado")
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    c.request("GET", "/api/convs?client=71", headers={"Host": "evil.example"})
    ok(c.getresponse().status == 403, "GET com Host externo -> 403")
    print("\nTUDO OK")
finally:
    proc.terminate(); tmp.cleanup()
