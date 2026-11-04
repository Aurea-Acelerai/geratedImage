#!/usr/bin/env python3
"""Os 12 gates de QA binários da fonte 2 (docs/fontes/02-design-visual-direcao-arte.md, seção 8) sobre a ESPECIFICAÇÃO
de uma peça (seção 7.1). Só stdlib. Um agente (ou o compose_text_overlay, quando existir) emite a especificação; este
módulo prova o que o código consegue provar e marca o resto como NAO_VERIFICAVEL, para o critic visual ou o humano.

Resultado de cada gate: PASSA | FALHA | NAO_VERIFICAVEL (código não alcança: precisa de pixels, de visão ou de decisão humana).
Veredito (regra da fonte): uma falha = REVISAR; duas falhas na mesma dimensão = REFAZER.

Esquema da especificação (todos os campos opcionais; o que faltar vira FALHA ou NAO_VERIFICAVEL conforme o gate):
{
  "canvas": [1080, 1920],
  "focal_point": "o frasco em primeiro plano", "focal_elements": 1,
  "typography": {"families": ["Inter"], "levels": [{"role": "headline|support|body|cta|legal", "size_px": 108}]},
  "contrast_pairs": [{"label": "titulo", "fg": "#F5F7FA", "bg": "#0B0D10", "size_px": 108, "bold": false}],
  "background_worst": {"fg": "#F5F7FA", "bgs": ["#1A1C20", "#2B2E34"], "size_px": 32},
  "text_boxes": [{"role": "headline", "box": [65, 300, 1015, 600]}],
  "ctas": [{"text": "Garanta 20% off hoje", "box": [65, 900, 1015, 1050], "fg": "#0B0D10", "bg": "#F2A541"}],
  "text_blocks": [["Garanta 20% off", "em halteres"]],
  "spacing_px": [8, 16, 24, 48],
  "transparency": {"blur": false, "scrim_opacity": 0.0, "fallback_opaque": true},
  "brand": {"palette": ["#0B0D10", "#F2A541"], "colors_used": ["#0B0D10", "#F2A541"], "anchors_applied": true, "master_editable": true}
}

Uso: python qa_gates.py --self-test
     python qa_gates.py spec.json
"""
import json, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import checks  # noqa: E402

SPACING_SCALE = {4, 8, 12, 16, 24, 32, 48, 64}
SCALE_RATIOS = (1.25, 1.333, 1.5)
GENERIC_CTA = ("clique aqui", "saiba mais", "confira", "clique", "veja mais", "leia mais", "acesse", "click here", "learn more")
PHONE_W = 390
DIMENSAO = {1: "hierarquia", 2: "hierarquia", 3: "legibilidade", 4: "legibilidade", 5: "legibilidade", 11: "legibilidade",
            6: "formato", 7: "cta", 8: "sistema", 13: "sistema", 9: "craft", 10: "craft", 12: "marca"}
NOMES = {1: "Ponto focal único", 2: "Hierarquia (3 níveis, título >= 2,5x o corpo)", 3: "Contraste do texto", 4: "Contraste no pior caso",
         5: "Legibilidade a 120 px", 6: "Safe zone", 7: "CTA", 8: "Tipografia", 9: "Luz", 10: "Fallback de transparência",
         11: "Densidade", 12: "Marca", 13: "Escala de espaçamento (regra 11)"}


def _r(gate, res, ev):
    return {"gate": gate, "nome": NOMES[gate], "dimensao": DIMENSAO.get(gate, "craft"), "resultado": res, "evidencia": ev}


def _sizes(spec):
    return [(l.get("role"), float(l["size_px"])) for l in (spec.get("typography") or {}).get("levels", []) if "size_px" in l]


def scale_coherent(sizes, tol=0.06):
    """Tamanhos pertencem a uma escala modular (razão 1,25 / 1,333 / 1,5) a partir do menor, com tolerância."""
    s = sorted(set(sizes))
    if len(s) < 2:
        return True
    base = s[0]
    for r in SCALE_RATIOS:
        ok = True
        for v in s:
            k = round(__import__("math").log(v / base, r))
            ok &= abs(v - base * r ** k) / v <= tol
        if ok:
            return True
    return False


def _screen_pt(spec, px):
    """px no canvas -> pt na tela do celular (largura de referência 390 pt)."""
    cw = (spec.get("canvas") or [0])[0]
    return px * PHONE_W / cw if cw else px * 0.75


def gate1(spec):
    if not spec.get("focal_point"):
        return _r(1, "FALHA", "ponto focal não declarado (declare antes de desenhar)")
    if spec.get("focal_elements", 1) != 1:
        return _r(1, "FALHA", f"{spec['focal_elements']} elementos disputam o foco; subordine por escala")
    sz = _sizes(spec)
    if sz and max(sz, key=lambda x: x[1])[0] == "headline":
        return _r(1, "PASSA", "declarado e o título é o maior elemento de texto (domínio visual: confirmar na revisão)")
    return _r(1, "NAO_VERIFICAVEL", "declarado; se ele domina por escala ou contraste só a revisão visual confirma")


def gate2(spec):
    sz = _sizes(spec)
    by = {}
    for role, px in sz:
        by.setdefault(role, px)
    if len(set(px for _, px in sz)) < 3:
        return _r(2, "FALHA", f"menos de 3 níveis de tamanho ({sorted(set(px for _, px in sz))})")
    if "headline" not in by or "body" not in by:
        return _r(2, "FALHA", "faltam níveis 'headline' e 'body' na tipografia")
    ratio = by["headline"] / by["body"]
    if ratio < 2.5:
        return _r(2, "FALHA", f"título/corpo = {ratio:.2f}x (< 2,5x)")
    if "support" in by and by["headline"] / by["support"] < 1.5:
        return _r(2, "FALHA", f"título/apoio = {by['headline'] / by['support']:.2f}x (< 1,5x)")
    return _r(2, "PASSA", f"3+ níveis, título/corpo = {ratio:.2f}x")


def gate3(spec):
    pairs = spec.get("contrast_pairs") or []
    if not pairs:
        return _r(3, "NAO_VERIFICAVEL", "informe contrast_pairs (cor do texto, cor do fundo, tamanho)")
    bad = []
    for p in pairs:
        pt = _screen_pt(spec, p["size_px"]) if "size_px" in p else 12
        ratio, passed, need = checks.contrast_ok(p["fg"], p["bg"], pt, p.get("bold", False))
        if not passed:
            bad.append(f"{p.get('label', p['fg'])}: {ratio}:1 < {need}:1")
    return _r(3, "FALHA", "; ".join(bad)) if bad else _r(3, "PASSA", f"{len(pairs)} par(es) >= mínimo")


def gate4(spec):
    w = spec.get("background_worst")
    if not w:
        return _r(4, "NAO_VERIFICAVEL", "precisa dos pixels do fundo sob o texto: informe background_worst (os pontos mais claro e mais escuro)")
    pt = _screen_pt(spec, w["size_px"]) if "size_px" in w else 12
    bad = []
    for bg in w["bgs"]:
        ratio, passed, need = checks.contrast_ok(w["fg"], bg, pt, w.get("bold", False))
        if not passed:
            bad.append(f"{bg}: {ratio}:1 < {need}:1")
    return _r(4, "FALHA", "pior caso reprova: " + "; ".join(bad)) if bad else _r(4, "PASSA", "todos os extremos do fundo passam")


def gate5(spec):
    cw = (spec.get("canvas") or [0])[0]
    head = next((px for role, px in _sizes(spec) if role == "headline"), None)
    if not cw or head is None:
        return _r(5, "NAO_VERIFICAVEL", "informe canvas e o tamanho do título")
    thumb = head * 120 / cw
    if thumb < 6:
        return _r(5, "FALHA", f"título a 120 px de largura teria {thumb:.1f} px de altura de fonte (< 6 px, heurística)")
    return _r(5, "PASSA", f"título a 120 px ≈ {thumb:.1f} px (heurística; confirmar com a revisão visual da miniatura)")


def gate6(spec):
    cw, ch = (spec.get("canvas") or [0, 0])[:2]
    boxes = [(t.get("role", "texto"), t["box"]) for t in spec.get("text_boxes", [])] + [("cta", c["box"]) for c in spec.get("ctas", []) if "box" in c]
    if not cw or not boxes:
        return _r(6, "NAO_VERIFICAVEL", "informe canvas e as caixas de texto/CTA")
    problems, norule = [], False
    for role, box in boxes:
        ok, why = checks.safe_zone_ok(box, cw, ch)
        norule |= why.startswith("sem regra")
        if not ok:
            problems.append(f"{role}: {why}")
    if problems:
        return _r(6, "FALHA", "; ".join(problems) + " (percentuais 14/35/6 a confirmar com a Meta)")
    return _r(6, "NAO_VERIFICAVEL" if norule else "PASSA", "sem regra para esta proporção" if norule else "dentro da zona segura 9:16 (14/35/6, a confirmar)")


def gate7(spec):
    ctas = spec.get("ctas") or []
    if not ctas:
        return _r(7, "NAO_VERIFICAVEL", "peça sem CTA declarado")
    if len(ctas) != 1:
        return _r(7, "FALHA", f"{len(ctas)} CTAs (deve haver um só)")
    c = ctas[0]
    txt = re.sub(r"\s+", " ", c.get("text", "").strip().lower())
    if any(txt == g or txt.startswith(g + " ") or txt.endswith(" " + g) for g in GENERIC_CTA) or len(txt.split()) < 2:
        return _r(7, "FALHA", f"CTA genérico ou sem benefício: '{c.get('text')}' (use verbo + benefício)")
    if "fg" in c and "bg" in c and checks.contrast_ratio(c["fg"], c["bg"]) < 4.5:
        return _r(7, "FALHA", f"CTA com contraste {checks.contrast_ratio(c['fg'], c['bg'])}:1 (< 4,5:1)")
    return _r(7, "PASSA", f"um CTA, não genérico: '{c.get('text')}' (se descreve o benefício: confirmar na revisão)")


def gate8(spec):
    t = spec.get("typography") or {}
    fam = t.get("families", [])
    if len(fam) > 2:
        return _r(8, "FALHA", f"{len(fam)} famílias ({', '.join(fam)}); máximo 2")
    sizes = [px for _, px in _sizes(spec)]
    if sizes and not scale_coherent(sizes):
        return _r(8, "FALHA", f"tamanhos {sorted(set(sizes))} fora de uma escala modular (1,25 / 1,333 / 1,5)")
    if not fam and not sizes:
        return _r(8, "NAO_VERIFICAVEL", "informe famílias e tamanhos")
    return _r(8, "PASSA", f"{len(fam)} família(s), escala coerente")


def gate9(spec):
    return _r(9, "NAO_VERIFICAVEL", "uma única fonte de luz coerente: só a revisão visual (critic) ou o humano julga")


def gate10(spec):
    tr = spec.get("transparency")
    if tr is None:
        return _r(10, "NAO_VERIFICAVEL", "informe transparency (se usa blur/vidro)")
    if not tr.get("blur"):
        return _r(10, "PASSA", "não usa blur nem transparência")
    probs = []
    if tr.get("scrim_opacity", 0) < 0.35:
        probs.append(f"scrim {tr.get('scrim_opacity', 0)} < 0,35")
    if not tr.get("fallback_opaque"):
        probs.append("sem fallback opaco")
    return _r(10, "FALHA", "; ".join(probs)) if probs else _r(10, "PASSA", "scrim >= 0,35 e fallback opaco")


def gate11(spec):
    blocks = spec.get("text_blocks")
    if not blocks:
        return _r(11, "NAO_VERIFICAVEL", "informe text_blocks (linhas de cada bloco)")
    bad = []
    for i, b in enumerate(blocks):
        if len(b) > 3:
            bad.append(f"bloco {i + 1}: {len(b)} linhas (> 3)")
        for ln in b:
            n = len(ln.split())
            if n > 7:
                bad.append(f"bloco {i + 1}: {n} palavras na linha '{ln[:30]}…' (> 7)")
    return _r(11, "FALHA", "; ".join(bad)) if bad else _r(11, "PASSA", "<= 3 linhas e <= 7 palavras por linha")


def _neutral(h):
    r, g, b = checks.hex_rgb(h)
    return max(r, g, b) - min(r, g, b) <= 12


def gate12(spec):
    br = spec.get("brand")
    if not br:
        return _r(12, "NAO_VERIFICAVEL", "informe brand (paleta, cores usadas, âncoras, master editável)")
    pal = {c.lower() for c in br.get("palette", [])}
    out = [c for c in br.get("colors_used", []) if c.lower() not in pal and not _neutral(c)]
    probs = []
    if out:
        probs.append("cores fora da paleta: " + ", ".join(out))
    if not br.get("anchors_applied"):
        probs.append("âncoras de marca (logo, tipo, espaçamento) não aplicadas")
    if not br.get("master_editable"):
        probs.append("sem master editável")
    return _r(12, "FALHA", "; ".join(probs)) if probs else _r(12, "PASSA", "paleta, âncoras e master ok (neutros permitidos)")


def gate13(spec):
    sp = spec.get("spacing_px")
    if not sp:
        return _r(13, "NAO_VERIFICAVEL", "informe spacing_px")
    bad = sorted({v for v in sp if v not in SPACING_SCALE})
    return _r(13, "FALHA", f"valores fora da escala 4/8/12/16/24/32/48/64: {bad}") if bad else _r(13, "PASSA", "todos na escala")


GATES = (gate1, gate2, gate3, gate4, gate5, gate6, gate7, gate8, gate9, gate10, gate11, gate12, gate13)


def validate_spec(spec):
    return [g(spec) for g in GATES]


def verdict(results):
    fails = [r for r in results if r["resultado"] == "FALHA"]
    by_dim = {}
    for r in fails:
        by_dim.setdefault(r["dimensao"], []).append(r["gate"])
    if any(len(v) >= 2 for v in by_dim.values()):
        return "REFAZER", by_dim
    if fails:
        return "REVISAR", by_dim
    if any(r["resultado"] == "NAO_VERIFICAVEL" for r in results):
        return "PENDENTE_REVISAO_VISUAL", {}
    return "APROVADO", {}


GOOD = {
    "canvas": [1080, 1920], "focal_point": "o frasco em primeiro plano", "focal_elements": 1,
    "typography": {"families": ["Inter"], "levels": [{"role": "body", "size_px": 32}, {"role": "support", "size_px": 48}, {"role": "headline", "size_px": 108}]},
    "contrast_pairs": [{"label": "titulo", "fg": "#F5F7FA", "bg": "#0B0D10", "size_px": 108}],
    "background_worst": {"fg": "#F5F7FA", "bgs": ["#1A1C20", "#2B2E34"], "size_px": 32},
    "text_boxes": [{"role": "headline", "box": [65, 300, 1015, 600]}],
    "ctas": [{"text": "Garanta 20% off hoje", "box": [65, 900, 1015, 1050], "fg": "#0B0D10", "bg": "#F2A541"}],
    "text_blocks": [["Garanta 20% off", "em halteres"]], "spacing_px": [8, 16, 24, 48],
    "transparency": {"blur": False, "scrim_opacity": 0.0, "fallback_opaque": True},
    "brand": {"palette": ["#0B0D10", "#F2A541", "#F5F7FA"], "colors_used": ["#0B0D10", "#F2A541", "#F5F7FA"], "anchors_applied": True, "master_editable": True},
}


def self_test():
    res = {r["gate"]: r for r in validate_spec(GOOD)}
    assert all(res[g]["resultado"] == "PASSA" for g in (1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13)), {g: r["resultado"] for g, r in res.items()}
    assert res[9]["resultado"] == "NAO_VERIFICAVEL"
    assert verdict(list(res.values()))[0] == "PENDENTE_REVISAO_VISUAL"
    # peça ruim: cada defeito reprova o gate certo
    bad = json.loads(json.dumps(GOOD))
    bad["typography"] = {"families": ["A", "B", "C"], "levels": [{"role": "body", "size_px": 40}, {"role": "support", "size_px": 40}, {"role": "headline", "size_px": 44}]}
    bad["contrast_pairs"] = [{"label": "legal", "fg": "#777777", "bg": "#888888", "size_px": 32}]
    bad["background_worst"] = {"fg": "#F5F7FA", "bgs": ["#FFFFFF"], "size_px": 32}
    bad["text_boxes"] = [{"role": "headline", "box": [65, 100, 1015, 400]}]
    bad["ctas"] = [{"text": "clique aqui", "box": [65, 900, 1015, 1050]}]
    bad["text_blocks"] = [["uma linha com muitas palavras demais para um anuncio ok", "b", "c", "d"]]
    bad["spacing_px"] = [8, 10, 24]
    bad["transparency"] = {"blur": True, "scrim_opacity": 0.1, "fallback_opaque": False}
    bad["brand"] = {"palette": ["#0B0D10"], "colors_used": ["#0B0D10", "#FF00AA"], "anchors_applied": False, "master_editable": False}
    r = {x["gate"]: x for x in validate_spec(bad)}
    for g in (2, 3, 4, 6, 7, 8, 10, 11, 12, 13):
        assert r[g]["resultado"] == "FALHA", (g, r[g])
    v, dims = verdict(list(r.values()))
    assert v == "REFAZER" and len(dims["legibilidade"]) >= 2, (v, dims)
    # uma falha só = REVISAR
    one = json.loads(json.dumps(GOOD)); one["spacing_px"] = [8, 10]
    assert verdict(validate_spec(one))[0] == "REVISAR"
    # campos ausentes não viram aprovação: o código diz que não consegue verificar
    empty = {x["gate"]: x["resultado"] for x in validate_spec({})}
    assert empty[1] == "FALHA" and empty[2] == "FALHA" and all(empty[g] == "NAO_VERIFICAVEL" for g in (3, 4, 6, 7, 9, 12, 13))
    assert verdict(validate_spec({}))[0] in ("REVISAR", "REFAZER")
    # 4:5 não tem regra de safe zone: não aprova nem reprova
    s45 = json.loads(json.dumps(GOOD)); s45["canvas"] = [1080, 1350]
    assert {x["gate"]: x["resultado"] for x in validate_spec(s45)}[6] == "NAO_VERIFICAVEL"
    # escala modular
    assert scale_coherent([32, 48, 108]) and not scale_coherent([32, 41, 108])
    # CTA: um genérico e um bom
    for txt, expect in (("Saiba mais", "FALHA"), ("Confira", "FALHA"), ("Ver", "FALHA"), ("Receba em casa hoje", "PASSA")):
        g = json.loads(json.dumps(GOOD)); g["ctas"] = [{"text": txt}]
        assert gate7(g)["resultado"] == expect, txt
    print("qa_gates self-test ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    elif len(sys.argv) > 1:
        out = validate_spec(json.load(open(sys.argv[1], encoding="utf-8")))
        for x in out:
            print(f"{x['gate']:>2} {x['resultado']:<16} {x['nome']}: {x['evidencia']}")
        print("veredito:", verdict(out))
    else:
        print(__doc__)
