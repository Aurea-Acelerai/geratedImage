# 13. Auditoria e plano do harness geral de imagens (rodada 1, 04/11/2026)

Escopo desta rodada: inventário, baseline de testes, auditoria do protótipo `aurora-harness.zip` e do código atual, e **uma** melhoria verificável (adapter da OpenAI). Tudo abaixo foi lido ou executado nesta rodada; o que não foi está marcado como **não auditado**.

## 1. Inventário do repositório

| Item | Estado observado |
|---|---|
| Remoto | `Aurea-Acelerai/geratedImage` (branch de trabalho `claude/aurora-image-harness-755c9a`, sem push) |
| Linguagem | Python 3.9 (máquina local), só stdlib; Pillow opcional (`regionedit`) |
| Frontend / backend | `test/chat/index.html` + `test/chat_server.py` (1.7 mil linhas, `http.server`); empacotado para Vercel por `api/index.py` e `vercel.json` |
| Armazenamento | `test/store.py`: `FileStore`, `MemoryStore`, `BlobStore` (Vercel Blob), com teste de conformidade |
| Filas / banco | Nenhum. Tarefas são threads em processo (`start_job`); estado em JSON por conversa |
| Geração e edição | `make_image` em `chat_server.py`: `/images/generations` sem entrada, `/images/edits` com entradas e máscara opcional |
| Contexto | Conversa inteira em `conversations/`; imagens anexadas ficam na conversa; alvo de edição resolvido por `resolve_turn`. **Não auditado a fundo nesta rodada** |
| Modelos e chaves | `IMAGE_MODEL`, `TEXT_MODEL`, `IMAGE_QUALITY`; chave lida de `OPENAI_API_KEY` a cada chamada (ou colada na tela / Keychain) |
| Agentes e skills | `agents/designer.md`, 9 skills em `skills/`; **nenhum** `.claude/agents` versionado e **nenhum** hook |
| CLAUDE.md / AGENTS.md | Não existem no repositório (existe `HANDOFF.md`) |
| CI | Não existia. Criado `.github/workflows/test.yml` |
| Alterações locais não commitadas ao começar | Nenhuma |

## 2. Baseline dos testes (antes de qualquer alteração)

`test/run_tests.sh` rodava `e2e_brand`, `e2e_convs`, `e2e_projects`, `e2e_chat`. Resultado: os três primeiros passaram; **`e2e_projects.py` não existe** e o runner terminava em falha (`FALHOU: e2e_projects.py`). `test_store.py` (96 verificações) e `e2e_vercel.py` existiam mas não estavam no runner. Duração: cerca de 24 s.

Gargalos observáveis: a chamada de imagem não tinha repetição para erro transitório, limite de gasto, validação de tamanho/máscara nem verificação do arquivo devolvido. Não há métricas de latência medidas (nenhuma rodada com a API real foi registrada neste repositório além de `HANDOFF.md`, com 1 geração por braço).

## 3. Obsidian e agentes

Vault encontrado em `~/Documents/Obsidian Vault` (via `obsidian.json`). Li só os cabeçalhos dos agentes abaixo; **não copiei nada do vault** e não li as notas de relatórios de segurança.

| Nota | Agente | Formato | Ferramentas pedidas | Observação |
|---|---|---|---|---|
| `Agentes/Qualidade e Testes/01 - Agente QA Revisor.md` | `eng-qa-revisor` (opus) | Nota Obsidian com frontmatter próprio (`id`, `fase`, `ferramentas`) | Read, Grep, Glob, Bash, Write | Nomes de ferramentas válidos no Claude Code |
| `Agentes/API e Integrações/01 - Agente Guardião de API.md` | `eng-api` (sonnet) | idem | Read, Grep, Glob, Bash, Write, Edit | Cobre o papel "especialista em APIs" |
| `Agentes/Arquitetura e Engenharia/01 - Agente Arquiteto de Software.md` | `eng-arquiteto` (opus) | idem | Read, Grep, Glob, Bash, Write | Foco em DDD; adaptar ao contexto de imagem |
| `.agents/agentes/00-orquestrador.md` e `01`…`15` | Operação de segurança | Frontmatter com ferramentas **inexistentes** no Claude Code (`ler_codigo`, `abrir_sessoes`, `gitleaks`…) | — | Escopo é segurança de outros sistemas; não importar sem adaptação |

Conclusões:
- **O vault não tem agente de imagem, direção de arte nem avaliação de imagem.** O "Ive" citado no `HANDOFF.md` não foi localizado por nome; fica pendente com o Kelvin.
- Os agentes `eng-*` são notas longas (14 a 17 KB) em formato de vault, não definições de subagente. Importar exige: frontmatter do Claude Code (`name`, `description`, `tools`, `model`), corpo enxuto e remoção de links `[[...]]` e referências a Linear/Orquestrador. Nada disso foi ativado.
- Os agentes de segurança do `.agents` declaram ferramentas que não existem; precisam de mapeamento antes de qualquer uso.
- O `.gitignore` do repositório ignora `.claude/` inteiro: agentes locais em `.claude/agents/` **não seriam versionados**. Mudar para ignorar só `.claude/worktrees/` e `settings.local.json` é uma decisão pendente (afeta como o time compartilha agentes).
- A sincronização Obsidian → repositório (manifesto, hashes, dry-run, sem sobrescrita nem exclusão, contenção de caminho) **não foi implementada nesta rodada**.

## 4. Auditoria do protótipo `aurora-harness.zip`

Extraído em pasta isolada e lido; nada foi importado. A `LICENSE` (MIT) do zip **não foi copiada**: o repositório não tem licença e a decisão é do dono.

| # | Achado | Onde | Gravidade |
|---|---|---|---|
| 1 | Regra global de múltiplos de 16, 3:1 e faixa de pixels, escrita no código | `core/spec.py` `assert_spec`, `core/validate.py` | Média. A documentação oficial atual confirma essas regras **para os modelos 2.5**, mas não como regra global. Rejeita 1080x1350 (padrão do feed). Agora é dado por modelo (ver §6) |
| 2 | "Contraste WCAG" calculado com percentis 1 e 99 de luminância de uma caixa | `core/validate.py` `rendered_contrast` | Alta. Não identifica texto e fundo; o gate `contrast:*` aprova ou reprova por um número sem significado de acessibilidade |
| 3 | Classificação incerta vira `ig_post` em silêncio | `router/router.py` `classify` | Alta (contraria "não transformar incerteza em default") |
| 4 | O compositor desenha sempre marca, o pedido inteiro como título e o CTA "QUERO ESSE", ignorando `text_policy="none"` e o pedido | `core/compose.py` | Alta |
| 5 | O compositor desenha sobre um gradiente sintético, **nunca sobre a imagem gerada**; a "composição determinística" prometida no README não ocorre | `core/compose.py`, `cli.py` | Alta |
| 6 | `--real` ignora `--out` e `--report`; a imagem sai em `generated/attempt_N.png` | `cli.py` | Média |
| 7 | O "reparo" só acrescenta texto ao prompt e **regenera**; nunca edita a imagem anterior. `source_image` nunca é preenchido pelo roteador | `critic/critic.py`, `pipeline/generator.py` | Alta |
| 8 | Gerador sem timeout, retry, tratamento de recusa, verificação do arquivo ou fechamento do arquivo aberto | `pipeline/generator.py` | Média |
| 9 | Paleta escura, ponto focal único, "espaço para copy", CTA e lime de acento impostos a toda imagem | `core/spec.py` `build_spec` / `compile_prompt` | Alta (o produto é geral) |
| 10 | Os 8 testes verificam a própria saída sintética: o gate mede contraste na imagem que o compositor acabou de desenhar; o "loop de reparo" usa o próprio compositor como gerador. Nenhum exercita a API, a edição ou a preservação | `tests/smoke_test.py` | Alta (aprova mock, não comportamento) |
| 11 | `manifest.json` afirma `"last_test": "8/8 PASS"` como texto fixo; README diz "juiz VLM" e OCR ausentes (lacuna reconhecida) | `manifest.json`, `README.md` | Baixa |

Decisão: o protótipo é referência de ideias (gates por código, contrato de spec), não base de código. O repositório atual já cobre mais (conversa, edição localizada com máscara, critic em camadas) e foi mantido.

## 5. Auditoria do código atual (somente o que foi lido)

| # | Achado | Estado |
|---|---|---|
| A | `run_tests.sh` apontava para arquivo inexistente e deixava `test_store.py` e `e2e_vercel.py` fora | **Corrigido** |
| B | `make_image`: sem retry, sem Retry-After, sem orçamento, sem validação prévia, sem verificação do arquivo devolvido | **Corrigido** (adapter) |
| C | Edição com máscara enviava o alvo no formato original (JPEG) e a máscara em PNG; a documentação exige o **mesmo formato e tamanho** | **Corrigido** (alvo convertido para PNG antes da chamada; coberto por teste com Pillow) |
| D | `vercel.json` não incluiria `provider_capabilities.json` no pacote; a função falharia em produção na 1ª imagem | **Corrigido** |
| E | `input_fidelity=high` é enviado por padrão. A documentação só diz que `gpt-image-2` não aceita o parâmetro; para os modelos 2.5 **não verifiquei**. O recuo automático existente trata a recusa | Aberto (registrado em `provider_capabilities.json`) |
| F | Chamadas de texto/critic (`ui.openai_post`, `/chat/completions`) seguem sem retry nem orçamento | Aberto |
| G | Não há `ExecutionService`/Runner: o preflight está espalhado em `run_chat` | Aberto |
| H | Estado da conversa, resolução de imagem-base, critic e `checks.py`: não auditados a fundo | Aberto |

## 6. O que foi implementado nesta rodada

- `test/provider.py`: `OpenAIImages` com `generate`, `edit`, `validate_request`, `get_capabilities`.
  - Validação antes da chamada paga, contra `test/provider_capabilities.json` (por modelo, com fonte e data). Modelo fora da tabela: só formato e aviso. Sem fallback de edição para geração.
  - Retry só para 429 (exceto cota esgotada), 500/502/503/504 e falha de conexão antes do envio. **Timeout de leitura não repete** (pode ter sido cobrado). Backoff com teto e jitter; respeita `Retry-After`; acima do limite de espera, levanta em vez de dormir.
  - Orçamento por sessão (`IMAGE_BUDGET_SESSION`, padrão 200) e por mensagem do chat (`IMAGE_BUDGET_TASK`, padrão 8) em **chamadas pagas**, contando cada repetição. Concorrência limitada (2). Cancelamento cooperativo.
  - Verifica a resposta (JSON, `data`, base64, assinatura de imagem, tamanho devolvido) e identifica recusa (`moderation_blocked`) e parâmetro recusado.
  - Trace por tentativa em `logs/events.jsonl` (`provider_call`: operação, modelo, tamanho, status, `request_id`, latência, nº de caracteres do prompt). Sem prompt, chave nem imagem.
- `chat_server.make_image` usa o adapter; `ApiError` mantém o contrato (400 validação, 429 orçamento, 502 demais).
- `test/test_provider.py`: 75 verificações de comportamento (o que foi enviado, quantas vezes, quanto esperou, que erro saiu), mais HTTP real contra `fake_openai.py`, que ganhou injeção de falhas (`flaky429`, `always500`, `moderated`).
- Runner e CI: `test/run_tests.sh` (POSIX) cobre `test_provider`, `test_store` e os 4 e2e existentes; `.github/workflows/test.yml` roda o mesmo comando.

### Fontes verificadas em 04/11/2026 (`developers.openai.com/api/docs/guides/image-generation`)
Modelos `gpt-image-2.5-sunburst` e `gpt-image-2.5-flare`; tamanhos custom com lados múltiplos de 16, proporção até 3:1, borda até 3840 px, 655.360 a 8.294.400 pixels, `auto`; qualidade `low|medium|high|xhigh|max|auto`; máscara com canal alfa, mesmo formato e tamanho da imagem, menos de 50 MB, válida para a primeira imagem; saída `b64_json`; erro `moderation_blocked`. **Não informados na página:** limites de taxa, preço por imagem dos modelos 2.5 (cobrança por tokens), `input_fidelity` nos 2.5.

## 7. Limites e o que NÃO foi feito

- **Nada foi medido com a API real.** Todos os testes usam transporte injetado ou a OpenAI falsa. Os resultados provam montagem de requisição e tratamento de resposta, não qualidade de imagem nem paridade com o ChatGPT. **Paridade com o ChatGPT: ainda não demonstrada.**
- Orçamento em dinheiro não existe (os modelos 2.5 cobram por tokens e a página não dá preço por imagem).
- Sem Runner, sem registro de pais/filhos entre versões de imagem, sem benchmark versionado, sem importação de agentes, sem sincronização Obsidian, sem CLAUDE.md, sem hooks.
- A verificação de tamanho do arquivo devolvido só lê PNG; JPEG e WebP têm só a assinatura checada.

## 8. Plano incremental (próximas rodadas, uma melhoria por vez)

1. **Obsidian → repositório**: `tools/obsidian_sync.py` com origem explícita, manifesto com hashes, dry-run por padrão, conflitos, sem sobrescrita nem exclusão, contenção de caminho. Antes: decidir o `.gitignore` de `.claude/agents` e quais agentes `eng-*` adaptar (propostos: `eng-api`, `eng-qa-revisor`, `eng-arquiteto`; um agente de direção de arte precisa ser **criado**, pois o vault não tem).
2. **Runner com preflight leve**: reunir validação de schema, referências, parâmetros, credenciais, orçamento e imagem-base ambígua num serviço testável, e estender retry/orçamento às chamadas de texto/critic (achado F).
3. **Estado e versões de imagem**: `parent_id`, modelo, parâmetros e versão do prompt por imagem; teste "mude só a cor" resolvendo a base antes da chamada.
4. **Benchmark versionado** (dev e avaliação final separados) com casos gerais, não só marketing; rodada com a API real **só com orçamento aprovado pelo Kelvin**; baseline externo apenas por comparação cega com referências obtidas legitimamente.
5. **Avaliação de texto**: OCR com limites explícitos para fidelidade textual; revisão humana nos casos subjetivos.

## 9. Como rodar

```bash
cd test
sh run_tests.sh                  # tudo, sem chave e sem custo
python3 -I test_provider.py      # só o adapter
```
