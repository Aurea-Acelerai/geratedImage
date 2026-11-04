---
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

### dark_cyberpunk
- **Mecanismo (nomeie no prompt):** luz emitida em fundo escuro. Em inglês: near-black surfaces (#0B0D10 to #14161A), a single neon accent used on at most 10% of the area, glow only on the accent, never on body text.
- **Aplicar:** preto profundo, nunca #000 em area grande; neon <=10% da area; neon jamais em corpo de texto; glow so em accent e CTA; numerais tabulares. Superfície: #0B0D10 a #14161A (nunca #000 em área grande). Texto: #F5F7FA / #C7CCD4. Acento: 1 neon (ciano, magenta ou verde-limão), ate 10% da area. Sombra: glow apenas em accent e CTA; nunca em corpo de texto. Tipo: sans geometrica/tecnica, tracking neutro, numerais tabulares.
- **Geração:** imagem. luz e clima vêm do modelo de imagem; numerais, texto e CTA por código.
- **Usar em / evitar:** gaming, tech, cripto, dev tools / varejo, oferta de preco, publico 45+.
- **Falha típica:** halation: neon sobre preto engrossa glifos e derruba legibilidade.

### glassmorphism
- **Mecanismo (nomeie no prompt):** blur de fundo + borda clara + scrim. Em inglês: frosted translucent panel (white fill 8-20%, 12-24px background blur, 1px light border) over a vivid backdrop, with a darkening scrim behind any text area.
- **Aplicar:** o painel herda a cor do que esta atras; medir contraste no pior caso; scrim >=35%; `backdrop-filter` com fallback opaco; nunca para dados densos. Referencia normativa: material e camada funcional, nao camada de conteudo (Apple HIG). Superfície: preenchimento branco 8-20% + backdrop-blur 12-24px. Texto: branco puro sobre scrim >=35% de opacidade. Acento: gradiente vivo apenas atras do vidro. Sombra: borda 1px branca 20-35% + sombra suave ampla. Tipo: sans humanista, peso medio, sem texto <14px.
- **Geração:** hibrido. o fundo/foto vem do modelo; o painel de vidro, o scrim e o texto são montados por código.
- **Usar em / evitar:** badge, selo, card de controle sobre imagem / tabela densa, texto pequeno, fundo cinza chapado (efeito desaparece).
- **Falha típica:** contraste variavel: nao existe valor unico, precisa do pior caso.

### minimal_flat
- **Mecanismo (nomeie no prompt):** subtracao + grid + escala tipografica. Em inglês: flat solid surfaces, subtraction and generous negative space, strict grid, depth only through surface color, no gradients, no shadows.
- **Aplicar:** profundidade por cor de superficie, nao gradiente; escala tipografica obrigatoria; espaco em branco como elemento ativo. Superfície: #FFFFFF / #F6F7F9. Texto: #0F1115. Acento: 1 cor solida, uso semantico. Sombra: quase nenhuma; separacao por cor de superficie. Tipo: sans neutra (Helvetica/Inter-like), escala 1.25-1.333.
- **Geração:** codigo. vetor, grid e escala tipográfica exatos; o modelo de imagem só faz fundo ou ilustração.
- **Usar em / evitar:** SaaS, B2B, conversao, oferta / marca que precisa de personalidade forte.
- **Falha típica:** sem efeito para esconder erro: toda falha aparece.

### neo_brutalism
- **Mecanismo (nomeie no prompt):** contorno duro + sombra sem blur + cor de choque. Em inglês: hard 2-4px black outlines, solid offset shadow with zero blur, flat shock colors (2-3 max), few elements.
- **Aplicar:** sombra offset solida com 0 blur; contorno 2-4px; maximo 3-4 elementos; 2-3 cores em choque. Superfície: bege, off-white ou cor chapada saturada. Texto: #000 puro. Acento: 2-3 cores em choque (amarelo, rosa, ciano). Sombra: offset 4-8px solido, 0 blur. Tipo: grotesca pesada ou mono; tracking apertado.
- **Geração:** codigo. contorno duro e sombra offset exatos; o modelo de imagem só faz o clima.
- **Usar em / evitar:** creator economy, moda, marca jovem, hook de feed / institucional, saude, financeiro tradicional.
- **Falha típica:** sopa visual em tamanho pequeno.

### material3
- **Mecanismo (nomeie no prompt):** cor tonal gerada + elevacao por superficie tonal. Em inglês: tonal surface elevation instead of drop shadows, fixed color roles (primary, secondary, tertiary, error), Material 3 type scale.
- **Aplicar:** elevacao por tonal surface; sombra so em FAB/dialogo/sheet; papeis de cor fixos (primary, secondary, tertiary, error); cor semantica nunca substituida por marca; niveis de contraste selecionaveis. Superfície: tonal surface 1-5 (elevacao por cor, nao sombra). Texto: on-surface / on-surface-variant. Acento: primary/secondary/tertiary + error semantico. Sombra: reservada a FAB, dialogo, sheet. Tipo: Google Sans/Roboto-like, escala M3.
- **Geração:** codigo. sistema de UI com papéis de cor: componentes por código; o modelo de imagem não é a ferramenta.
- **Usar em / evitar:** produto Android, app de sistema, dashboard / marca com paleta proprietaria rigida.
- **Falha típica:** usar marca no lugar de cor semantica de erro/sucesso.

### skeuomorphism
- **Mecanismo (nomeie no prompt):** textura + relevo + sombra realista. Em inglês: realistic material textures (leather, paper, metal, wood) with embossed relief, one consistent light source, layered shadows.
- **Aplicar:** uma fonte de luz; highlight interno coerente; textura com escala realista (nao repeticao visivel). Superfície: couro, papel, metal, madeira. Texto: serif/sans com emboss discreto. Acento: dourado, metalico. Sombra: multiplas camadas + highlight interno. Tipo: serif classica ou sans humanista.
- **Geração:** imagem. texturas e relevo realistas são força do modelo; cuidado com a fonte de luz única.
- **Usar em / evitar:** audio, instrumentos, nostalgia, citacao / produto digital moderno, mobile first.
- **Falha típica:** incoerencia de fonte de luz entre elementos.

### aurora
- **Mecanismo (nomeie no prompt):** mesh gradient difuso organico. Em inglês: soft organic mesh gradient of 3-5 blurred color blobs as background only, no shadows, depth from blur.
- **Aplicar:** gradiente e fundo, nunca conteudo; testar nos extremos; scrim para texto; 3-5 blobs no maximo. Superfície: 3-5 blobs desfocados, pastel ou saturado. Texto: branco/preto com scrim. Acento: derivado do gradiente. Sombra: nenhuma; profundidade vem do blur. Tipo: sans leve, titulos finos grandes.
- **Geração:** imagem. mesh gradient é fundo: o modelo gera; texto por código sobre scrim.
- **Usar em / evitar:** saude, meditacao, fintech emocional, hero de landing / dados, texto longo.
- **Falha típica:** contraste imprevisivel no ponto mais claro do gradiente.

### typographic
- **Mecanismo (nomeie no prompt):** tipografia como arquitetura. Em inglês: typography as architecture: extreme-scale display type (4x the body size), monochrome or one color, one accent color on one keyword.
- **Aplicar:** display >=4x o corpo; tracking negativo proporcional; 1 cor para 1 palavra-chave; imagem opcional. Superfície: monocromatico (preto/branco) ou 1 cor. Texto: display em escala extrema (>=4x o corpo). Acento: 1 cor para 1 palavra-chave. Sombra: nenhuma. Tipo: grotesca de display + texto em peso leve.
- **Geração:** codigo. a tipografia é o estilo: composição por código; o modelo de imagem, no máximo, a textura de fundo.
- **Usar em / evitar:** agencia, midia, manifesto, hook de social / quando ha imagem de produto obrigatoria.
- **Falha típica:** vira ilegivel sem dominio de tamanho optico e tracking.

### retro_pixel
- **Mecanismo (nomeie no prompt):** grade de pixel + paleta limitada. Em inglês: pixel grid with a limited 8-16 color palette, dithering instead of blur, pixel font only, no smooth vector shapes.
- **Aplicar:** paleta de 8-16 cores; fontes bitmap em multiplos de 8px; dithering em vez de blur; zero vetor suave. Superfície: paleta de 8-16 cores. Texto: bitmap/pixel font em multiplos de 8px. Acento: 1-2 cores de destaque. Sombra: dithering, nunca blur. Tipo: pixel exclusivamente.
- **Geração:** hibrido. o modelo imita pixel art, mas a grade exata exige código; conferir se há vetor suave misturado.
- **Usar em / evitar:** games indie, cultura dev, nostalgia 90s / leitura longa, legibilidade pequena.
- **Falha típica:** misturar pixel com vetor suave.

### brutalism
- **Mecanismo (nomeie no prompt):** ausencia deliberada de estilo. Em inglês: deliberately unstyled: system default type, plain white or gray, default link blue, broken layout on purpose.
- **Aplicar:** Times/mono, azul de link, layout quebrado com intencao; usar apenas quando o publico compartilha o codigo. Superfície: branco/cinza padrao. Texto: #000, Times ou mono padrao. Acento: azul de link (#0000EE). Sombra: nenhuma. Tipo: default do sistema, tamanhos sem escala.
- **Geração:** codigo. layout padrão do sistema: montar por código.
- **Usar em / evitar:** galeria, arte, dev tools, portfolio / trafego pago de varejo.
- **Falha típica:** lido como amadorismo por publico nao iniciado.

### isometric
- **Mecanismo (nomeie no prompt):** projecao axonometrica 30 graus. Em inglês: 30-degree axonometric projection, one light direction, neutral background, objects on a consistent grid, soft contact shadows.
- **Aplicar:** 30 graus consistentes; uma direcao de luz; grid axonometrico; objetos de altura multipla de 8. Superfície: fundo neutro para destacar objetos. Texto: sans neutra, pouca quantidade. Acento: 2-4 cores para categorias. Sombra: sombra suave sob os objetos, 1 direcao de luz. Tipo: sans geometrica.
- **Geração:** imagem. o modelo gera cenas isométricas; conferir se o ângulo é consistente.
- **Usar em / evitar:** logistica, smart city, infraestrutura, processo / retrato, emocao, storytelling humano.
- **Falha típica:** angulos inconsistentes quebram a ilusao.

### claymorphism
- **Mecanismo (nomeie no prompt):** volume inflado + sombra interna e externa. Em inglês: inflated soft 3D clay volume, 24-40px rounded corners, soft outer shadow plus light inner shadow from the top, saturated pastels.
- **Aplicar:** raio 24-40px; sombra externa suave + interna clara; pastel sempre com texto escuro; evitar marca seria. Superfície: pastel 3D, cantos 24-40px. Texto: sans arredondada, peso medio. Acento: pastel saturado. Sombra: externa suave + interna clara (luz superior). Tipo: sans rounded.
- **Geração:** imagem. volume inflado e pastel são força do modelo; texto escuro por código.
- **Usar em / evitar:** educacao, infantil, wellness, onboarding / marca seria, dados, B2B.
- **Falha típica:** contraste baixo por natureza do pastel.

### bento
- **Mecanismo (nomeie no prompt):** grid modular assimetrico. Em inglês: asymmetric modular card grid, each cell with its own surface, one color per cell group, clear visual anchor.
- **Aplicar:** celulas com superficie propria; hierarquia interna por peso; 1 cor por grupo; assimetria precisa de ancora visual. Superfície: cards com superficie propria. Texto: hierarquia por peso dentro de cada celula. Acento: 1 cor por grupo de celulas. Sombra: sutil ou nenhuma. Tipo: sans neutra, escala consistente entre celulas.
- **Geração:** codigo. grid modular exato: montar por código; o modelo gera só o conteúdo de cada célula.
- **Usar em / evitar:** feature showcase, landing, social multiargumento / conteudo unico e simples.
- **Falha típica:** assimetria sem hierarquia vira bagunca.

### neumorphism
- **Mecanismo (nomeie no prompt):** sombra clara + escura sobre o mesmo tom. Em inglês: single-tone surface with a light and a dark opposing shadow (8-20px blur), strong accent color on interactive elements.
- **Aplicar:** nao usar como interface inteira; texto >=7:1; interativos exigem cor de acento + foco visivel; sempre oferecer alternativa com contraste. Superfície: tom unico #E0E5EC-like. Texto: cinza escuro, >=7:1 recomendado. Acento: obrigatorio em interativos (senao nao ha affordance). Sombra: 2 sombras opostas, blur 8-20px. Tipo: sans neutra.
- **Geração:** codigo. sombra dupla exata e acento em interativos: UI por código; evitar para texto e fluxo crítico.
- **Usar em / evitar:** acento, toggle decorativo, nao interface inteira / texto pequeno, dados, qualquer fluxo critico.
- **Falha típica:** hostil a acessibilidade por design: contraste baixo estrutural.


## Modo especificação (quando o pedido é uma especificação de peça ou de UI, não uma imagem)
Responda neste formato: `OFERTA` · `PONTO FOCAL` · `ESTILO: <slug> — mecanismo: …` · `ESPECIFICAÇÃO` (HEX, escala tipográfica em px, spacing da escala 4/8/12/16/24/32/48/64, raio, sombra) · `RACIONAL` (uma frase por decisão crítica: "escolhi X porque Y, abri mão de Z") · `QA` (12 gates PASSA/FALHA, ver `test/qa_gates.py`) · `RISCOS` (o que pode falhar e como detectar). Nunca invente métrica de desempenho.

## Revisão (critic)
- O estilo aplicado é o **pedido** (ou o escolhido e declarado), com o **mecanismo** presente na imagem, e não só o nome popular?
- Neon: no máximo ~10% da área, nunca em corpo de texto; sem halation que engrosse glifos.
- Vidro/blur/aurora/gradiente atrás de texto: há **scrim** e área calma? O contraste no **pior ponto** do fundo passa?
- Uma única fonte de luz (sombra, relevo, isométrico, skeuomorfismo).
- Pastel (clay), sombra dupla (neumorfismo) e sombra dura em tamanho pequeno: o texto continua legível a 120 px?
- Estilo de código (minimal, neo-brutalism, bento, tipográfico) com texto renderizado pelo modelo de imagem = texto provisório; reprove se deformado.
