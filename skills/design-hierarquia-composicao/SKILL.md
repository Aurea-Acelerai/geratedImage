---
name: design-hierarquia-composicao
description: Hierarquia, ponto focal, zonas, espaço negativo, peso visual e Gestalt aplicados ao briefing de imagem (regras H1 a H6). Use em toda peça com layout, especialmente hero com espaço para texto.
always: true
order: 20
---

# Hierarquia e composição (H1 a H6)

Os exemplos ilustram forma, não conteúdo: nunca herde deles assunto, cena ou luz. Você controla a **imagem**; quando a peça tem texto, ele entra depois, por código. Por isso a hierarquia se constrói em duas camadas: a cena (onde está o peso e o espaço calmo) e o texto composto (escala e posição). Descreva as duas no briefing.

### H1 — Três níveis de leitura com salto real
- **Por quê:** sem salto de escala ou peso, tudo parece igual e o olho não sabe por onde entrar.
- **Aplicar:** nível 1 = ponto focal/título (domina); nível 2 = apoio (cerca de 40–60% da escala do nível 1); nível 3 = CTA, legal, assinatura. Entre níveis, razão de escala ≥ 1,5. Em peça sem texto: assunto (1), contexto (2), detalhe (3). No briefing: "dominant subject, calm secondary context, minimal tertiary detail".
- **Verificar:** teste dos olhos semicerrados (borre a imagem): sobram 3 massas distintas?
- **Falha típica:** título e subtítulo quase do mesmo tamanho; CTA maior que a oferta.

### H2 — Um único ponto focal
- **Aplicar:** o foco se cria por **contraste, escala, isolamento, cor, direção e nitidez** (profundidade de campo). Use dois ou três ao mesmo tempo no foco e nenhum nos demais. Direção: o olhar do modelo e as linhas da cena apontam para a oferta ou o CTA. Prompt (forma): "shallow depth of field, subject sharp, background softly blurred" e, só se houver texto planejado, "subject looking toward the area reserved for the headline".
- **Verificar:** onde o olho pousa primeiro (peça borrada)? É o foco declarado?
- **Falha típica:** dois rostos de tamanho igual; elemento decorativo mais saturado que o assunto.

### H3 — Zonas
- **Aplicar:** vertical (4:5, 9:16): topo = marca ou proposta; meio = mensagem e visual; base = CTA. Horizontal (1.91:1, 16:9): leitura em Z (marca no canto superior esquerdo, assunto à direita, CTA embaixo à direita). Combine as zonas com as áreas de risco da interface do canal (skill `design-formato-canal`). **Só com texto planejado**, defina no briefing a região do texto em **proporções do quadro**: "upper 30% reserved for headline, calm and uniform".
- **Verificar:** o texto previsto cai numa região calma e fora da área coberta pela interface.
- **Falha típica:** CTA na faixa inferior que a plataforma cobre com legenda e botões.

### H4 — Espaço negativo com função
- **Por quê:** é o que dá respiro e onde o texto vai viver. Sem ele o texto briga com a imagem.
- **Aplicar:** **só quando há texto planejado** (peça de marketing, `hero`), reserve 30–40% do quadro como área calma. Em imagem livre **não deixe espaço vazio "para título"**: a composição é toda do assunto. Área calma: baixa variação de detalhe, gradiente suave, sem rosto nem objeto cortado. Posicione o assunto num terço e o espaço no oposto. Prompt: "negative space in the upper third, smooth out-of-focus sky, no objects, no text". Em `cell` (quadro cheio) o espaço negativo é interno ao design, não reservado.
- **Verificar:** a região reservada é visivelmente uniforme (pouca textura, luminância estável): o contraste do texto (C1) fica previsível.
- **Falha típica:** espaço "vazio" cheio de textura (folhas, ondas) que derruba a legibilidade.

### H5 — Peso visual equilibrado
- **Aplicar:** equilíbrio assimétrico: um elemento pesado e pequeno equilibra uma área grande e leve. Peso aumenta com tamanho, escuridão, saturação, nitidez e posição mais baixa. Prefira diagonais e terços ao centro estático.
- **Verificar:** a peça "pende" para um lado sem motivo?
- **Falha típica:** tudo no centro; um canto pesado e o resto vazio sem intenção.

### H6 — Prägnanz: a leitura mais simples vence
- **Aplicar:** no máximo cerca de cinco elementos distintos (assunto, fundo, título, apoio, CTA/logo). Se precisa de explicação, simplifique. Cada elemento tem função declarada; sem função, sai (teste de subtração: remova 30% e defenda o que sobrou).
- **Verificar:** a mensagem se entende em 1,5 s?
- **Falha típica:** peça "completa" que ninguém consegue ler no feed.

## Gestalt aplicada ao briefing

| Princípio | Como pedir ou usar | Falha |
|---|---|---|
| Proximidade | agrupe oferta e CTA por distância, sem caixas | espaçamento igual entre tudo |
| Similaridade | repita forma, cor e tratamento nos itens da mesma família | itens de mesma função com estilos diferentes |
| Fechamento | permita recorte e minimalismo; o cérebro completa a forma | recorte que corta o que é essencial |
| Região comum | card de preço e bloco de prova dentro do mesmo contorno | contorno em tudo |
| Figura-fundo | assunto separado do fundo por luz e contraste | assunto da cor do fundo |
| Continuidade | linhas e olhar levam ao foco ou ao CTA | linhas levando para fora do quadro |

## Teste da miniatura
Reduza mentalmente a peça a cerca de 120 px de largura: o ponto focal e o texto principal ainda se leem? Se a peça só funciona no zoom, ela reprova no feed.

## Revisão (critic)
- Um único ponto focal? Onde o olho pousa primeiro numa versão de 120 px?
- Existem 3 níveis com salto de escala real (≥ 1,5)?
- A área reservada ao texto é calma e uniforme? Está fora das áreas cobertas pelo canal?
- Elementos competindo pelo mesmo peso? Mais de ~5 elementos distintos?
- A peça se entende em 1,5 s? Se precisa ser decifrada, `hierarchy` ≤ 6.
