#!/usr/bin/env python3
"""Checagens por código das regras de design (docs/08). Só stdlib.

Duas funções fazem as regras valerem em toda geração:
- design_fundamentals(): lê o bloco de regras de docs/08 e o injeta no system prompt do designer.
  Falha alto se o bloco sumir: o designer nunca roda sem as regras.
- apply(review, b64, size): confere o PNG por código e acrescenta vetos ao resultado do critic.

As demais funções (contraste, safe zone, mínimos de tipografia) são para o compose_text_overlay,
que ainda não existe: ele deve chamá-las antes de aceitar uma composição.

Uso: python checks.py --self-test
"""
import base64, pathlib, re, struct, sys

ROOT = pathlib.Path(__file__).resolve().parent
DOC_PATH = ROOT.parent / "docs" / "08-fundamentos-design.md"
START, END = "<!-- agent:start -->", "<!-- agent:end -->"

# Safe zone por proporção: (topo, base, lateral) em fração da altura/largura.
# 9:16 vem do documento-fonte e está marcado "a confirmar" em docs/08 (F2). Sem valor = sem checagem.
SAFE_ZONES = {"9:16": (0.14, 0.35, 0.06)}


def design_fundamentals():
    txt = DOC_PATH.read_text(encoding="utf-8")
    if START not in txt or END not in txt or txt.index(START) > txt.index(END):
        raise RuntimeError(f"{DOC_PATH.name}: marcadores {START} / {END} ausentes; o designer não roda sem as regras")
    block = txt[txt.index(START) + len(START):txt.index(END)].strip()
    if len(block) < 500:
        raise RuntimeError("bloco de regras de design vazio ou truncado")
    return block


# ---------- contraste (WCAG 2.x) ----------
def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hex_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def contrast_ratio(fg, bg):
    """fg e bg: (r,g,b) 0-255 ou '#rrggbb'."""
    f = hex_rgb(fg) if isinstance(fg, str) else fg
    b = hex_rgb(bg) if isinstance(bg, str) else bg
    hi, lo = sorted((luminance(f), luminance(b)), reverse=True)
    return round((hi + 0.05) / (lo + 0.05), 2)


def contrast_ok(fg, bg, size_pt, bold=False):
    """C1: >= 4,5:1; >= 3:1 se grande (>= 18pt ou >= 14pt negrito). Retorna (razão, aprovado, mínimo)."""
    large = size_pt >= 18 or (bold and size_pt >= 14)
    need = 3.0 if large else 4.5
    r = contrast_ratio(fg, bg)
    return r, r >= need, need


# ---------- safe zone ----------
def _ratio_key(w, h):
    from math import gcd
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


def safe_zone_ok(box, w, h):
    """F2: box=(x0,y0,x1,y1) em px. Retorna (ok, motivo). Proporção sem safe zone conhecida: (True, 'sem regra')."""
    sz = SAFE_ZONES.get(_ratio_key(w, h))
    if not sz:
        return True, "sem regra para esta proporção"
    top, bottom, side = sz
    x0, y0, x1, y1 = box
    if y0 < h * top:
        return False, f"invade o topo ({y0:.0f}px < {h * top:.0f}px)"
    if y1 > h * (1 - bottom):
        return False, f"invade a base ({y1:.0f}px > {h * (1 - bottom):.0f}px)"
    if x0 < w * side or x1 > w * (1 - side):
        return False, "invade a lateral"
    return True, "ok"


def type_min_ok(kind, px):
    """T5: corpo >= 16 px, headline >= 32 px."""
    need = {"body": 16, "headline": 32}[kind]
    return px >= need, need


# ---------- imagem ----------
def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def check_png(b64, size):
    """Dimensões do PNG contra o contêiner pedido ('1536x1024'). Retorna lista de problemas (vazia = ok)."""
    try:
        got = png_size(base64.b64decode(b64))
    except Exception:
        return ["imagem ilegível (base64 inválido)"]
    if got is None:
        return []  # não é PNG (ex.: jpeg ou mock): não dá para checar, não reprova
    m = re.fullmatch(r"(\d+)x(\d+)", size or "")
    if m and got != (int(m.group(1)), int(m.group(2))):
        return [f"dimensões {got[0]}x{got[1]} diferentes do pedido {size}"]
    return []


def apply(review, b64, size):
    """Acrescenta vetos por código ao review do critic. Nunca remove nada."""
    probs = check_png(b64, size)
    if probs:
        review.setdefault("veto", [])
        if "formato_incorreto" not in review["veto"]:
            review["veto"].append("formato_incorreto")
        review.setdefault("issues", []).extend(
            {"criterion": "format", "evidence": p, "severity": "alta"} for p in probs)
    return review


def self_test():
    # regras: carregam e trazem IDs
    f = design_fundamentals()
    assert "E1." in f and "H1." in f and "F2." in f and "Pendências" not in f
    # contraste: preto/branco = 21; cinza claro sobre branco reprova texto normal
    assert contrast_ratio("#000", "#fff") == 21.0
    assert contrast_ok("#777777", "#ffffff", 16)[1] is False
    assert contrast_ok("#777777", "#ffffff", 20)[1] is True  # grande exige só 3:1
    assert contrast_ok("#595959", "#ffffff", 12)[1] is True
    # safe zone 9:16 (1080x1920): topo 14% = 268px; base livre até 65% = 1248px
    assert safe_zone_ok((100, 300, 900, 1200), 1080, 1920)[0] is True
    assert safe_zone_ok((100, 100, 900, 400), 1080, 1920)[0] is False
    assert safe_zone_ok((100, 300, 900, 1500), 1080, 1920)[0] is False
    assert safe_zone_ok((0, 0, 10, 10), 1024, 1024)[1].startswith("sem regra")
    assert type_min_ok("headline", 28)[0] is False and type_min_ok("body", 16)[0] is True
    # PNG mínimo 2x1 e checagem de dimensões
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 2, 1) + b"\x08\x02\x00\x00\x00"
    b64 = base64.b64encode(png).decode()
    assert check_png(b64, "2x1") == [] and check_png(b64, "4x4") != []
    rv = apply({"scores": {}, "veto": []}, b64, "4x4")
    assert rv["veto"] == ["formato_incorreto"]
    assert apply({"scores": {}, "veto": []}, base64.b64encode(b"nao-e-png").decode(), "4x4")["veto"] == []
    print("checks self-test ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(__doc__)
