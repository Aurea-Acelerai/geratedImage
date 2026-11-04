#!/usr/bin/env python3
"""Adapters da OpenAI: OpenAIImages (generate, edit, validate_request, get_capabilities) e OpenAIText (post_json para chat
completions e responses), sobre a mesma base OpenAIClient (retry, orçamento, concorrência, trace). Só stdlib.

O que faz (e o que não faz):
- Valida a requisição ANTES de qualquer chamada paga, contra provider_capabilities.json (dados por modelo, com
  fonte e data). Modelo fora da tabela: só checagem de formato, com aviso "não verificado". Não há regra global
  de múltiplos de 16 nem de modelo fixo.
- Nunca troca edição por geração: edit() sem imagem de entrada falha; generate() com imagem de entrada falha.
- Retry só para erro transitório e seguro: 429 (sem insufficient_quota), 500/502/503/504 e falha de conexão antes do
  envio. Timeout de leitura NÃO repete (a geração pode ter sido processada e cobrada). A API de imagens não
  oferece chave de idempotência; este módulo não promete idempotência.
- Backoff exponencial com teto e jitter; respeita Retry-After (se maior que max_retry_after, não espera: levanta).
- Orçamento por sessão e por tarefa em CHAMADAS PAGAS (cada tentativa HTTP conta). Orçamento em dinheiro não existe:
  os modelos 2.5 cobram por tokens, sem tabela por imagem; o campo usage da resposta é repassado quando existe.
- Limite de concorrência (semáforo) e cancelamento cooperativo (threading.Event) antes de cada tentativa e durante
  a espera do backoff. Uma chamada HTTP já enviada não é interrompida.
- Verifica o arquivo devolvido: JSON válido, data não vazia, base64 válido, assinatura PNG/JPEG/WebP, dimensões
  quando legíveis (PNG) comparadas com o tamanho pedido. Divergência de tamanho vira aviso, não erro.
- O trace de eventos nunca contém prompt, chave nem bytes de imagem; `usage` entra só com campos numéricos.
- Texto (OpenAIText): mesma política de retry. Orçamentos separados dos de imagem; o da TAREFA vem do contexto da thread
  (`with task_scope(text=Budget(...))`), então os pontos de chamada não precisam carregá-lo. Valida o payload (endpoint,
  modelo, messages/input, JSON serializável) e a resposta (JSON, choices/content, recusa); não valida modelo nem
  parâmetros contra a documentação (não há tabela de capacidades para texto).
"""
import base64, binascii, json, os, random, re, socket, struct, threading, time, urllib.error, urllib.request, uuid
from email.utils import parsedate_to_datetime
from pathlib import Path

CAPS_PATH = Path(__file__).resolve().parent / "provider_capabilities.json"
RETRY_STATUS = {500, 502, 503, 504}
REFUSAL_CODES = {"moderation_blocked", "content_policy_violation"}
MIME_MAGIC = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}


class ProviderError(Exception):
    """kind: validation | budget | cancelled | auth | forbidden | model | refused | unsupported_param | rate_limit |
    quota | transient | timeout | network | bad_request | bad_response."""

    def __init__(self, kind, message, status=None, retryable=False, request_id=None, retry_after=None, param=None, attempts=0):
        super().__init__(message)
        self.kind, self.status, self.retryable = kind, status, retryable
        self.request_id, self.retry_after, self.param, self.attempts = request_id, retry_after, param, attempts


class TransportError(Exception):
    def __init__(self, kind, message):  # kind: connect | timeout | network
        super().__init__(message)
        self.kind = kind


class Budget:
    """Limite de chamadas pagas. Cada tentativa HTTP conta, inclusive as repetições do retry."""

    def __init__(self, name, max_calls=None):
        self.name, self.max_calls, self.calls, self._lock = name, max_calls, 0, threading.Lock()

    def remaining(self):
        """Chamadas que ainda cabem (None = sem limite)."""
        with self._lock:
            return None if self.max_calls is None else max(0, self.max_calls - self.calls)

    def reserve(self):
        with self._lock:
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise ProviderError("budget", f"Orçamento '{self.name}' esgotado: {self.calls} de {self.max_calls} chamadas pagas. Nada foi enviado.")
            self.calls += 1


def load_capabilities(path=CAPS_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _png_info(data):
    """(largura, altura, tipo_de_cor) de um PNG, ou None."""
    if data[:8] == MIME_MAGIC["image/png"] and len(data) >= 26:
        w, h = struct.unpack(">II", data[16:24])
        return w, h, data[25]
    return None


def sniff_format(data):
    if data[:8] == MIME_MAGIC["image/png"]:
        return "image/png"
    if data[:3] == MIME_MAGIC["image/jpeg"]:
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _default_transport(method, url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, socket.timeout):
            raise TransportError("timeout", "tempo esgotado")
        if isinstance(reason, (ConnectionRefusedError, socket.gaierror)):
            raise TransportError("connect", f"não conectou: {reason}")  # nada foi enviado
        raise TransportError("network", f"falha de rede: {reason}")
    except socket.timeout:
        raise TransportError("timeout", "tempo esgotado")


def _multipart(fields, files):
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    for name, fname, mime, data in files:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + b"\r\n")
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def parse_retry_after(value, now=None):
    """Segundos (Retry-After em número ou data HTTP), ou None."""
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return float(value)
    try:
        dt = parsedate_to_datetime(value)
        return max(0.0, dt.timestamp() - (now if now is not None else time.time()))
    except (TypeError, ValueError):
        return None

_CTX = threading.local()


class task_scope:
    """Orçamento da tarefa corrente, por thread: with task_scope(text=Budget(...)): ... Os clientes somam este orçamento aos seus."""

    def __init__(self, **budgets):
        self.budgets = budgets

    def __enter__(self):
        self._prev = getattr(_CTX, "budgets", {})
        _CTX.budgets = {**self._prev, **self.budgets}
        return self

    def __exit__(self, *exc):
        _CTX.budgets = self._prev


def current_task_budgets(kind):
    b = getattr(_CTX, "budgets", {}).get(kind)
    return [b] if b else []



class OpenAIClient:
    """Base: envio com retry seguro, Retry-After, orçamento, concorrência, cancelamento e trace. Sem regra de endpoint."""
    budget_kind = "image"

    def __init__(self, base_url, api_key, budgets=(), max_retries=2, backoff_base=1.0, backoff_cap=20.0,
                 max_retry_after=30.0, timeout=300, max_concurrency=2, transport=None, sleep=None, rng=None, on_event=None):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key  # callable ou string: lido a cada chamada (a chave pode ser colada depois de subir o servidor)
        self.budgets = list(budgets)
        self.max_retries, self.backoff_base, self.backoff_cap = max_retries, backoff_base, backoff_cap
        self.max_retry_after, self.timeout = max_retry_after, timeout
        self._sem = threading.BoundedSemaphore(max_concurrency)
        self._transport = transport or _default_transport
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._on_event = on_event

    # ---------- execução com retry ----------
    def _event(self, **f):
        if self._on_event:
            try:
                self._on_event(f)
            except Exception:
                pass  # observabilidade nunca derruba a geração

    def _wait(self, seconds, cancel):
        if self._sleep:
            self._sleep(seconds)
            if cancel is not None and cancel.is_set():
                raise ProviderError("cancelled", "Cancelado durante a espera entre tentativas.")
        elif cancel is not None:
            if cancel.wait(seconds):
                raise ProviderError("cancelled", "Cancelado durante a espera entre tentativas.")
        else:
            time.sleep(seconds)

    def _call(self, op, path, body, ctype, model, size, quality, finalize, cancel, extra_budgets, prompt_chars, timeout=None, method="POST", paid=True):
        timeout = timeout or self.timeout
        key = self._api_key() if callable(self._api_key) else self._api_key
        if not key:
            raise ProviderError("auth", "Defina OPENAI_API_KEY antes de iniciar o servidor (ou use --mock).", status=400)
        client_id = uuid.uuid4().hex
        headers = {"Authorization": f"Bearer {key}", "X-Client-Request-Id": client_id}
        if ctype:
            headers["Content-Type"] = ctype
        attempt, last = 0, None
        with self._sem:
            while True:
                attempt += 1
                if cancel is not None and cancel.is_set():
                    raise ProviderError("cancelled", "Cancelado antes de enviar.", attempts=attempt - 1)
                for b in (self.budgets + list(extra_budgets) + current_task_budgets(self.budget_kind)) if paid else []:  # consulta gratuita não gasta orçamento
                    try:
                        b.reserve()
                    except ProviderError as e:
                        e.attempts = attempt - 1
                        raise
                t0 = time.time()
                try:
                    status, rh, raw = self._transport(method, self.base_url + path, headers, body, timeout)
                except TransportError as e:
                    self._event(kind="provider_call", op=op, model=model, size=size, quality=quality, attempt=attempt,
                                client_request_id=client_id, error=e.kind, ms=round((time.time() - t0) * 1000), prompt_chars=prompt_chars)
                    if e.kind == "timeout":  # pode ter sido processado e cobrado: não repete
                        raise ProviderError("timeout", f"A OpenAI não respondeu em {timeout}s; não repeti a chamada para não cobrar duas vezes.", attempts=attempt)
                    last = ProviderError("network", f"Falha de rede: {e}", retryable=(e.kind == "connect"), attempts=attempt)
                    if e.kind != "connect" or attempt > self.max_retries:
                        raise last
                    self._wait(self._delay(attempt, None), cancel)
                    continue
                ms = round((time.time() - t0) * 1000)
                rid = rh.get("x-request-id")
                common = dict(kind="provider_call", op=op, model=model, size=size, quality=quality, attempt=attempt, request_id=rid,
                              client_request_id=client_id, ms=ms, prompt_chars=prompt_chars)
                if status == 200:
                    try:
                        res = finalize(raw, rid, client_id, attempt, ms)
                    except ProviderError as e:
                        self._event(**common, status=status, error=e.kind)
                        raise
                    u = res.get("usage") if isinstance(res, dict) else None
                    self._event(**common, status=status, usage={k: v for k, v in u.items() if isinstance(v, int)} if isinstance(u, dict) else None)
                    return res
                self._event(**common, status=status)
                err = self._http_error(status, raw, rh, rid, attempt)
                if not err.retryable or attempt > self.max_retries:
                    raise err
                delay = err.retry_after if err.retry_after is not None else self._delay(attempt, None)
                if delay > self.max_retry_after:
                    raise ProviderError(err.kind, f"{err} (Retry-After de {delay:.0f}s acima do limite de espera de {self.max_retry_after:.0f}s)",
                                        status=status, request_id=rid, retry_after=delay, attempts=attempt)
                self._wait(delay, cancel)

    def _delay(self, attempt, _):
        return min(self.backoff_cap, self.backoff_base * (2 ** (attempt - 1))) * (0.5 + self._rng.random() / 2)

    def _http_error(self, status, raw, rh, rid, attempt):
        try:
            e = json.loads(raw.decode("utf-8", "replace"))["error"]
            msg, code = str(e.get("message") or ""), str(e.get("code") or "")
        except Exception:
            msg, code = raw.decode("utf-8", "replace")[:500], ""
        text = f"OpenAI {status}: {msg}"
        ra = parse_retry_after(rh.get("retry-after"))
        kw = dict(status=status, request_id=rid, attempts=attempt)
        if code in REFUSAL_CODES:
            return ProviderError("refused", text, **kw)
        if status == 429:
            if code == "insufficient_quota":
                return ProviderError("quota", text, **kw)
            return ProviderError("rate_limit", text, retryable=True, retry_after=ra, **kw)
        if status in RETRY_STATUS:
            return ProviderError("transient", text, retryable=True, retry_after=ra, **kw)
        if status == 401:
            return ProviderError("auth", text, **kw)
        if status == 403:
            return ProviderError("forbidden", text, **kw)  # inclui organização sem verificação para o modelo
        if status == 404:
            return ProviderError("model", text, **kw)
        if status == 400:
            m = re.search(r"(?:unknown|unsupported|unrecognized)[^']*parameter[^']*'([a-z_]+)'", msg, re.I) or \
                re.search(r"'([a-z_]+)'[^.]*(?:not supported|is not allowed|unknown)", msg, re.I) or \
                re.search(r"(?:does not|doesn't) support the '([a-z_]+)' parameter", msg, re.I)  # "The model 'x' does not support the 'input_fidelity' parameter."
            if m:
                return ProviderError("unsupported_param", text, param=m.group(1), **kw)
        return ProviderError("bad_request", text, **kw)


class OpenAIImages(OpenAIClient):
    budget_kind = "image"

    def __init__(self, base_url, api_key, capabilities=None, **kw):
        super().__init__(base_url, api_key, **kw)
        self.caps = capabilities if capabilities is not None else load_capabilities()

    # ---------- capacidades e validação ----------
    def get_capabilities(self, model):
        c = self.caps.get("models", {}).get(model)
        out = {"model": model, "verified": c is not None, "source": self.caps.get("_source"), "verified_on": self.caps.get("_verified_on")}
        if c:
            out.update(c)
        return out

    def validate_request(self, op, model, size, quality=None, inputs=(), mask=None, n=1, output_format=None, output_compression=None):
        """Levanta ProviderError(validation) com TODOS os problemas; devolve a lista de avisos (não bloqueiam)."""
        problems, warnings = [], []
        cap = self.get_capabilities(model)
        if op not in ("generate", "edit"):
            problems.append(f"operação desconhecida: {op!r}")
        if not model:
            problems.append("modelo ausente")
        if n != 1:
            problems.append("n deve ser 1 (decisão do harness: uma imagem por chamada paga)")
        if op == "edit" and not inputs:
            problems.append("edição sem imagem de entrada: não há fallback silencioso para geração")
        if op == "generate" and (inputs or mask):
            problems.append("geração recebeu imagens ou máscara: use edit() (não descarto referências em silêncio)")
        if mask and not inputs:
            problems.append("máscara sem imagem de entrada")
        m = re.fullmatch(r"(\d+)x(\d+)", size or "")
        if size != "auto" and not m:
            problems.append(f"size inválido: {size!r} (use LARGURAxALTURA ou auto)")
        if not cap["verified"]:
            warnings.append(f"modelo '{model}' fora de provider_capabilities.json: só o formato foi validado")
        else:
            sz = cap["sizes"]
            if size == "auto":
                if not sz.get("auto"):
                    problems.append(f"{model} não aceita size=auto")
            elif m:
                w, h = int(m.group(1)), int(m.group(2))
                if sz.get("multiple_of") and (w % sz["multiple_of"] or h % sz["multiple_of"]):
                    problems.append(f"{model}: lados devem ser múltiplos de {sz['multiple_of']} ({w}x{h})")
                if sz.get("max_edge") and max(w, h) > sz["max_edge"]:
                    problems.append(f"{model}: lado acima de {sz['max_edge']}px ({w}x{h})")
                if sz.get("max_aspect") and max(w, h) / max(1, min(w, h)) > sz["max_aspect"]:
                    problems.append(f"{model}: proporção acima de {sz['max_aspect']}:1 ({w}x{h})")
                if sz.get("min_pixels") and not sz["min_pixels"] <= w * h <= sz.get("max_pixels", w * h):
                    problems.append(f"{model}: total de pixels fora de {sz['min_pixels']}..{sz.get('max_pixels')} ({w * h})")
            if quality and quality not in cap["quality"]:
                problems.append(f"{model}: quality {quality!r} fora de {cap['quality']}")
        limit = cap.get("max_input_bytes")
        first = None
        for i, x in enumerate(inputs):
            data, mime = x.get("bytes") or b"", x.get("mime")
            real = sniff_format(data)
            if mime not in ("image/png", "image/jpeg", "image/webp"):
                problems.append(f"entrada {i}: tipo {mime!r} não suportado para edição (use PNG, JPEG ou WebP)")
            elif real != mime:
                problems.append(f"entrada {i}: o conteúdo não é {mime} (assinatura {real})")
            if limit and len(data) > limit:
                problems.append(f"entrada {i}: {len(data)} bytes acima do limite de {limit}")
            if i == 0:
                first = (real, _png_info(data))
        if mask:
            minfo = _png_info(mask)
            if not minfo:
                problems.append("máscara deve ser PNG")
            else:
                if minfo[2] not in (4, 6):
                    problems.append("máscara sem canal alfa (PNG tipo de cor 4 ou 6)")
                if first and first[0] != "image/png":
                    problems.append("máscara e imagem devem ter o mesmo formato: converta o alvo para PNG antes de enviar")
                elif first and first[1] and first[1][:2] != minfo[:2]:
                    problems.append(f"máscara {minfo[0]}x{minfo[1]} diferente da imagem {first[1][0]}x{first[1][1]}")
            if limit and len(mask) > limit:
                problems.append("máscara acima do limite de tamanho")
        formats = cap.get("output_formats") or ["png", "jpeg", "webp"]
        if output_format is not None and output_format not in formats:
            problems.append(f"output_format {output_format!r} fora de {formats}")
        if output_compression is not None:
            rng = cap.get("output_compression") or {"min": 0, "max": 100, "only_for": ["jpeg", "webp"]}
            if not isinstance(output_compression, int) or isinstance(output_compression, bool) or not rng["min"] <= output_compression <= rng["max"]:
                problems.append(f"output_compression deve ser inteiro de {rng['min']} a {rng['max']}")
            elif (output_format or "png") not in rng["only_for"]:
                problems.append(f"output_compression só vale para {'/'.join(rng['only_for'])}, não para {(output_format or 'png')}")
        if output_format not in (None, "png") and mask:
            problems.append("máscara exige o mesmo formato da imagem: edição com máscara fica em PNG")
        if problems:
            raise ProviderError("validation", "Requisição inválida, nada foi enviado: " + "; ".join(problems))
        return warnings

    # ---------- operações ----------
    def generate(self, prompt, model, size, quality=None, n=1, cancel=None, extra_budgets=(), timeout=None, output_format=None, output_compression=None):
        warnings = self.validate_request("generate", model, size, quality, n=n, output_format=output_format, output_compression=output_compression)
        body = {"model": model, "prompt": prompt, "size": size, "n": n}
        if quality:
            body["quality"] = quality
        if output_format:
            body["output_format"] = output_format
        if output_compression is not None:
            body["output_compression"] = output_compression
        return self._call("generate", "/images/generations", json.dumps(body).encode(), "application/json", model, size, quality,
                          lambda raw, rid, cid, att, ms: self._parse(raw, "generate", model, size, warnings, rid, cid, att, ms), cancel, extra_budgets, len(prompt), timeout)

    def edit(self, prompt, model, size, quality=None, inputs=(), mask=None, fidelity=None, n=1, cancel=None, extra_budgets=(), timeout=None,
             output_format=None, output_compression=None):
        warnings = self.validate_request("edit", model, size, quality, inputs=inputs, mask=mask, n=n, output_format=output_format, output_compression=output_compression)
        fields = {"model": model, "prompt": prompt, "size": size, "n": n}
        if quality:
            fields["quality"] = quality
        if output_format:
            fields["output_format"] = output_format
        if output_compression is not None:
            fields["output_compression"] = output_compression
        if fidelity:
            fields["input_fidelity"] = fidelity
        exts = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
        files = [("image[]", f"in{i}.{exts[x['mime']]}", x["mime"], x["bytes"]) for i, x in enumerate(inputs)]
        if mask:  # vale para a primeira imagem; transparente = onde o modelo pode editar
            files.append(("mask", "mask.png", "image/png", mask))
        body, ctype = _multipart(fields, files)
        return self._call("edit", "/images/edits", body, ctype, model, size, quality,
                          lambda raw, rid, cid, att, ms: self._parse(raw, "edit", model, size, warnings, rid, cid, att, ms), cancel, extra_budgets, len(prompt), timeout)

    def _parse(self, raw, op, model, size, warnings, rid, client_id, attempts, ms):
        ctx = dict(request_id=rid, attempts=attempts)
        try:
            doc = json.loads(raw.decode("utf-8"))
        except Exception:
            raise ProviderError("bad_response", "Resposta da OpenAI não é JSON válido.", **ctx)
        data = doc.get("data") if isinstance(doc, dict) else None
        if not data or not isinstance(data, list) or not isinstance(data[0], dict):
            raise ProviderError("bad_response", "Resposta da OpenAI sem imagem (data vazia).", **ctx)
        b64 = data[0].get("b64_json")
        if not b64:
            raise ProviderError("bad_response", "Resposta sem b64_json (formato de saída inesperado).", **ctx)
        try:
            img = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            raise ProviderError("bad_response", "b64_json inválido: falha ao decodificar.", **ctx)
        fmt = sniff_format(img)
        if not fmt:
            raise ProviderError("bad_response", "O arquivo devolvido não é PNG, JPEG nem WebP.", **ctx)
        warnings = list(warnings)
        info = _png_info(img)
        dims = (info[0], info[1]) if info else None
        if dims and size != "auto" and f"{dims[0]}x{dims[1]}" != size:
            warnings.append(f"tamanho devolvido {dims[0]}x{dims[1]} difere do pedido {size}")
        return {"b64": b64, "bytes": img, "mime": fmt, "ext": {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[fmt],
                "dims": dims, "usage": doc.get("usage"), "request_id": rid, "client_request_id": client_id,
                "attempts": attempts, "ms": ms, "model": model, "op": op, "warnings": warnings}


class OpenAIText(OpenAIClient):
    """Chamadas JSON de texto (chat completions e responses): briefing, critic, resolvedor, localização e pesquisa.
    Mesma política de retry, Retry-After, orçamento (separado do de imagens), concorrência e trace do adapter de imagens.
    Orçamento da tarefa: vem do contexto da thread (task_scope), para os pontos de chamada não precisarem carregá-lo."""
    budget_kind = "text"
    PATHS = ("/chat/completions", "/responses")
    ROLES = ("system", "developer", "user", "assistant", "tool")

    def validate_payload(self, path, payload):
        problems = []
        if path not in self.PATHS:
            problems.append(f"endpoint de texto não suportado: {path!r}")
        if not isinstance(payload, dict):
            problems.append("payload deve ser um objeto JSON")
        else:
            if not isinstance(payload.get("model"), str) or not payload.get("model"):
                problems.append("modelo ausente")
            if path == "/chat/completions":
                msgs = payload.get("messages")
                if not isinstance(msgs, list) or not msgs:
                    problems.append("messages ausente ou vazio")
                else:
                    for i, m in enumerate(msgs):
                        if not isinstance(m, dict) or m.get("role") not in self.ROLES:
                            problems.append(f"messages[{i}] sem role válido")
            if path == "/responses" and not payload.get("input"):
                problems.append("input ausente")
            try:
                json.dumps(payload)
            except (TypeError, ValueError):
                problems.append("payload não serializável em JSON")
        if problems:
            raise ProviderError("validation", "Requisição inválida, nada foi enviado: " + "; ".join(problems))

    def post_json(self, path, payload, timeout=None, cancel=None, extra_budgets=()):
        self.validate_payload(path, payload)
        body = json.dumps(payload).encode()
        return self._call("text", path, body, "application/json", payload["model"], None, None,
                          lambda raw, rid, cid, att, ms: self._parse_json(path, raw, rid, att), cancel, extra_budgets, len(body), timeout)

    GET_PATH = re.compile(r"/models(/(?!\.+$)[A-Za-z0-9._:-]{1,100})?")  # sem segmento só de pontos (..)

    def get_json(self, path, timeout=None, cancel=None):
        """Consulta GRATUITA (lista de modelos): mesma política de retry e Retry-After, sem gastar orçamento de chamadas pagas."""
        if not self.GET_PATH.fullmatch(path or ""):
            raise ProviderError("validation", f"Requisição inválida, nada foi enviado: consulta {path!r} não suportada (só /models)")
        return self._call("get", path, None, None, None, None, None, lambda raw, rid, cid, att, ms: self._parse_json(path, raw, rid, att),
                          cancel, (), 0, timeout, method="GET", paid=False)

    def _parse_json(self, path, raw, rid, attempts):
        ctx = dict(request_id=rid, attempts=attempts)
        try:
            doc = json.loads(raw.decode("utf-8"))
        except Exception:
            raise ProviderError("bad_response", "Resposta da OpenAI não é JSON válido.", **ctx)
        if not isinstance(doc, dict):
            raise ProviderError("bad_response", "Resposta da OpenAI não é um objeto JSON.", **ctx)
        if path == "/chat/completions":
            ch = doc.get("choices")
            msg = ch[0].get("message") if isinstance(ch, list) and ch and isinstance(ch[0], dict) else None
            if not isinstance(msg, dict):
                raise ProviderError("bad_response", "Resposta de texto sem choices[0].message.", **ctx)
            if msg.get("refusal"):
                raise ProviderError("refused", "O modelo recusou o pedido: " + str(msg["refusal"])[:200], **ctx)
            if not msg.get("content") and not msg.get("tool_calls"):
                raise ProviderError("bad_response", "Resposta de texto vazia (sem content).", **ctx)
        elif doc.get("error"):
            raise ProviderError("bad_response", "Resposta com erro: " + str(doc["error"])[:200], **ctx)
        return doc


def from_env(budgets=(), on_event=None, **kw):
    """Instância padrão do servidor: base e chave vêm do ambiente (a chave é lida a cada chamada)."""
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAIImages(base, lambda: os.getenv("OPENAI_API_KEY"), budgets=budgets, on_event=on_event, **kw)


def text_from_env(budgets=(), on_event=None, **kw):
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAIText(base, lambda: os.getenv("OPENAI_API_KEY"), budgets=budgets, on_event=on_event, **kw)
