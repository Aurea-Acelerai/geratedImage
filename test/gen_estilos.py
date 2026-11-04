#!/usr/bin/env python3
"""Gera prompts/estilos.json e skills/design-estilos/SKILL.md a partir da fonte (docs/fontes/02-design-visual-direcao-arte.md).

A fonte é a verdade: os 14 estilos (seção 5 em JSON), as regras de aplicação (4.1) e a tabela (4) são lidos dela, não
redigitados. Só o que NÃO está na fonte é nosso e fica marcado como proposta: a classificação de geração
(imagem/híbrido/código) e a frase de prompt em inglês de cada estilo.

  python3 gen_estilos.py            # regenera os dois arquivos
  python3 gen_estilos.py --check    # falha se estiverem fora de sincronia com a fonte (usado nos testes)
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "fontes" / "02-design-visual-direcao-arte.md"
OUT_JSON = ROOT / "prompts" / "estilos.json"
OUT_SKILL = ROOT / "skills" / "design-estilos" / "SKILL.md"

# --- NOSSA proposta (a validar com testes de geração): quem desenha o estilo, o modelo de imagem ou o código? ---
CLASSE = {
    "dark_cyberpunk": ("imagem", "luz e clima vêm do modelo de imagem; numerais, texto e CTA por código"),
    "glassmorphism": ("hibrido", "o fundo/foto vem do modelo; o painel de vidro, o scrim e o texto são montados por código"),
    "minimal_flat": ("codigo", "vetor, grid e escala tipográfica exatos; o modelo de imagem só faz fundo ou ilustração"),
    "neo_brutalism": ("codigo", "contorno duro e sombra offset exatos; o modelo de imagem só faz o clima"),
    "material3": ("codigo", "sistema de UI com papéis de cor: componentes por código; o modelo de imagem não é a ferramenta"),
    "skeuomorphism": ("imagem", "texturas e relevo realistas são força do modelo; cuidado com a fonte de luz única"),
    "aurora": ("imagem", "mesh gradient é fundo: o modelo gera; texto por código sobre scrim"),
    "typographic": ("codigo", "a tipografia é o estilo: composição por código; o modelo de imagem, no máximo, a textura de fundo"),
    "retro_pixel": ("hibrido", "o modelo imita pixel art, mas a grade exata exige código; conferir se há vetor suave misturado"),
    "brutalism": ("codigo", "layout padrão do sistema: montar por código"),
    "isometric": ("imagem", "o modelo gera cenas isométricas; conferir se o ângulo é consistente"),
    "claymorphism": ("imagem", "volume inflado e pastel são força do modelo; texto escuro por código"),
    "bento": ("codigo", "grid modular exato: montar por código; o modelo gera só o conteúdo de cada célula"),
    "neumorphism": ("codigo", "sombra dupla exata e acento em interativos: UI por código; evitar para texto e fluxo crítico"),
}
PROMPT_EN = {
    "dark_cyberpunk": "near-black surfaces (#0B0D10 to #14161A), a single neon accent used on at most 10% of the area, glow only on the accent, never on body text",
    "glassmorphism": "frosted translucent panel (white fill 8-20%, 12-24px background blur, 1px light border) over a vivid backdrop, with a darkening scrim behind any text area",
    "minimal_flat": "flat solid surfaces, subtraction and generous negative space, strict grid, depth only through surface color, no gradients, no shadows",
    "neo_brutalism": "hard 2-4px black outlines, solid offset shadow with zero blur, flat shock colors (2-3 max), few elements",
    "material3": "tonal surface elevation instead of drop shadows, fixed color roles (primary, secondary, tertiary, error), Material 3 type scale",
    "skeuomorphism": "realistic material textures (leather, paper, metal, wood) with embossed relief, one consistent light source, layered shadows",
    "aurora": "soft organic mesh gradient of 3-5 blurred color blobs as background only, no shadows, depth from blur",
    "typographic": "typography as architecture: extreme-scale display type (4x the body size), monochrome or one color, one accent color on one keyword",
    "retro_pixel": "pixel grid with a limited 8-16 color palette, dithering instead of blur, pixel font only, no smooth vector shapes",
    "brutalism": "deliberately unstyled: system default type, plain white or gray, default link blue, broken layout on purpose",
    "isometric": "30-degree axonometric projection, one light direction, neutral background, objects on a consistent grid, soft contact shadows",
    "claymorphism": "inflated soft 3D clay volume, 24-40px rounded corners, soft outer shadow plus light inner shadow from the top, saturated pastels",
    "bento": "asymmetric modular card grid, each cell with its own surface, one color per cell group, clear visual anchor",
    "neumorphism": "single-tone surface with a light and a dark opposing shadow (8-20px blur), strong accent color on interactive elements",
}


def read_source():
    t = SRC.read_text(encoding="utf-8")
    blk = re.search(r"## 5\. Bloco consumivel por maquina\s+```json\n(.*?)\n```", t, re.S).group(1)
    estilos = json.loads(blk)
    secao = t.split("### 4.1")[1].split("## 5.")[0]
    regras = {m.group(1): m.group(2).strip() for m in re.finditer(r"^\*\*([a-z0-9_]+)\*\* — (.+)$", secao, re.M)}
    assert set(regras) == set(estilos) == set(CLASSE) == set(PROMPT_EN), "estilos, regras 4.1 e classificação não batem"
    return estilos, regras


def build_json(estilos):
    return {"versao": 1, "fonte": "docs/fontes/02-design-visual-direcao-arte.md (seção 5, copiada sem alteração)",
            "estilos": estilos,
            "proposta_nossa": {s: {"geracao": CLASSE[s][0], "nota_geracao": CLASSE[s][1], "prompt_en": PROMPT_EN[s]} for s in estilos}}


HEAD = '''---
name: design-estilos
description: Catálogo de 14 estilos visuais (glassmorphism, neo-brutalism, dark cyberpunk, bento, aurora, isométrico etc.) com o mecanismo de cada um, quando usar, risco e como escrever o prompt. Use quando o pedido nomeia um estilo ou é uma peça de UI/dashboard/landing; não impõe estilo em imagem livre.
always: false
triggers: [estilo, visual, glassmorphism, glass, vidro, neo-brutalism, neobrutalismo, brutalismo, brutalism, cyberpunk, neon, bento, aurora, isometrico, isométrico, isometric, claymorphism, clay, argila, neumorphism, neumorfismo, skeuomorphism, esqueumorfismo, retro pixel, pixel art, tipografico, tipográfico, minimalista, minimal, flat, material design, material 3, dashboard, ui, interface, landing, landing page, dark mode]
order: 45
---

# Estilos visuais (catálogo de 14)

Fonte: `docs/fontes/02-design-visual-direcao-arte.md` (seções 4 e 5). Dados em `prompts/estilos.json`. Esta skill é **gerada** por `test/gen_estilos.py`: não edite à mão.

## Quando usar (e quando não)
- **O pedido nomeia um estilo** ("glassmorphism", "neo-brutalismo", "cyberpunk"…): use a ficha dele. O pedido manda; traduza o nome em **mecanismo**.
- **Peça de UI, dashboard ou landing**, ou peça de marketing em que nem o pedido nem a marca definem o visual: escolha **um** estilo do catálogo e declare o mecanismo e o risco aceito.
- **Imagem livre sem estilo pedido** (foto, ilustração, retrato, cena): **não imponha estilo do catálogo.** O medium vem do pedido. Estilo de UI não é "estilo de arte" para toda imagem.
- Nunca escolha estilo por moda. Nunca antes de saber onde a peça aparece e para quem (o catálogo parte disso).

## Ordem de decisão (a fonte exige esta ordem)
1. Qual é a **única ação** desejada (oferta em uma frase e CTA)?
2. **Onde** será vista (proporção, safe zone, tempo de leitura)?
3. **Quem** lê e em que estado (nível de consciência, tolerância a ruído)?
4. **Qual estilo** serve essa combinação? Cite **slug + mecanismo + risco aceito + o que abriu mão**.
5. **Como prova** que funcionou (métrica, hipótese, uma variável por vez)? Hoje não há métrica; registre a hipótese.

**Nunca pule do passo 2 para o 4**: a causa mais comum de peça ruim é escolher estilo antes de saber onde ela vai aparecer.

## Como escrever o prompt (compilador)
Modelo: `[OBJETIVO] + [ESTILO: o MECANISMO, não só o nome] + [SISTEMA: grid, paleta com papéis, tipografia] + [RESTRIÇÕES: sem texto renderizado, área limpa para copy, contraste medido, uma fonte de luz] + [PROPORÇÃO NUMÉRICA] + [NEGATIVOS]`.

- **Nomeie o mecanismo** ("frosted panel with background blur and a darkening scrim"), não "glassmorphism style".
- **Remova ruído:** "8k", "4k", "high quality", "trending on Dribbble", "beautiful UI", "wide format" (use 16:9, 4:5, 9:16).
- **Texto:** o que deve estar exato (preço, selo, logo, CTA) é montado por código; "sem texto renderizado" vale para peça de marketing. Título curto e decorativo que o usuário pediu pode ir ao modelo, com revisão letra por letra.
- Ruim: `Cyberpunk dashboard, 8k, trending on Dribbble, neon, high quality, wide format`.
  Bom: `Cybersecurity operations dashboard UI, dark theme with near-black surfaces (#0B0D10) and a single neon accent on <=10% of the area, elevation via tonal surface color instead of drop shadows, 12-column grid, 8px spacing scale, tabular numerals, no glow on body text, no decorative elements, 16:9, negative: gibberish text, glow bleed, oversaturated background`.

## Quem desenha o estilo: imagem, híbrido ou código (proposta nossa, a validar)
- **imagem:** o modelo de imagem entrega o estilo (luz, textura, volume). Texto, números e CTA por código.
- **hibrido:** o modelo gera o fundo; o elemento do estilo (vidro, pixel exato) é montado por código.
- **codigo:** o estilo depende de exatidão (grid, contorno, tipografia): componha por código; ao modelo de imagem peça só clima ou fundo, **sem texto**.

## Fichas
'''

TAIL = '''
## Modo especificação (quando o pedido é uma especificação de peça ou de UI, não uma imagem)
Responda neste formato: `OFERTA` · `PONTO FOCAL` · `ESTILO: <slug> — mecanismo: …` · `ESPECIFICAÇÃO` (HEX, escala tipográfica em px, spacing da escala 4/8/12/16/24/32/48/64, raio, sombra) · `RACIONAL` (uma frase por decisão crítica: "escolhi X porque Y, abri mão de Z") · `QA` (12 gates PASSA/FALHA, ver `test/qa_gates.py`) · `RISCOS` (o que pode falhar e como detectar). Nunca invente métrica de desempenho.

## Revisão (critic)
- O estilo aplicado é o **pedido** (ou o escolhido e declarado), com o **mecanismo** presente na imagem, e não só o nome popular?
- Neon: no máximo ~10% da área, nunca em corpo de texto; sem halation que engrosse glifos.
- Vidro/blur/aurora/gradiente atrás de texto: há **scrim** e área calma? O contraste no **pior ponto** do fundo passa?
- Uma única fonte de luz (sombra, relevo, isométrico, skeuomorfismo).
- Pastel (clay), sombra dupla (neumorfismo) e sombra dura em tamanho pequeno: o texto continua legível a 120 px?
- Estilo de código (minimal, neo-brutalism, bento, tipográfico) com texto renderizado pelo modelo de imagem = texto provisório; reprove se deformado.
'''


def build_skill(estilos, regras):
    out = [HEAD]
    for slug, e in estilos.items():
        cls, nota = CLASSE[slug]
        out.append(f"### {slug}\n"
                   f"- **Mecanismo (nomeie no prompt):** {e['mecanismo']}. Em inglês: {PROMPT_EN[slug]}.\n"
                   f"- **Aplicar:** {regras[slug]} Superfície: {e['surface']}. Texto: {e['text']}. Acento: {e['accent']}. Sombra: {e['shadow']}. Tipo: {e['type']}.\n"
                   f"- **Geração:** {cls}. {nota}.\n"
                   f"- **Usar em / evitar:** {e['melhor_uso']} / {e['evitar']}.\n"
                   f"- **Falha típica:** {e['risco']}.\n")
    out.append(TAIL)
    return "\n".join(out)


def expected():
    estilos, regras = read_source()
    return json.dumps(build_json(estilos), ensure_ascii=False, indent=2) + "\n", build_skill(estilos, regras)


def check():
    """True se os arquivos gerados batem com a fonte; levanta AssertionError se não."""
    js, sk = expected()
    ok = OUT_JSON.exists() and OUT_SKILL.exists() and OUT_JSON.read_text(encoding="utf-8") == js and OUT_SKILL.read_text(encoding="utf-8") == sk
    assert ok, "estilos.json / skills/design-estilos fora de sincronia com a fonte: rode python3 test/gen_estilos.py"
    return True


def main():
    if "--check" in sys.argv:
        check()
        print("estilos em sincronia com a fonte")
        return
    js, sk = expected()
    OUT_SKILL.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(js, encoding="utf-8")
    OUT_SKILL.write_text(sk, encoding="utf-8")
    print(f"gerados: {OUT_JSON.relative_to(ROOT)}, {OUT_SKILL.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
