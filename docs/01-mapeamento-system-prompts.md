# 01 — Mapeamento dos system prompts vazados (OpenAI) sobre geração de imagem

Fonte: https://github.com/asgeirtj/system_prompts_leaks/tree/main/OpenAI (lido em 04/11/2026, commit `ecab027`).
Os trechos abaixo são resumos e citações curtas; o texto completo está nos arquivos linkados.

## 1. Como o repositório está organizado

| Padrão de arquivo | O que é |
|---|---|
| `gpt-5.x-thinking.md`, `gpt-5.x-instant.md`, `gpt-5.6-sol.md` | System prompt do **app ChatGPT** (chatgpt.com) |
| `gpt-5.x-api.md` | System message oculta injetada em **chamadas de API** |
| `chatgpt-gpt-5-agent-mode.md` | Modo agente (tem política própria de imagem para slides) |
| `Codex/` | Codex CLI |

## 2. O achado central: tamanho do harness

| Arquivo | Tamanho (caracteres) | Menções a image_gen |
|---|---|---|
| `gpt-5.6-sol.md` (ChatGPT) | ~126.800 | 17 |
| `gpt-5.5-thinking.md` (ChatGPT) | ~115.900 | 18 |
| `gpt-5.5-instant.md` (ChatGPT) | ~84.800 | 7 |
| `gpt-5.5-api.md` (API) | **~860** | 0 |
| `gpt-5.5-pro-api.md` (API) | ~835 | 0 |
| `gpt-5.4-api.md` (API) | ~864 | 0 |

O que a API injeta é só data, nível de verbosidade e canais. **Nenhuma instrução de imagem, memória, ferramentas ou estilo.**

## 3. A ferramenta `image_gen` no ChatGPT (gpt-5.6-sol.md)

Namespace `image_gen`, canal `commentary`, uma função: `text2im`.

```ts
type text2im = (_: {
  prompt?: string | null,
  size?: string | null,
  n?: integer | null,
  transparent_background?: boolean | null,
  is_style_transfer?: boolean | null,
  referenced_image_ids?: string[] | null,
}) => any;
```

Regras de roteamento e comportamento (resumo):

1. **Quando acionar:** qualquer pedido de cena, diagrama, retrato, quadrinho, meme, mapa, gráfico; qualquer edição de imagem anexada (cor, objeto, estilo, upscale).
2. **Gerar direto**, sem pedir confirmação, exceto quando a imagem incluir o próprio usuário (aí pede uma foto de referência pelo menos uma vez).
3. **Edição:** só chama a ferramenta se existir um **alvo real** na conversa (imagem anexada ou identificável). Alvo "inventado" ou só citado por id → pede o upload.
4. **Pós-geração:** não descreve a imagem, responde vazio, não menciona download.
5. **Política:** recusa educadamente, sem oferecer alternativas.
6. **Regra crítica repetida em CAIXA ALTA:** os argumentos da ferramenta **nunca** aparecem como texto/JSON para o usuário; ficam só no payload da chamada.
7. **Python (`python_user_visible`)** é a alternativa quando é preciso anotar uma imagem com precisão.
8. Nas versões novas: se o pedido é editar/transformar imagem, "STRONGLY default" para `image_gen`.

Outras ferramentas e variações:
- `gpt-4o.md` tem a mesma ferramenta com `referenced_image_ids` descrito como "só use se o usuário especificar".
- `chatgpt-gpt-5-agent-mode.md` usa `imagegen.make_image` e define **Imagegen policies**: não usar imagegen para gráficos, tabelas, dataviz ou imagens com texto dentro; só para imagens decorativas/abstratas; não retratar entidades reais (logos, marcos).
- Existe ainda o `image_group` (busca de imagens da web em carrossel/bento). É busca, não geração.

## 4. Onde está a receita de qualidade

O **system prompt do app ChatGPT** só diz *quando* chamar a ferramenta e *como se comportar*. A receita de como montar o prompt está em outro arquivo do mesmo repositório: a **skill `imagegen` do Codex** (`OpenAI/Codex/skills/imagegen/SKILL.md` + `references/prompting.md` + `references/sample-prompts.md`). Ela traz taxonomia de casos de uso, schema rotulado de prompt, política de especificidade, regras de texto/edição/iteração e validação. Está resumida em `04-comparativo-fornecedores.md`.

O restante do que gera imagem boa no chat está fora de texto visível:

1. **O modelo de raciocínio escreve o campo `prompt`.** O pedido curto do usuário vira um prompt detalhado, usando o contexto da conversa, memória do usuário e imagens anexadas. Esse trabalho acontece no raciocínio do modelo, não em texto de sistema visível.
2. **Contexto persistente** (memória, bio, instruções do usuário) entra antes da chamada.
3. **O modelo de imagem em si** (família `gpt-image`) é treinado para receber esse tipo de prompt.
4. Parâmetros auxiliares (`size`, `n`, `transparent_background`, `is_style_transfer`) são escolhidos pelo orquestrador, não pelo usuário.

Conclusão para o nosso caso: **dá para replicar a orquestração e boa parte da receita de prompt** (skill do Codex + diretiva de arte da Meta + consistência do Gemini). O que não dá para copiar é o raciocínio interno do modelo. Veja `02-chat-vs-api.md`, `03-arquitetura-agente-designer.md`, `04-comparativo-fornecedores.md` e o prompt consolidado em `../prompts/designer-imagegen.system.md`.
