# 07 — Filtro por arquivo: o que saiu de cada fonte e o que foi descartado

Visão por **arquivo de origem** (o doc 06 é por ponto de melhoria). Para cada arquivo: o que foi aproveitado, onde entrou no nosso prompt (`prompts/designer-imagegen.system.md`, v0.3) ou no resto do pacote, e o que ficou de fora e por quê.

Repositório de origem: `asgeirtj/system_prompts_leaks`. "Lido" = li o conteúdo. "Não lido" = ainda não abri o arquivo.

## 1. OpenAI

| Arquivo | Lido | Aproveitado | Onde entrou | Descartado e por quê |
|---|---|---|---|---|
| `gpt-5.6-sol.md` (e `gpt-5.5-thinking`, `gpt-5.5-instant`) | Sim | Esquema da ferramenta `image_gen.text2im` (`prompt, size, n, transparent_background, is_style_transfer, referenced_image_ids`). Gerar direto sem reconfirmar. Edição só com alvo real. Pessoa real exige foto. Argumentos da ferramenta nunca vão ao usuário. Recusar sem sugerir contorno. Python para anotar com precisão. | Prompt §2, §5, §7, §8; regra 9; ferramenta `compose_text_overlay` | Resposta vazia depois de gerar e "não mencione download": são regras de UX do chat. Nosso agente roda fora do chat e responde com o caminho do arquivo (prompt §7). Memória, busca, anúncios, personalidade e as outras ~97% do arquivo: não são de imagem. |
| `gpt-5.x-api.md` (3 arquivos, ~860 caracteres) | Sim | Só a medida: a API injeta data, verbosidade e canais, sem nada de imagem. Isso sustenta a hipótese de que o app tem um harness e a API não. | `docs/01`, `docs/02` | Nada a copiar, o conteúdo é mínimo. |
| `gpt-4o.md` | Sim (parcial) | `referenced_image_ids` só quando o usuário especificar. | Regra 9 (papéis das imagens), de forma indireta | Modelo antigo; o resto do arquivo não é de imagem. |
| `chatgpt-gpt-5-agent-mode.md` | Sim | Imagegen policies: não usar imagem para gráficos, tabelas, dataviz ou imagens com texto dentro; não retratar entidades reais (logos, marcos). | Prompt §2 e regra 11; ferramentas `render_chart`, `search_reference_image` | Restrição a "só imagens decorativas ou abstratas": é específica de slides. Para marca precisamos de fotos e peças de campanha. |
| `Codex/skills/imagegen/SKILL.md` | Sim | **Núcleo da receita.** Taxonomia de casos de uso. Schema rotulado. Normalizar vs. expandir, com lista do que pode e não pode ser acrescentado. Texto verbatim, soletrar palavras difíceis. Edição com "change only X" e invariantes. Uma mudança por vez. Uma chamada por ativo (`n` só para variações). Salvar sem sobrescrever e reportar o prompt final. Código vs. bitmap. | Prompt §3, §4 (regras 1–3, 7, 9, 10), §5, §6, §7 | O modo "built-in vs. CLI fallback": é mecânica do Codex. Nós chamamos a API direto. A regra "nunca modifique `image_gen.py`": só vale para o Codex. |
| `references/prompting.md` | Sim | Guia por tipo de peça (fotorrealismo, mockup, UI, infográfico, logo, ads, edições). Vocabulário de luz, câmera e materiais. Texto primeiro. Verbo forte no início. | Prompt "Guia por tipo de peça" e "Vocabulário de direção de arte" (v0.3) | O que é específico do fluxo do Codex (arquivos e workspace). |
| `references/sample-prompts.md` | Sim, para extrair dicas por tipo | Só as dicas por tipo, condensadas em uma ou duas linhas cada. | Prompt "Guia por tipo de peça" | **Os exemplos completos não foram trazidos.** É a maior lacuna: o arquivo original tem ~17 mil caracteres de receitas e o nosso tem poucas linhas. Proposta: pasta `references/` carregada sob demanda. |
| `references/cli.md` | Sim | Rascunho em `low`, final em `medium`/`high`. Quadrado é o mais rápido. `--dry-run` imprime o payload sem custo. `generate-batch` só quando o usuário pedir muitos ativos distintos. | Prompt §5; teste `--dry-run` | Uso do CLI em si, caminhos `tmp/imagegen/`, `CODEX_HOME`. Não usamos esse CLI. |
| `references/image-api.md` | Sim | `gpt-image-2` sempre em alta fidelidade para imagens de entrada e sem `input_fidelity`. Máscara é guiada por prompt, forma exata não é garantida. Tamanhos válidos. Quando subir a qualidade. | Prompt §5 e regra 9; ferramenta `composite_with_mask` (a máscara não garante pixels idênticos, então a composição fica por código) | Parâmetros de modelos antigos. A transparência via `gpt-image-1.5` está desatualizada: a doc de nov/2026 usa `background="transparent"` nos modelos atuais. |
| `references/codex-network.md` | Não | — | — | Rede e sandbox do Codex, fora do escopo. |
| **`scripts/image_gen.py`** | **Não** | — | — | **Esta é a parte de código e teste do Codex.** Só li a documentação do CLI, não o script. Vale ler para aproveitar `--dry-run`, validações e o formato JSONL do batch no nosso `run_comparison.py`. |

## 2. Google

| Arquivo | Lido | Aproveitado | Onde entrou | Descartado e por quê |
|---|---|---|---|---|
| `gemini-3.8-flash.md` | Sim | `aspect_ratio` explícito. `image_references` com todas as imagens relevantes anteriores. Prefixo de consistência ("Maintaining the same character appearance, art style, and color palette as..."). Gerar uma por vez em série. Query como frase nominal sem embelezar. Não repetir a query que falhou. | Prompt §5 (proporção), regra 10 (série), regras 1–3, §6 e §7 | O restante do prompt, que não trata de imagem. |
| `gemini-2.5-flash-image-preview.md` | Sim | Nomear cada elemento recorrente. Edição reescrevendo a descrição com a mudança. | Regra 10 e regra 9 | **"Depiction Protocol" e "defer content judgment":** instruem a nunca recusar e delegar a segurança ao modelo de imagem. Inadequado para cliente com marca (prompt §8 mantém julgamento próprio). Também descartada a tag `img`, que é formato do Gemini. |

## 3. Meta

| Arquivo | Lido | Aproveitado | Onde entrou | Descartado e por quê |
|---|---|---|---|---|
| `muse-agent/.../presentation/references/image-directive.md` | Sim | **Diretiva de arte em 7 partes** (medium, assunto, composição, cor e valor, qualidade, proporção, exclusões). Medium único no conjunto. Composição por papel (hero com espaço negativo, célula preenchida). Anti-lavado. Resolução mínima. Proporção do contêiner. Buscar entidade real em vez de gerar. | Prompt §3 (`role`), §4 (regras 4–6, 8), §5, rubrica itens 2–4 | Regra "sem texto, números ou legendas dentro da imagem" aplicada sem exceção: nós permitimos título curto decorativo (até ~5 palavras) com revisão, e o resto vai por código. O contexto de slides (HTML de apresentação). |
| `muse-spark-1.1-web.md` | Sim | Subagente que expande o detalhe visual antes da ferramenta. Ajustar vestuário à cena. Snapshot para sequências. | Etapa 2 (briefing) da arquitetura; "Vocabulário" (pessoas); regra 10 (parcial: usamos referências + prefixo, não snapshot) | O restante do prompt, que não trata de imagem. |

## 4. xAI, Mistral, Anthropic

| Arquivo | Lido | Aproveitado | Onde entrou | Descartado e por quê |
|---|---|---|---|---|
| `xAI/grok-4.7.md` | Sim | Separar one-shot de pipeline. Edição com imagem-base mais até 4 referências, ancorada na base. Buscar imagens para entidades reais. Prompt fiel ao pedido. | Arquitetura (rascunho assíncrono vs. fluxo completo), regra 9 (parcial), regras 1–3 | Componente de render direto do Grok, que não existe no nosso ambiente. |
| `Mistral/mistral-medium-3.5.md` | Sim | Prompt em inglês, autocontido, sem referência a contexto inacessível. Várias chamadas paralelas. | Prompt §4 | "Nunca gerar a mesma imagem duas vezes": contradiz a política de versionar (`-v2`). |
| `Anthropic/claude-fable-5.1.md` | Sim | Padrão de carregar a skill antes de agir. | `skills/designer-imagegen/SKILL.md`, `agents/designer.md` | Não há geração nativa de imagem; nada de qualidade a copiar. |

## 5. O que não veio de arquivo nenhum

Estas partes do nosso prompt não estão em prompt vazado. Vieram da documentação oficial, de artigos e de relatos (doc 05) e estão **sem teste real**:

- Composição de texto por código e *underdrawing* (relatos de uso e HN).
- Rubrica item 9 (vinculação de atributos, contagem, negação) e a ideia de critic em ciclo (pesquisa PromptEnhancer e VLM-as-judge).
- Modelos `gpt-image-2.5-sunburst` e `flare`, `safety_identifier`, tratamento de `image_generation_user_error` (documentação oficial de nov/2026).
- Triage, Brand Kit separado e poucas ferramentas ativas (caso Moda/LangChain).

## 6. Lacunas que este mapa revela

1. `scripts/image_gen.py` do Codex não foi lido. É o equivalente deles a "código e teste".
2. `sample-prompts.md` foi condensado em dicas, mas os exemplos completos não vieram. É o maior candidato a pasta `references/`.
3. O arquivo `gpt-4o.md` foi lido só no trecho da ferramenta de imagem.
