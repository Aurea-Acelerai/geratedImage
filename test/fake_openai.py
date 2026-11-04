#!/usr/bin/env python3
"""OpenAI falsa para testar o caminho "real" do chat sem chave e sem custo. Só stdlib.

  python3 fake_openai.py --port 9101
  OPENAI_BASE_URL=http://127.0.0.1:9101/v1 OPENAI_API_KEY=fake python3 chat_server.py

Implementa /v1/models, /v1/chat/completions (briefing e critic), /v1/images/generations e /v1/images/edits
(multipart), e GET /__stats com contadores. NÃO valida a semântica da API real: serve para provar que o nosso
código monta as requisições e trata as respostas. Comportamentos de teste:
- o 1º review do critic reprova (nota 6) e o 2º aprova, para exercitar a correção;
- pedido com "wrongsize" devolve uma imagem de 512x512 (o veto formato_incorreto tem que aparecer);
- pedido com "perguntar" faz o designer devolver uma pergunta;
- --models-missing lista só modelos antigos (o aviso de modelo ausente tem que aparecer).
"""
import argparse, base64, email, json, re, struct, sys, threading, time, zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATS = {"models": 0, "chat_writer": 0, "chat_critic": 0, "generations": 0, "edits": 0, "edit_images": [], "writer_images": [],
         "critic_images": [], "auth": set(), "edit_fields": [], "last_writer_user": "", "writer_systems": [], "image_prompts": [], "critic_systems": [], "resolver_users": [], "web_queries": []}
LOCK = threading.Lock()
CRITIC_KEYS = ["subject", "style", "composition", "hierarchy", "legibility_size", "message_clarity", "craft", "color_contrast",
               "text", "defects", "format", "binding_count", "invariants", "brand_fit", "style_mechanism", "identity_match"]


def png(w, h):
    raw = b"".join(b"\x00" + bytes([(x * 7 + y) % 256 for x in range(0, w, 1)][:w]) for y in range(h)) if w * h < 10000 else \
        b"".join(b"\x00" + (b"\x80" * w) for _ in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


class H(BaseHTTPRequestHandler):
    models_missing = False
    delay = 0.0

    def _json(self, code, obj):
        d = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(d)))
        self.end_headers(); self.wfile.write(d)

    def do_GET(self):
        STATS["auth"].add(self.headers.get("Authorization", ""))
        if self.path.startswith("/w/api.php"):
            import urllib.parse as up
            qs = up.parse_qs(up.urlparse(self.path).query)
            STATS["web_queries"].append(qs.get("gsrsearch", [""])[0])
            port = self.server.server_port
            pages = {"1": {"index": 1, "title": "File:Logo CVC 1989.png", "imageinfo": [{"thumburl": f"http://127.0.0.1:{port}/img/logo.png", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Logo_CVC_1989.png",
                     "mime": "image/png", "width": 512, "height": 512, "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "Artist": {"value": "<a href='x'>Autor Teste</a>"}}}]},
                     "2": {"index": 2, "title": "File:Doc.pdf", "imageinfo": [{"mime": "application/pdf", "url": "http://x/doc.pdf"}]}}
            return self._json(200, {"query": {"pages": pages}})
        if self.path == "/img/logo.png":
            d = png(64, 64); self.send_response(200); self.send_header("Content-Type", "image/png"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d); return
        if self.path == "/img/falso.png":
            d = b"isto nao e uma imagem"; self.send_response(200); self.send_header("Content-Type", "image/png"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d); return
        if self.path == "/__stats":
            return self._json(200, {k: (sorted(v) if isinstance(v, set) else v) for k, v in STATS.items()})
        if self.path == "/v1/models":
            STATS["models"] += 1
            ids = ["gpt-4o", "gpt-image-1", "text-embedding-3-small"] if self.models_missing else \
                  ["gpt-5.5", "gpt-4o", "gpt-image-2.5-sunburst", "gpt-image-1", "whisper-1", "text-embedding-3-small"]
            return self._json(200, {"data": [{"id": i} for i in ids]})
        self._json(404, {"error": {"message": "rota desconhecida"}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        with LOCK:
            STATS["auth"].add(self.headers.get("Authorization", ""))
        if self.path == "/v1/chat/completions":
            req = json.loads(body); msgs = req["messages"]
            system = msgs[0]["content"]; user = msgs[1]["content"]
            parts = user if isinstance(user, list) else [{"type": "text", "text": user}]
            utext = "\n".join(p["text"] for p in parts if p["type"] == "text")
            nimg = sum(1 for p in parts if p["type"] == "image_url")
            if "resolve o contexto" in system:
                msg = re.search(r"Nova mensagem do usuário: (.*)", utext, re.S).group(1).strip()
                with LOCK:
                    STATS["resolver_users"].append(utext)
                pend = re.search(r"PERGUNTA PENDENTE.*?\(pedido original: (.*?); intenção original: (\w+)\)\s*$", utext.split("\n\nImagens disponíveis")[0], re.S | re.M)
                lasts = re.findall(r"Pedido: (.*?) \|", utext.split("\n\nImagens disponíveis")[0])
                if pend:
                    out = {"intent": pend.group(2), "request": f"{pend.group(1)} {msg}", "use_last_image": pend.group(2) in ("edit", "variation"), "carry": []}
                elif re.search(r"\b(mude|troque|tire|agora|mais|deixe)\b", msg, re.I) and lasts:
                    ref = re.search(r"([^,;|]+?) \(referencia\) \[id (\w+)\]", utext) if re.search(r"refer[eê]ncia", msg, re.I) else None
                    out = ({"intent": "edit", "request": f"{lasts[-1]}; {msg}", "use_last_image": False, "edit_target": ref.group(2), "carry": []} if ref
                           else {"intent": "edit", "request": f"{lasts[-1]}; {msg}", "use_last_image": True, "carry": []})
                else:
                    out = {"intent": "new", "request": msg, "use_last_image": False, "carry": []}
                return self._json(200, {"choices": [{"message": {"content": json.dumps(out)}}]})
            if "revisor de qualidade" in system:
                with LOCK:
                    STATS["chat_critic"] += 1; STATS["critic_images"].append(nimg); k = STATS["chat_critic"]
                    STATS["critic_systems"].append({"hierarchy": "`hierarchy`" in system, "brand_fit": "`brand_fit`" in system, "text": "`text`" in system,
                                                    "cta_vago": "`cta_vago`" in system, "subject": "`subject`" in system,
                                                    "identity_match": "`identity_match`" in system})
                bad = k % 2 == 1
                rv = {"issues": [{"criterion": "hierarchy", "evidence": "foco fraco", "severity": "media"}] if bad else [],
                      "scores": {c: (6 if bad else 9) for c in CRITIC_KEYS}, "veto": [], "fix": "aumentar o contraste do foco" if bad else ""}
                if "trocarpessoa" in utext:
                    rv["veto"] = ["identidade_divergente"]
                return self._json(200, {"choices": [{"message": {"content": json.dumps(rv)}}]})
            with LOCK:
                STATS["chat_writer"] += 1; STATS["writer_images"].append(nimg); STATS["last_writer_user"] = utext
                STATS["writer_systems"].append({"livre": "MODO LIVRE" in system, "marca": "MODO COM MARCA" in system, "setor_no_prompt": "moda praia" in system})
            if "buscarweb" in utext.lower() and "o designer PERGUNTOU" not in utext:
                return self._json(200, {"choices": [{"message": {"content": json.dumps({"question": "Quer que eu busque o logo na web?", "search": [{"q": "logo CVC", "kind": "logo"}]})}}]})
            if "perguntar" in utext.lower() and "o designer PERGUNTOU" not in utext:  # pergunta uma vez; depois a memória já tem a resposta
                out = {"question": "Qual é a oferta exata?"} if "perguntaoferta" in utext.lower() else {"question": "Qual é a oferta da peça e qual foto de referência devo usar?"}
            else:
                m = re.search(r"Pedido atual[^:]*: (.*)", utext)
                out = {"use_case": "ads-marketing", "role": "cell",
                       "prompt": f"Use case: ads-marketing\nPrimary request: {m.group(1) if m else ''}\nInput images: {nimg}"}
            return self._json(200, {"choices": [{"message": {"content": json.dumps(out)}}]})
        if self.path.startswith("/v1/images/"):
            time.sleep(self.delay)  # simula a demora da geração
        if self.path == "/v1/images/generations":
            req = json.loads(body)
            with LOCK:
                STATS["generations"] += 1; STATS["image_prompts"].append(req["prompt"])
            w, h = (512, 512) if "wrongsize" in req["prompt"].lower() else map(int, req["size"].split("x"))
            return self._json(200, {"data": [{"b64_json": base64.b64encode(png(w, h)).decode()}]})
        if self.path == "/v1/images/edits":
            raw = b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body
            msg = email.message_from_bytes(raw)
            fields = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in msg.get_payload()
                      if not p.get_filename()}
            imgs = sum(1 for p in msg.get_payload() if p.get_param("name", header="content-disposition") == "image[]")
            with LOCK:
                STATS["edits"] += 1; STATS["edit_images"].append(imgs); STATS["edit_fields"].append(sorted(fields))
                STATS["image_prompts"].append(fields.get("prompt", b"").decode())
            if "rejectfidelity" in fields.get("prompt", b"").decode().lower() and "input_fidelity" in fields:
                return self._json(400, {"error": {"message": "Unknown parameter: 'input_fidelity'."}})
            size = fields.get("size", b"1024x1024").decode()
            w, h = (512, 512) if "wrongsize" in fields.get("prompt", b"").decode().lower() else map(int, size.split("x"))
            return self._json(200, {"data": [{"b64_json": base64.b64encode(png(w, h)).decode()}]})
        self._json(404, {"error": {"message": "rota desconhecida"}})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9101)
    ap.add_argument("--models-missing", action="store_true")
    ap.add_argument("--delay", type=float, default=0.0, help="segundos de espera por imagem")
    a = ap.parse_args()
    H.models_missing = a.models_missing
    H.delay = a.delay
    print(f"OpenAI falsa em http://127.0.0.1:{a.port}/v1", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
