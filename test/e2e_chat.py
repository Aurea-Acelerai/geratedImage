#!/usr/bin/env python3
"""Teste de ponta a ponta do chat contra a OpenAI falsa (fake_openai.py). Sem chave, sem custo.

  python3 e2e_chat.py

Sobe a OpenAI falsa e o chat em portas livres, com uma pasta de dados TEMPORÁRIA (CHAT_DATA_DIR): nunca toca em
test/clients nem test/chat_out, que guardam o seu uso real. Prova que o nosso código monta as requisições, trata as
respostas e respeita modos e melhorias; não valida a semântica da API real.

Variantes (a mesma bateria inteira):
  python3 e2e_chat.py                          disco (FileStore), tarefas em thread: o comportamento local de sempre
  E2E_INLINE=1 python3 e2e_chat.py             idem, mas com JOBS_INLINE=1 (o pipeline roda dentro da requisição; estado no Store)
  E2E_STORE=memory python3 e2e_chat.py         servidor NO MESMO PROCESSO com STORE=memory: prova que nenhum ponto de chamada
                                               toca o disco (a pasta temporária de dados fica vazia)
  E2E_STORE=memory E2E_INLINE=1 ...            as duas coisas juntas (é o que a Vercel faz)
O teste lê e grava o estado só pela interface Store (S), nunca por caminhos de disco, para valer nas quatro variantes.
"""
import base64, json, os, pathlib, socket, struct, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request, zlib

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import store as store_mod  # noqa: E402
STORE_MODE = os.getenv("E2E_STORE", "file")
INLINE = os.getenv("E2E_INLINE") == "1"
assert STORE_MODE in ("file", "memory"), "E2E_STORE deve ser file ou memory"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


FAKE, CHAT = free_port(), free_port()
tmp = tempfile.TemporaryDirectory()
SRV_ENV = {"CHAT_DATA_DIR": tmp.name, "OPENAI_API_KEY": "fake", "OPENAI_BASE_URL": f"http://127.0.0.1:{FAKE}/v1",
           "COMMONS_API": f"http://127.0.0.1:{FAKE}/w/api.php", "WEB_ALLOW_LOCAL": "1"}
if INLINE:
    SRV_ENV["JOBS_INLINE"] = "1"
procs = [subprocess.Popen([sys.executable, str(ROOT / "fake_openai.py"), "--port", str(FAKE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
if STORE_MODE == "file":
    S = store_mod.FileStore(tmp.name)  # o servidor (processo filho) grava aqui; o teste lê pelo mesmo contrato
    procs.append(subprocess.Popen([sys.executable, str(ROOT / "chat_server.py"), "--port", str(CHAT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  env={**os.environ, **SRV_ENV}))
else:
    os.environ.update({**SRV_ENV, "STORE": "memory"})
    import chat_server as cs0  # noqa: E402
    from http.server import ThreadingHTTPServer
    S = cs0.get_store()
    assert S.name == "memory"
    srv0 = ThreadingHTTPServer(("127.0.0.1", 0), cs0.H)  # porta 0: o SO escolhe no bind (free_port() + import lento de chat_server era uma corrida entre sessões)
    CHAT = srv0.server_address[1]
    threading.Thread(target=srv0.serve_forever, daemon=True).start()
try:
    for _ in range(50):  # a OpenAI falsa precisa estar de pé antes da primeira chamada (o servidor em memória sobe na hora)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{FAKE}/__stats", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CHAT}/api/state", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        sys.exit("o servidor do chat não subiu")

    def call(base, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{base}{path}", data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    def png(w,h):
        raw=b"".join(b"\x00"+b"\x80"*w for _ in range(h)); c=lambda t,d: struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
        return b"\x89PNG\r\n\x1a\n"+c(b"IHDR",struct.pack(">IIBBBBB",w,h,8,0,0,0,0))+c(b"IDAT",zlib.compress(raw))+c(b"IEND",b"")
    def run(body):
        st, j = call(CHAT, "/api/chat", body); assert st == 200, (st, j)
        steps, since = [], 0
        for _ in range(200):
            time.sleep(0.4); _, p = call(CHAT, "/api/job", {"id": j["job"], "since": since}); since = p["next"]; steps += p["steps"]
            if p["status"] != "running": return p, steps
        raise SystemExit("timeout")
    ok = lambda c, m: print(("OK   " if c else "FALHA"), m) or (c or sys.exit(1))

    st, m = call(CHAT, "/api/models"); print("models:", m)
    ok(m["ok"] and "gpt-image-2.5-sunburst" in m["image_models"] and "gpt-5.5" in m["text_models"] and "whisper-1" not in m["text_models"], "lista de modelos filtrada e sem avisos")
    _, a = call(CHAT, "/api/asset", {"client": "71", "kind": "logo", "name": "logo.png", "mime": "image/png", "b64": base64.b64encode(png(64, 64)).decode()}); aid = a["asset"]["id"]
    st, e = call(CHAT, "/api/asset", {"client": "71", "kind": "logo", "name": "l.svg", "mime": "image/svg+xml", "b64": "AA=="}); ok(st == 400 and "SVG" in e["error"], "SVG recusado no modo real")

    # 1) com logo: briefing vê a imagem, edição multipart, reprova no 1º ciclo e aprova no 2º
    p, steps = run({"client": "71", "text": "banner de promocao de verao com a nossa logo", "asset_ids": [aid], "size": "1536x1024", "quality": "low"})
    msg = p["message"]; print("passos:", [s["text"][:60] for s in steps])
    ok(p["status"] == "done" and msg["kind"] == "image", "job terminou com imagem")
    ok(msg["generations"] == 2 and msg["approved"] and msg["score"] >= 8, f"correção funcionou: 2 gerações, nota {msg['score']}")
    ok(len(msg["cycles"]) == 2 and msg["cycles"][0]["approved"] is False and msg["cycles"][0]["fix"], "ciclo 1 reprovado com correção")
    ok(all(c["url"] for c in msg["cycles"]) and msg["id"] == msg["cycles"][1]["id"], "cada tentativa salvou sua imagem; a melhor é a final")
    ok(any(s.get("image_url") for s in steps), "progresso mostra imagem intermediária")
    ok("design-tipografia-texto" in msg["skills"], "skills roteadas no caminho real")
    _, s = call(FAKE, "/__stats")
    ok(s["edits"] == 2 and s["edit_images"] == [1, 1] and s["generations"] == 0, f"usou /images/edits com a logo (image[]={s['edit_images']})")
    ok(s["writer_images"][0] == 1, "o designer recebeu a logo como imagem")
    ok(s["critic_images"][0] == 2, "o critic recebeu a imagem gerada + a logo de referência")
    ok([a for a in s["auth"] if a] == ["Bearer fake"], "autenticação enviada em todas as chamadas à API")
    ok("quality" in s["edit_fields"][0] and "prompt" in s["edit_fields"][0], "campos do multipart")

    # 2) edição da imagem anterior (alvo) + sem logo
    p, _ = run({"client": "71", "text": "deixe mais quente", "edit_of": msg["id"], "history": [{"role": "user", "text": "banner"}], "review": False})
    m2 = p["message"]; ok(m2["kind"] == "image" and m2["score"] is None and m2["inputs"][0]["kind"] == "alvo", "edição usa a imagem anterior como alvo, sem revisão")
    _, s = call(FAKE, "/__stats"); ok(s["edits"] == 3, "mais uma chamada de edição")
    ok("Conversa até aqui" in s["last_writer_user"] and "ALVO DE EDIÇÃO" in s["last_writer_user"], "histórico e alvo no briefing")

    # 3) sem imagens: /images/generations
    p, _ = run({"client": "71", "text": "paisagem de praia", "review": False}); ok(p["message"]["kind"] == "image", "geração sem entradas")
    _, s = call(FAKE, "/__stats"); ok(s["generations"] == 1, "usou /images/generations")

    # 4) tamanho errado: veto por código mesmo com nota alta
    p, _ = run({"client": "71", "text": "banner wrongsize", "size": "1024x1024"}); m3 = p["message"]
    ok("formato_incorreto" in m3["veto"] and m3["approved"] is False, f"veto formato_incorreto aplicado (vetos {m3['veto']})")

    # 5) pergunta do designer
    p, _ = run({"client": "71", "text": "preciso perguntar algo"}); ok(p["message"]["kind"] == "text" and "oferta" in p["message"]["text"].lower(), "designer pergunta quando falta a oferta")
    # 6) validações síncronas
    ok(call(CHAT, "/api/chat", {"client": "71", "text": " "})[0] == 400, "mensagem vazia recusada na hora")
    ok(call(CHAT, "/api/chat", {"client": "71", "text": "x", "edit_of": "naoexiste"})[0] == 404, "alvo inexistente recusado na hora")
    ok(call(CHAT, "/api/job", {"id": "nada"})[0] == 404, "job inexistente")

    # 7) modos, melhorias independentes e comparação com o GPT puro
    p, _ = run({"client": "71", "text": "um gato astronauta numa estacao espacial", "review": False}); m = p["message"]
    _, s = call(FAKE, "/__stats"); sysm = s["writer_systems"][-1]
    ok(sysm["livre"] and not sysm["marca"] and not sysm["setor_no_prompt"], f"modo livre (padrão): nada do cliente no system prompt {sysm}")
    ok(m["mode"] == "livre" and "design-estrategia" not in m["skills"], f"imagem livre não carrega a skill de estratégia de marketing ({m['skills']})")
    p, _ = run({"client": "71", "text": "banner de black friday", "mode": "marca", "review": False}); m = p["message"]
    _, s = call(FAKE, "/__stats"); sysm = s["writer_systems"][-1]
    ok(sysm["marca"] and sysm["setor_no_prompt"] and m["mode"] == "marca", "modo com marca carrega o cliente")
    ok("design-estrategia" in m["skills"], "peça de marketing carrega a skill de estratégia")
    n_writers = s["chat_writer"]
    p, steps = run({"client": "71", "text": "garrafa de vidro ambar sobre marmore preto", "improve": {"designer": False}, "review": False}); m = p["message"]
    _, s = call(FAKE, "/__stats")
    ok(s["chat_writer"] == n_writers, "designer desligado: nenhuma chamada ao redator de briefing")
    ok(s["image_prompts"][-1] == "garrafa de vidro ambar sobre marmore preto", "o texto do usuário vai EXATAMENTE ao modelo de imagem")
    ok(m["skills"] == [] and m["generations"] == 1 and m["prompt"] == m["request"], "sem designer: sem skills, 1 geração, prompt = pedido")
    p, steps = run({"client": "71", "text": "retrato de senhora idosa rindo", "improve": {"compare_raw": True}}); m = p["message"]
    _, s = call(FAKE, "/__stats")
    ok(m.get("raw") and m["raw"]["url"] and m["raw"].get("score") is not None, "comparação: GPT puro gerado e avaliado na mesma régua")
    ok(s["image_prompts"][-1] == "retrato de senhora idosa rindo", "a versão pura usa só o texto do usuário")
    ok(any("GPT puro" in x["text"] for x in steps), "progresso informa a versão pura")
    pa = run({"client": "71", "text": "gato astronauta", "review": False})[0]["message"]["prompt"]
    pb = run({"client": "71", "text": "garrafa de vidro", "review": False})[0]["message"]["prompt"]
    ok(pa != pb and "gato" in pa.lower() and "garrafa" in pb.lower() and "praia" not in (pa + pb).lower(), "pedidos diferentes geram briefings diferentes, sem cena do cliente")

    # 8) o critic recebe só os critérios do caso de uso (base neutra + pacotes)
    p, _ = run({"client": "71", "text": "um gato astronauta numa estacao espacial"}); m = p["message"]
    _, s = call(FAKE, "/__stats"); cs = s["critic_systems"][-1]
    ok(m["packs"] == [] and cs["subject"] and not cs["hierarchy"] and not cs["cta_vago"] and not cs["brand_fit"], f"imagem livre: critic só com a base ({cs})")
    ok(m["score"] is not None, "imagem livre recebe nota")
    p, _ = run({"client": "71", "text": "banner de promocao de verao"}); m = p["message"]
    _, s = call(FAKE, "/__stats"); cs = s["critic_systems"][-1]
    ok("marketing" in m["packs"] and cs["hierarchy"] and cs["cta_vago"] and not cs["brand_fit"], f"peça de marketing: base + marketing ({m['packs']})")
    p, _ = run({"client": "71", "text": "retrato de senhora idosa rindo", "mode": "marca"}); m = p["message"]
    _, s = call(FAKE, "/__stats"); cs = s["critic_systems"][-1]
    ok(m["packs"] == ["brand"] and cs["brand_fit"] and not cs["hierarchy"], f"modo com marca: base + brand ({m['packs']})")
    p, _ = run({"client": "71", "text": 'cartaz com a frase "Bom dia"'}); m = p["message"]
    _, s = call(FAKE, "/__stats"); cs = s["critic_systems"][-1]
    ok("text" in m["packs"] and cs["text"], "texto entre aspas: pacote de texto")
    # 9) memória da conversa, referência de pessoa fixa, edição por contexto, fidelidade e identidade
    import pathlib
    PNGB = base64.b64encode(png(64, 64)).decode()
    pid = call(CHAT, "/api/asset", {"client": "71", "kind": "pessoa", "name": "rodrigo.webp", "mime": "image/png", "b64": PNGB})[1]["asset"]["id"]
    conv = "convmem1"
    p, _ = run({"client": "71", "conv": conv, "text": "gere uma imagem com o Rodrigo Faro na praia", "asset_ids": [pid], "review": False}); m1 = p["message"]
    _, s = call(FAKE, "/__stats")
    ok(m1["kind"] == "image" and "identity" in m1["packs"] and any(i["kind"] == "pessoa" for i in m1["inputs"]), f"pessoa anexada: pacote de identidade ({m1['packs']})")
    ok("input_fidelity" in s["edit_fields"][-1], "edição com pessoa pede input_fidelity=high")
    p, steps = run({"client": "71", "conv": conv, "text": "agora com camisa azul", "asset_ids": [pid], "review": False}); m2 = p["message"]
    _, s = call(FAKE, "/__stats")
    ok(m2["intent"] == "edit" and "Rodrigo Faro" in m2["resolved"] and "camisa azul" in m2["resolved"], f"o contexto lembra o Rodrigo: {m2['resolved']!r}")
    ok([i["kind"] for i in m2["inputs"]] == ["alvo", "pessoa"] and s["edit_images"][-1] == 2, f"edição usa a última imagem como alvo + a pessoa fixada ({[i['kind'] for i in m2['inputs']]})")
    ok("Rodrigo Faro" in s["last_writer_user"] and "EDIÇÃO" in s["last_writer_user"] and "Memória da conversa" in s["last_writer_user"], "o designer recebe memória, pedido resolvido e intenção")
    ok(any(x["text"].startswith("Memória: entendi como edição") for x in steps), "o progresso mostra o que a IA entendeu")
    p, _ = run({"client": "71", "conv": conv, "text": "preciso perguntar uma coisa", "review": False}); mq = p["message"]
    ok(mq["kind"] == "text", "designer pergunta")
    p, _ = run({"client": "71", "conv": conv, "text": "30% off", "asset_ids": [pid], "review": False}); m4 = p["message"]
    ok("preciso perguntar uma coisa" in m4["resolved"] and "30% off" in m4["resolved"] and m4["intent"] == "new", f"resposta à pergunta completa o pedido original: {m4['resolved']!r}")
    cfile = f"conversations/71/{conv}.json"
    cv = json.loads(S.read_text(cfile))
    ok(S.exists(cfile) and len(cv["turns"]) == 4 and cv["turns"][2].get("question") and cv["turns"][1]["intent"] == "edit", f"conversa salva em disco com {len(cv['turns'])} turnos")
    # conversa nova não herda memória
    p, _ = run({"client": "71", "conv": "convnova", "text": "agora com camisa azul", "review": False}); m5 = p["message"]
    ok(m5["intent"] == "new" and m5["resolved"] == "agora com camisa azul", "conversa nova começa sem memória")
    # fidelidade: o modelo recusa o parâmetro -> repete sem ele e avisa
    n0 = len(call(FAKE, "/__stats")[1]["edit_fields"])
    p, _ = run({"client": "71", "conv": "convfid", "text": "foto com a pessoa rejectfidelity", "asset_ids": [pid], "review": False}); mf = p["message"]
    ef = call(FAKE, "/__stats")[1]["edit_fields"][n0:]
    ok(len(ef) == 2 and "input_fidelity" in ef[0] and "input_fidelity" not in ef[1] and any("input_fidelity" in a for a in mf["avisos"]), "input_fidelity recusado: repete sem ele e avisa")
    # critic de identidade
    p, _ = run({"client": "71", "conv": "convid", "text": "retrato com a pessoa", "asset_ids": [pid]}); mi = p["message"]
    cs = call(FAKE, "/__stats")[1]["critic_systems"][-1]
    ok("identity" in mi["packs"] and cs["identity_match"], "critic recebe o critério identity_match quando há pessoa de referência")
    # retag do tipo na biblioteca
    ok(call(CHAT, "/api/asset/kind", {"client": "71", "id": pid, "kind": "referencia"})[0] == 200, "tipo da imagem pode ser corrigido")
    ok(call(CHAT, "/api/asset/kind", {"client": "71", "id": pid, "kind": "invalido"})[0] == 400, "tipo inválido recusado")
    # 10) problemas achados na revisão independente
    import threading
    # (a) duas tarefas simultâneas na mesma conversa não perdem turnos
    cc = "convconc"
    run({"client": "71", "conv": cc, "text": "uma xicara de cafe", "review": False})
    out = []
    ths = [threading.Thread(target=lambda tx=tx: out.append(run({"client": "71", "conv": cc, "text": tx, "review": False})[0]["status"])) for tx in ("um gato preto", "uma bicicleta azul")]
    [x.start() for x in ths]; [x.join() for x in ths]
    cvc = json.loads(S.read_text(f"conversations/71/{cc}.json"))
    ok(out == ["done", "done"] and [x["n"] for x in cvc["turns"]] == [1, 2, 3], f"duas tarefas simultâneas: nenhum turno perdido ({[x['n'] for x in cvc['turns']]})")
    # (b) anexo apagado da biblioteca não é ignorado em silêncio
    gid = call(CHAT, "/api/asset", {"client": "71", "kind": "pessoa", "name": "apagar.png", "mime": "image/png", "b64": PNGB})[1]["asset"]["id"]
    call(CHAT, "/api/asset/delete", {"client": "71", "id": gid})
    st, e = call(CHAT, "/api/chat", {"client": "71", "conv": "convdel", "text": "retrato", "asset_ids": [gid]})
    ok(st == 409 and "não existe mais" in e["error"], "imagem fixada que sumiu da biblioteca: erro claro, não geração sem referência")
    # (c) editar sem a imagem anterior vira pedido novo, com aviso
    p, _ = run({"client": "71", "conv": "convnoimg", "text": "um vaso de flores", "review": False}); mn = p["message"]
    for f in S.list(f"chat_out/71/{mn['id']}."):
        S.delete(f)
    p, _ = run({"client": "71", "conv": "convnoimg", "text": "agora mude para rosas vermelhas", "review": False}); mn2 = p["message"]
    ok(mn2["intent"] == "new" and any("imagem anterior" in a for a in mn2["avisos"]) and not any(i["kind"] in ("alvo", "variacao") for i in mn2["inputs"]), "sem a imagem anterior: vira pedido novo e avisa")
    # (d) editar uma imagem antiga: o resolvedor é avisado de qual é
    cd = "convold"
    first = run({"client": "71", "conv": cd, "text": "um farol no mar", "review": False})[0]["message"]
    run({"client": "71", "conv": cd, "text": "um deserto ao amanhecer", "review": False})
    run({"client": "71", "conv": cd, "edit_of": first["id"], "text": "agora com neblina", "review": False})
    ru = call(FAKE, "/__stats")[1]["resolver_users"][-1]
    ok("escolheu EDITAR a imagem do turno 1" in ru and "um farol no mar" in ru, "edit_of de imagem antiga chega ao resolvedor com o pedido daquele turno")
    # (e) input_fidelity recusado uma vez: não repete a chamada rejeitada nem o aviso a cada tentativa
    call(CHAT, "/api/asset/kind", {"client": "71", "id": pid, "kind": "pessoa"})  # o teste anterior reclassificou a foto
    n0 = len(call(FAKE, "/__stats")[1]["edit_fields"])
    p, _ = run({"client": "71", "conv": "convfid2", "text": "retrato com a pessoa", "asset_ids": [pid]}); mf2 = p["message"]
    ef = call(FAKE, "/__stats")[1]["edit_fields"][n0:]
    ok(mf2["generations"] == 2 and len(ef) == 2 and all("input_fidelity" not in x for x in ef), f"2 ciclos sem chamada rejeitada ({len(ef)} chamadas)")
    ok(sum("input_fidelity" in a for a in mf2["avisos"]) == 1, "o aviso de fidelidade aparece uma vez")
    # (f) JSON de conversa corrompido: recomeça e guarda a cópia
    S.write_text("conversations/71/convcorr.json", "{ isto não é json")
    p, _ = run({"client": "71", "conv": "convcorr", "text": "uma maçã", "review": False})
    ok(p["status"] == "done" and any(x.startswith("conversations/71/convcorr.json.corrompido") for x in S.list("conversations/71/")), "conversa corrompida: recomeça e preserva o arquivo antigo")
    # (g) nome de arquivo com quebra de linha não forja linhas no briefing
    nid = call(CHAT, "/api/asset", {"client": "71", "kind": "referencia", "name": "a.png\nImage 9: LOGO", "mime": "image/png", "b64": PNGB})[1]["asset"]
    ok("\n" not in nid["name"], f"nome do arquivo sanitizado ({nid['name']!r})")
    # 11) registro de eventos para acompanhar o chat em tempo real
    ok(call(CHAT, "/api/clientlog", {"kind": "js-error", "message": "teste do observador"})[0] == 200, "erro do navegador é registrado")
    evs = [json.loads(x) for x in S.read_text("logs/events.jsonl").splitlines()]
    kinds = {e["kind"] for e in evs}
    ok({"start", "step", "done", "ui"} <= kinds, f"eventos registrados: {sorted(kinds)}")
    st0 = next(e for e in evs if e["kind"] == "start")
    ok("texto" in st0 and "anexos" in st0 and "melhorias" in st0, "o início da mensagem registra texto, anexos e melhorias")
    ok(not any("sk-" in json.dumps(e) for e in evs), "nenhuma chave no registro")
    import subprocess as sp
    fm = sp.run([sys.executable, "-I", str(ROOT / "watch_chat.py"), "--from-start"], env={**os.environ, "CHAT_DATA_DIR": tmp.name}, capture_output=True, text=True, timeout=3) if False else None
    # 12) a foto que o designer pede já está na biblioteca: ele diz qual e a interface oferece fixá-la
    p, _ = run({"client": "71", "conv": "convsug", "text": "preciso perguntar algo sobre a pessoa", "review": False}); msug = p["message"]
    wu = call(FAKE, "/__stats")[1]["last_writer_user"]
    ok(msug["kind"] == "text" and any(s["id"] == pid and s["kind"] == "pessoa" for s in msug["suggest"]), "pergunta traz a foto da biblioteca como sugestão")
    ok("NÃO estão anexadas" in wu and "rodrigo.webp (pessoa)" in wu, "o designer é informado do que há na biblioteca e não está anexado")
    p, _ = run({"client": "71", "conv": "convsug2", "text": "preciso perguntar algo sobre a pessoa", "asset_ids": [pid], "review": False}); msug2 = p["message"]
    ok(msug2["kind"] == "text" and not any(s["id"] == pid for s in msug2["suggest"]), "foto já anexada não é sugerida de novo")
    # 13) contexto da conversa inteiro, arquivos que ficam, apelidos, web e segurança
    # (a) o nome citado anexa sozinho; (b) a conversa lembra os arquivos; (c) transcrição completa; (d) soltar funciona
    cx = "convctx"
    p, steps = run({"client": "71", "conv": cx, "text": "gere uma imagem com o Rodrigo Faro", "review": False}); mc1 = p["message"]
    ok(any(i["kind"] == "pessoa" for i in mc1["inputs"]) and pid in mc1["files"], f"o nome citado anexa a foto sozinho ({[i['kind'] for i in mc1['inputs']]})")
    ok(any(x["text"].startswith("Anexei automaticamente pelo nome") for x in steps), "o progresso avisa o anexo automático")
    p, _ = run({"client": "71", "conv": cx, "text": "agora de oculos escuros", "review": False}); mc2 = p["message"]
    ok([i["kind"] for i in mc2["inputs"]] == ["alvo", "pessoa"], f"sem reanexar nada e sem citar o nome: a pessoa continua na conversa ({[i['kind'] for i in mc2['inputs']]})")
    wu = call(FAKE, "/__stats")[1]["last_writer_user"]
    ok("[1] Usuário: gere uma imagem com o Rodrigo Faro" in wu and "[2] Usuário: agora de oculos escuros" not in wu and "Arquivos da conversa" in wu and "rodrigo.webp (pessoa; apelido: rodrigo)" in wu,
       "o designer recebe a transcrição e os arquivos da conversa com o apelido")
    cvx = json.loads(S.read_text(f"conversations/71/{cx}.json"))
    ok(pid in cvx["files"], "os arquivos da conversa ficam gravados no servidor")
    call(CHAT, "/api/conv/files", {"client": "71", "conv": cx, "drop": [pid]})
    p, _ = run({"client": "71", "conv": cx, "text": "agora com fundo azul", "review": False}); mc3 = p["message"]
    ok(not any(i["kind"] == "pessoa" for i in mc3["inputs"]), "depois de soltar a foto, ela sai da conversa")
    # (e) apelido editável
    ok(call(CHAT, "/api/asset/alias", {"client": "71", "id": pid, "alias": "Rodrigo Faro"})[0] == 200, "apelido editável")
    p, _ = run({"client": "71", "conv": "convalias", "text": "foto do rodrigo faro sorrindo", "review": False})
    ok(any(i["kind"] == "pessoa" for i in p["message"]["inputs"]), "apelido de duas palavras casa com o texto")
    # (f) busca na web e adição à biblioteca
    st, ws = call(CHAT, "/api/websearch", {"q": "logo CVC"})
    ok(st == 200 and len(ws["results"]) == 1 and ws["results"][0]["license"] == "CC BY-SA 4.0" and ws["results"][0]["author"] == "Autor Teste", f"busca na web: candidato com licença e autor ({ws['results'][0]['title']})")
    ok("logo CVC" in call(FAKE, "/__stats")[1]["web_queries"][-1], "a consulta chega à fonte")
    r0 = ws["results"][0]
    st, wa = call(CHAT, "/api/webadd", {"client": "71", "kind": "logo", "url": r0["url"], "name": r0["title"], "page": r0["page"], "license": r0["license"], "alias": "CVC"})
    ok(st == 200 and wa["asset"]["kind"] == "logo" and wa["asset"]["origem"] == "web" and wa["asset"]["licenca"] == "CC BY-SA 4.0" and wa["asset"]["alias"] == "CVC", "imagem da web entra na biblioteca com origem, licença e apelido")
    ok(call(CHAT, "/api/webadd", {"client": "71", "kind": "logo", "url": f"http://127.0.0.1:{FAKE}/img/falso.png"})[0] == 400, "link que não é imagem é recusado (confere o conteúdo)")
    p, _ = run({"client": "71", "conv": "convweb", "text": "banner da CVC", "review": False})
    ok(any(i["kind"] == "logo" for i in p["message"]["inputs"]), "o logo adicionado pela web é anexado ao citar o nome")
    # (g) designer sugere buscar na web
    p, _ = run({"client": "71", "conv": "convsw", "text": "preciso buscarweb o logo", "review": False}); msw = p["message"]
    ok(msw["kind"] == "text" and msw["suggest_web"] and msw["suggest_web"][0]["q"] == "logo CVC" and msw["suggest_web"][0]["kind"] == "logo", "a pergunta do designer traz o botão de buscar na web")
    # (h) falha de identidade fica explícita
    p, _ = run({"client": "71", "conv": "convfail", "text": "foto do rodrigo faro trocarpessoa"}); mfl = p["message"]
    ok(mfl["falha_identidade"] is True and mfl["approved"] is False and any("NÃO manteve a identidade" in a for a in mfl["avisos"]), "identidade divergente: falha explícita, nunca aprovada")
    # (i) só o navegador local
    def raw(path, body, headers):
        rq = urllib.request.Request(f"http://127.0.0.1:{CHAT}{path}", data=json.dumps(body).encode(), method="POST")
        for k, v in headers.items(): rq.add_header(k, v)
        try:
            with urllib.request.urlopen(rq, timeout=20) as rr: return rr.status
        except urllib.error.HTTPError as e: return e.code
    ok(raw("/api/state", {}, {"Origin": "https://site-malicioso.example"}) == 403, "página de outro site (Origin) é bloqueada")
    ok(raw("/api/state", {}, {"Host": "site-malicioso.example"}) == 403, "Host estranho (DNS rebinding) é bloqueado")
    # (j) chave: formato, validação na OpenAI e nada no registro
    ok(call(CHAT, "/api/setkey", {"key": "abc"})[0] == 400, "chave com formato inválido é recusada")
    okk = "sk-" + "x" * 30
    st, kr = call(CHAT, "/api/setkey", {"key": okk, "save": False})
    ok(st == 200 and kr["ok"] and kr["saved"] is False, "chave válida é aceita (validada na OpenAI)")
    p, _ = run({"client": "71", "conv": "convkey", "text": "uma xicara", "review": False})
    ok(f"Bearer {okk}" in call(FAKE, "/__stats")[1]["auth"], "a nova chave passa a ser usada nas chamadas")
    evs2 = S.read_text("logs/events.jsonl")
    ok(okk not in evs2 and any(json.loads(x)["kind"] == "chave" for x in evs2.splitlines()), "a chave nunca vai para o registro")
    # (k) proteção contra SSRF (rede interna) com a trava ligada
    sys.path.insert(0, str(ROOT))
    os.environ.pop("WEB_ALLOW_LOCAL", None)
    cs = __import__("chat_server")
    cs.WEB_ALLOW_LOCAL = False  # (no modo em memória o módulo já estava carregado com a trava desligada)
    for bad in ("http://example.com/a.png", "https://localhost/a.png", "https://127.0.0.1/a.png", "https://169.254.169.254/latest", "file:///etc/passwd"):
        try:
            cs._check_url(bad); ok(False, f"deveria bloquear {bad}")
        except Exception as e:
            ok(type(e).__name__ == "ApiError", f"bloqueia {bad}")
    # 14) imagem antiga (sem apelido gravado) ganha apelido a partir do nome do arquivo
    arr = json.loads(S.read_text("clients/71/assets.json"))
    legacy = {"id": "legado01", "kind": "pessoa", "name": "maria_souza.png", "file": "legado01.png", "mime": "image/png"}
    S.write_bytes("clients/71/assets/legado01.png", png(8, 8))
    S.write_text("clients/71/assets.json", json.dumps(arr + [legacy]))
    al = {a["id"]: a for a in call(CHAT, "/api/client", {"id": "71"})[1]["assets"]}
    ok(al["legado01"]["alias"] == "maria souza", f"apelido derivado do nome do arquivo: {al['legado01']['alias']!r}")
    p, _ = run({"client": "71", "conv": "convlegado", "text": "retrato da Maria Souza no escritorio", "review": False})
    ok(any(i["name"] == "maria_souza.png" for i in p["message"]["inputs"]), "citar o nome anexa a imagem antiga sozinha")
    # 15) o botão de fixar só aparece quando a pergunta é sobre imagem
    p, _ = run({"client": "71", "conv": "convoferta", "text": "preciso perguntar perguntaoferta", "review": False}); mo = p["message"]
    ok(mo["kind"] == "text" and "foto" not in mo["text"].lower() and mo["suggest"] == [] and mo["suggest_web"] == [], "pergunta sobre a oferta não oferece fixar foto")
    # 16) o alvo da edição pode ser uma imagem ANEXADA (a foto de referência), não só a última gerada
    rid = call(CHAT, "/api/asset", {"client": "71", "kind": "referencia", "name": "peca_campanha.png", "mime": "image/png", "b64": PNGB})[1]["asset"]["id"]
    call(CHAT, "/api/asset/kind", {"client": "71", "id": pid, "kind": "pessoa"})
    run({"client": "71", "conv": "convtarget", "text": "banner de natal", "asset_ids": [pid, rid], "review": False})
    p, steps = run({"client": "71", "conv": "convtarget", "text": "troque a pessoa da foto de referencia pela pessoa da foto", "asset_ids": [pid, rid], "review": False}); mt = p["message"]
    ks = [(i["kind"], i["name"]) for i in mt["inputs"]]
    ok(mt["intent"] == "edit" and ks[0] == ("alvo", "peca_campanha.png"), f"o alvo é a imagem anexada, não a última gerada ({ks})")
    ok(("pessoa", "rodrigo.webp") in ks and len(ks) == 2, "a foto da pessoa continua como identidade e não é duplicada")
    ok(any(x["text"].startswith("Alvo da edição: a imagem anexada") for x in steps), "o progresso diz qual é o alvo")
    # sem citar a imagem anexada, continua editando a última gerada
    p, _ = run({"client": "71", "conv": "convtarget", "text": "agora mais claro", "asset_ids": [pid, rid], "review": False})
    ok(p["message"]["inputs"][0]["kind"] == "alvo" and p["message"]["inputs"][0]["name"] != "peca_campanha.png", "sem citar a imagem anexada, o alvo é a última gerada")
    # 17) novo cliente
    st, nc = call(CHAT, "/api/client/new", {"name": "Super Brilho", "sector": "supermercado"})
    ok(st == 200 and nc["id"] == "super-brilho" and nc["client"]["name"] == "Super Brilho", f"cliente novo criado ({nc.get('id')})")
    st2, nc2 = call(CHAT, "/api/client/new", {"name": "Super Brilho"})
    ok(nc2["id"] == "super-brilho-2", "nome repetido ganha sufixo")
    ok(call(CHAT, "/api/client/new", {"name": " "})[0] == 400, "nome vazio é recusado")
    # 18) conversa NOVA com a peça anexada: o alvo da edição já vale na primeira mensagem, e o tamanho acompanha o alvo
    p, steps = run({"client": "71", "conv": "convprimeira", "text": "troque a pessoa da foto de referencia pela pessoa da foto", "asset_ids": [pid, rid], "review": False}); m1t = p["message"]
    ok(m1t["intent"] == "edit" and m1t["inputs"][0]["kind"] == "alvo" and m1t["inputs"][0]["name"] == "peca_campanha.png", "primeira mensagem de uma conversa nova já edita a imagem anexada")
    ok(m1t["size"] == "auto", f"tamanho automático acompanha o alvo ({m1t['size']})")
    p, _ = run({"client": "71", "conv": "convsemalvo", "text": "um gato astronauta", "review": False})
    ok(p["message"]["size"] == "1024x1024", "sem alvo, o tamanho automático vira 1024x1024")
    # 19) edição localizada e extensão de fundo: o original volta idêntico fora da região (precisa de Pillow)
    try:
        from PIL import Image as PILImage
    except ImportError:
        PILImage = None
    if PILImage is None:
        print("(pulado: Pillow ausente; rode com test/.venv/bin/python para cobrir a edição localizada)")
    else:
        import io
        def real_png(w, h, rgb):
            b = io.BytesIO(); PILImage.new("RGB", (w, h), rgb).save(b, "PNG"); return b.getvalue()
        orig_id = call(CHAT, "/api/asset", {"client": "71", "kind": "referencia", "name": "peca_real.png", "mime": "image/png", "alias": "peca real",
                                            "b64": base64.b64encode(real_png(200, 250, (200, 30, 30))).decode()})[1]["asset"]["id"]
        p, steps = run({"client": "71", "conv": "convregion", "text": "troque a pessoa da foto de referencia pela pessoa da foto", "asset_ids": [pid, orig_id], "review": False}); mr = p["message"]
        s = call(FAKE, "/__stats")[1]
        ok(any(x["text"].startswith("Edição localizada") for x in steps) and s["locator_calls"] >= 1, "o localizador de regiões foi chamado e o progresso mostra as caixas")
        ok(s["edit_masks"][-1] == [200, 250] and s["edit_first_sizes"][-1] == [200, 250], f"a máscara tem o tamanho do original ({s['edit_masks'][-1]})")
        im = PILImage.open(io.BytesIO(S.read_bytes(f"chat_out/71/{mr['id']}.png"))).convert("RGB")
        ok(im.size == (200, 250) and im.getpixel((5, 5)) == (200, 30, 30) and im.getpixel((190, 240)) == (200, 30, 30), "fora da região o ORIGINAL volta idêntico (pixels)")
        ok(im.getpixel((130, 125)) == (128, 128, 128), "dentro da região vale o que o modelo gerou")
        ok(S.exists(f"chat_out/71/{mr['id']}raw.png"), "o que o modelo gerou fica guardado para análise")
        # extensão para story
        p, steps = run({"client": "71", "conv": "convextend", "text": "troque o formato da foto de referencia para story vertical", "asset_ids": [orig_id], "review": False}); me = p["message"]
        s = call(FAKE, "/__stats")[1]
        im = PILImage.open(io.BytesIO(S.read_bytes(f"chat_out/71/{me['id']}.png"))).convert("RGB")
        ok(any(x["text"].startswith("Extensão de fundo") for x in steps) and me["size"] == "1024x1536", f"extensão de fundo para 1024x1536 ({me['size']})")
        ok(s["edit_first_sizes"][-1] == [1024, 1536] and s["edit_masks"][-1] == [1024, 1536], "o modelo recebe a tela estendida e a máscara do mesmo tamanho")
        ok(im.size == (1024, 1536) and im.getpixel((500, 10)) == (128, 128, 128) and im.getpixel((500, 768)) == (200, 30, 30), "faixas novas vêm do modelo; a peça original fica idêntica no centro")
        # sem escopo local/extend (global), edita a imagem inteira como antes
        p, _ = run({"client": "71", "conv": "convglobal", "text": "agora com camisa azul", "asset_ids": [pid], "review": False})
        ok(call(FAKE, "/__stats")[1]["edit_masks"][-1] is None or p["message"]["intent"] != "edit", "edição sem região continua sem máscara")
    # 20) tarefas: em modo inline o pipeline roda dentro da requisição e o estado vive no Store; no modo local, em memória + thread
    st, j = call(CHAT, "/api/chat", {"client": "71", "conv": "convjob", "text": "um barco a vela", "review": False})
    ok(st == 200 and "job" in j, "POST /api/chat devolve o id da tarefa")
    if INLINE:
        ok(j.get("status") == "done" and j["message"]["kind"] == "image" and j.get("error") is None, "inline: /api/chat já devolve a mensagem pronta")
        ok(S.exists(f"jobs/{j['job']}.json"), "inline: estado da tarefa gravado no Store")
        sj = json.loads(S.read_text(f"jobs/{j['job']}.json"))
        _, pj = call(CHAT, "/api/job", {"id": j["job"], "since": 0})
        ok(pj["status"] == "done" and pj["message"] == j["message"] and pj["next"] == len(sj["steps"]) and pj["steps"], "inline: /api/job responde pelo Store com os mesmos passos")
        _, pj2 = call(CHAT, "/api/job", {"id": j["job"], "since": pj["next"]})
        ok(pj2["steps"] == [] and pj2["next"] == pj["next"], "inline: 'since' continua valendo")
        ok(call(CHAT, "/api/job", {"id": "../../clients/71/client"})[0] == 404 and call(CHAT, "/api/job", {"id": "0123456789"})[0] == 404, "inline: id de tarefa inválido ou desconhecido é 404")
        if STORE_MODE == "memory":
            ok(cs.JOBS == {}, "inline: nenhum job ficou no dicionário em memória nem em thread")
        if STORE_MODE == "memory":  # falha dentro do pipeline: vira estado 'error' persistido, sem derrubar a requisição
            def boom(emit):
                emit("antes da falha"); raise cs.ui.ApiError(502, "falha simulada")
            jid = cs.start_job(boom, {"teste": True})
            pe = cs.api_job({"id": jid})
            ok(pe["status"] == "error" and "falha simulada" in pe["error"] and [x["text"] for x in pe["steps"]] == ["antes da falha"], "inline: erro do pipeline fica gravado no estado da tarefa")
    else:
        ok("status" not in j, "local: /api/chat só devolve o id; o resultado vem por polling")
        ok(not S.exists(f"jobs/{j['job']}.json"), "local: nenhum estado de tarefa gravado no Store")
        for _ in range(100):
            time.sleep(0.4); _, pj = call(CHAT, "/api/job", {"id": j["job"]})
            if pj["status"] != "running": break
        ok(pj["status"] == "done", "local: a tarefa em thread termina e /api/job responde")
    # 20) com STORE=memory nada foi gravado em disco
    if STORE_MODE == "memory":
        ok(not any(pathlib.Path(tmp.name).rglob("*.*")), "STORE=memory: a pasta de dados em disco continua vazia")
    print("\nTUDO OK")
finally:
    for p in procs:
        p.terminate()
    tmp.cleanup()
