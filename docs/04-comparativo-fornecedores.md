# 04 — Comparativo: o que cada fornecedor faz em geração de imagem

Fonte: repositório `asgeirtj/system_prompts_leaks` (lido em 04/11/2026). Varredura automática em todos os `.md/.txt` (~1.000 arquivos) buscando ferramentas e regras de imagem; os arquivos abaixo foram lidos.

## 1. Onde está cada coisa

| Fornecedor | Arquivo | O que tem |
|---|---|---|
| OpenAI (app) | `OpenAI/gpt-5.6-sol.md`, `gpt-5.5-*.md` | Ferramenta `image_gen.text2im` + regras de roteamento |
| **OpenAI (Codex)** | `OpenAI/Codex/skills/imagegen/SKILL.md`, `references/prompting.md`, `references/sample-prompts.md` | **A receita real de montagem de prompt**: taxonomia, schema, regras de augmentação, validação |
| OpenAI (API) | `OpenAI/gpt-5.x-api.md` | ~860 caracteres, sem nada de imagem |
| OpenAI (agent) | `OpenAI/chatgpt-gpt-5-agent-mode.md` | Imagegen policies para slides |
| Google | `Google/gemini-3.8-flash.md`, `gemini-2.5-flash-image-preview.md` | `generate_image` com `aspect_ratio` e `image_references`; consistência de personagem |
| Meta | `Meta/muse-agent/.../presentation/references/image-directive.md`, `muse-spark-1.1-web.md` | **Diretiva de direção de arte** (7 partes) e subagente que expande o detalhe visual |
| xAI | `xAI/grok-4.7.md` | `generate_image`/`edit_image` com `ref_images`, separação one-shot vs. pipeline |
| Mistral | `Mistral/mistral-medium-3.5.md` | Imagem via Black Forest; prompt em inglês, autocontido, verboso |
| Anthropic | `Anthropic/claude-fable-5.1.md` | Sem ferramenta nativa de imagem; só roteia para skill `imagegen` do usuário |

## 2. O que cada um faz melhor

### OpenAI (Codex skill): melhor em **estrutura e controle de qualidade do prompt**
- **Taxonomia de casos de uso** (slugs): `photorealistic-natural`, `product-mockup`, `ui-mockup`, `infographic-diagram`, `ads-marketing`, `logo-brand`, `illustration-story`, `stylized-concept`, etc. + edições (`text-localization`, `identity-preserve`, `precise-object-edit`, `background-extraction`, `compositing`...).
- **Schema rotulado** do prompt: Use case / Asset type / Primary request / Input images / Scene / Subject / Style / Composition / Lighting / Palette / Materials / Text (verbatim) / Constraints / Avoid.
- **Política de especificidade:** prompt já detalhado → só normalizar; prompt genérico → aumentar com critério. Lista do que **pode** e **não pode** ser adicionado (nada de personagens, marcas, slogans, paletas não implícitos).
- **Texto na imagem:** entre aspas, tipografia e posição, soletrar palavras difíceis, "render exatamente uma vez, sem texto extra".
- **Edição:** "change only X; keep Y unchanged", repetir invariantes a cada iteração, rotular cada imagem de entrada por papel (alvo, referência).
- **Iteração:** uma mudança por vez.
- **Validação:** inspecionar assunto, estilo, composição, texto, invariantes e itens proibidos.
- **Operação:** uma chamada por ativo (não usar `n` para ativos distintos), salvar sem sobrescrever (`hero-v2.png`), reportar prompt final.
- **Decisão código vs. bitmap:** se for ícone/logo/UI que deve casar com SVG/HTML existente, não gerar bitmap.
- `gpt-image-2`: `quality` low (rascunho) → medium/high/auto (final, texto denso); tamanhos múltiplos de 16, razão ≤ 3:1.

### Meta: melhor em **direção de arte consistente e anti-"lavado"**
Diretiva `image-directive.md`, 7 partes em ordem: Medium → Subject → Composition → Color & value → Quality → Aspect ratio → Exclusions.
- **Medium único e consistente** em todo o conjunto de peças (fotografia editorial **ou** um estilo de ilustração; não misturar).
- **Composição por papel da imagem:** *hero/full-bleed* (texto sobreposto) → deixar espaço negativo calmo; *content/cell* (texto ao lado) → preencher o quadro, sem espaço morto.
- **Cor e valor:** graduar para a paleta da marca **mas** manter foco nítido, contraste forte e profundidade tonal. Proíbe explicitamente: névoa, estourado, leitoso, chapado, baixo contraste.
- **Qualidade:** resolução alta (borda longa ≥ 1536 px), nunca upscalada; rejeitar fonte abaixo do piso.
- **Proporção pedida conforme o contêiner.**
- **Exclusões:** sem texto/números/legendas/logos/UI dentro da imagem; gráficos e rótulos vão em HTML.
- **Quando gerar:** assunto real (empresa, produto, pessoa) → buscar imagem; não gerar só para aumentar contagem.
- No chat: **subagente expande o detalhe visual** e a ferramenta recebe a conversa intercalada (texto + imagens), não um prompt seco; para cenas com vestuário implícito, ajusta roupa.

### Google (Gemini): melhor em **consistência entre imagens e controle de formato**
- `aspect_ratio` explícito (1:1, 4:5, 9:16, 16:9, 21:9, etc.).
- `image_references` com os IDs de **todas** as imagens anteriores relevantes; prefixo fixo: *"Maintaining the same character appearance, art style, and color palette as the reference image(s): ..."*.
- Para personagem/série: gerar **uma por vez**, anotar qual sujeito cada imagem estabelece.
- Query = **frase nominal centrada no assunto**, preservando todos os detalhes do usuário **sem embelezar**; manter verbos que implicam estilo; remover palavras genéricas ("imagem", "foto de").
- Edição: reescrever a descrição original incorporando a mudança + passar a referência.
- Falha: não repetir a mesma query; informar sem inventar.
- Contra-ponto: Gemini **não** expande o prompt (deixa para a ferramenta); OpenAI/Meta expandem. Para marca, expandir com critério (OpenAI) é melhor.

### xAI (Grok): melhor em **separar one-shot de pipeline**
- `generate_image` (grava em disco, para quando a imagem é insumo de documento/app/iteração) vs. componente de render direto (one-shot que o usuário só quer ver).
- `edit_image` com **imagem-base + até 4 `ref_images`**; o resultado fica ancorado na base. Para mais fontes, montar colagem antes.
- `search_images` para entidades reais em vez de gerar.
- Regra: "o prompt deve permanecer fiel ao pedido e não apresentar informação incorreta".

### Mistral (Black Forest): melhor em **prompt autocontido**
- Reescrever em inglês, conciso mas **verboso o bastante**, **sem referências a contexto inacessível** ("como falamos antes", "sua casa"); sempre descrições explícitas.
- Regenerar/alterar = elaborar o prompt anterior.
- Várias chamadas paralelas para várias imagens.

### Anthropic
Sem geração nativa; o sistema delega a skills do usuário (`imagegen`). Bom padrão de **carregar a skill antes de agir**, mas nada a copiar para qualidade de imagem.

## 3. Matriz de capacidades (o que absorver)

| Capacidade | OpenAI | Meta | Google | xAI | Mistral | No nosso prompt? |
|---|---|---|---|---|---|---|
| Classificar tipo de peça (taxonomia) | ✔ | ~ | | | | **Sim** |
| Schema rotulado de prompt | ✔ | ~ | | | | **Sim** |
| Política "normalizar vs. expandir" | ✔ | | ✔ (não embelezar) | | | **Sim** |
| Direção de arte consistente no conjunto | | ✔ | | | | **Sim** |
| Composição por papel (hero vs. célula) | | ✔ | | | | **Sim** |
| Anti-lavado / contraste / foco | | ✔ | | | | **Sim** |
| Resolução mínima / proporção do contêiner | ✔ | ✔ | ✔ | ✔ | | **Sim** |
| Texto verbatim com tipografia | ✔ | (proíbe) | ✔ | | | **Sim** (regra de decisão abaixo) |
| Edição com invariantes | ✔ | | ✔ | ✔ | | **Sim** |
| Referências rotuladas por papel | ✔ | | ✔ | ✔ | | **Sim** |
| Consistência de personagem/marca | ✔ (workflow) | ✔ (snapshot) | ✔ | ✔ | | **Sim** |
| Gráfico/tabela/dados fora do imagegen | ✔ (agent) | ✔ | | | ✔ | **Sim** |
| Buscar em vez de gerar entidades reais | | ✔ | | ✔ | | **Sim** |
| Prompt autocontido | | | | | ✔ | **Sim** |
| Rascunho barato → final caro | ✔ | | | | | **Sim** |
| Validação pós-geração | ✔ | ✔ | | | | **Sim (critic)** |
| Não expor argumentos / resposta enxuta | ✔ | | ✔ | | | **Sim** |

## 4. O que NÃO copiar

- **Gemini 2.5 flash image (`img` tag) e Gemini/Meta "Depiction Protocol / defer content judgment":** instruem o roteador a nunca recusar e delegar toda a segurança ao modelo de imagem. Para agentes de design de clientes com marca, isso é inadequado. Mantemos nossas próprias regras de segurança e de marca.
- Regras de UX do ChatGPT (resposta vazia depois de gerar, "não mencione download"): adaptar para "resposta curta com caminho do arquivo", porque nosso agente roda fora do chat.
- Mistral "nunca gerar a mesma imagem duas vezes" e Gemini "sempre gerar nova": política contraditória; decidimos por versionar (`-v2`).

## 5. Critérios de revisão (rubrica do critic)

Consolidados das fontes (OpenAI validação + Meta anti-lavado + Google consistência):

| # | Critério | Fonte | Peso |
|---|---|---|---|
| 1 | Assunto e ação conforme briefing | OpenAI | 2 |
| 2 | Estilo/medium conforme briefing e igual ao do conjunto de peças do cliente | OpenAI/Meta | 1 |
| 3 | Composição adequada ao papel (hero com espaço negativo / célula preenchida) | Meta | 1 |
| 4 | Cor: paleta da marca + contraste forte + foco nítido; sem aspecto lavado | Meta | 2 |
| 5 | Texto exato (quando houver), legível, sem extras | OpenAI | 2 |
| 6 | Sem defeitos (anatomia, mãos, objetos, artefatos) | geral | 1 |
| 7 | Resolução e proporção corretas | Meta/Google | 0,5 |
| 8 | Invariantes preservados (edição) / personagem consistente (série) | OpenAI/Google | 0,5 |
| 9 | Vinculação de atributos (cor/objeto ligado ao elemento certo), contagem e negações respeitadas | PromptEnhancer (docs/05) | 1 |
| 10 | Itens proibidos ausentes (logo inventado, watermark, texto indevido, pessoa real sem referência, dado inventado) | OpenAI/Meta | veto |

*Rubrica v2: acrescentou o item 9 (docs/05, seção 6) e ampliou os vetos. Pesos usados no código: ver `test/run_comparison.py`.*

Nota final = soma ponderada normalizada para 0–10. Aprovar com ≥ 8 e sem veto. Reprovou → feedback focado **em uma mudança por vez** (OpenAI) e regerar (máx. 2 ciclos).
