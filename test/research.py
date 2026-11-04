#!/usr/bin/env python3
"""Pesquisa de marca na web com a ferramenta de busca da OpenAI (Responses API). Só stdlib.

Por que existe: o ChatGPT, ao receber "crie um banner da CVC com o Rodrigo Faro", pesquisa a marca (slogan, cores, ofertas
vigentes, logo) antes de desenhar; o nosso app inventava. Aqui a pesquisa vira um passo do pipeline, com fontes citadas, e o
resultado entra no briefing como fatos (e só eles: o que a pesquisa não achou fica `null`, nunca inventado).

  brand_research(post, query, model) -> (brief: dict, sources: [{"url","title"}])
  find_logo_url(html, base_url)      -> melhor URL candidata de logo/ícone da página oficial

O `post` é `ui.openai_post(path, payload, timeout)`. Se a conta/modelo não aceitar a ferramenta de busca, levanta erro e o
chamador segue sem pesquisa, avisando (nunca finge que pesquisou).

Uso: python research.py --self-test
"""
import json, re, sys, urllib.parse

RESEARCH_SYSTEM = (
    "Você é pesquisador de marca de uma agência de design. Use a busca na web (fontes oficiais primeiro: site da marca, páginas de "
    "campanha, perfis oficiais). Pesquise o que o pedido menciona (marca, campanha, produto) e devolva SOMENTE JSON: "
    '{"marca":"...","site_oficial":"https://..."|null,"slogan":"..."|null,"cores":[{"nome":"amarelo","hex":"#RRGGBB"|null}],'
    '"tom":"..."|null,"ofertas_vigentes":[{"texto":"...","fonte":"https://...","data":"..."|null}],'
    '"logo_url":"https://...imagem do logo oficial (png, jpg ou webp)"|null,"formatos_comuns":["..."],"avisos":["..."]}. '
    "REGRAS: não invente; use null (ou lista vazia) quando não achar. Ofertas e condições só com a fonte e a data; não afirme preço, "
    "prazo ou parcelamento que não esteja na fonte. Hex só se a fonte trouxer; senão null. Não descreva o rosto de pessoas."
)


def _text_and_sources(resp):
    text, sources = [], []
    if isinstance(resp.get("output_text"), str):
        text.append(resp["output_text"])
    for item in resp.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content", []) or []:
            if part.get("type") == "output_text":
                if not isinstance(resp.get("output_text"), str):
                    text.append(part.get("text", ""))
                for a in part.get("annotations", []) or []:
                    if a.get("type") == "url_citation" and a.get("url"):
                        sources.append({"url": a["url"], "title": str(a.get("title", ""))[:120]})
    seen, uniq = set(), []
    for s in sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            uniq.append(s)
    return "\n".join(text), uniq


def parse_brief(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("a pesquisa não devolveu JSON")
    d = json.loads(m.group(0))
    if not isinstance(d, dict):
        raise ValueError("pesquisa inválida")
    d.setdefault("ofertas_vigentes", [])
    d.setdefault("cores", [])
    return d


def brand_research(post, query, model, timeout=150):
    payload = {"model": model, "tools": [{"type": "web_search"}],
               "input": [{"role": "system", "content": RESEARCH_SYSTEM}, {"role": "user", "content": f"Pesquise para um banner publicitário: {query}"}]}
    resp = post("/responses", payload, timeout)
    text, sources = _text_and_sources(resp)
    brief = parse_brief(text)
    for item in resp.get("output", []) or []:  # fontes consultadas pela busca, quando o modelo não anota citações no texto
        for s in ((item.get("action") or {}).get("sources") or []) if item.get("type") == "web_search_call" else []:
            if isinstance(s, dict) and str(s.get("url", "")).startswith("http"):
                sources.append({"url": s["url"], "title": str(s.get("title", ""))[:120]})
    for o in brief.get("ofertas_vigentes", []):  # a fonte que o próprio resumo cita por oferta também conta
        if isinstance(o, dict) and str(o.get("fonte", "")).startswith("http"):
            sources.append({"url": o["fonte"], "title": ""})
    seen, uniq = set(), []
    for s in sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            uniq.append(s)
    return brief, uniq


def brief_text(brief, sources):
    """Bloco para o designer: só fatos pesquisados, com fonte."""
    L = ["Pesquisa na web já feita (use ESTES fatos; o que está null não existe: não invente slogan, oferta, cor ou condição):"]
    L.append(f"- Marca: {brief.get('marca')} | site oficial: {brief.get('site_oficial')} | slogan: {brief.get('slogan')} | tom: {brief.get('tom')}")
    cores = ", ".join(f"{c.get('nome')} {c.get('hex') or '(hex não encontrado)'}" for c in brief.get("cores", []) if isinstance(c, dict))
    L.append(f"- Cores da marca: {cores or 'não encontradas'}")
    for o in brief.get("ofertas_vigentes", [])[:4]:
        if isinstance(o, dict):
            L.append(f"- Oferta vigente: «{o.get('texto')}» (fonte {o.get('fonte')}, data {o.get('data')})")
    if not brief.get("ofertas_vigentes"):
        L.append("- Ofertas vigentes: nenhuma confirmada pela pesquisa (não invente número, preço, prazo ou parcelamento)")
    L.append("- Fontes: " + (", ".join(s["url"] for s in sources[:5]) or "nenhuma citada"))
    return "\n".join(L)


def find_logo_url(html, base_url):
    """Melhor candidata de logo na página oficial: <img> com 'logo', apple-touch-icon, og:image (nesta ordem)."""
    cands = []
    for m in re.finditer(r"<img\b[^>]*>", html, re.I):
        tag = m.group(0)
        src = re.search(r'\bsrc=["\']([^"\']+)["\']', tag, re.I)
        if src and re.search(r"logo", tag, re.I) and not src.group(1).lower().endswith(".svg"):
            cands.append(src.group(1))
    for m in re.finditer(r"<link\b[^>]*>", html, re.I):
        tag = m.group(0)
        if re.search(r'rel=["\'][^"\']*apple-touch-icon', tag, re.I):
            h = re.search(r'\bhref=["\']([^"\']+)["\']', tag, re.I)
            if h:
                cands.append(h.group(1))
    for m in re.finditer(r"<meta\b[^>]*>", html, re.I):
        tag = m.group(0)
        if re.search(r'(property|name)=["\'](og|twitter):image', tag, re.I):
            c = re.search(r'\bcontent=["\']([^"\']+)["\']', tag, re.I)
            if c:
                cands.append(c.group(1))
    for c in cands:
        u = urllib.parse.urljoin(base_url, c.strip())
        if urllib.parse.urlparse(u).scheme in ("http", "https"):
            return u
    return None


def self_test():
    resp = {"output": [{"type": "web_search_call"}, {"type": "message", "content": [{"type": "output_text", "text": 'ok {"marca":"X","slogan":null,"ofertas_vigentes":[{"texto":"10x","fonte":"https://a.com","data":"2026-11"}]} fim',
            "annotations": [{"type": "url_citation", "url": "https://a.com", "title": "A"}, {"type": "url_citation", "url": "https://a.com", "title": "A"}, {"type": "x"}]}]}]}
    brief, src = brand_research(lambda path, payload, timeout: resp, "marca X", "m")
    assert brief["marca"] == "X" and brief["slogan"] is None and brief["cores"] == [] and src == [{"url": "https://a.com", "title": "A"}], (brief, src)
    bt = brief_text(brief, src)
    assert "10x" in bt and "não invente" in bt and "https://a.com" in bt
    assert "nenhuma confirmada" in brief_text({"marca": "Y", "ofertas_vigentes": []}, [])
    try:
        parse_brief("sem json aqui")
        raise AssertionError("deveria falhar")
    except ValueError:
        pass
    html = '<head><meta property="og:image" content="/social.jpg"><link rel="apple-touch-icon" href="/icon.png"></head><img class="x" src="/a.svg"><img alt="Logo CVC" src="/img/logo.png">'
    assert find_logo_url(html, "https://www.site.com/p") == "https://www.site.com/img/logo.png"
    assert find_logo_url('<link rel="apple-touch-icon" href="/i.png"><meta property="og:image" content="/s.jpg">', "https://s.com/") == "https://s.com/i.png"
    assert find_logo_url('<meta name="twitter:image" content="/t.jpg">', "https://s.com/") == "https://s.com/t.jpg"
    assert find_logo_url("<p>nada</p>", "https://s.com/") is None
    print("research self-test ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(__doc__)
