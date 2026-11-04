---
name: design-cor-contraste-craft
description: Cor, contraste medido, saturação como orçamento e craft de imagem: luz única, sombras, grão, alinhamento óptico e vocabulário curto (regras C1, C2 e K1 a K5). Use em toda peça gerada.
always: true
order: 30
---

# Cor, contraste e craft (C1, C2, K1 a K5)

Os exemplos ilustram forma, não conteúdo: escolha luz, hora do dia, paleta e clima **pelo pedido**; nunca adote "golden hour" ou cores quentes por padrão. "Parecer caro" é percepção controlada: luz coerente, sombras proporcionais, textura que une as camadas e restrição de vocabulário. Nada disso é filtro.

### C1 — Contraste medido, não achado
- **Por quê:** texto sobre imagem é o ponto onde mais peças falham.
- **Aplicar:** mínimos WCAG: texto normal **4,5:1**; texto grande (≥ 18pt ou ≥ 14pt negrito) **3:1**; AA é o piso, não a meta. Elementos gráficos essenciais (borda de botão, ícone) **3:1** contra o fundo. Meça no **pior ponto** da região do texto, não na média. Se o fundo varia, o texto composto por código recebe um *scrim* (gradiente escuro ou claro sob o texto) ou uma caixa de cor sólida. Nunca dependa só da cor para distinguir informação (teste em tons de cinza).
  Quando há texto planejado, peça ao modelo de imagem a região certa (forma): "calm, low-detail zone, dark enough for light text". Cores da marca: o código aplica os hex exatos; no prompt de imagem prefira o **nome** da cor ("deep navy blue, warm amber") ao código hex.
- **Verificar:** `checks.contrast_ok(fg, bg, size_pt, bold)` quando o texto é composto por código; o critic avalia a região reservada por inspeção e a nota de `legibility_size`.
- **Falha típica:** texto branco sobre céu claro; "contraste bom" medido no centro da foto e não na borda.

### C2 — Saturação é orçamento
- **Aplicar:** proporção de partida 60–30–10 (neutro dominante, cor secundária, um acento). Uma cor forte por peça, com papel (CTA ou foco). Hipercor e paletas hipersaturadas só quando é a decisão de conceito do cliente. A foto não pode ser mais saturada que o acento da marca.
- **Verificar:** quantas cores competem? O acento está no foco?
- **Falha típica:** arco-íris de acentos; foto saturada apagando a identidade.

### K1 — Uma única fonte de luz
- **Aplicar:** declare **direção, qualidade e temperatura** da luz uma vez e repita em todos os elementos: (forma) "single soft key light from one side, one consistent color temperature, shadows falling the same way" — a luz concreta (estúdio, luz do dia, noite, neon, contraluz) vem do pedido. Elementos de origens diferentes (produto + modelo + fundo) são o sinal mais claro de colagem.
- **Verificar:** as sombras caem na mesma direção? A temperatura de cor é a mesma no sujeito e no ambiente?
- **Falha típica:** produto iluminado pela esquerda e modelo pela direita.

### K2 — Sombras proporcionais à escala
- **Aplicar:** sombra de contato curta e nítida onde o objeto toca a superfície; sombra projetada mais suave e longa conforme o objeto se afasta. Opacidade e desfoque crescem com a distância à superfície; objetos pequenos têm sombras pequenas. Prompt: "soft contact shadow under the object, shadow softness consistent with the light".
- **Verificar:** o objeto "pousa" ou flutua? A sombra combina com a luz declarada?
- **Falha típica:** sombra-adesivo (mesma em qualquer escala); objeto sem sombra de contato.

### K3 — Grão e textura que unificam
- **Aplicar:** grão fino sutil tira o aspecto plástico e une camadas de origens diferentes. Prompt: "subtle natural film grain, visible skin texture, no airbrushed look". Se houver composição por código, um passe final de grão leve (cerca de 2–4% de ruído) no conjunto. Blend modes (multiply para sombras, screen para brilho) unificam colagem.
- **Verificar:** a pele e os materiais parecem reais ou lisos demais? As camadas parecem da mesma foto?
- **Falha típica:** pele de plástico; fundo digital limpo atrás de sujeito fotográfico.

### K4 — Alinhamento óptico
- **Aplicar:** alinhamento matemático engana: círculos e triângulos precisam "estourar" um pouco a margem para parecerem alinhados; ícone ao lado de texto alinha pelo peso visual, não pela caixa. Para texto composto: margem óptica (aspas e pontuação penduradas), baseline comum entre itens na mesma linha. Margens simétricas e consistentes (mesmo valor nos quatro lados, em % da largura).
- **Verificar:** o conjunto "senta" na grade ou parece torto, mesmo medindo igual?
- **Falha típica:** logo centralizado pela caixa que parece deslocado; margens diferentes em cada lado sem intenção.

### K5 — Vocabulário curto repetido com precisão
- **Aplicar:** restrição, não variedade: no máximo 2 famílias tipográficas, 3 cores de marca + neutros, um raio de borda, um estilo de sombra, um tratamento de imagem por peça e por série. Reutilize os mesmos tokens (ver `design-serie-marca`).
- **Verificar:** quantos "estilos" coexistem na peça?
- **Falha típica:** três tratamentos de imagem e quatro estilos de botão na mesma campanha.

## Revisão (critic)
- Região do texto: o contraste do **pior ponto** parece ≥ 4,5:1 (≥ 3:1 se grande)? Se duvidar, dê a menor nota.
- Uma fonte de luz coerente em todos os elementos? Sombras na mesma direção e com escala proporcional?
- Aspecto plástico, pele lisa demais ou colagem visível → `craft` ≤ 6.
- Cores competindo (mais de um acento forte)? Paleta fora da marca derruba `color_contrast`.
- Mais de um tratamento de imagem ou estilo gráfico na mesma peça?
