---
name: design-movimento-video
description: Movimento e vídeo: estrutura de hook, timing, easing e storyboard para peças animadas. Use quando o pedido é vídeo, animação, motion, GIF ou Reels em vídeo. O pipeline atual gera só imagem estática: esta skill produz o roteiro e os quadros-chave.
always: false
triggers: [video, vídeo, animacao, animação, animado, motion, gif, storyboard, reels em video, reels em vídeo, kinetic]
order: 70
---

# Movimento e vídeo

**Limite atual:** o pipeline gera **imagem estática**. Para um pedido de vídeo ou animação, **não finja gerar vídeo**: entregue (1) um **roteiro por quadro** e (2) os **quadros-chave** como imagens estáticas (um por beat), aplicando as demais skills a cada quadro. Diga ao usuário que a animação em si ainda não é gerada aqui.

## Estrutura (hook → CTA)
`hook (0–1,5 s) → problema → mecanismo/diferencial → prova → oferta → CTA`, com **re-hook visual por volta dos 7 s**. Nunca abra com logo. Tipos de hook: interrupção de padrão, afirmação numérica, pergunta, antes/depois, demonstração em uso, prova social.

- Duração: Reels e Stories 15–30 s; Feed 30–60 s; acima de 90 s raramente compensa.
- Mudo primeiro: tudo que importa escrito na tela (F5); legenda queimada ou texto animado.
- O gargalo é o início: cerca de 65% de quem passa dos 3 s chega aos 10 s (dado de guia de mercado; trate como hipótese).

## Timing (duração por tipo)

| Tipo de movimento | Duração |
|---|---|
| Feedback imediato (hover, toque, toggle) | 80–150 ms |
| Mudança pequena de estado | 150–250 ms |
| Transição padrão | 220–400 ms |
| Transformação estrutural / tela cheia | 350–650 ms |
| Movimento narrativo / hero de campanha | 700–1200 ms (raramente mais) |

## Easing
- **ease-out** nas entradas (chega rápido, assenta devagar); **ease-in** nas saídas; **ease-in-out** no reposicionamento; **linear** só em loops contínuos.
- Saídas com ~70–80% da duração da entrada.
- *Stagger* de 40–80 ms entre itens; sequência total ≤ 600–800 ms.
- Movimento **explica ou decora?** Se decora e distrai do CTA, corte.

## Roteiro por quadro (formato de entrega)
Para cada beat: tempo (início–fim), **ponto focal**, **texto na tela** (literal), movimento (o que entra, como, easing), áudio/legenda e a **imagem-chave** (briefing). Quadros em 9:16 respeitam a safe zone (`design-formato-canal`).

## Revisão (critic)
- Cada quadro-chave cumpre as regras de imagem estática (hierarquia, contraste, safe zone)?
- O roteiro tem hook claro nos primeiros 1,5 s e CTA único no fim? Abre com logo? (não pode)
- Há movimento decorativo sem função?
- O texto na tela se entende sem som?
