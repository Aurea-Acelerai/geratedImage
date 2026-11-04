# Piloto: caso 5 ("VERÃO 2027")

Modelo: gpt-image-2.5-sunburst (via Figma), 1024x1024, uma geração por braço. Avaliador: o critic da rubrica v2, aplicado por um modelo de texto e visão (não é avaliação humana cega).

| Braço | Prompt | Nota | Veto |
|---|---|---|---|
| A | pedido cru + nome do cliente + hex | 6,62 | texto_indevido |
| B | briefing gerado pelo system prompt v0.4 | 8,57 | nenhum |

**A:** título correto, mas a arte trouxe texto que ninguém pediu: o rótulo "Cliente Exemplo 71 (dados fictícios para teste)" e o subtítulo inventado "Mais dias incríveis te esperam".
**B:** título "VERÃO 2027" exato, com til, uma vez, sem texto extra; paleta da marca. Falhou a instrução de horizonte no terço inferior (ficou perto do meio) e o visual é um pouco saturado, estilo HDR.

Limites: uma geração por braço; o prompt do braço A é o nosso modelo do fluxo atual (template + nome + cores), não o prompt real do Robocop; o ganho do B vem em parte de o briefing não incluir o nome do cliente.
