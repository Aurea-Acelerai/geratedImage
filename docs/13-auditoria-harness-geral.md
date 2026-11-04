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
- O `.gitignore` ignorava `.claude/` inteiro, o que impediria versionar agentes locais. **Atualização (rodada 2):** passou a ignorar só `.claude/worktrees/` e `settings.local.json`.
- **Atualização (rodada 2):** a sincronização Obsidian → repositório foi implementada (`tools/obsidian_sync.py`, 32 verificações) e 3 agentes estão em `.claude/agents/`; registro de origem, hashes e alterações em `agents/IMPORTACAO.md`.

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
| F | Chamadas de texto/critic (`ui.openai_post`, `/chat/completions`) sem retry nem orçamento | **Corrigido na rodada 4** (§11) |
| G | Não há `ExecutionService`/Runner: o preflight está espalhado em `run_chat` | **Corrigido na rodada 3** (`test/runner.py`, ver §10). Falta estender retry/orçamento às chamadas de texto (F) |
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
- (Rodada 1) Sem Runner, sem registro de pais/filhos entre versões de imagem, sem benchmark versionado, sem hooks. Importação de agentes, sincronização Obsidian e `CLAUDE.md` entraram na rodada 2.
- A verificação de tamanho do arquivo devolvido só lê PNG; JPEG e WebP têm só a assinatura checada.

## 8. Plano incremental (próximas rodadas, uma melhoria por vez)

1. ~~**Obsidian → repositório**~~ (feito na rodada 2): `tools/obsidian_sync.py` com origem explícita, manifesto com hashes, dry-run por padrão, conflitos, sem sobrescrita nem exclusão, contenção de caminho. Antes: decidir o `.gitignore` de `.claude/agents` e quais agentes `eng-*` adaptar (propostos: `eng-api`, `eng-qa-revisor`, `eng-arquiteto`; um agente de direção de arte precisa ser **criado**, pois o vault não tem).
2. ~~**Runner com preflight leve**~~ (feito nas rodadas 3 e 4, §10 e §11): reunir validação de schema, referências, parâmetros, credenciais, orçamento e imagem-base ambígua num serviço testável, e estender retry/orçamento às chamadas de texto/critic (achado F).
3. **Estado e versões de imagem**: `parent_id`, modelo, parâmetros e versão do prompt por imagem; teste "mude só a cor" resolvendo a base antes da chamada.
4. **Benchmark versionado** (dev e avaliação final separados) com casos gerais, não só marketing; rodada com a API real **só com orçamento aprovado pelo Kelvin**; baseline externo apenas por comparação cega com referências obtidas legitimamente.
5. **Avaliação de texto**: OCR com limites explícitos para fidelidade textual; revisão humana nos casos subjetivos.

## 9. Como rodar

```bash
cd test
sh run_tests.sh                  # tudo, sem chave e sem custo
python3 -I test_provider.py      # só o adapter
```

## 10. Rodada 3: Runner com preflight leve

**O que existe agora** (`test/runner.py`, ligado ao `run_chat` em `chat_server.py`):

- **Preflight** (`Runner.preflight`): roda sem rede e sem custo, **antes do briefing** (chamada paga de texto) e de qualquer imagem. Junta **todos** os problemas numa única falha (`PreflightError` → `ApiError 400`, "Pré-checagem falhou, nada foi gerado: …"). Checagens: esquema; referências existentes e pertencentes à biblioteca do escopo; imagem-base sem ambiguidade (duas bases, ou edição sem base); credencial; parâmetros aceitos pelo modelo (a mesma `validate_request` do adapter, com o alvo já convertido e a máscara final); orçamento da sessão e da tarefa; armazenamento gravável (escrita de teste só no disco).
- **Orçamento limita o plano:** se o orçamento cobre menos gerações que o planejado, o laço é reduzido e o usuário recebe o aviso.
- **Laço com decisão explícita** (`Runner.run` + `Runner.decide`): aceita (aprovada ou revisão desligada), repara, **escalona** para revisão humana ou para. Escalona por limite de reparos, orçamento esgotado ou **ausência de progresso** (nota igual ou menor que a da tentativa anterior). Escalonado = a melhor tentativa é entregue, marcada como não aprovada, com aviso claro. Em empate de nota fica a primeira tentativa.
- **Trace por execução** (`msg["trace"]` e no turno da conversa): por tentativa, decisão e motivo, nota, tempo, `request_id`, tentativas de rede e `usage`. Sem prompt, chave nem imagem. A resposta traz também `preflight` (as checagens feitas).
- **Sem contorno:** o preflight não tem flag para ser pulado e o adapter valida de novo a requisição exata antes de cada chamada paga. A suíte de testes **não** roda dentro da requisição: continua em `test/run_tests.sh` e no CI.

**Mudança de comportamento (intencional):** antes, a revisão reprovada sempre gastava os 2 reparos; agora para quando a nota não melhora. O preflight é pulado em modo demonstração e sem chave (o fluxo "só briefing via Claude CLI" não gera imagem).

**Testes novos:** `test_runner.py` (45 verificações; 14 mutações no Runner, todas mortas) e `e2e_preflight.py` (a falha acontece antes do briefing: 0 chamadas ao redator e 0 imagens; escalonamento por orçamento). Os e2e existentes passam inalterados, inclusive nas variantes `E2E_STORE=memory` e `E2E_INLINE=1`.

**Ainda aberto:** (F, resolvido na rodada 4) chamadas de texto e do critic sem retry nem orçamento; concorrência só é aplicada na hora da chamada (semáforo), não no preflight; sem `parent_id` entre versões de imagem; benchmark; OCR. Nada disso foi medido com a API real.

## 11. Rodada 4: retry e orçamento nas chamadas de texto

**O que mudou** (`test/provider.py`, `test/ui_server.py`, `test/chat_server.py`):

- O adapter foi dividido numa base `OpenAIClient` (retry seguro, `Retry-After`, orçamento, concorrência, cancelamento, trace) com duas especializações: `OpenAIImages` (como antes) e `OpenAIText.post_json` (chat completions e responses). `ui.openai_post` agora usa o cliente de texto; por isso **todas** as chamadas de texto herdam o comportamento: briefing, critic, resolvedor de contexto, localização de região e pesquisa de marca. Os 74 testes de imagem passaram sem alteração depois da refatoração.
- **Retry:** mesma política das imagens (429 sem `insufficient_quota`, 5xx, falha de conexão antes do envio; timeout de leitura não repete).
- **Orçamento de texto, separado do de imagem:** por sessão (`TEXT_BUDGET_SESSION`, padrão 2000) e por mensagem do chat (`TEXT_BUDGET_TASK`, padrão 40); concorrência `TEXT_CONCURRENCY` (padrão 4). **Os padrões são escolhas do harness, não fatos do provedor.** O orçamento da tarefa vem do contexto da thread (`task_scope`), então nenhum ponto de chamada precisou mudar. O preflight barra a tarefa se o orçamento de texto da sessão estiver esgotado.
- **Validação de payload e de resposta:** endpoint suportado, modelo, `messages`/`input`, JSON serializável; resposta JSON, `choices[0].message`, conteúdo não vazio (ou chamada de ferramenta), recusa (`refusal`) e `error` em `/responses`. Não há tabela de capacidades de texto, então modelo e parâmetros de texto **não** são validados contra a documentação.
- **Trace:** cada chamada de texto vai ao mesmo `events.jsonl` (operação, modelo, tentativa, status, `request_id`, latência, tamanho do corpo e `usage` só com campos numéricos). As chamadas de imagem também passaram a registrar `usage`. Nunca prompt, chave nem imagem.
- **Bug achado na integração:** `resolve_turn`, a localização de região e a pesquisa capturam qualquer exceção ("nunca derruba o fluxo"), o que engoliria orçamento esgotado, requisição inválida e chave ausente como um aviso genérico. Agora essas falhas **locais** (400/429) interrompem a tarefa com a mensagem clara; falha do provedor (502, depois das repetições) segue degradando como antes.
- `ui_server.api_image` (interface de teste) passou a usar o adapter de imagens.

**Testes:** `test_provider.py` foi de 75 para 114 verificações; `test_runner.py` tem 48; `e2e_preflight.py` ganhou 3 cenários (429 de texto repetido e tarefa concluída; texto da sessão = 0 e da tarefa = 1 interrompem antes do briefing e da imagem). 11 mutações no código novo (e a regra de falha local) foram todas mortas; uma mutação no preflight de texto também.

**Ainda aberto:** `GET /models` (gratuito) segue sem retry; as chamadas de busca na web (Wikimedia) e de download de imagem não passam por este adapter; pesquisa de marca (`/responses` com busca) pode custar mais por chamada do que o orçamento por contagem reflete (o orçamento conta chamadas, não tokens); parent_id entre versões; benchmark; OCR. Nada foi medido com a API real.

## 12. Rodada 5: versões pai/filho de imagem e `GET /models` pelo adapter

**Versões de imagem** (`test/versions.py`, ligado ao `run_chat`):
- Cada geração grava `versions/<escopo>/<id>.json` pela interface Store (disco, memória e Blob): `parent_id`, `base_kind` (`generated`, `attachment` ou nenhum), `base_asset`, conversa, intenção, pedido e pedido resolvido, operação (`generate`/`edit`), **modelo, tamanho, qualidade, fidelidade**, região (local/extend), entradas (tipo e nome), ciclo, modo, skills e pacotes, **`prompt_sha` (hash do briefing) e `prompt_version` (hash do system prompt do designer)**, `request_id`, tentativas, latência e `usage`; depois do critic, nota, aprovação e vetos. **Não guarda bytes, chave nem o texto do briefing** (ele já está no turno da conversa).
- A base é resolvida **antes** da chamada (botão "Editar esta imagem", alvo citado ou última imagem) e marcada na entrada com `src_image_id`; `base_of` extrai daí o pai. "Mude só a cor", sem botão, grava como pai a imagem anterior. Alvo vindo de **anexo** não tem pai gerado: grava `base_kind=attachment` e o asset.
- `POST /api/lineage` ({scope|client, id}) devolve o registro, a genealogia (raiz → imagem, com `complete` e o motivo quando falta registro, há ciclo ou a cadeia é longa demais) e os filhos. Id e escopo são validados (nada de `../`). Gravar a versão nunca derruba a geração: o erro vai ao log.
- Testes: `test_versions.py` (54 verificações, nos stores de memória e de disco; 10 mutações mortas) e `e2e_versions.py` (do zero → edição pelo botão → "mude só a cor" sem botão: pai certo, genealogia de 3 níveis, ciclos de revisão com nota por ciclo, 404/400; 5 mutações na ligação mortas).

**`GET /models` pelo adapter:** `OpenAIText.get_json` (só `/models` e `/models/<id>` simples, sem segmento de pontos) com a mesma política de retry e `Retry-After`; é consulta gratuita e **não gasta orçamento**. `chat_server.openai_get` usa o adapter e mantém as mensagens de erro de antes. `api_setkey` e `api_models` seguem funcionando (cobertos por teste). 5 mutações mortas.

**Fora do adapter, de propósito:** a busca na Wikimedia, o download de imagem (`fetch_image`) e o fetch de páginas da pesquisa de logo. São chamadas a terceiros, não à OpenAI, e a lógica de logo em cadeia está em edição por outra sessão; mexer ali agora só criaria conflito. Continuam com timeout e allowlist de redirecionamento próprios, sem política de retry comum.

**Limites:** a genealogia só cobre imagens geradas a partir desta versão (conversas antigas não têm registro: `/api/lineage` devolve 404 para elas). Nada foi medido com a API real.

## 13. Rodada 5 (cont.): OCR com limites e benchmark versionado

Feito por um subagente com escopo fechado (só arquivos novos) e **revisado de forma independente**: reexecutei os testes, o `validate`, as recusas do caminho pago (uma exigência por vez, com chave falsa e a base apontada para uma porta fechada), o pacote cego e o relatório; conferi que nenhum arquivo rastreado foi alterado e que o conteúdo dos casos não cita marcas nem pessoas reais.

**OCR** (`test/ocr.py`): `read_text` com backend injetável e, por padrão, o CLI `tesseract` via `subprocess` **sem shell**, com timeout. Sem tesseract o status é `unavailable`: **nenhum texto é inventado e nenhum literal passa**. `text_fidelity` devolve `match`/`near`/`missing`/`not_verified` por literal (acentos contam: "Promoção" vs "Promocao" é `near`; confiança < 60 não vale como evidência de `match`); `all_match` é `None` quando algo não foi verificado. Limites declarados no módulo: texto pequeno, fontes decorativas, baixo contraste, texto curvo e idioma fora de `lang` não são verificáveis; OCR é auxiliar, nunca prova de fidelidade. **Tesseract não está instalado nesta máquina**, então o caminho com motor real não foi exercitado.

**Benchmark** (`bench/`, `test/bench.py`): 17 casos de desenvolvimento e 9 de avaliação final, 14 categorias (fotografia, ilustração, cena complexa, texto em português, produto, personagem recorrente, edição local, troca de fundo, preservação de identidade, múltiplas referências, peça de marketing, diagrama com dados do usuário, pedido ambíguo, falha esperada). Cada caso: pedido, referências (imagens reais são fornecidas por você em `bench/refs/`, fora do git), critérios obrigatórios (`human`, `auto:size`, `auto:ocr`, `auto:preservation`), o que não pode mudar, literais de texto, tamanho e método de avaliação.
- **Dev x final:** o final é travado por hash (`bench/LOCK.json`, com histórico de cada mudança e razão); `validate` falha se mudou sem `lock`, se há quase duplicata dev x final ou categoria faltando. Rodar o final exige `--confirm-final`, avisa que não serve para ajustar prompts e registra o uso em `bench/final_runs.jsonl`.
- **Gasto:** `run --generate openai` exige `OPENAI_API_KEY`, `--max-calls N` (N ≥ 1) **e** `--i-approve-paid-calls`, usa o adapter com orçamento de N chamadas pagas e registra o que ficou sem rodar. `--generate fake` é local, sem rede. **Nenhuma execução com a API real foi feita.**
- **Checagens:** `auto:size` compara o tamanho real; `auto:ocr` devolve `not_verified` sem motor; critérios humanos ficam `pending_human`; **`auto:preservation` está `not_implemented`** (exigiria comparação de pixels fora de uma máscara). Nada vira "passou" sem evidência.
- **Comparação cega:** `blind-pack` embaralha com seed registrada, anonimiza (X/Y), limpa metadados auxiliares de PNG e põe o mapeamento só em `key.json`, **fora** da pasta do avaliador; `blind-score` agrega preferência e fidelidade; `report` inclui custo (em chamadas pagas e `usage`), latência e tentativas.
- **Regra de honestidade:** sem baseline externo legítimo com avaliação cega, o relatório diz "**paridade ainda não demonstrada**" e nunca afirma superioridade ou igualdade com o ChatGPT. Não se automatiza o acesso à interface dele.
- Testes: `test_ocr` (68 verificações) e `test_bench` (218; bloqueiam acesso a socket); 61 mutações do subagente morreram (3 sobreviveram na 1ª rodada e os testes foram reforçados).

**Não implementado:** comparação de pixels para preservação; importação de baseline externo (o formato mínimo do `results.json` está no README, sem comando); preço em dinheiro; estatística (sem teste, intervalo de confiança nem concordância entre avaliadores); o caminho `openai` do benchmark chama o adapter com o pedido literal, **sem Runner, briefing nem critic**, então os pedidos ambíguos só podem ser julgados num harness conversacional.
