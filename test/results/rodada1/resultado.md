# Rodada 1: casos 1 a 6, braços A (pedido cru) e B (briefing do nosso prompt)

Modelo: gpt-image-2.5-sunburst via Figma; 1 geração por braço e caso; avaliador: critic da rubrica v2 aplicado por um modelo de texto e visão (não é avaliação humana cega). A tabela completa está em `painel.png`.

| Caso | A (cru) | B (nosso prompt) | Observação |
|---|---|---|---|
| 1 post de promoção | 6,71 reprovada (texto indevido) | 8,71 aprovada | A trouxe 3x "Cliente Exemplo 71" e textos inventados; B é foto limpa com espaço para o título |
| 2 banner | falhou | falhou | Falha de geração 1536x1024 (2 tentativas por braço) |
| 3 três biquínis | 7,29 reprovada (texto indevido) | 9,29 aprovada | A acertou a contagem e as cores, mas escreveu "Três cores, infinitas possibilidades"; B sem texto, com varal e prendedores como no briefing |
| 4 canga | 8,29 aprovada | 9,06 aprovada | A acrescentou chapéu e óculos que ninguém pediu; B limpa, uma canga, sem letras |
| 5 "VERÃO 2027" | 6,62 reprovada (texto indevido) | 8,57 aprovada | Ver `piloto-caso5/` |
| 6 série, 1º post | 5,67 reprovada (texto indevido) | falhou | A virou peça corporativa com laptop e texto inventado; B falhou duas vezes na geração |

Média nos 4 casos com os dois braços (1, 3, 4, 5): A 7,23 (1 de 4 aprovada); B 8,91 (4 de 4 aprovadas).

## Limites
- Uma geração por braço: não mede consistência. Falta repetir.
- Avaliador é o critic aplicado por modelo, não a nota humana cega. O critic nunca foi calibrado.
- O prompt do braço A é o nosso modelo do fluxo atual (pedido + nome do cliente + cores), sem setor nem estilo. No caso 6 isso pesa: o pedido cru não diz que é moda praia. O ganho do B inclui o contexto do cliente que o briefing carrega.
- O texto "Cliente Exemplo 71 (dados fictícios para teste)" vazou nas imagens do A porque entrou no prompt. O briefing do B não inclui o nome do cliente.
- As falhas de geração (casos 2 e 6-B) não foram investigadas: o Figma devolve só "Image generation failed".
