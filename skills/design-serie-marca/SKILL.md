---
name: design-serie-marca
description: Séries, campanhas e sistema de marca: tokens, grade por formato, consistência entre peças, matriz de criativos e governança. Use em pedidos de série, campanha, variações, carrossel, kit ou conjunto de peças.
always: false
triggers: [serie, série, campanha, variacao, variação, variacoes, variações, conjunto, carrossel, kit, template, mesma linha, varias pecas, várias peças, varias imagens, várias imagens, opcoes, opções]
order: 60
---

# Séries, campanhas e sistema de marca

O diferencial real não é uma peça boa: é **20 peças que parecem irmãs**, produzidas rápido. Isso exige sistema (tokens, grade, componentes) e disciplina de variação.

## Tokens (decididos uma vez por cliente)
- **Cor:** primária, acento, fundo, neutros (4–5 tons); papel de cada uma (fundo, destaque, texto).
- **Tipografia:** até 2 famílias, escala de tamanhos (razão 1,25–1,5 entre níveis), pesos permitidos.
- **Espaçamento:** escala de múltiplos de 8 (8, 16, 24, 32…); margem do quadro em % da largura (partida: 6–8%).
- **Forma:** um raio de borda, um estilo de sombra, um tratamento de imagem (K5).
- **Fonte dos tokens:** `get_client` e `get_brand_kit`. Tokens ausentes não se inventam: pergunte ou use o padrão neutro e registre.

## Grade por formato
Uma grade por proporção (4:5, 9:16, 1:1, 1.91:1): colunas, margens, zona de título, zona de CTA, zona de logo. A mesma peça em dois formatos usa a **mesma linguagem** em grades **diferentes** (F1).

## Consistência numa série (para o modelo de imagem)
- Um **descritor fixo** do assunto repetido em todas as peças ("the same woman as Image 1: shoulder-length dark hair, navy swimsuit").
- Um **prefixo de consistência** idêntico: estilo/medium, luz (K1), paleta (por nome), enquadramento base.
- Imagem da peça anterior ou da referência como entrada, rotulada ("Image 1: reference for the character, keep identical").
- Varie **uma** coisa por peça (cena, ângulo de câmera ou item); o restante permanece (invariantes).
- Logo e texto por código, nas mesmas posições da grade.

## Matriz de criativos (variações com propósito)

| Eixo | Exemplos |
|---|---|
| Ângulo (E4) | dor, desejo, prova, comparação, urgência, educação |
| Formato | 1:1, 4:5, 9:16, 16:9 |
| Tratamento | foto, tipografia dominante, colagem, 3D, UGC |
| Hook (E2) | número, pergunta, demonstração, antes/depois |

**Ordem de variação:** ângulo → hook → tratamento → formato → cor. Trocar cor sozinha não é teste de conceito. Para testar, **uma variável por vez**, com hipótese declarada ("se X, então Y porque Z"). Hoje não há métricas de performance: guarde a hipótese e a peça para comparar quando houver.

## Governança
- Aprovadas e reprovadas ficam registradas **com o motivo**: é o material de aprendizado do sistema.
- Mudou token ou grade de um cliente? Versione e registre a data.
- Nomenclatura: `campanha_formato_conceito_versao` (F8).

## Revisão (critic)
- As peças parecem da mesma família (cor, luz, tipografia, tratamento, grade)? Compare com as referências rotuladas.
- Personagem, produto e estilo permanecem consistentes com as imagens de referência? Deriva = `invariants` baixo.
- As variações diferem em ângulo ou hook, ou só em cor? Só cor = variação pobre.
- Logo e texto nas posições da grade, idênticos entre as peças?
