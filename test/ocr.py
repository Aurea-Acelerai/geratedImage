#!/usr/bin/env python3
"""OCR auxiliar com limites explícitos para checar texto literal em imagens geradas. Só stdlib.

O que faz:
- available(): True só se o executável `tesseract` existir no PATH. Sem ele (caso desta máquina), o módulo
  degrada com honestidade: status "unavailable", nenhum texto inventado.
- read_text(): lê o texto da imagem. O backend padrão chama o CLI do tesseract por subprocess, SEM shell (lista de
  argumentos), com a imagem num arquivo dentro de uma pasta temporária e com timeout. Um backend pode ser injetado
  (callable(bytes, lang) -> dict com text e words=[{text, conf}]), o que serve aos testes e a outros motores.
- text_fidelity(): compara literais esperados com o que o OCR leu. Veredito por literal: match | near | missing |
  not_verified. Se o OCR não está "ok", TODOS saem not_verified: ausência de OCR nunca aprova nem reprova.

O que NÃO faz (limites, também devolvidos em `limits` de cada resultado):
- O OCR é AUXILIAR, nunca prova de fidelidade. "match" diz que o OCR leu o literal com confiança razoável;
  "missing" diz só que o OCR não achou, não que o texto esteja errado na imagem.
- Não verifica de forma confiável: texto pequeno, fontes decorativas ou manuscritas, baixo contraste, texto curvo
  ou em perspectiva, e idiomas fora de `lang`.
- Dimensões válidas do arquivo não provam fidelidade textual.
- Casos críticos (preço, telefone, dosagem, nome próprio, dado numérico) vão para revisão humana mesmo com "match".
"""
import os, re, shutil, subprocess, tempfile, unicodedata

LIMITS = [
    "O OCR é auxiliar e nunca prova fidelidade textual; casos críticos exigem revisão humana.",
    "Texto pequeno, fontes decorativas ou manuscritas, baixo contraste e texto curvo ou em perspectiva não são verificáveis de forma confiável.",
    "Idiomas fora do configurado em `lang` não são verificáveis.",
    "Palavras com confiança abaixo de 60 não contam como evidência de correspondência exata.",
    "'missing' significa apenas que o OCR não encontrou o literal, não que o texto esteja errado na imagem.",
    "Dimensões válidas do arquivo não provam fidelidade textual.",
]
CONF_MIN = 60          # abaixo disto a palavra não é evidência de "match"
NEAR_MIN = 0.75        # razão mínima (1 - distância/tamanho do literal) para "near"
ACCENT_COST = 0.5      # trocar uma letra pela sua versão sem acento custa meia edição
_LANG_RE = re.compile(r"[A-Za-z0-9_]+(\+[A-Za-z0-9_]+)*")


def available():
    """True só se o executável `tesseract` existir."""
    return shutil.which("tesseract") is not None


def _sniff_ext(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _parse_tsv(tsv):
    """Saída `tesseract ... tsv` -> {"text", "words"}. Só linhas de palavra (nível 5) com texto; conf -1 é ignorada."""
    words, lines, order = [], {}, []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5" or not cols[11].strip():
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            continue
        if conf < 0:
            continue
        w = {"text": cols[11].strip(), "conf": conf}
        words.append(w)
        key = tuple(cols[2:5])  # bloco, parágrafo, linha
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(w["text"])
    return {"text": "\n".join(" ".join(lines[k]) for k in order), "words": words}


def _tesseract_backend(timeout):
    """Backend padrão: CLI do tesseract, sem shell, arquivo temporário em pasta temporária, com timeout."""

    def backend(image_bytes, lang):
        ext = _sniff_ext(image_bytes)
        if not ext:
            raise ValueError("formato de imagem não reconhecido (PNG, JPEG ou WebP)")
        if not _LANG_RE.fullmatch(lang or ""):
            raise ValueError(f"lang inválido: {lang!r}")
        with tempfile.TemporaryDirectory(prefix="ocr_") as tmp:
            path = os.path.join(tmp, "in." + ext)
            with open(path, "wb") as f:
                f.write(image_bytes)
            cmd = ["tesseract", path, "stdout", "-l", lang, "tsv"]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, shell=False,
                                  env={**os.environ, "OMP_THREAD_LIMIT": "1"})
        if proc.returncode != 0:
            raise RuntimeError("tesseract falhou: " + proc.stderr.decode("utf-8", "replace").strip()[:300])
        return _parse_tsv(proc.stdout.decode("utf-8", "replace"))

    return backend


def _result(status, text="", words=None, mean_conf=None, reason=None, lang=None):
    return {"status": status, "text": text, "words": words or [], "mean_conf": mean_conf,
            "reason": reason, "lang": lang, "limits": list(LIMITS)}


def read_text(image_bytes, backend=None, lang="por", timeout=20):
    """{"status": "ok"|"unavailable"|"error", "text", "words", "mean_conf", "limits", ...}.

    Sem tesseract e sem backend injetado => "unavailable", sem texto. Qualquer falha do motor (timeout, código de
    saída, idioma ausente, formato ilegível, resposta fora do contrato) => "error", também sem texto."""
    if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
        return _result("error", reason="imagem vazia ou não é bytes", lang=lang)
    if backend is None:
        if not available():
            return _result("unavailable", reason="tesseract não está instalado: nenhum texto foi lido", lang=lang)
        backend = _tesseract_backend(timeout)
    try:
        out = backend(bytes(image_bytes), lang)
    except subprocess.TimeoutExpired:
        return _result("error", reason=f"tesseract excedeu o timeout de {timeout}s", lang=lang)
    except Exception as e:  # o motor é externo: qualquer falha vira "error", nunca texto inventado
        return _result("error", reason=f"{type(e).__name__}: {e}"[:300], lang=lang)
    if not isinstance(out, dict) or not isinstance(out.get("text"), str):
        return _result("error", reason="o backend de OCR devolveu algo fora do contrato (esperado dict com text)", lang=lang)
    words = []
    for w in out.get("words") or []:
        try:
            words.append({"text": str(w["text"]), "conf": float(w["conf"])})
        except (KeyError, TypeError, ValueError):
            return _result("error", reason="o backend de OCR devolveu words fora do contrato ({text, conf})", lang=lang)
    mean = round(sum(w["conf"] for w in words) / len(words), 2) if words else None
    return _result("ok", text=out["text"], words=words, mean_conf=mean, lang=lang)


# ---------------------------------------------------------------- fidelidade


def _strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def _norm(s, accent_sensitive=True):
    s = unicodedata.normalize("NFC", str(s)).casefold()
    if not accent_sensitive:
        s = _strip_accents(s)
    return re.sub(r"\s+", " ", s).strip()


def _sub_cost(a, b):
    if a == b:
        return 0.0
    return ACCENT_COST if _strip_accents(a) == _strip_accents(b) else 1.0


def best_substring_distance(needle, hay):
    """Menor distância de edição entre `needle` e QUALQUER trecho de `hay` (Sellers). Inserção e remoção custam 1;
    trocar uma letra pela sua versão sem acento custa 0,5 (um acento errado é meia edição); demais trocas custam 1."""
    if not needle:
        return 0.0
    prev = [0.0] * (len(hay) + 1)  # o trecho pode começar em qualquer posição de hay
    for i, a in enumerate(needle, 1):
        cur = [float(i)]
        for j, b in enumerate(hay, 1):
            cur.append(min(prev[j - 1] + _sub_cost(a, b), prev[j] + 1.0, cur[j - 1] + 1.0))
        prev = cur
    return min(prev)


def _contains_bounded(needle, hay):
    return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", hay) is not None


def _verdict(literal, ocr_result, accent_sensitive):
    e = _norm(literal, accent_sensitive)
    if not e:
        return {"literal": literal, "verdict": "not_verified", "ratio": None, "note": "literal vazio"}
    words = ocr_result.get("words") or []
    full = _norm(ocr_result.get("text", ""), accent_sensitive)
    # palavra de baixa confiança vira um separador (\x00): não pode "emendar" duas palavras seguras num falso match
    confident = _norm(" ".join(w["text"] if w["conf"] >= CONF_MIN else "\x00" for w in words), accent_sensitive)
    ratio = max(0.0, 1.0 - best_substring_distance(e, full) / len(e)) if full else 0.0
    ratio = round(ratio, 3)
    if words and _contains_bounded(e, confident):
        return {"literal": literal, "verdict": "match", "ratio": 1.0}
    if _contains_bounded(e, full):
        # achado, mas sem evidência confiável: sem palavras com confiança ou só em palavras abaixo de CONF_MIN
        why = "OCR sem confiança por palavra" if not words else f"literal visto só em palavras com confiança < {CONF_MIN}"
        return {"literal": literal, "verdict": "near", "ratio": min(ratio, 0.99), "note": why}
    if ratio >= NEAR_MIN:
        return {"literal": literal, "verdict": "near", "ratio": min(ratio, 0.99)}  # 1.0 fica reservado ao match
    return {"literal": literal, "verdict": "missing", "ratio": ratio}


def text_fidelity(expected, ocr_result, accent_sensitive=True):
    """Compara literais esperados com o resultado de read_text.

    Retorna {"results": [{"literal", "verdict", "ratio"}...], "verified": bool, "all_match": bool|None,
    "not_verified": n, "counts": {...}, "limits": [...]}. Normalização: casefold e espaços; acentos contam por padrão
    ("Promoção" vs "Promocao" é near, não match). Se o status do OCR não for "ok", todos os literais saem
    not_verified. `all_match` é None quando algum literal não foi verificado (ou não há literais)."""
    if isinstance(expected, str):
        expected = [expected]
    expected = list(expected or [])
    ocr_ok = isinstance(ocr_result, dict) and ocr_result.get("status") == "ok"
    if ocr_ok:
        results = [_verdict(lit, ocr_result, accent_sensitive) for lit in expected]
    else:
        results = [{"literal": lit, "verdict": "not_verified", "ratio": None} for lit in expected]
    counts = {v: sum(1 for r in results if r["verdict"] == v) for v in ("match", "near", "missing", "not_verified")}
    nv = counts["not_verified"]
    return {
        "results": results,
        "verified": bool(results) and nv == 0,
        "all_match": None if (nv or not results) else counts["match"] == len(results),
        "not_verified": nv,
        "counts": counts,
        "ocr_status": ocr_result.get("status") if isinstance(ocr_result, dict) else None,
        "limits": list(LIMITS),
    }
