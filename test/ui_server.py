#!/usr/bin/env python3
"""Interface local para testar o system prompt do designer-imagegen.

  python3 ui_server.py            # http://127.0.0.1:8765  (usa OPENAI_API_KEY)
  python3 ui_server.py --mock     # sem API: briefing/imagem/revisão falsos, só para ver a UI

Sem dependências (só stdlib). O system prompt é relido de prompts/designer-imagegen.system.md
a cada chamada: edite o arquivo e rode de novo, sem reiniciar o servidor.
A rubrica, a nota e a regra de aprovação vêm de run_comparison.py (mesma lógica do teste A/B/C).
"""
import argparse, hashlib, json, os, pathlib, random, shutil, sys, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run_comparison as rc  # noqa: E402

MOCK = False
OPENAI = "https://api.openai.com/v1"


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def env_models():
    return {
        "text_model": os.getenv("TEXT_MODEL", "gpt-5.5"),
        "image_model": os.getenv("IMAGE_MODEL", "gpt-image-2.5-sunburst"),
        "quality": os.getenv("IMAGE_QUALITY", "medium"),
    }


def openai_post(path, payload, timeout=240):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ApiError(400, "Defina OPENAI_API_KEY antes de iniciar o servidor (ou use --mock).")
    req = urllib.request.Request(
        OPENAI + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body)["error"]["message"]
        except Exception:
            msg = body[:500]
        raise ApiError(502, f"OpenAI {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise ApiError(502, f"Falha de rede: {e.reason}")


# ---------- handlers ----------
def api_defaults(_):
    client = json.loads((ROOT / "client_71.json").read_text(encoding="utf-8"))
    cases = json.loads((ROOT / "eval_set.json").read_text(encoding="utf-8"))
    return {"client": client, "cases": cases, "mock": MOCK, "has_key": bool(os.getenv("OPENAI_API_KEY")),
            "has_claude": shutil.which("claude") is not None,
            **env_models(), "pass_score": rc.PASS_SCORE, "weights": rc.WEIGHTS,
            "prompt_path": str(rc.SYSTEM_PROMPT_PATH.relative_to(ROOT.parent))}


def api_system(b):
    text = rc.load_system_prompt(b.get("client") or {}, b.get("agency") or "Aurea Tech")
    return {"system": text, "chars": len(text), "sha": hashlib.sha1(text.encode()).hexdigest()[:8],
            "mtime": time.strftime("%H:%M:%S", time.localtime(rc.SYSTEM_PROMPT_PATH.stat().st_mtime))}


def api_naive(b):
    return {"prompt": rc.naive_prompt(b.get("client") or {}, b["request"])}


def api_briefing(b):
    client_ctx, request = b.get("client") or {}, b["request"]
    system = rc.load_system_prompt(client_ctx)
    user = f"Pedido: {request}\n"
    if b.get("feedback"):
        user += (f"\nA versão anterior foi reprovada. Prompt anterior:\n{b.get('prev')}\n\n"
                 f"Corrija APENAS isto: {b['feedback']}\nRepita as invariantes.")
    user += '\n\nResponda SOMENTE JSON: {"use_case":"...","role":"hero|cell","prompt":"<prompt final em inglês no schema>"}'
    if b.get("provider") == "claude" and not MOCK:
        import run_briefings_claude as rbc
        try:
            out = rbc.briefing(request, client_ctx, b.get("claude_model") or "sonnet", b.get("size"),
                               feedback=b.get("feedback"), prev=b.get("prev"))
        except Exception as e:  # noqa: BLE001
            raise ApiError(502, f"claude CLI: {e}")
        out["system_chars"] = len(system)
        return out
    if MOCK:
        time.sleep(0.6)
        return {"use_case": "ads-marketing", "role": "cell", "system_chars": len(system),
                "prompt": f"Use case: ads-marketing\nPrimary request: {request}\nStyle/medium: editorial photography\n"
                          f"Color palette: {', '.join(client_ctx.get('palette', []))}\nAvoid: no watermark, no extra text"
                          + (f"\n[mock: corrigido -> {b['feedback']}]" if b.get("feedback") else "")}
    r = openai_post("/chat/completions", {
        "model": b.get("text_model") or env_models()["text_model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"}})
    out = json.loads(r["choices"][0]["message"]["content"])
    out["system_chars"] = len(system)
    return out


def api_image(b):
    size, quality = b.get("size") or "1024x1024", b.get("quality") or "medium"
    t0 = time.time()
    if MOCK:
        time.sleep(1.0)
        w, h = (int(x) for x in size.split("x"))
        hue = random.randint(0, 360)
        svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'>"
               f"<rect width='100%' height='100%' fill='hsl({hue},60%,55%)'/>"
               f"<text x='50%' y='50%' font-size='{w // 14}' fill='white' text-anchor='middle'>mock {size}</text></svg>")
        import base64
        return {"b64": base64.b64encode(svg.encode()).decode(), "mime": "image/svg+xml", "seconds": round(time.time() - t0, 1)}
    r = openai_post("/images/generations", {
        "model": b.get("image_model") or env_models()["image_model"],
        "prompt": b["prompt"], "size": size, "quality": quality, "n": 1})
    return {"b64": r["data"][0]["b64_json"], "mime": "image/png", "seconds": round(time.time() - t0, 1)}


def api_review(b):
    """Mesma revisão do teste A/B/C: critic.py (rubrica v3) + vetos por código (checks.py)."""
    client_ctx, request = b.get("client") or {}, b["request"]
    if MOCK:
        time.sleep(0.6)
        rv = {"scores": {k: random.randint(6, 10) for k in rc.WEIGHTS}, "veto": random.choice([[], [], ["watermark"]]),
              "issues": ["(mock) exemplo de problema"], "fix": "(mock) aumentar contraste do primeiro plano"}
    else:
        model = b.get("text_model") or env_models()["text_model"]

        def vlm(system, user_text, images):
            content = [{"type": "text", "text": user_text}]
            for label, b64 in images:
                content += [{"type": "text", "text": label},
                            {"type": "image_url", "image_url": {"url": f"data:{b.get('mime', 'image/png')};base64,{b64}"}}]
            r = openai_post("/chat/completions", {"model": model, "response_format": {"type": "json_object"},
                                                  "messages": [{"role": "system", "content": system},
                                                               {"role": "user", "content": content}]})
            return r["choices"][0]["message"]["content"]

        rv = rc.critic.review(vlm, b["briefing"], client_ctx, request, [("Imagem avaliada", b["b64"])])
    rv = rc.checks.apply(rv, b["b64"], b.get("size"))
    score, ok = rc.decide(rv)
    return {"review": rv, "score": score, "approved": ok}


ROUTES = {"/api/system": api_system, "/api/naive": api_naive, "/api/briefing": api_briefing,
          "/api/image": api_image, "/api/review": api_review}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "ui" / "index.html").read_bytes(), "text/html")
        elif self.path == "/api/defaults":
            self._send(200, api_defaults({}))
        else:
            self._send(404, {"error": "não encontrado"})

    def do_POST(self):
        fn = ROUTES.get(self.path)
        if not fn:
            return self._send(404, {"error": "não encontrado"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self._send(200, fn(body))
        except ApiError as e:
            self._send(e.status, {"error": str(e)})
        except KeyError as e:
            self._send(400, {"error": f"campo ausente: {e}"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def main():
    global MOCK
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--mock", action="store_true", help="não chama a API; dados falsos para ver a UI")
    a = ap.parse_args()
    MOCK = a.mock
    rc.self_test()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    modo = "MOCK (sem API)" if MOCK else ("OPENAI_API_KEY ok" if os.getenv("OPENAI_API_KEY") else "SEM OPENAI_API_KEY: só o system prompt renderizado funciona")
    print(f"Interface: http://127.0.0.1:{a.port}  [{modo}]", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
