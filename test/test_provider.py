#!/usr/bin/env python3
"""Testes do adapter provider.py. Sem rede e sem custo: transporte injetado + a OpenAI falsa local (HTTP real em 127.0.0.1).

  cd test && python3 -I test_provider.py

Cada caso afirma comportamento observável (o que foi enviado, quantas vezes, quanto esperou, que erro saiu),
não que um mock foi chamado.
"""
import base64, calendar, json, os, pathlib, struct, sys, threading, time, zlib
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import provider as pv  # noqa: E402
import fake_openai  # noqa: E402

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
    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00")) + chunk(b"IEND", b"")


def good(w=1024, h=1024):
    return 200, {"x-request-id": "req_ok"}, json.dumps({"data": [{"b64_json": base64.b64encode(png(w, h)).decode()}], "usage": {"total_tokens": 7}}).encode()


def err(status, message="x", code="", headers=None):
    return status, headers or {}, json.dumps({"error": {"message": message, "code": code}}).encode()


class Script:
    """Transporte que devolve respostas em sequência e registra o que recebeu."""

    def __init__(self, *responses):
        self.responses, self.calls, self.lock = list(responses), [], threading.Lock()

    def __call__(self, method, url, headers, body, timeout):
        with self.lock:
            self.calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout, "method": method})
            r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def make(*responses, **kw):
    t = Script(*responses)
    sleeps = []
    kw.setdefault("sleep", sleeps.append)
    kw.setdefault("rng", type("R", (), {"random": lambda self: 1.0})())  # jitter máximo => atraso = base*2^(n-1)
    return pv.OpenAIImages("http://x/v1", kw.pop("key", "k-test"), transport=t, **kw), t, sleeps


def raises(fn, kind):
    try:
        fn()
    except pv.ProviderError as e:
        return e if e.kind == kind else None
    return None


def test_validation():
    p, t, _ = make(good())
    for size in ("1024x1024", "1536x1024", "2048x1152", "auto"):
        p.validate_request("generate", MODEL, size, "high")
    ok(True, "tamanhos documentados passam (1024x1024, 1536x1024, 2048x1152, auto)")
    for size, frag in (("1000x1000", "múltiplos de 16"), ("4096x1024", "3840"), ("3840x1024", "proporção"), ("512x512", "pixels"), ("abc", "inválido")):
        e = raises(lambda: p.validate_request("generate", MODEL, size), "validation")
        ok(e is not None and frag in str(e), f"{size} rejeitado antes da chamada ({frag})")
    ok(raises(lambda: p.validate_request("generate", MODEL, "1024x1024", "ultra"), "validation") is not None, "quality fora da lista é rejeitada")
    for q in ("low", "medium", "high", "xhigh", "max", "auto"):
        p.validate_request("generate", MODEL, "1024x1024", q)
    ok(True, "quality xhigh e max aceitas (documentação atual)")
    w = p.validate_request("generate", "modelo-novo-x", "1000x1000", "qualquer")
    ok(any("fora de provider_capabilities" in x and "modelo-novo-x" in x for x in w), "modelo fora da tabela: sem regra global de 16, só aviso de que não foi verificado")
    ok(raises(lambda: p.validate_request("generate", "m", "10x"), "validation") is not None, "modelo fora da tabela ainda valida o formato do size")
    e = raises(lambda: p.validate_request("edit", MODEL, "1024x1024", inputs=[]), "validation")
    ok(e is not None and "fallback" in str(e), "edit sem imagem falha (nada de fallback silencioso para geração)")
    e = raises(lambda: p.validate_request("generate", MODEL, "1024x1024", inputs=[{"bytes": png(), "mime": "image/png"}]), "validation")
    ok(e is not None, "generate com imagem de entrada falha (referências não são descartadas em silêncio)")
    img = {"bytes": png(), "mime": "image/png"}
    mask_ok = png(color_type=6)
    p.validate_request("edit", MODEL, "1024x1024", inputs=[img], mask=mask_ok)
    ok(True, "máscara PNG RGBA do mesmo tamanho passa")
    ok("alfa" in str(raises(lambda: p.validate_request("edit", MODEL, "1024x1024", inputs=[img], mask=png(color_type=2)), "validation")), "máscara sem canal alfa rejeitada")
    ok("diferente" in str(raises(lambda: p.validate_request("edit", MODEL, "1024x1024", inputs=[img], mask=png(512, 512, 6)), "validation")), "máscara de outro tamanho rejeitada")
    jpg = {"bytes": b"\xff\xd8\xff" + b"\x00" * 50, "mime": "image/jpeg"}
    ok("mesmo formato" in str(raises(lambda: p.validate_request("edit", MODEL, "1024x1024", inputs=[jpg], mask=mask_ok), "validation")), "máscara PNG sobre imagem JPEG rejeitada (doc: mesmo formato)")
    ok("assinatura" in str(raises(lambda: p.validate_request("edit", MODEL, "1024x1024", inputs=[{"bytes": b"nao sou png", "mime": "image/png"}]), "validation")), "entrada cujo conteúdo não é o tipo declarado rejeitada")
    ok("não suportado" in str(raises(lambda: p.validate_request("edit", MODEL, "1024x1024", inputs=[{"bytes": b"<svg/>", "mime": "image/svg+xml"}]), "validation")), "SVG como entrada de edição rejeitado")
    big = {"bytes": png() + b"\x00" * (50 * 1024 * 1024), "mime": "image/png"}
    ok("limite" in str(raises(lambda: p.validate_request("edit", MODEL, "1024x1024", inputs=[big]), "validation")), "entrada acima de 50 MB rejeitada")
    e = raises(lambda: p.validate_request("generate", MODEL, "1000x1000", "ultra", n=3), "validation")
    ok(e is not None and str(e).count(";") >= 2, "todos os problemas saem juntos, não só o primeiro")
    ok(t.calls == [], "nenhuma validação chegou ao transporte")
    cap = p.get_capabilities(MODEL)
    ok(cap["verified"] and cap["source"].startswith("https://") and cap["verified_on"], "get_capabilities traz fonte e data de verificação")
    ok(p.get_capabilities("x")["verified"] is False, "get_capabilities marca modelo desconhecido como não verificado")


def test_invalid_never_sent():
    p, t, _ = make(good())
    raises(lambda: p.generate("a", MODEL, "1000x1000"), "validation")
    raises(lambda: p.edit("a", MODEL, "1024x1024", inputs=[]), "validation")
    ok(t.calls == [], "requisição inválida: zero chamadas pagas")


def test_success_and_response_checks():
    p, t, _ = make(good())
    r = p.generate("um gato", MODEL, "1024x1024", "medium")
    c = t.calls[0]
    ok(c["url"] == "http://x/v1/images/generations" and json.loads(c["body"]) == {"model": MODEL, "prompt": "um gato", "size": "1024x1024", "n": 1, "quality": "medium"},
       "generate envia o corpo JSON esperado para /images/generations")
    ok(c["headers"]["Authorization"] == "Bearer k-test" and len(c["headers"]["X-Client-Request-Id"]) == 32, "envia chave e id de requisição do cliente")
    ok(r["mime"] == "image/png" and r["dims"] == (1024, 1024) and r["request_id"] == "req_ok" and r["usage"] == {"total_tokens": 7} and r["attempts"] == 1,
       "resultado traz mime, dimensões, request_id, usage e tentativas")
    ok(r["warnings"] == [], "tamanho igual ao pedido: sem aviso")
    r = make(good(512, 512))[0].generate("x", MODEL, "1024x1024")
    ok(any("512x512" in w for w in r["warnings"]), "tamanho devolvido diferente vira aviso (o critic decide)")
    r = make(good(512, 512))[0].generate("x", MODEL, "auto")
    ok(r["warnings"] == [], "size=auto não gera aviso de tamanho")
    for resp, frag in (((200, {}, b"nao json"), "JSON"), ((200, {}, b'{"data": []}'), "vazia"), ((200, {}, b'{"data": [{"url": "http://x"}]}'), "b64_json"),
                       ((200, {}, b'{"data": [{"b64_json": "@@@@"}]}'), "decodificar"),
                       ((200, {}, json.dumps({"data": [{"b64_json": base64.b64encode(b"texto").decode()}]}).encode()), "PNG, JPEG nem WebP")):
        e = raises(lambda: make(resp)[0].generate("x", MODEL, "1024x1024"), "bad_response")
        ok(e is not None and frag in str(e), f"resposta inválida tratada: {frag}")


def test_edit_request():
    p, t, _ = make(good())
    img, mask = {"bytes": png(), "mime": "image/png"}, png(color_type=6)
    p.edit("troque a cor", MODEL, "1024x1024", "high", inputs=[img, {"bytes": png(64, 64), "mime": "image/png"}], mask=mask, fidelity="high")
    c = t.calls[0]
    body = c["body"]
    ok(c["url"].endswith("/images/edits") and c["headers"]["Content-Type"].startswith("multipart/form-data; boundary="), "edit usa /images/edits em multipart")
    ok(body.count(b'name="image[]"') == 2 and body.count(b'name="mask"') == 1 and b'name="input_fidelity"\r\n\r\nhigh' in body, "edit envia as 2 imagens, a máscara e input_fidelity")
    p2, t2, _ = make(good())
    p2.edit("x", MODEL, "1024x1024", inputs=[img])
    ok(b"input_fidelity" not in t2.calls[0]["body"] and b'name="mask"' not in t2.calls[0]["body"], "sem fidelity e sem máscara, os campos não vão")


def test_retry():
    p, t, sleeps = make(err(429, "slow down", "rate_limit_exceeded", {"retry-after": "2"}), good())
    r = p.generate("x", MODEL, "1024x1024")
    ok(len(t.calls) == 2 and sleeps == [2.0] and r["attempts"] == 2, "429: espera o Retry-After (2s) e repete uma vez")
    ok(t.calls[0]["headers"]["X-Client-Request-Id"] == t.calls[1]["headers"]["X-Client-Request-Id"], "as repetições levam o mesmo id de requisição do cliente")
    p, t, sleeps = make(err(500), err(502), good())
    r = p.generate("x", MODEL, "1024x1024")
    ok(len(t.calls) == 3 and sleeps == [1.0, 2.0], "500 e 502: backoff exponencial limitado (1s, 2s)")
    p, t, sleeps = make(err(503))
    e = raises(lambda: p.generate("x", MODEL, "1024x1024"), "transient")
    ok(e is not None and len(t.calls) == 3 and e.attempts == 3, "erro persistente: para em 1 + 2 repetições e informa tentativas")
    p, t, sleeps = make(err(429, "x", "rate_limit_exceeded", {"retry-after": "120"}))
    e = raises(lambda: p.generate("x", MODEL, "1024x1024"), "rate_limit")
    ok(e is not None and len(t.calls) == 1 and sleeps == [] and e.retry_after == 120, "Retry-After acima do limite de espera: não dorme, levanta com retry_after")
    p, t, sleeps = make(err(429, "You exceeded your quota", "insufficient_quota"))
    ok(raises(lambda: p.generate("x", MODEL, "1024x1024"), "quota") is not None and len(t.calls) == 1, "429 por cota esgotada não repete")
    for status, kind in ((400, "bad_request"), (401, "auth"), (403, "forbidden"), (404, "model")):
        p, t, _ = make(err(status, "x"))
        ok(raises(lambda: p.generate("x", MODEL, "1024x1024"), kind) is not None and len(t.calls) == 1, f"HTTP {status} não repete ({kind})")
    p, t, _ = make(pv.TransportError("timeout", "t"))
    ok(raises(lambda: p.generate("x", MODEL, "1024x1024"), "timeout") is not None and len(t.calls) == 1, "timeout de leitura NÃO repete (pode ter sido cobrado)")
    p, t, sleeps = make(pv.TransportError("connect", "recusou"), good())
    p.generate("x", MODEL, "1024x1024")
    ok(len(t.calls) == 2, "falha de conexão antes do envio repete")
    p, t, _ = make(pv.TransportError("network", "reset"))
    ok(raises(lambda: p.generate("x", MODEL, "1024x1024"), "network") is not None and len(t.calls) == 1, "queda no meio da resposta não repete")
    e = make(err(400, "blocked", "moderation_blocked"))[0]
    x = raises(lambda: e.generate("x", MODEL, "1024x1024"), "refused")
    ok(x is not None and x.retryable is False, "recusa por moderação vira 'refused', sem repetir")
    e = make(err(400, "Unknown parameter: 'input_fidelity'."))[0]
    x = raises(lambda: e.generate("x", MODEL, "1024x1024"), "unsupported_param")
    ok(x is not None and x.param == "input_fidelity", "parâmetro recusado é identificado (para o chamador recuar com aviso)")
    ok(pv.parse_retry_after("3") == 3.0 and pv.parse_retry_after(None) is None and pv.parse_retry_after("lixo") is None, "parse_retry_after: número, ausente e inválido")
    ok(abs(pv.parse_retry_after("Wed, 21 Oct 2026 07:28:10 GMT", now=calendar.timegm((2026, 10, 21, 7, 28, 5)) ) - 5) < 1, "parse_retry_after: data HTTP")


def test_budget():
    s = pv.Budget("sessão", 3)
    p, t, _ = make(good(), budgets=[s])
    for _ in range(3):
        p.generate("x", MODEL, "1024x1024")
    e = raises(lambda: p.generate("x", MODEL, "1024x1024"), "budget")
    ok(e is not None and len(t.calls) == 3 and "esgotado" in str(e), "orçamento da sessão: a 4ª chamada é barrada antes de enviar")
    s = pv.Budget("sessão", 10)
    task = pv.Budget("tarefa", 2)
    p, t, _ = make(err(500), good(), budgets=[s])
    p.generate("x", MODEL, "1024x1024", extra_budgets=[task])
    ok(s.calls == 2 and task.calls == 2, "cada tentativa HTTP, inclusive a repetição, consome orçamento")
    p, t, _ = make(err(500), budgets=[s])
    e = raises(lambda: p.generate("y", MODEL, "1024x1024", extra_budgets=[pv.Budget("tarefa", 2)]), "budget")
    ok(e is not None and len(t.calls) == 2, "o retry também respeita o orçamento da tarefa (2 chamadas, não 3)")


def test_cancel_key_trace_concurrency():
    ev = threading.Event()
    ev.set()
    p, t, _ = make(good())
    ok(raises(lambda: p.generate("x", MODEL, "1024x1024", cancel=ev), "cancelled") is not None and t.calls == [], "cancelado antes de enviar: zero chamadas")
    ev = threading.Event()
    p, t, _ = make(err(429, "x", "rate_limit_exceeded", {"retry-after": "5"}), good(), sleep=lambda s: ev.set())
    ok(raises(lambda: p.generate("x", MODEL, "1024x1024", cancel=ev), "cancelled") is not None and len(t.calls) == 1, "cancelado durante a espera do backoff: não repete")
    ok(raises(lambda: make(good(), key=None)[0].generate("x", MODEL, "1024x1024"), "auth") is not None, "sem chave: erro claro antes de qualquer transporte")
    holder = {"k": None}
    p = pv.OpenAIImages("http://x/v1", lambda: holder["k"], transport=Script(good()))
    holder["k"] = "chave-colada-depois"
    p.generate("x", MODEL, "1024x1024")
    ok(p._transport.calls[0]["headers"]["Authorization"] == "Bearer chave-colada-depois", "a chave é lida a cada chamada (pode ser colada depois de subir)")
    events = []
    p, t, _ = make(err(500), good(), on_event=events.append)
    p.generate("PROMPT-SECRETO-123", MODEL, "1024x1024")
    dump = json.dumps(events)
    ok(len(events) == 2 and events[0]["status"] == 500 and events[1]["status"] == 200, "trace tem um evento por tentativa")
    ok("PROMPT-SECRETO-123" not in dump and "k-test" not in dump and "b64" not in dump and events[0]["prompt_chars"] == 18, "trace não contém prompt, chave nem imagem")
    p, _, _ = make(good(), on_event=lambda e: 1 / 0)
    ok(p.generate("x", MODEL, "1024x1024")["attempts"] == 1, "falha no observador de eventos não derruba a geração")

    live, peak, lock = {"n": 0}, {"n": 0}, threading.Lock()

    def slow(method, url, headers, body, timeout):
        with lock:
            live["n"] += 1; peak["n"] = max(peak["n"], live["n"])
        time.sleep(0.05)
        with lock:
            live["n"] -= 1
        return good()
    p = pv.OpenAIImages("http://x/v1", "k", transport=slow, max_concurrency=2)
    ths = [threading.Thread(target=p.generate, args=("x", MODEL, "1024x1024")) for _ in range(6)]
    [x.start() for x in ths]; [x.join() for x in ths]
    ok(peak["n"] == 2, f"limite de concorrência respeitado (pico {peak['n']} de 2)")


def test_http_against_fake():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), fake_openai.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    sleeps = []
    p = pv.OpenAIImages(base, "fake", sleep=sleeps.append, timeout=10)
    try:
        r = p.generate("uma paisagem", MODEL, "1024x1536")
        ok(r["dims"] == (1024, 1536) and r["mime"] == "image/png", "HTTP real: generate devolve PNG 1024x1536")
        r = p.generate("flaky429 uma paisagem", MODEL, "1024x1024")
        ok(r["attempts"] == 2 and sleeps == [0.0], "HTTP real: 429 com Retry-After: 0 é repetido e funciona")
        e = raises(lambda: p.generate("always500 x", MODEL, "1024x1024"), "transient")
        ok(e is not None and e.attempts == 3 and "OpenAI 500" in str(e), "HTTP real: 500 persistente para em 3 tentativas")
        e = raises(lambda: p.generate("moderated x", MODEL, "1024x1024"), "refused")
        ok(e is not None and e.status == 400, "HTTP real: moderation_blocked vira 'refused'")
        r = p.edit("editar", MODEL, "1024x1024", inputs=[{"bytes": png(), "mime": "image/png"}], mask=png(color_type=6), fidelity="high")
        ok(r["op"] == "edit" and fake_openai.STATS["edits"] == 1 and fake_openai.STATS["edit_images"] == [1] and fake_openai.STATS["edit_masks"][0] == (1024, 1024),
           "HTTP real: edit chega como multipart com 1 imagem e máscara 1024x1024")
        dead = pv.OpenAIImages("http://127.0.0.1:9/v1", "fake", sleep=sleeps.append, timeout=2, max_retries=1)
        e = raises(lambda: dead.generate("x", MODEL, "1024x1024"), "network")
        ok(e is not None and e.attempts == 2, "HTTP real: porta fechada é falha de conexão, repetida uma vez e depois reportada")
    finally:
        srv.shutdown()


def test_make_image_wiring():
    """make_image (chat_server) passa pelo adapter: orçamento da tarefa, erro como ApiError e alvo JPEG convertido p/ PNG com máscara."""
    import chat_server as cs
    import ui_server as ui
    t = Script(err(500), good())
    cs._IMAGES = pv.OpenAIImages("http://x/v1", "k", transport=t, sleep=lambda s: None)
    task = pv.Budget("tarefa", 1)
    try:
        cs.make_image("x", "1024x1024", "medium", [], MODEL, budget=task)
        ok(False, "a repetição deveria estourar o orçamento da tarefa")
    except ui.ApiError as e:
        ok(e.status == 429 and "esgotado" in str(e) and len(t.calls) == 1, "make_image: orçamento da tarefa esgotado vira ApiError 429 sem 2ª chamada")
    t = Script(good())
    cs._IMAGES = pv.OpenAIImages("http://x/v1", "k", transport=t, sleep=lambda s: None)
    try:
        cs.make_image("x", "1000x1000", "medium", [], MODEL)
        ok(False, "size inválido deveria falhar")
    except ui.ApiError as e:
        ok(e.status == 400 and t.calls == [], "make_image: requisição inválida vira ApiError 400 e nada é enviado")
    try:
        from PIL import Image
        import io
    except ImportError:
        print("pulado: Pillow ausente (conversão JPEG->PNG para máscara)")
        return
    buf = io.BytesIO(); Image.new("RGB", (1024, 1024), (200, 30, 30)).save(buf, "JPEG")
    t = Script(good())
    cs._IMAGES = pv.OpenAIImages("http://x/v1", "k", transport=t, sleep=lambda s: None)
    cs.make_image("troque", "1024x1024", "medium", [{"bytes": buf.getvalue(), "mime": "image/jpeg", "kind": "alvo", "name": "a.jpg"}], MODEL, mask=png(color_type=6))
    body = t.calls[0]["body"]
    ok(b'filename="in0.png"' in body and b"image/jpeg" not in body, "make_image: alvo JPEG com máscara chega como PNG (a API exige o mesmo formato)")
    cs._IMAGES = None


def chat_ok(content="{\"a\": 1}", usage=None):
    doc = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        doc["usage"] = usage
    return 200, {"x-request-id": "req_t"}, json.dumps(doc).encode()


def make_text(*responses, **kw):
    t = Script(*responses)
    sleeps = []
    kw.setdefault("sleep", sleeps.append)
    kw.setdefault("rng", type("R", (), {"random": lambda self: 1.0})())
    return pv.OpenAIText("http://x/v1", kw.pop("key", "k-test"), transport=t, **kw), t, sleeps


CHAT = {"model": "gpt-5.5", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}


def test_text_adapter():
    p, t, _ = make_text(chat_ok(usage={"prompt_tokens": 11, "completion_tokens": 5, "details": {"x": 1}}))
    r = p.post_json("/chat/completions", CHAT)
    ok(t.calls[0]["url"] == "http://x/v1/chat/completions" and json.loads(t.calls[0]["body"]) == CHAT and r["choices"][0]["message"]["content"] == "{\"a\": 1}",
       "post_json envia o payload intacto e devolve o JSON da resposta (contrato que os chamadores já usavam)")
    ok(t.calls[0]["timeout"] == 300, "timeout padrão do cliente")
    p.post_json("/chat/completions", CHAT, timeout=7)
    ok(t.calls[1]["timeout"] == 7, "timeout por chamada (a pesquisa usa o seu)")
    for path, payload, frag in (("/images/generations", CHAT, "não suportado"), ("/chat/completions", {"model": "", "messages": CHAT["messages"]}, "modelo ausente"),
                                ("/chat/completions", {"model": "m"}, "messages ausente"), ("/chat/completions", {"model": "m", "messages": [{"role": "robo", "content": "x"}]}, "role"),
                                ("/chat/completions", {"model": "m", "messages": ["x"]}, "role"), ("/chat/completions", [1], "objeto"),
                                ("/responses", {"model": "m"}, "input ausente"), ("/chat/completions", {"model": "m", "messages": [{"role": "user", "content": {1, 2}}]}, "serializável")):
        p2, t2, _ = make_text(chat_ok())
        e = raises(lambda: p2.post_json(path, payload), "validation")
        ok(e is not None and frag in str(e) and t2.calls == [], f"texto inválido barrado antes de enviar ({frag})")
    p, t, sleeps = make_text(err(429, "slow", "rate_limit_exceeded", {"retry-after": "3"}), chat_ok())
    p.post_json("/chat/completions", CHAT)
    ok(len(t.calls) == 2 and sleeps == [3.0], "texto: 429 espera o Retry-After e repete")
    p, t, sleeps = make_text(err(502), err(503), chat_ok())
    p.post_json("/chat/completions", CHAT)
    ok(len(t.calls) == 3 and sleeps == [1.0, 2.0], "texto: 502 e 503 com backoff exponencial")
    p, t, _ = make_text(err(500))
    e = raises(lambda: p.post_json("/chat/completions", CHAT), "transient")
    ok(e is not None and len(t.calls) == 3 and "OpenAI 500" in str(e), "texto: erro persistente para em 3 tentativas com a mensagem de sempre")
    p, t, _ = make_text(pv.TransportError("timeout", "t"))
    ok(raises(lambda: p.post_json("/chat/completions", CHAT), "timeout") is not None and len(t.calls) == 1, "texto: timeout de leitura não repete")
    for status, kind in ((400, "bad_request"), (401, "auth"), (404, "model")):
        p, t, _ = make_text(err(status, "x"))
        ok(raises(lambda: p.post_json("/chat/completions", CHAT), kind) is not None and len(t.calls) == 1, f"texto: HTTP {status} não repete")
    for resp, kind, frag in (((200, {}, b"lixo"), "bad_response", "JSON"), ((200, {}, b"[1]"), "bad_response", "objeto"), ((200, {}, b'{"choices": []}'), "bad_response", "choices"),
                             ((200, {}, json.dumps({"choices": [{"message": {"content": ""}}]}).encode()), "bad_response", "vazia"),
                             ((200, {}, json.dumps({"choices": [{"message": {"content": None, "refusal": "não posso"}}]}).encode()), "refused", "recusou")):
        e = raises(lambda: make_text(resp)[0].post_json("/chat/completions", CHAT), kind)
        ok(e is not None and frag in str(e), f"resposta de texto inválida tratada ({frag})")
    ok(make_text((200, {}, json.dumps({"choices": [{"message": {"content": None, "tool_calls": [{"id": "1"}]}}]}).encode()))[0].post_json("/chat/completions", CHAT), "chamada de ferramenta sem content é resposta válida")
    ok(raises(lambda: make_text((200, {}, b'{"error": {"message": "x"}}'))[0].post_json("/responses", {"model": "m", "input": "x"}), "bad_response") is not None, "/responses com campo error é recusado")
    make_text((200, {}, b'{"output_text": "ok", "error": null}'))[0].post_json("/responses", {"model": "m", "input": "x"})
    ok(True, "/responses sem erro passa")
    ok(raises(lambda: make_text(chat_ok(), key=None)[0].post_json("/chat/completions", CHAT), "auth") is not None, "texto sem chave: erro claro antes do transporte")

    print("-- orçamento de texto")
    sess = pv.Budget("texto da sessão", 2)
    p, t, _ = make_text(chat_ok(), budgets=[sess])
    p.post_json("/chat/completions", CHAT); p.post_json("/chat/completions", CHAT)
    e = raises(lambda: p.post_json("/chat/completions", CHAT), "budget")
    ok(e is not None and len(t.calls) == 2 and "texto da sessão" in str(e), "orçamento de texto da sessão barra a 3ª chamada antes de enviar")
    task = pv.Budget("texto da tarefa", 2)
    p, t, _ = make_text(chat_ok())
    with pv.task_scope(text=task):
        p.post_json("/chat/completions", CHAT); p.post_json("/chat/completions", CHAT)
        e = raises(lambda: p.post_json("/chat/completions", CHAT), "budget")
    ok(e is not None and len(t.calls) == 2 and task.calls == 2, "dentro de task_scope o orçamento da tarefa vale sem ser passado a cada chamada")
    p.post_json("/chat/completions", CHAT)
    ok(len(t.calls) == 3 and task.calls == 2, "fora do task_scope o orçamento da tarefa não se aplica")
    task = pv.Budget("texto da tarefa", 5)
    p, t, _ = make_text(err(500), chat_ok())
    with pv.task_scope(text=task):
        p.post_json("/chat/completions", CHAT)
    ok(task.calls == 2, "a repetição também consome o orçamento de texto da tarefa")
    img = pv.Budget("imagem da tarefa", 1)
    p, t, _ = make_text(chat_ok())
    with pv.task_scope(image=img):
        p.post_json("/chat/completions", CHAT)
    ok(img.calls == 0, "orçamento de imagem não é consumido por chamada de texto")
    a, b = pv.Budget("a", 1), pv.Budget("b", 1)
    seen = {}

    def worker(name, budget):
        with pv.task_scope(text=budget):
            p2, _, _ = make_text(chat_ok())
            p2.post_json("/chat/completions", CHAT)
            seen[name] = pv.current_task_budgets("text")[0].name
    th = [threading.Thread(target=worker, args=("a", a)), threading.Thread(target=worker, args=("b", b))]
    [x.start() for x in th]; [x.join() for x in th]
    ok(seen == {"a": "a", "b": "b"} and a.calls == 1 and b.calls == 1 and pv.current_task_budgets("text") == [], "task_scope é por thread: duas tarefas não dividem orçamento e nada vaza")
    with pv.task_scope(text=pv.Budget("externo", 9)):
        with pv.task_scope(text=pv.Budget("interno", 9)):
            inner = pv.current_task_budgets("text")[0].name
        outer = pv.current_task_budgets("text")[0].name
    ok((inner, outer) == ("interno", "externo"), "task_scope aninhado restaura o anterior ao sair")

    print("-- trace de texto")
    events = []
    p, t, _ = make_text(chat_ok(usage={"prompt_tokens": 11, "completion_tokens": 5, "details": {"x": 1}}), on_event=events.append)
    p.post_json("/chat/completions", {"model": "gpt-5.5", "messages": [{"role": "user", "content": "PROMPT-SECRETO-XYZ"}]})
    dump = json.dumps(events)
    ok(len(events) == 1 and events[0]["op"] == "text" and events[0]["usage"] == {"prompt_tokens": 11, "completion_tokens": 5} and events[0]["request_id"] == "req_t",
       "trace de texto: operação, request_id e consumo (só campos numéricos)")
    ok("PROMPT-SECRETO-XYZ" not in dump and "k-test" not in dump, "trace de texto não contém prompt nem chave")
    events = []
    p, _, _ = make_text(chat_ok(""), on_event=events.append)
    raises(lambda: p.post_json("/chat/completions", CHAT), "bad_response")
    ok(events[0]["error"] == "bad_response" and events[0]["status"] == 200, "resposta inválida deixa rastro no trace com o tipo do erro")

    print("-- ui.openai_post")
    import ui_server as ui
    ui._TEXT = pv.OpenAIText("http://x/v1", "k", transport=Script(err(429, "x", "insufficient_quota")))
    try:
        ui.openai_post("/chat/completions", CHAT)
        ok(False, "deveria levantar ApiError")
    except ui.ApiError as e:
        ok(e.status == 502 and "OpenAI 429" in str(e), "ui.openai_post: erro do provedor vira ApiError 502 com a mensagem de sempre")
    ui._TEXT = pv.OpenAIText("http://x/v1", "k", transport=Script(chat_ok()))
    try:
        ui.openai_post("/chat/completions", {"model": "m", "messages": []})
        ok(False, "deveria levantar ApiError")
    except ui.ApiError as e:
        ok(e.status == 400, "ui.openai_post: requisição inválida vira ApiError 400")
    ui._TEXT = pv.OpenAIText("http://x/v1", "k", transport=Script(chat_ok()), budgets=[pv.Budget("x", 0)])
    try:
        ui.openai_post("/chat/completions", CHAT)
        ok(False, "deveria levantar ApiError")
    except ui.ApiError as e:
        ok(e.status == 429, "ui.openai_post: orçamento esgotado vira ApiError 429")
    ui._TEXT = None


def test_get_models():
    models = (200, {}, json.dumps({"data": [{"id": "gpt-5.5"}, {"id": "gpt-image-2.5-sunburst"}]}).encode())
    sess, task = pv.Budget("texto da sessão", 1), pv.Budget("texto da tarefa", 1)
    p, t, _ = make_text(models, budgets=[sess])
    with pv.task_scope(text=task):
        for _ in range(3):
            r = p.get_json("/models")
    c = t.calls[0]
    ok(c["method"] == "GET" and c["url"] == "http://x/v1/models" and c["body"] is None and "Content-Type" not in c["headers"] and c["headers"]["Authorization"] == "Bearer k-test",
       "get_json: GET sem corpo e sem Content-Type, com a chave")
    ok(len(r["data"]) == 2 and sess.calls == 0 and task.calls == 0 and len(t.calls) == 3, "consulta gratuita não gasta orçamento de sessão nem de tarefa (3 consultas, 0 reservas)")
    p, t, sleeps = make_text(err(429, "slow", "rate_limit_exceeded", {"retry-after": "2"}), err(503), models)
    p.get_json("/models")
    ok(len(t.calls) == 3 and sleeps == [2.0, 2.0], "get_json: 429 respeita o Retry-After e 503 faz backoff; a 3ª tentativa funciona")
    p, t, _ = make_text(err(401, "bad key"))
    e = raises(lambda: p.get_json("/models"), "auth")
    ok(e is not None and len(t.calls) == 1 and "OpenAI 401" in str(e), "get_json: 401 não repete e mantém a mensagem")
    p, t, _ = make_text(pv.TransportError("timeout", "t"))
    ok(raises(lambda: p.get_json("/models"), "timeout") is not None and len(t.calls) == 1, "get_json: timeout de leitura não repete (política única)")
    for bad in ("/chat/completions", "/models/../x", "/models/..", "/models/a/b", "models", "", "/models?x=1", "/files"):
        p2, t2, _ = make_text(models)
        ok(raises(lambda: p2.get_json(bad), "validation") is not None and t2.calls == [], f"get_json recusa caminho fora de /models antes de enviar ({bad!r})")
    p2, t2, _ = make_text(models)
    p2.get_json("/models/gpt-5.5")
    ok(t2.calls[0]["url"].endswith("/models/gpt-5.5"), "get_json aceita /models/<id> simples")
    ok(raises(lambda: make_text(models, key=None)[0].get_json("/models"), "auth") is not None, "get_json sem chave: erro antes do transporte")
    events = []
    p, t, _ = make_text(models, on_event=events.append)
    p.get_json("/models")
    ok(events and events[0]["op"] == "get" and events[0]["status"] == 200 and "gpt-5.5" not in json.dumps(events), "trace de get_json: operação get, sem o corpo")
    import chat_server as cs
    import ui_server as ui
    old = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = "k-test"
    try:
        ui._TEXT = pv.OpenAIText("http://x/v1", "k-test", transport=Script(models), sleep=lambda s: None)
        ok([m["id"] for m in cs.openai_get("/models")["data"]] == ["gpt-5.5", "gpt-image-2.5-sunburst"], "chat_server.openai_get usa o adapter e devolve o JSON de sempre")
        ui._TEXT = pv.OpenAIText("http://x/v1", "k-test", transport=Script(err(500)), sleep=lambda s: None)
        try:
            cs.openai_get("/models")
            ok(False, "deveria levantar ApiError")
        except ui.ApiError as e:
            ok(e.status == 502 and "OpenAI 500" in str(e), "openai_get: 500 persistente vira ApiError 502 depois das repetições")
        am = cs.api_models({})
        ok(am["ok"] is False and any("OpenAI 500" in n for n in am["notes"]), "api_models devolve o diagnóstico em vez de derrubar a tela")
        os.environ.pop("OPENAI_API_KEY")
        try:
            cs.openai_get("/models")
            ok(False, "deveria levantar ApiError")
        except ui.ApiError as e:
            ok(e.status == 400 and "Sem OPENAI_API_KEY" in str(e), "openai_get sem chave: a mesma mensagem de antes")
    finally:
        ui._TEXT = None
        if old is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = old


def main():
    for fn in (test_validation, test_invalid_never_sent, test_success_and_response_checks, test_edit_request, test_retry, test_budget,
               test_cancel_key_trace_concurrency, test_http_against_fake, test_make_image_wiring, test_text_adapter, test_get_models):
        print(f"== {fn.__name__}")
        fn()
    print(f"\nTUDO OK ({N['ok']} verificações)")


if __name__ == "__main__":
    main()
