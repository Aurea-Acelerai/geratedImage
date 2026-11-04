#!/usr/bin/env python3
"""Testes de ocr.py. Sem rede, sem custo e sem tesseract: o backend é injetado ou o subprocess é substituído.

  python3 -I test/test_ocr.py        (da raiz do repositório)
  cd test && python3 -I test_ocr.py

Cada caso afirma comportamento observável (veredito, status, o comando que seria executado), não que um mock foi chamado.
"""
import os, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import ocr  # noqa: E402

N = {"ok": 0}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def ok(cond, msg):
    print(("OK   " if cond else "FALHA"), msg)
    if not cond:
        sys.exit(1)
    N["ok"] += 1


def words(*pairs):
    return [{"text": t, "conf": c} for t, c in pairs]


def fake_ocr(text, ws=None, status="ok"):
    """Resultado de read_text já pronto (o que um backend legítimo devolveria)."""
    ws = ws if ws is not None else [{"text": t, "conf": 95.0} for t in text.split()]
    return {"status": status, "text": text, "words": ws, "mean_conf": 95.0, "limits": list(ocr.LIMITS)}


def verdicts(expected, res, **kw):
    return [r["verdict"] for r in ocr.text_fidelity(expected, res, **kw)["results"]]


class patched:
    """Troca atributos de módulos por um instante (e devolve ao sair)."""

    def __init__(self, *triples):
        self.triples = triples

    def __enter__(self):
        self.old = [(o, n, getattr(o, n)) for o, n, _ in self.triples]
        for o, n, v in self.triples:
            setattr(o, n, v)

    def __exit__(self, *exc):
        for o, n, v in self.old:
            setattr(o, n, v)


def test_available_and_unavailable():
    with patched((ocr.shutil, "which", lambda name: None)):
        ok(ocr.available() is False, "available() é False sem o executável tesseract")
        r = ocr.read_text(PNG)
    ok(r["status"] == "unavailable", "sem tesseract e sem backend: status unavailable")
    ok(r["text"] == "" and r["words"] == [] and r["mean_conf"] is None, "unavailable não inventa texto, palavras nem confiança")
    ok(r["limits"] and any("auxiliar" in x for x in r["limits"]), "unavailable também devolve os limites")
    with patched((ocr.shutil, "which", lambda name: "/usr/bin/tesseract" if name == "tesseract" else None)):
        ok(ocr.available() is True, "available() é True quando o executável existe")
    seen = []
    with patched((ocr.shutil, "which", lambda name: None)):
        r = ocr.read_text(PNG, backend=lambda b, lang: seen.append(lang) or {"text": "Oi", "words": words(("Oi", 90))})
    ok(r["status"] == "ok" and seen == ["por"], "backend injetado funciona sem tesseract e recebe o idioma padrão por")


def test_read_text_backend():
    seen = {}

    def backend(b, lang):
        seen["bytes"], seen["lang"] = b, lang
        return {"text": "Olá mundo", "words": words(("Olá", 90), ("mundo", 70))}

    r = ocr.read_text(PNG, backend=backend, lang="eng")
    ok(r["status"] == "ok" and r["text"] == "Olá mundo" and r["mean_conf"] == 80.0, "ok: texto e média de confiança calculada das palavras")
    ok(seen["lang"] == "eng" and seen["bytes"] == PNG, "o backend recebe os bytes e o idioma pedidos")
    ok(len(r["limits"]) >= 5, "limites vão no resultado")
    r = ocr.read_text(PNG, backend=lambda b, l: {"text": "", "words": []})
    ok(r["status"] == "ok" and r["text"] == "" and r["mean_conf"] is None, "OCR que não leu nada é ok com texto vazio (sem média inventada)")
    r = ocr.read_text(PNG, backend=lambda b, l: 1 / 0)
    ok(r["status"] == "error" and r["text"] == "" and "ZeroDivisionError" in r["reason"], "exceção do backend vira status error, sem texto")
    r = ocr.read_text(PNG, backend=lambda b, l: "texto solto")
    ok(r["status"] == "error", "backend fora do contrato (não é dict) vira error")
    r = ocr.read_text(PNG, backend=lambda b, l: {"text": "x", "words": [{"text": "x"}]})
    ok(r["status"] == "error", "words sem conf vira error (não assume confiança)")
    ok(ocr.read_text(b"", backend=backend)["status"] == "error", "imagem vazia: error")
    ok(ocr.read_text("não sou bytes", backend=backend)["status"] == "error", "entrada que não é bytes: error")


def test_default_backend_subprocess():
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "1\t1\t0\t0\t0\t0\t0\t0\t100\t50\t-1\t\n"
           "4\t1\t1\t1\t1\t0\t0\t0\t90\t20\t-1\t\n"
           "5\t1\t1\t1\t1\t1\t0\t0\t40\t20\t91.5\tPromoção\n"
           "5\t1\t1\t1\t1\t2\t45\t0\t40\t20\t88\tde\n"
           "5\t1\t1\t1\t2\t1\t0\t30\t40\t20\t42.0\tVerão\n"
           "5\t1\t1\t1\t2\t2\t45\t30\t40\t20\t-1\t \n")
    cap = {}

    def run_ok(cmd, **kw):
        cap["cmd"], cap["kw"] = cmd, kw
        cap["existed"] = os.path.exists(cmd[1])
        cap["tmpdir"] = os.path.dirname(cmd[1])
        cap["content"] = open(cmd[1], "rb").read()
        return subprocess.CompletedProcess(cmd, 0, tsv.encode("utf-8"), b"")

    with patched((ocr.shutil, "which", lambda n: "/x/tesseract"), (ocr.subprocess, "run", run_ok)):
        r = ocr.read_text(PNG, lang="por", timeout=7)
    ok(r["status"] == "ok" and r["text"] == "Promoção de\nVerão", "TSV do tesseract vira texto por linhas (linhas sem palavra e conf -1 ignoradas)")
    ok([w["text"] for w in r["words"]] == ["Promoção", "de", "Verão"] and r["words"][2]["conf"] == 42.0, "palavras com confiança preservada, inclusive a baixa")
    ok(r["mean_conf"] == round((91.5 + 88 + 42.0) / 3, 2), "média de confiança das palavras")
    cmd = cap["cmd"]
    ok(isinstance(cmd, list) and cmd[0] == "tesseract" and cmd[2:] == ["stdout", "-l", "por", "tsv"], "comando é lista de argumentos: tesseract <arquivo> stdout -l por tsv")
    ok(not cap["kw"].get("shell"), "sem shell")
    ok(cap["kw"].get("timeout") == 7, "o timeout pedido chega ao subprocess")
    tmp_root = os.path.realpath(tempfile.gettempdir())
    ok(cap["existed"] and cap["content"] == PNG and os.path.realpath(cap["tmpdir"]).startswith(tmp_root + os.sep),
       "a imagem estava num arquivo dentro de uma pasta temporária, com o conteúdo exato, na hora da chamada")
    ok(not os.path.exists(cap["tmpdir"]), "pasta temporária removida depois")

    def run_fail(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, b"", b"Failed loading language 'xyz'")

    with patched((ocr.shutil, "which", lambda n: "/x/tesseract"), (ocr.subprocess, "run", run_fail)):
        r = ocr.read_text(PNG, lang="xyz")
    ok(r["status"] == "error" and "Failed loading language" in r["reason"] and r["text"] == "", "código de saída diferente de zero: error com a causa, sem texto")

    def run_timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    with patched((ocr.shutil, "which", lambda n: "/x/tesseract"), (ocr.subprocess, "run", run_timeout)):
        r = ocr.read_text(PNG, timeout=3)
    ok(r["status"] == "error" and "timeout" in r["reason"] and "3" in r["reason"], "timeout vira error explicando o limite")

    calls = []

    def run_spy(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    with patched((ocr.shutil, "which", lambda n: "/x/tesseract"), (ocr.subprocess, "run", run_spy)):
        r1 = ocr.read_text(PNG, lang="por; rm -rf /")
        r2 = ocr.read_text(PNG, lang="-psm")
        r3 = ocr.read_text(b"isto nao e imagem")
        r4 = ocr.read_text(PNG, lang="por+eng")
    ok(r1["status"] == "error" and r2["status"] == "error", "lang com metacaracteres ou começando com '-' é recusado")
    ok(r3["status"] == "error", "bytes que não são imagem são recusados antes de chamar o tesseract")
    ok(len(calls) == 1 and calls[0][4] == "por+eng", "só o pedido válido chegou ao subprocess (lang composto por+eng é aceito)")


def test_fidelity_without_ocr():
    for status in ("unavailable", "error"):
        res = {"status": status, "text": "", "words": [], "mean_conf": None, "limits": []}
        f = ocr.text_fidelity(["Promoção", "50% OFF"], res)
        ok([r["verdict"] for r in f["results"]] == ["not_verified"] * 2, f"OCR {status}: todos os literais ficam not_verified")
        ok(f["verified"] is False and f["all_match"] is None and f["not_verified"] == 2, f"OCR {status}: nunca aprova (all_match None) nem reprova")
        ok(all(r["ratio"] is None for r in f["results"]), f"OCR {status}: sem razão inventada")
    # mesmo que o resultado traga texto, status != ok não conta como evidência
    sneaky = {"status": "unavailable", "text": "Promoção", "words": words(("Promoção", 99))}
    ok(verdicts(["Promoção"], sneaky) == ["not_verified"], "texto presente com status unavailable não vira match")
    with patched((ocr.shutil, "which", lambda n: None)):
        f = ocr.text_fidelity(["Oferta"], ocr.read_text(PNG))
    ok(f["all_match"] is None and f["ocr_status"] == "unavailable", "fluxo completo sem tesseract: unavailable -> not_verified")


def test_fidelity_verdicts():
    ok(verdicts(["Promoção de Verão"], fake_ocr("PROMOÇÃO  de   verão")) == ["match"], "casefold e espaços não atrapalham o match")
    ok(verdicts(["Promoção"], fake_ocr("Promocao")) == ["near"], "Promoção vs Promocao é near, não match (acento conta)")
    f = ocr.text_fidelity(["Promoção"], fake_ocr("Promocao"))
    ok(0.75 <= f["results"][0]["ratio"] < 1.0 and f["all_match"] is False, "near tem razão entre 0,75 e 1 e não é all_match")
    ok(verdicts(["Promoção"], fake_ocr("Promocao"), accent_sensitive=False) == ["match"], "accent_sensitive=False aceita Promocao")
    ok(verdicts(["Promoção"], fake_ocr("Promoção")) == ["match"], "acento igual: match")
    ok(verdicts(["Oferta"], fake_ocr("completamente outra coisa aqui")) == ["missing"], "texto sem relação: missing")
    ok(verdicts(["50% OFF"], fake_ocr("S0% OFF")) == ["near"], "um caractere trocado pelo OCR: near")
    ok(verdicts(["50%"], fake_ocr("150% mais")) == ["near"], "literal só dentro de outra palavra (150%) não é match")
    f = ocr.text_fidelity(["50%"], fake_ocr("150% mais"))
    ok(f["results"][0]["ratio"] < 1.0, "e a razão não chega a 1,0 (reservado ao match)")
    ok(verdicts(["Oferta"], fake_ocr("Oferta!")) == ["match"], "pontuação colada não impede o match")
    ok(verdicts(["Oferta"], fake_ocr("")) == ["missing"], "OCR ok que não leu nada: missing (não aprova)")
    # confiança baixa
    low = fake_ocr("Promoção de Verão", words(("Promoção", 40), ("de", 95), ("Verão", 95)))
    ok(verdicts(["Promoção"], low) == ["near"], "palavra com confiança < 60 não conta como evidência de match")
    ok("confiança" in ocr.text_fidelity(["Promoção"], low)["results"][0]["note"], "e o motivo fica registrado")
    ok(verdicts(["Verão"], low) == ["match"], "palavras confiáveis do mesmo texto continuam match")
    edge = fake_ocr("Promoção de Verão", words(("Promoção", 59.9), ("de", 60), ("Verão", 60)))
    ok(verdicts(["Promoção", "de Verão"], edge) == ["near", "match"], "limite: 59,9 não vale, 60 vale")
    gap = fake_ocr("ver ABC mais", words(("ver", 95), ("ABC", 10), ("mais", 95)))
    ok(verdicts(["ver mais"], gap) != ["match"], "palavra de baixa confiança no meio não emenda duas palavras seguras num falso match")
    noconf = {"status": "ok", "text": "Oferta", "words": [], "mean_conf": None, "limits": []}
    ok(verdicts(["Oferta"], noconf) == ["near"], "OCR sem confiança por palavra: no máximo near")
    ok(verdicts(["Oferta"], fake_ocr("Oferta")) == ["match"], "com confiança alta: match")
    ok(verdicts([""], fake_ocr("x")) == ["not_verified"], "literal vazio não é verificável")
    ok(verdicts("Oferta", fake_ocr("Oferta")) == ["match"], "um literal em string simples também funciona")


def test_fidelity_aggregate():
    f = ocr.text_fidelity(["Oferta", "Verão"], fake_ocr("Oferta de Verão"))
    ok(f["verified"] is True and f["all_match"] is True and f["not_verified"] == 0 and f["counts"]["match"] == 2, "tudo match: verified e all_match True")
    f = ocr.text_fidelity(["Oferta", "Promocao"], fake_ocr("Oferta Promoção"))
    ok(f["verified"] is True and f["all_match"] is False, "algum near: verificado, mas all_match False")
    f = ocr.text_fidelity([], fake_ocr("Oferta"))
    ok(f["verified"] is False and f["all_match"] is None, "sem literais não há o que verificar: all_match None")
    f = ocr.text_fidelity(["Oferta", ""], fake_ocr("Oferta"))
    ok(f["not_verified"] == 1 and f["all_match"] is None, "um literal não verificável deixa all_match None mesmo com o outro em match")
    ok(f["limits"] and any("revisão humana" in x for x in f["limits"]), "limites também no resultado da fidelidade")
    ok(any("Dimensões válidas" in x for x in ocr.LIMITS), "limite documentado: dimensões válidas não provam fidelidade textual")
    doc = ocr.__doc__.lower()
    ok(all(x in doc for x in ("texto pequeno", "fontes decorativas", "baixo contraste", "texto curvo", "idiomas")), "limites documentados no módulo")


def test_distance():
    d = ocr.best_substring_distance
    ok(d("abc", "xxabcxx") == 0.0, "trecho exato em qualquer posição: distância 0")
    ok(d("abc", "xxabxx") == 1.0, "uma remoção: distância 1")
    ok(d("promoção", "xxpromocaoxx") == 1.0, "dois acentos errados = 2 x 0,5")
    ok(d("abc", "") == 3.0, "texto vazio: distância é o tamanho do literal")
    ok(d("a", "b") == 1.0, "troca de letra diferente custa 1")


def main():
    for fn in (test_available_and_unavailable, test_read_text_backend, test_default_backend_subprocess, test_fidelity_without_ocr,
               test_fidelity_verdicts, test_fidelity_aggregate, test_distance):
        print(f"== {fn.__name__}")
        fn()
    print(f"\nTUDO OK ({N['ok']} verificações)")


if __name__ == "__main__":
    main()
