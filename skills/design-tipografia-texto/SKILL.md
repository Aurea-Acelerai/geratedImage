---
name: design-tipografia-texto
description: Tipografia e texto da peça: famílias, entrelinha, tracking, alinhamento, tamanho mínimo relativo à tela, densidade e CTA (regras T1 a T7). Use quando a peça tem título, preço, oferta, CTA ou qualquer texto.
always: false
triggers: [texto, titulo, título, headline, frase, slogan, preco, preço, oferta, promo, desconto, cta, botao, botão, legenda, escrito, copy, banner, anuncio, anúncio, ads, flyer, panfleto, cartaz, aspas]
order: 40
---

# Tipografia e texto (T1 a T7)

**Regra de ouro:** texto exato, preço, data, logo e CTA **nunca saem do modelo de imagem**; são compostos por código (`compose_text_overlay`) sobre uma arte sem texto. Estas regras são os **parâmetros** dessa composição. Para o modelo de imagem, o briefing pede apenas a área reservada e "no text, no letters, no logos, blank signage".

### T1 — No máximo duas famílias; varie o peso
- **Aplicar:** uma família para títulos (display) e uma para apoio, ou uma só em pesos diferentes. Pareie contraste de estrutura (geométrica + humanista), nunca duas parecidas. Passos de peso claros (ex.: 400 e 700, não 500 e 600). A tipografia do cliente (`typography` no contexto) manda.
- **Falha típica:** três fontes; duas sans quase iguais que parecem erro.

### T2 — Entrelinha por função
- **Aplicar:** display/título: **1,05–1,15**; corpo: **1,4–1,6**. Título em caixa alta aceita o limite inferior. Entrelinha apertada demais encosta ascendentes e descendentes; larga demais quebra a unidade do bloco.
- **Falha típica:** título de 3 linhas com entrelinha de corpo (1,5), parecendo frases soltas.

### T3 — Tracking por tamanho
- **Aplicar:** quanto maior o título, mais **negativo** o tracking; texto pequeno pede tracking **positivo**. Referência SF Pro (ajuste óptico da Apple): 12pt = 0; 13 = −0,08; 14 = −0,15; 16 = −0,31; 17 = −0,43. Caixa alta pede tracking positivo (heurística: +4% a +8% da largura do em) para respirar. Em fontes que não são SF Pro, a escala é só a direção do ajuste; ajuste a olho no resultado composto.
- **Falha típica:** título gigante com tracking padrão (parece frouxo); legenda pequena apertada.

### T4 — Nunca justifique texto curto
- **Aplicar:** alinhamento à esquerda (leitura) ou centralizado (peças simétricas, no máximo 2–3 linhas). Justificado cria rios e buracos em linhas curtas. Evite viúvas (uma palavra sozinha na última linha) e quebre linhas por sentido, não por largura.
- **Falha típica:** bloco justificado com lacunas enormes; "para" sozinho na linha.

### T5 — Tamanho mínimo medido na tela, não na tela de design
- **Por quê:** o mínimo "corpo ≥ 16 px e headline ≥ 32 px" vale para CSS em uma tela. Uma peça de 1080 px de largura é exibida em um celular com cerca de 390 pt de largura: **fator ≈ 0,36**. Um título de 32 px no canvas aparece com ~11,6 pt: pequeno demais.
- **Aplicar:** derive o tamanho do canvas: `px_canvas = px_na_tela × (largura_canvas ÷ 390)`. Metas de partida para 1080 de largura (heurística derivada, a validar com o time): corpo/legal ≥ 33 px (≈12 pt na tela), apoio ≥ 45 px, título ≥ 80 px. `checks.type_min_canvas(kind, canvas_w)` calcula o mínimo.
- **Falha típica:** peça "aprovada" no zoom de 200% e ilegível no feed.

### T6 — Densidade
- **Aplicar:** no máximo **7 palavras por linha** e **3 linhas** em anúncio; título ≤ 7 palavras (E2). Menos texto = mais leitura; detalhes vão para a landing. Números e prova grandes, o resto pequeno. Não existe "regra dos 20% de texto" da Meta desde 2020: não reprove por percentual, reprove por densidade ilegível.
- **Falha típica:** parágrafo em banner; letra miúda competindo com o título.

### T7 — Teste dos 3 níveis sem cor
- **Aplicar:** converta mentalmente a peça para tons de cinza: a hierarquia (título, apoio, CTA) ainda se sustenta só por escala e peso? Se depende da cor para separar níveis, está frágil (e inacessível).
- **Falha típica:** hierarquia criada só pela cor do texto.

## CTA no texto da peça
- **Um só**, no fim da leitura, alto contraste, **verbo + benefício** ("Garanta 20% off", "Receba em casa hoje"). Nunca "clique aqui", "saiba mais", "confira".
- Em imagem estática de anúncio, o botão clicável é o da plataforma; o CTA na peça é um **sinal visual** do mesmo comando (não precisa ter alvo de toque). O alvo ≥ 44 pt vale para botões reais (HTML5, e-mail, landing).

## Detalhes de composição por código
- A fonte precisa ter os acentos do português (á, ç, ã, õ, ê); confira a cobertura de glifos antes de compor.
- Texto do cliente é literal: não corrija, traduza nem "melhore". Se parecer erro, pergunte.
- Reserve a região do texto **antes** de gerar a arte (H4) e meça o contraste depois (C1).

## Revisão (critic)
- Existe texto dentro da imagem que ninguém pediu, ilegível ou com letras inventadas? Veto `texto_indevido`.
- Mais de 2 famílias, justificado em linhas curtas, entrelinha ou tracking fora das faixas?
- Texto principal legível reduzido a 120 px? Tamanho relativo ≥ metas do T5?
- CTA único, verbo + benefício, destacado? Genérico ("saiba mais") ou diluído no fundo = veto `cta_vago` (só quando o briefing pede CTA).
- Mais de 7 palavras por linha ou mais de 3 linhas?
