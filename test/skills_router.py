#!/usr/bin/env python3
"""Roteador das skills de design (skills/design-*/SKILL.md). Só stdlib.

Cada skill tem no frontmatter: `always` (sempre carregada), `triggers` (palavras do pedido) e `order`.
`select()` decide quais skills valem para o pedido; `render()` devolve o texto para o system prompt do
designer; `review_notes()` devolve as seções "Revisão (critic)" para o critic checar as mesmas regras.

A seleção é determinística (palavras-chave, tamanho, imagens de entrada), então roda offline e é testável.
Uma triagem por modelo pode complementar depois; ela nunca deve *remover* as skills `always`.

Uso: python skills_router.py --self-test
     python skills_router.py "banner de promoção para stories com a nossa logo"
"""
import pathlib, re, sys, unicodedata

ROOT = pathlib.Path(__file__).resolve().parent
SKILLS_DIR = ROOT.parent / "skills"
DOC_PATH = ROOT.parent / "docs" / "08-fundamentos-design.md"
ID_RE = re.compile(r"\b([EHCKTF]\d)\b")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _meta(block):
    meta = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            meta[k.strip()] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        elif v.lower() in ("true", "false"):
            meta[k.strip()] = v.lower() == "true"
        else:
            meta[k.strip()] = v
    return meta


def load_all():
    skills = {}
    for p in sorted(SKILLS_DIR.glob("design-*/SKILL.md")):
        m = re.match(r"---\n(.*?)\n---\n(.*)", p.read_text(encoding="utf-8"), re.S)
        if not m:
            raise RuntimeError(f"{p}: frontmatter ausente")
        meta, body = _meta(m.group(1)), m.group(2).strip()
        meta["name"] = meta.get("name") or p.parent.name
        meta["body"] = body
        meta["order"] = int(meta.get("order", 100))
        skills[meta["name"]] = meta
    if not skills:
        raise RuntimeError(f"nenhuma skill design-* em {SKILLS_DIR}")
    return skills


def select(request="", size=None, has_inputs=False):
    """Nomes das skills que valem para este pedido, na ordem de `order`."""
    text = norm(request)
    chosen = []
    for name, s in load_all().items():
        hit = s.get("always", False)
        if not hit:
            for t in s.get("triggers", []):
                t = norm(t)
                # palavra inteira para termos curtos (evita "ads" casar dentro de "cadastro"); trecho para os longos
                if (len(t) <= 4 and re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text)) or (len(t) > 4 and t in text):
                    hit = True
                    break
            if not hit and s["name"] == "design-formato-canal" and size and size != "1024x1024":
                hit = True  # formato não quadrado: o canal importa
            if not hit and s["name"] == "design-serie-marca" and has_inputs and re.search(r"\b(mesm[oa]|igual)\b", text):
                hit = True
        if hit:
            chosen.append(name)
    allk = load_all()
    return sorted(chosen, key=lambda n: allk[n]["order"])


def compact(body):
    """Versão para o designer: tira 'Por quê' e 'Verificar' (servem a humanos e ao critic) e a seção de revisão
    (vai para o critic via review_notes). Mantém 'Aplicar', 'Falha típica', tabelas e testes."""
    body = re.split(r"\n## Revisão \(critic\)", body)[0]
    kept = [ln for ln in body.splitlines() if not re.match(r"- \*\*(Por quê|Verificar):\*\*", ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def packs_for(request="", size=None, has_inputs=False, mode="livre", has_edit=False):
    """Pacotes da rubrica do critic (prompts/rubric.json) para este caso de uso. A base vale sempre; os pacotes só
    entram quando o caso de uso os pede, para não julgar uma imagem livre por critérios de peça de marketing."""
    sel = set(select(request, size, has_inputs))
    packs = []
    if "design-estrategia" in sel:
        packs.append("marketing")
    if mode == "marca":
        packs.append("brand")
    if "design-tipografia-texto" in sel or re.search(r'["“”]', request or ""):
        packs.append("text")
    if has_edit or "design-serie-marca" in sel:
        packs.append("edit")
    if "design-estilos" in sel:
        packs.append("estilos")
    return packs


def render(names, full=False):
    """full=True devolve o texto completo das skills (leitura humana); o padrão é o compacto para o prompt."""
    allk = load_all()
    if not names:
        return ""
    head = ("Skills de design aplicáveis a este pedido (aprofundam as regras acima; valem em toda peça deste pedido): "
            + ", ".join(names) + ".\n")
    return head + "\n\n".join(f"<skill name=\"{n}\">\n{allk[n]['body'] if full else compact(allk[n]['body'])}\n</skill>" for n in names)


def review_notes(names):
    """Seções '## Revisão (critic)' das skills escolhidas, para o critic."""
    allk, out = load_all(), []
    for n in names:
        m = re.search(r"## Revisão \(critic\)\n(.*?)(?=\n## |\Z)", allk[n]["body"], re.S)
        if m:
            out.append(f"[{n}]\n{m.group(1).strip()}")
    return "\n\n".join(out)


def doc_rule_ids():
    txt = DOC_PATH.read_text(encoding="utf-8")
    block = txt[txt.index("<!-- agent:start -->"):txt.index("<!-- agent:end -->")]
    return sorted(set(re.findall(r"\*\*([EHCKTF]\d)\.\*\*", block)))


def self_test():
    allk = load_all()
    for n, s in allk.items():
        assert n == s["name"] and n.startswith("design-"), n
        assert s.get("description"), f"{n}: sem description"
        assert "## Revisão (critic)" in s["body"], f"{n}: sem seção de revisão"
        assert "always" in s, f"{n}: sem 'always'"
        assert s.get("always") or s.get("triggers"), f"{n}: sem gatilhos"
    # cobertura: toda regra do docs/08 está aprofundada em alguma skill (### ID)
    covered = {i for s in allk.values() for i in re.findall(r"^### ([EHCKTF]\d)\b", s["body"], re.M)}
    missing = [i for i in doc_rule_ids() if i not in covered]
    assert not missing, f"regras sem aprofundamento em skill: {missing}"
    # roteamento
    base = {"design-hierarquia-composicao", "design-cor-contraste-craft"}  # imagem livre: só composição e craft
    assert set(select("paisagem de praia ao entardecer")) == base
    assert set(select("um gato astronauta flutuando numa estação espacial, ilustração")) == base
    assert "design-estrategia" in select("banner de promoção de verão")
    s1 = select("banner de promoção de verão com a nossa logo")
    assert {"design-tipografia-texto", "design-formato-canal", "design-estrategia"} <= set(s1) and base <= set(s1)
    assert "design-serie-marca" in select("série de 4 posts da campanha de inverno")
    assert "design-movimento-video" in select("reels em vídeo do lançamento")
    assert "design-formato-canal" in select("paisagem", size="1024x1536")
    assert "design-tipografia-texto" not in select("cadastro de clientes na foto")  # "ads" não casa em "cadastro"
    assert select("banner") == sorted(select("banner"), key=lambda n: allk[n]["order"])
    # pacotes da rubrica por caso de uso
    assert packs_for("um gato astronauta numa estação espacial") == []
    assert packs_for("banner de promoção de verão") == ["marketing", "text"] or packs_for("banner de promoção de verão")[0] == "marketing"
    assert packs_for("retrato de senhora idosa", mode="marca") == ["brand"]
    assert "edit" in packs_for("deixe mais quente", has_edit=True)
    assert "text" in packs_for('cartaz com a frase "Bom dia"')
    assert "estilos" in packs_for("card glassmorphism sobre foto")
    # render e notas
    r = render(s1)
    assert all(f'name="{n}"' in r for n in s1) and "## Revisão (critic)" not in r  # o designer recebe a versão compacta
    assert "**Por quê:**" not in r and "**Aplicar:**" in r and "**Falha típica:**" in r
    assert len(render(s1, full=True)) > len(r) * 1.15 and "**Por quê:**" in render(s1, full=True)
    notes = review_notes(s1)
    assert all(f"[{n}]" in notes for n in s1)
    print(f"skills_router self-test ok ({len(allk)} skills, {len(doc_rule_ids())} regras cobertas)")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    elif len(sys.argv) > 1:
        sel = select(" ".join(sys.argv[1:]))
        print("skills:", ", ".join(sel))
    else:
        print(__doc__)
