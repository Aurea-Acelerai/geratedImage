# Fontes de dados de cliente no banco compartilhado do CRM (mapa por código)

Data: 04/11/2026. Autor: eng-banco (somente leitura, sem acesso ao banco, sem credenciais). Status: **pronto para revisão** (não aprovado, C16).

Objetivo: o chat de design (`test/chat_server.py`) deve passar a puxar cliente, imagens e celebridades direto do Supabase compartilhado do CRM. Esta nota mapeia **o que o código e as migrations dizem**. Nada foi conectado em produção; nenhuma credencial foi procurada ou usada.

Legenda: **[F]** fato com arquivo:linha. **[H]** hipótese, a confirmar por consulta somente leitura autorizada ou pelo Kelvin.

## 0. Fontes usadas e ressalvas (C10)

Aliases de caminho usados nas citações:

| Alias | Caminho |
|---|---|
| `BASE` | `/Users/kelvin.wendell/Documents/GitHub/crm-acelerai-v2/supabase/migrations/20260117000000_crm_preview_baseline.sql` |
| `HIST` | `.../crm-acelerai-v2/supabase/migration-history/` |
| `TIPOS` | `.../crm-acelerai-v2/packages/types/src/supabase.ts` |
| `OBS` | `.../crm-acelerai-v2/docs/supabase/observed/2026-09-23/` (retrato de produção de 23/09, MCP somente leitura) |
| `EDGE` | `/Users/kelvin.wendell/Documents/GitHub/Comercial/.claude/worktrees/crm-889-plano-conclusao/Projetos/crm-acelerai-v2/supabase/edge-snapshots/` (cópia do código das Edge Functions; repositório `Comercial`, commit `6efeb0c3`) |

- Repositório canônico usado: `crm-acelerai-v2`, checkout atual na branch `kelvinwendell/crm-889-so-cair-lead-para-quem-esta-ativo` (HEAD `471c3498`, 29/10/2026), com `master` em `00516d01` e merge-base igual a `00516d01`. As cópias `-fonte-unica` e `-espelho-migrations` só diferem em migrations de presença de vendedor (CRM-889), contrato e identidade de login: **nenhuma toca cliente, marca ou celebridade** (`diff` das listas de migrations). Nenhum checkout foi feito.
- **A fonte do DDL é o baseline** (`BASE`), pois as migrations antigas foram trocadas por `SELECT 1` e a fonte original está em `HIST` (ex.: `supabase/migrations/20260326100000_create_onboarding_identity.sql:1-3`) [F]. O baseline é um dump de "preview"; o estado real de produção só é provado pelo retrato `OBS` (23/09, com ~6 semanas) [H sobre deriva desde então]. Reconferir por consulta antes de implementar.
- O código das Edge Functions de onboarding **não está em `crm-acelerai-v2/supabase/functions`** [F: `ls` não lista nenhuma função de onboarding/logo/identity]; achei apenas em `EDGE` (cópia de snapshot) [F]. Quem é o dono e qual versão está publicada é [H].
- Os repositórios `acelerai-vision`, `integracoes-crm` e `integracao-mgs` **não definem tabelas de cliente/marca/celebridade próprias**. Só consomem: Vision espelha `celebridadesReferencia` (`acelerai-vision/docs/pipeline-implementation.md:61`) [F]; `integracoes-crm` lê `celebridadesReferencia.nome` para Atendy/Omie (`integracoes-crm/.context/modules/cadastrar-cliente-atendy/README.md:76`, `.../dashboard/omie/README.md:44`) [F]; `integracao-mgs` não tem nada relevante (grep vazio) [F].
- Divergência de regra (C10): `crm-acelerai-v2/.context/security.md` ainda diz "R-SEM-RLS: não propor RLS"; a Regra da Casa C13 (27/10) diz que o agente **propõe** e só humano aplica. Esta nota segue C13.
- Os contratos em `docs/supabase/contracts/*` são de 23/09 e têm pontos defasados (ex.: `public.imagemProposta.md` aponta `compras.imagemproposta_id` sem dizer que a FK é para `idproposta` uuid, não para `id` bigint; ver 3.9).

## 1. Inventário

### 1.1 O elo central: **a marca vive na COMPRA, não no cliente** [F]

`onboarding_identity`, `onboarding_briefings`, `onboarding_logo_history`, `onboarding_identity_submissions` têm chave `compra_id` (1:1 ou 1:N com `compras`), **não `cliente_id`** (`BASE:38330`, `38225`, `38401`, `38369`; FKs `BASE:50464,50479,50484,50499`). O elo cliente → marca é `clientes.id` ← `compras.cliente_id` (`BASE:49844`, `ON DELETE CASCADE`) → `onboarding_*.compra_id`. Um cliente com várias compras (renovação, upsell) pode ter várias identidades. **Regra de qual compra vale é de negócio: pergunta Q1.**

Elegibilidade que o próprio onboarding usa: `compras.clicksign_status = 'Assinado'` **e** (`checkout_status = 'pago'` **ou** `vendaaprovada = true`) (`EDGE/list-onboarding-eligible-purchases/list-onboarding-eligible-purchases/index.ts:94-98`; `EDGE/get-onboarding-data/get-onboarding-data/index.ts:161-181`) [F].

### 1.2 Cliente e cadastro

| Objeto | Colunas relevantes (tipo) | Chaves / relações | Cardinalidade | Fonte |
|---|---|---|---|---|
| `public.clientes` | `id` uuid PK; `lead_id` uuid; `nome` text NOT NULL; `nome_fantasia` text; `razaosocial` text; `segmento` uuid; `subsegmento` uuid; `classificacao_id` uuid; `status` enum `status_producaocompra`; `created_at`/`updated_at` timestamptz (default `now() AT TIME ZONE 'America/Sao_Paulo'`). PII: `email`, `telefone`, `cpf`, `cnpj`, `endereco_completo`, `cep`, `logradouro`, `numero`, `complemento`, `bairro`, `cidade`, `estado`, `data_nascimento`, `observacoes`, `signatario`, `nps`, `valortotalcompra`, `ticketmedio`, `quantidadecompras`, `cnpj_snapshot` jsonb, `bdc_snapshot` jsonb | FK `lead_id`→`leads.lead_id` (`BASE:49799`); `segmento`→`segmentos.id` (`49804`); `subsegmento`→`subsegmento.id` (`49809`); `vendedorresponsavel`→`vendedores.id` (`49814`); `classificacao_id`→`cliente_classificacao.id` (`49794`) | 1 cliente : N compras | `BASE:29438-29481` |
| `public.compras` | `id` uuid; `cliente_id` uuid; `celebridade` uuid (principal); `segmento`/`subsegmento` uuid; `leadid` uuid; `imagemproposta_id` uuid; `cancelado` **jsonb**; `vendarecusada` bool; `is_test` bool; `checkout_status` enum (`aguardando_pagamento`,`pago`,`recusado`,`cancelado`,`expirado`,`parcialmente_pago`); `clicksign_status` text; `vendaaprovada` bool; `created_at` timestamptz (default SP naïve) | FK `cliente_id`→`clientes` (`49844`); `celebridade`→`celebridadesReferencia` (`49824`); `imagemproposta_id`→`imagemProposta(idproposta)` (`49854`) | 1:N | `BASE:2061-2160`; enum `BASE:280-287` |
| `public.segmentos` (id uuid, nome, active) / `public.subsegmento` (id, nome, segmento uuid, descricao) / `public.negocio` (id, nome, segmento_id, subsegmento_id, ativo, porte_comercial) | taxonomia comercial; vira o "setor" | `clientes`/`compras` apontam para segmentos e subsegmento | catálogo | `BASE:30546,30569,30149` |
| `public.leads` | tem `empresa`, `instagram`, `analise_instagram_ia(_resumido)`, `celebridadeDesejada`, mas **também** e-mail, telefone, `cpf_cnpj`, `faturamento_*`, `analise_ia` | `leads.lead_id` | secundário | `TIPOS:5757-5830` |
| `get_dossie_lead(p_lead_id)` (RPC `SECURITY DEFINER`) | dossiê **comercial** do lead: score, tier, faturamento, regime tributário, BigDataCorp, Receita Federal. **Não é o dossiê de marca** | `GRANT` a `authenticated`, `service_role`, `intel_dossie` | por lead | `BASE:12618-12706`, `53413-53416` |
| `bi.clientes`, `bi.mv_clientes` | cópias de `clientes` **com PII** (cpf, email, telefone) para BI | leitura `bi_readonly` | - | `BASE:29544-29590`, `55170` |

### 1.3 Identidade de marca (onboarding)

| Objeto | Colunas | Chaves | Observações | Fonte |
|---|---|---|---|---|
| `public.onboarding_identity` | `id` uuid PK; `compra_id` uuid **UNIQUE** NOT NULL; `choice` text CHECK(`add_now`,`later`); `logo_path` text; `brand_palette` text[] NOT NULL default `{}`; `font_choice` text; `campaign_images_paths` text[]; `campaign_notes` text (texto livre do cliente); `production_path` CHECK(`standard`,`hybrid`); `site_url`; `instagram_handle` (sem @); `brand_display_name` (precede `clientes.nome` em todos os jobs de IA); `created_at`/`updated_at` timestamptz | FK `compra_id`→`compras` `ON DELETE CASCADE` (`BASE:50479`); UNIQUE `BASE:45781` | **1:1 com a compra** | `BASE:38330-38354`; `HIST/20260424184940_onboarding_edit_and_logo_history.sql:3-12` |
| `public.onboarding_logo_history` | `id`; `compra_id`; `logo_path` NOT NULL; `original_filename`; `mime_type`; `size_bytes`; `uploaded_at`; `uploaded_by_user_id`→`auth.users`; `is_active` bool; `source` CHECK(`unknown`,`admin`,`public_onboarding`) | índice único parcial **1 ativo por compra** (`HIST/20260424184940...sql:27-28`) | 1:N por compra; o logo vigente é `is_active = true` | `BASE:38401-38419`; FKs `BASE:50499,50504` |
| `public.onboarding_identity_submissions` | trilha imutável: `compra_id`, `identity_id`, `logo_history_id`, `source`, `choice`, `site_url`, `instagram_handle`, `campaign_notes`, `brand_palette`, `production_path`, `logo_*`, `submitted_at`, `metadata` jsonb | FKs `BASE:50484,50489,50494` | 1:N, histórico | `BASE:38369-38397`. **Não usar no chat:** é auditoria |
| `public.onboarding_briefings` | `compra_id` **UNIQUE**; `mode` (`text`,`audio`,`both`); `brief_text`; `audio_path`; `transcript`; `briefing_json` jsonb; `citations_json` jsonb; `status` (`pending`,`done`,`error`); `provider`, `prompt_version` etc. | `BASE:45756` unique; FK `BASE:50464` | 1:1. `briefing_json` (jsonb) guarda `objetivo_campanha`, `publico_alvo`, `tom_voz`, `mensagem_central`, `cta_principal`, `insights_pecas[]` | `BASE:38225-38266`; chaves lidas em `EDGE/create-ai-campaign-job/create-ai-campaign-job/index.ts:326-350` |
| `public.onboarding_enrichment_jobs` | `compra_id`; `extracted_palette` text[]; `extracted_palette_source` (`logo_algorithm`,`logo_gemini`,`site_css`,...); `detected_font`; `detected_font_source`; `font_validated`; fases e `phases_log` jsonb | FK por `compra_id` | 1:N (jobs) | `BASE:38296-38328` |
| `public.onboarding_progress`, `onboarding_access(_events)`, `onboarding_acceptances`, `onboarding_copy(_versions)` | progresso, acesso, aceites (`metadata`, IP/UA possíveis [H]) | por `compra_id` | **fora do escopo do chat** | `OBS/tables.tsv` |
| `public.ai_campaign_jobs` / `ai_campaign_assets` | peças geradas pelo pipeline do CRM: `job_id`, `group_name` (`moderna`,`clean`,`retail`), `format` (`1:1`,`4:5`,`16:9`,`9:16`), `image_url` (**caminho no bucket** quando não começa com `http`), `width`,`height`,`status` | `ai_campaign_jobs.compra_id` | 1 job : N assets | `BASE:32228-32290`; assinatura em `EDGE/get-ai-campaign-status/get-ai-campaign-status/index.ts:94-108` |
| `public.previewLogoCeleb` | prévias de logo com celebridade: `url_image`, `celebridade` (**texto**, nome), `segmento` uuid, `thumbnail`, `url_image_ai`, `template_id` | sem FK para cliente | catálogo de templates, não é do cliente | `BASE:38665-38675` |
| `public.garden_jobs` (+ `creatives`, `creative_history`, `turbo_config`) | pipeline paralelo de geração de imagem ("Garden"/post-gen); **já existe geração de imagem dentro do CRM** | RLS off no retrato | [H] sobreposição funcional com este chat | `BASE:36158`; `OBS/tables.tsv:296`; `EDGE/post-gen/post-gen/index.ts` |

### 1.4 Celebridades

| Objeto | Colunas | Chaves | Observações | Fonte |
|---|---|---|---|---|
| `public.celebridadesReferencia` (**canônica**) | `id` **uuid**; `nome`; `nomeJuridico`; `fotoPrincipal`, `fotoSecundaria`, `fotoMobile` (URLs); `ativo` bool; `nivel`; `gruponovo`; `description`; `instagram_followers` bigint; `celeb_favorita`; `is_pair`; `celebridade_duplas` uuid[]; `sgc_uuid` | FK `sgc_uuid`→`sgc_celebridades.uuid` (`49739`); `gruponovo`→`blocos_valor.bloco` (`50089`). Referenciada por `compras.celebridade`, `compras_celebridades`, `imagemProposta.celebridade1..3`, `leads.celebridadeDesejada`, `bloqueiosCelebridades`, `observacoes_bloqueios_celebridades` | catálogo | `BASE:29384-29409` |
| `public.celebridades` (**legada**, `id` bigint) | `nome`, `fotoPrincipal/Secundaria/Mobile`, `ativo` | sem FKs de entrada observadas | comentário da outra tabela: "duplicate of celebridades" (`BASE:29409`). `post-turbo-generate` ainda lê esta (`EDGE/post-turbo-generate/.../index.ts:228-236`) | `BASE:34128-34146` |
| `public.compras_celebridades` | `id` uuid; `compra_id`; `celebridade_id`→`celebridadesReferencia`; `principal` bool; `origem` text default `troca` | UNIQUE(`compra_id`,`celebridade_id`) (`BASE:44981`); FKs `49829,49834` (sem `ON DELETE`) | **N:N** compra↔celebridade. "Exatamente 1 `principal=true` por compra, espelhada em `compras.celebridade`" | `BASE:34695-34712`; escrita em `apps/crm-shell/src/features/cs/troca-celebridade/api/troca-celebridade-api.ts:195-240` |
| `public.celebridade_omie_projeto` | mapa celebridade→projeto Omie: `celebridade_id` uuid, `omie_projeto_id`, `omie_projeto_cod_int`, ... | - | **financeiro, nunca ao chat** | `BASE:34093-34110` |
| `public.sgc_celebridades` | cadastro externo SGC: `name`, `avatar`, `supplier_commission`, `businessman_commission`, `celebrity_commission`, `salesforce_*` | `uuid` UNIQUE | **comissões: confidencial, nunca ao chat** | `BASE:39300-39325` |
| `public.vra_marcas_pipeline` | **não é celebridade**: Kanban do parceiro VRA, `compra_id` PK (1:1), `etapa` (`novo`,`negociando`,`fechado`,`perdido`), `disponivel_em`, `notas` | FK `compra_id`→`compras` CASCADE | irrelevante para o chat | `BASE:42782-42810` |
| `public.bloqueiosCelebridades` | restrição de exclusividade por praça. **A coluna `cliente` é FK para `compras`, não para `clientes`** (`BASE:49694`) | - | irrelevante para o chat | `BASE:29328`; `troca-celebridade-api.ts:247-250` |
| `public.imagemProposta` | proposta: `idproposta` uuid, `id` bigint, `id_lead`, `celebridade1..3` uuid, `nome_empresa`, `imagem` text, `pdf_v2_url`, valores | FKs `BASE:50144-50154` | financeiro (valores); só se precisar da proposta | `BASE:30336-30412` |

### 1.5 Buckets de Storage

Ver seção 4 (tabela completa com visibilidade e como obter URL).

### 1.6 Roles do banco que já existem [F]

`BASE:25-30` cria os papéis `acelera_design_tool_ro`, `atendy_readonly`, `aurea_recall_ro`, `bi_readonly`, `intel_dossie`, `portal_reader`. O `acelera_design_tool_ro` tem `USAGE` em `public` (`BASE:52271`), `SELECT` em `compras` (`52464`), `leads` (`52739`) e **`celebridadesReferencia`** (`55048`), e política de leitura `USING (true)` em compras e leads (`HIST/reconciliation-20260921-access/verify-catalog.sql:1977-1983`). **Não** tem `SELECT` em `clientes`, `onboarding_*`, `compras_celebridades`, nem acesso ao bucket `onboarding-identity` [F]. O nome sugere ferramenta de design; **quem é o dono e se é este chat é [H] / pergunta Q9**. São papéis com login (conexão direta Postgres), não necessariamente via API REST [H].

## 2. Dado pessoal e o que NÃO vai ao chat nem ao gerador de imagem (LGPD)

Fato de código que eleva o risco: o `client.json` inteiro é injetado **verbatim** no system prompt (`test/run_comparison.py:47-50`, `json.dumps(client_ctx...)`) e no prompt do crítico/VLM (`test/critic.py:107`). **Qualquer campo extra que entrar no JSON do cliente vai para a OpenAI/Anthropic.** Portanto o adaptador precisa de **lista permitida (whitelist)**, nunca "tudo menos o proibido" [F].

**Pode entrar no `client.json`/prompt (lista permitida proposta):** nome de exibição da marca, setor/segmento/subsegmento (nomes), paleta (hex), fonte (nome), tom, público-alvo, estilo, site (URL pública da marca), `@` do Instagram da marca, nome artístico da celebridade, imagens do logo e de referência (como arquivo, não como URL assinada).

**Nunca vai ao chat, ao prompt, ao log nem ao `client.json`:**

| Grupo | Colunas / objetos | Por quê |
|---|---|---|
| Identificação pessoal | `clientes.cpf`, `cnpj` (pode ser MEI = pessoa física), `email`, `telefone`, `data_nascimento`, `signatario`, `razaosocial`, `cnpj_snapshot`, `bdc_snapshot`, `leads.email/celularBot/cpf_cnpj/facebook` | dado pessoal direto (LGPD art. 5º I) |
| Endereço | `endereco_completo`, `cep`, `logradouro`, `numero`, `complemento`, `bairro`; `cidade`/`estado` só se for decisão de negócio (praça) | localização de pessoa natural |
| Financeiro/comercial | `valor_*`, `ticketmedio`, `valortotalcompra`, `forma_pagamento`, `checkout_*`, `clicksign_*` (signers), `contrato_storage_url`, `numero_contrato`, `faturamento_*`, `lead_score*`, `get_dossie_lead`, `imagemProposta.valor*`, `celebridade_omie_projeto`, `sgc_celebridades.*commission*` | sigilo comercial e dado financeiro |
| Texto livre do cliente | `clientes.observacoes`, `compras.observacoes`, `comentario_vendedor`, `onboarding_identity.campaign_notes`, `onboarding_briefings.brief_text`, `transcript`, `audio_path`, `citations_json` | o cliente pode ter digitado telefone, e-mail, nome de terceiros. Se for usar `campaign_notes`, **filtrar** padrões de CPF/telefone/e-mail antes (proposta) |
| Auditoria/acesso | `onboarding_identity_submissions.metadata`, `onboarding_acceptances.metadata`, `onboarding_access*`, `logs_cliente`, `uploaded_by_user_id` | pode conter IP, user-agent, usuário interno [H] |
| Pessoa em foto | qualquer arquivo de `campaign_images_paths`, `LogoClientes`, `producao-attachments` pode conter rosto de pessoa identificável | imagem de pessoa natural é dado pessoal; enviar a provedor externo exige base legal |
| Celebridade | direito de uso de imagem: o contrato do bucket diz "direito de uso da imagem não é avaliado aqui" (`docs/supabase/contracts/buckets/storage.celebs.md`, campo `sensitivity`) | uso de semelhança de celebridade num gerador de imagem é decisão jurídica/comercial: **Q6** |

Regras de minimização (C8/C2): se um campo faltar, o chat mostra "indisponível", **nunca** paleta vazia como se a marca não tivesse cores (C2, "falha nunca vira zero").

## 3. Armadilhas dos dados

1. **Marca por compra, não por cliente** (1.1). Query por `cliente_id` sem escolher a compra mistura identidades [F].
2. **`compras.celebridade` x `compras_celebridades`**: a compra pode ter só o espelho `compras.celebridade` (compras antigas, sem linhas na N:N) ou as duas. Resolver com a N:N e cair para `compras.celebridade` quando a compra não tiver linhas (`BASE:34712` comentário; `troca-celebridade-api.ts:195-240`) [F quanto à regra de espelho; H quanto a compras antigas sem linhas].
3. **Duas tabelas de celebridade**: `celebridades` (id bigint, legada) e `celebridadesReferencia` (id uuid, canônica). `post-turbo-generate` ainda usa a legada por `nome` (`EDGE/post-turbo-generate/post-turbo-generate/index.ts:228-236`). Os UUIDs de `compras_celebridades` só existem na canônica (FK `BASE:49829`) [F].
4. **camelCase e minúsculas misturados**: `"celebridadesReferencia"`, `"fotoPrincipal"`, `"fotoMobile"`, `"nomeJuridico"`, `"imagemProposta"` exigem aspas duplas no SQL; `clientes.vendedorresponsavel` minúsculo vs `leads.vendedorResponsavel` (`docs/supabase/contracts/tables/public.clientes.md`, seção Entradas) [F].
5. **Nomes singulares**: `subsegmento` e `negocio` (singular), não `subsegmentos` [F: `BASE:30569,30149`].
6. **jsonb que deveria ser coluna / texto que deveria ser outra coisa**: `compras.cancelado` é **jsonb** (nulo = não cancelado), use `crm_compra_nao_cancelada(cancelado, vendarecusada)` (`BASE:4859-4863`, critério "CRM-20") [F]; `brand_palette` é `text[]` sem CHECK de formato (hex não garantido) [F: `BASE:38330-38354` sem CHECK], validar `^#[0-9A-Fa-f]{6}$` no adaptador; `onboarding_briefings.briefing_json` é jsonb sem schema (campos lidos por chave em `create-ai-campaign-job/index.ts:326-350`) [F]; `clientes.nps`, `quantidadecompras`, `valortotalcompra`, `ticketmedio` são **text** (`BASE:29438-29481`) [F].
7. **Timezone SP**: `clientes`/`compras`/`jobs_producao` têm default `now() AT TIME ZONE 'America/Sao_Paulo'` em coluna `timestamptz` (`BASE:2061-2075`, `29438-29470`, `36301-36320`), ou seja, instantes deslocados ~3 h; `imagemProposta.created_at` também (`docs/supabase/contracts/tables/public.imagemProposta.md`, "naive-SP") [F]. As tabelas `onboarding_*`, `ai_campaign_*` usam `now()` normal [F: `BASE:38330-38354`, `32228-32290`]. Para "últimos 30 dias" de entregas, não misture as duas famílias sem converter.
8. **Tipos gerados defasados**: `TIPOS` (19/10/2026, `git log` do arquivo) **não tem** `onboarding_identity.brand_display_name`, `clientes.bdc_snapshot`/`email_opt_in_*`, nem as tabelas `onboarding_logo_history`/`onboarding_identity_submissions` (grep por essas chaves em `TIPOS` não retorna nada; `TIPOS:9159-9172` lista `onboarding_identity` sem `brand_display_name`) [F]. Não gerar o adaptador a partir de `TIPOS`; usar `BASE`.
9. **Contrato defasado de `imagemProposta`**: o contrato descreve `id` bigint; a FK de `compras.imagemproposta_id` é para `idproposta` uuid (`BASE:49854`) [F].
10. **Duplicidades**: UNIQUE(`compra_id`,`celebridade_id`) evita duplicata na N:N (`BASE:44981`), mas **não** há UNIQUE em `celebridadesReferencia.nome` (`BASE:44886` só PK): nomes repetidos/duplas (`is_pair`, `celebridade_duplas`) podem gerar mais de uma linha para o mesmo nome [H]. `post-gen` busca por `ilike nome ... limit 1` (`EDGE/post-gen/post-gen/index.ts:80-92`), o que escolhe arbitrariamente em caso de duplicata [F quanto ao código].
11. **Tabelas de backup com cópia de clientes** foram apagadas (CRM-852, `supabase/migrations/20261016202136_crm_852_apagar_tabelas_backup.sql:1-30`); não usar nomes `bkp_*`/`_backup_*` [F]. O `OBS` de 23/09 ainda os lista.
12. **Dados de teste**: `compras.is_test` e leads de teste existem (`BASE:2125`, `2254`); R-LEAD-TESTE/C12 proíbe testar com lead real. Filtrar `is_test` e validar o adaptador só com compras de teste [F].
13. **`foto*` em celebridades aponta para vários buckets**: 6 URLs em `celebs` e 64 em `celebs-corpo` (`OBS/storage_url_refs.tsv`); arquivos PNG de ~2,8 MiB em média (`docs/supabase/contracts/buckets/storage.celebs.md`) [F]: baixar com miniatura (ver 4).
14. **Chave de cliente do chat**: o chat usa id inteiro/slug (`client_71.json`, `chat_server.py:67-82`); o banco usa uuid. Não há id numérico de cliente em `clientes` [F]. **Q1/Q2**.

## 4. Buckets: público x privado e como obter a URL (sem chave)

Retrato de 23/09 (`OBS/buckets.tsv`, `OBS/storage_objects.tsv`) [F]:

| Bucket | Visibilidade | Conteúdo / caminho | Como obter URL de imagem | Uso no chat |
|---|---|---|---|---|
| `celebs`, `celebs-corpo`, `celebs-final`, `celebs-total` | **público** | fotos de celebridade; o caminho **não é montado pelo código**, a URL completa vem gravada em `celebridadesReferencia."fotoPrincipal"/"fotoSecundaria"/"fotoMobile"` (`docs/supabase/contracts/buckets/storage.celebs.md`) | **URL pública direta** (a coluna já é a URL). Miniatura: trocar `/storage/v1/object/public/` por `/storage/v1/render/image/public/` com `width`/`height` (`apps/crm-shell/src/features/proposta/lib/thumb-url.ts:2,16`) | sim (celebridade) |
| `previewLogoCelebridade`, `...Creatomate`, `...Thumb` | público | prévias com celebridade | URL pública (referência em `previewLogoCeleb`) | não |
| `onboarding-identity` | **privado**; policies só de `service_role` (INSERT/SELECT) (`HIST/20260326100002_onboarding_identity_storage.sql:4-12`) | logo em `{compra_id}/logos/{uuid}.{ext}` (`EDGE/save-onboarding-identity/.../index.ts:222`; `EDGE/admin-upload-logo/.../index.ts:67`); 43 objetos, png/jpeg/webp/svg | **URL assinada** (`createSignedUrl`) criada no **servidor com service role**: `EDGE/create-ai-campaign-job/.../index.ts:265-267` usa `AI_CAMPAIGN_URL_EXPIRY_SECONDS` default **604800 s (7 dias)**; `admin-upload-logo/.../index.ts:131-133` também 7 dias | sim (logo e imagens de campanha) |
| `LogoClientes` (443 obj., png) e `previewLogoClientes` (434 obj.) | **privado** | sem consumidor no código, sem dono, sem coluna do banco que os referencie (`docs/supabase/reference/storage-buckets.md:220-230,290-300`; `OBS/storage_refs_db.tsv` sem linhas) ; upload via protocolo S3 com `service_role` de um cliente Node não localizado (`docs/supabase/surfaces/storage.md:111-113`) | assinatura (1 criação em 24 h) | **não usar** até o Kelvin dizer o que são (Q8) |
| `ai-campaign-assets` | privado, 10 MiB, png/jpeg/webp | peças geradas; `ai_campaign_assets.image_url` guarda **caminho** | `createSignedUrl` quando `image_url` não começa com `http` (`EDGE/get-ai-campaign-status/.../index.ts:94-108`) | opcional (peças) |
| `nanobanana-references` | privado | 1 objeto de referência do gerador | assinatura (`create-ai-campaign-job/index.ts:47-49`) | não |
| `producao-attachments` | **público**, 50 MiB | anexos espelhados do ClickUp (`producao_attachments.url_supabase`); `producao_tasks.client_id` aponta para `producao_clients`, **sem FK para `clientes`** (`BASE:50674`) | URL pública gravada em `url_supabase` | [H] possível fonte de "peças entregues"; ligação por nome é frágil (Q5) |
| `img_vendedores` | público | foto de funcionário (PII) | - | **não** |
| `chat-media`, `wa-media`, `contratos-assinados`, `boletos`, `propostas-pdf`, `transaction-attachments`, `suporte-imagens` | vários | mensagens, contratos, boletos | - | **não** (PII/financeiro) |

Pontos de segurança confirmados:
- URL assinada **não pode ser revogada** pelo projeto (só expira): `docs/supabase/surfaces/storage.md:118-121` [F]. Para o chat, **assinar com validade curta (minutos), baixar no servidor e não gravar a URL**.
- Só `service_role` lê `onboarding-identity` [F]. Logo, o chat só obtém o logo/imagens de campanha por (a) `service_role` no servidor local (hoje a única via existente) ou (b) um mecanismo novo proposto na seção 7.
- Policy global `chat_media_allow_all_insert` (`WITH CHECK true`) deixa qualquer papel, inclusive `anon`, enviar arquivo para qualquer bucket (`OBS/storage_policies.tsv:21`) [F]. Não é um risco de leitura, mas significa que **conteúdo de bucket público não é confiável** (pode ter sido enviado por terceiro): tratar download como entrada não confiável (tipo/tamanho, SSRF já tratado no chat).

## 5. PROPOSTA de mapeamento para o `client.json` do chat

Formato atual (`test/client_71.json`): `id, name, sector, audience, tone, palette[], typography, image_style, approved_references[], deliveries_last_30d`. Assets (`test/clients/71/assets.json`): `id, kind (pessoa|referencia|logo|peca|produto), name, alias, file, mime`.

| Campo do chat | Origem proposta (banco) | Situação |
|---|---|---|
| `id` | `clientes.id` (uuid) como string | **decisão (Q1/Q2)**: o chat hoje usa slug/inteiro; verificar se `slug()` aceita uuid (hipótese) |
| `name` | `onboarding_identity.brand_display_name` > `clientes.nome_fantasia` > `clientes.nome` | [F] precedência do `brand_display_name` (`create-ai-campaign-job/index.ts:308-310`). O código do CRM usa `nome` **antes** de `nome_fantasia` (`:300-303`); preferir `nome_fantasia` é **[H]** (**Q3**: `nome` pode ser pessoa física) |
| `sector` | `segmentos.nome` (+ `subsegmento.nome`) via `clientes.segmento/subsegmento` (ou `compras.*`) | existe, mas é taxonomia **comercial**, mais grossa que "moda praia" (**lacuna parcial**, Q4) |
| `audience` | `onboarding_briefings.briefing_json->>'publico_alvo'` onde `status='done'` | [F] campo; é texto gerado por IA, qualidade [H]; vazio se o cliente não fez briefing |
| `tone` | `briefing_json->>'tom_voz'` | idem |
| `palette` | `onboarding_identity.brand_palette` (validar hex); fallback `onboarding_enrichment_jobs.extracted_palette` (extraída por algoritmo/Gemini/CSS) | [F] colunas; formato hex **[H]** |
| `typography` | `onboarding_identity.font_choice` (valor semântico desconhecido: nome da fonte ou opção do formulário?); fallback `onboarding_enrichment_jobs.detected_font` | **lacuna parcial**: o chat usa frase descritiva ("sans-serif geométrica..."); o banco só tem nome/escolha (Q4) |
| `image_style` | **não existe** | **LACUNA.** Aproximações: `campaign_notes` (texto livre do cliente, com risco de PII) e `briefing_json.insights_pecas[].direcao_criativa`. `ai_campaign_assets.group_name` (`moderna`,`clean`,`retail`) é estilo do **gerador**, não da marca |
| `approved_references` | **não existe flag de aprovação** | **LACUNA.** Candidatos sem noção de "aprovado": `campaign_images_paths` (enviadas pelo cliente), `ai_campaign_assets` com `status='completed'` (geradas pelo CRM) |
| `deliveries_last_30d` | **não existe coluna**; candidatos: `ai_campaign_assets` `completed` (timestamp normal), `jobs_producao`/`tarefas_producao` concluídas (timestamp **SP naïve**), `producao_tasks` | **LACUNA de definição (Q5)**: "entrega" é regra de negócio |
| (novo) `site_url`, `instagram_handle` | `onboarding_identity.site_url`, `instagram_handle` | existem; hoje o `client.json` não tem esses campos; o chat tem busca web e já trata SSRF |
| (novo) `celebrities[]` | `compras_celebridades` + `celebridadesReferencia` (`id`, `nome`, `principal`, URLs `foto*`) | existe; uso de semelhança é **Q6** |

`assets.json` (cada item do banco vira um asset local/virtual):

| `kind` do chat | Origem | Observação |
|---|---|---|
| `logo` | `onboarding_logo_history` (`is_active=true` primeiro) → `logo_path` no bucket `onboarding-identity` | `name` = `original_filename` (pode conter nome de pessoa [H]; preferir nome neutro); `mime` = `mime_type` |
| `referencia` | `onboarding_identity.campaign_images_paths[]` | sem nome/mime no banco (inferir pela extensão); podem ter pessoas |
| `peca` | `ai_campaign_assets` completed (bucket `ai-campaign-assets`) | não é "peça já entregue ao cliente" com certeza (Q5) |
| `pessoa` | foto de celebridade (`fotoPrincipal`) | o `KIND_ROLE["pessoa"]` do chat diz "foto de pessoa real **com autorização**" (`chat_server.py:44-48`); autorização de celebridade = Q6 |
| `produto` | **não existe** no banco | **LACUNA** |

Lacunas que o chat continua dono (continuam locais): `alias` de asset, conversas, `carry`, histórico (conforme `docs/12-memoria-na-vercel.md`, banco **próprio** do chat; **não** gravar nada no banco do CRM).

### Perguntas de regra de negócio para o Kelvin (C8: não inventei)

- **Q1.** Qual é a "chave do cliente" no chat: `clientes.id`, `compras.id` (a marca é por compra), `leads.lead_id` ou outro? E, para cliente com várias compras, qual compra define a marca: a mais recente elegível, a vigente (`fimdireitouso`), a que o usuário escolhe?
- **Q2.** Quais clientes aparecem no seletor do chat: só os elegíveis do onboarding (assinado e pago), todos, só ativos? Cancelados e `is_test` ficam fora?
- **Q3.** Nome exibido: `brand_display_name` > `nome_fantasia` > `nome`? Como tratar pessoa física (nome da pessoa não deve ir ao prompt)?
- **Q4.** Setor e tipografia: basta a taxonomia comercial (`segmentos`/`subsegmento`) e o nome da fonte, ou o chat deve manter campos editáveis localmente (`sector` detalhado, `typography`, `image_style`) e **mesclar** com o banco? Quem prevalece em conflito (banco ou edição local)?
- **Q5.** Definição de "entrega" (`deliveries_last_30d`) e de "referência aprovada" (`approved_references`): de onde sai e quem aprova? Há onde ficam as "peças entregues" (ClickUp espelhado em `producao_*`, `ai_campaign_assets`, outro)?
- **Q6.** Pode o chat gerar imagem usando a foto/semelhança de uma celebridade do catálogo? Há contrato/autorização de uso de imagem para geração por IA? (O contrato do bucket registra que isso **não** foi avaliado.)
- **Q7.** Enviar a foto de logo ou de referência do cliente a provedores externos de IA (OpenAI/Anthropic) tem base legal/consentimento? Há política da Aurea sobre isso?
- **Q8.** O que são `LogoClientes` e `previewLogoClientes` (maiores acervos de logo, sem dono no código)? Podem ser fonte oficial de logo?
- **Q9.** `acelera_design_tool_ro` é do chat de design? Se sim, quem criou e qual o escopo desejado (hoje só lê `compras`, `leads`, `celebridadesReferencia`)?
- **Q10.** O chat será só leitura sempre? (Recomendação desta nota: sim, nunca escrever no CRM.)

## 6. SQL somente leitura proposto

Todas são **HIPÓTESE (H)** quanto ao resultado até rodar com autorização; as colunas, tipos e JOINs são **fato (F)** conforme `BASE`. Sem `SELECT *`; sem colunas de PII; todas com `LIMIT`. Parâmetros `$1..$n` (nunca concatenar texto). Para `ilike`, o servidor deve **escapar `%` `_` `\`** do termo e usar `escape '\'`. Rodar em transação `READ ONLY` com `statement_timeout` curto. Ao testar: usar compras `is_test = true` (C12/R-LEAD-TESTE).

Elegibilidade comum (F, `EDGE/list-onboarding-eligible-purchases/.../index.ts:94-98` + `BASE:4859`):
`k.clicksign_status = 'Assinado' and (k.checkout_status = 'pago' or k.vendaaprovada is true) and public.crm_compra_nao_cancelada(k.cancelado, k.vendarecusada) and coalesce(k.is_test,false) = false`. Aplicá-la como padrão é **[H] pendente de Q2**.

**Q-A. Listar clientes (marca, setor; sem PII)**

```sql
-- $1 = termo (nullable, já escapado), $2 = limite (<= 50)
with elegiveis as (
  select distinct on (k.cliente_id)
         k.cliente_id, k.id as compra_id, k.created_at, k.segmento, k.subsegmento
    from public.compras k
   where k.clicksign_status = 'Assinado'
     and (k.checkout_status = 'pago' or k.vendaaprovada is true)
     and public.crm_compra_nao_cancelada(k.cancelado, k.vendarecusada)
     and coalesce(k.is_test, false) = false
   order by k.cliente_id, k.created_at desc          -- H: "mais recente" (Q1)
)
select c.id as cliente_id,
       e.compra_id,
       coalesce(nullif(btrim(oi.brand_display_name), ''),
                nullif(btrim(c.nome_fantasia), ''), c.nome) as nome_exibicao,   -- H: precedência (Q3)
       sg.nome as setor
  from elegiveis e
  join public.clientes c            on c.id = e.cliente_id
  left join public.onboarding_identity oi on oi.compra_id = e.compra_id
  left join public.segmentos sg     on sg.id = coalesce(e.segmento, c.segmento)
 where $1::text is null
    or coalesce(nullif(btrim(oi.brand_display_name), ''), nullif(btrim(c.nome_fantasia), ''), c.nome)
       ilike '%' || $1 || '%' escape '\'
 order by nome_exibicao
 limit least($2, 50);
```

**Q-B. Carregar um cliente (campos permitidos)**

```sql
-- $1 = clientes.id (uuid). Compra escolhida: mais recente elegível (H, Q1)
select c.id as cliente_id, k.id as compra_id,
       coalesce(nullif(btrim(oi.brand_display_name), ''),
                nullif(btrim(c.nome_fantasia), ''), c.nome) as nome_exibicao,
       sg.nome as segmento, ssg.nome as subsegmento,
       oi.brand_palette, oi.font_choice, oi.site_url, oi.instagram_handle,
       oi.updated_at as identidade_atualizada_em,
       b.briefing_json ->> 'publico_alvo'       as publico_alvo,
       b.briefing_json ->> 'tom_voz'            as tom_voz,
       b.briefing_json ->> 'objetivo_campanha'  as objetivo,
       b.briefing_json ->> 'mensagem_central'   as mensagem_central,
       ej.extracted_palette, ej.detected_font
  from public.clientes c
  join lateral (
        select k.* from public.compras k
         where k.cliente_id = c.id
           and k.clicksign_status = 'Assinado'
           and (k.checkout_status = 'pago' or k.vendaaprovada is true)
           and public.crm_compra_nao_cancelada(k.cancelado, k.vendarecusada)
           and coalesce(k.is_test, false) = false
         order by k.created_at desc limit 1) k on true
  left join public.onboarding_identity oi on oi.compra_id = k.id
  left join public.onboarding_briefings b on b.compra_id = k.id and b.status = 'done'
  left join lateral (select e.extracted_palette, e.detected_font
                       from public.onboarding_enrichment_jobs e
                      where e.compra_id = k.id order by e.created_at desc limit 1) ej on true
  left join public.segmentos sg   on sg.id  = coalesce(k.segmento, c.segmento)
  left join public.subsegmento ssg on ssg.id = coalesce(k.subsegmento, c.subsegmento)
 where c.id = $1
 limit 1;
```
`campaign_notes`, `brief_text`, `transcript` ficam **fora** de propósito (texto livre, seção 2). Se Q4 pedir `campaign_notes`, passar por filtro de PII antes.

**Q-C. Listar logos e fotos do cliente (caminhos; URL é assinada pelo servidor)**

```sql
-- logos: $1 = clientes.id
select h.id, h.compra_id, h.logo_path, h.mime_type, h.size_bytes, h.uploaded_at, h.is_active, h.source
  from public.onboarding_logo_history h
  join public.compras k on k.id = h.compra_id
 where k.cliente_id = $1 and coalesce(k.is_test, false) = false
 order by h.is_active desc, h.uploaded_at desc
 limit 20;

-- imagens de campanha enviadas pelo cliente
select oi.compra_id, p.path
  from public.compras k
  join public.onboarding_identity oi on oi.compra_id = k.id
  cross join lateral unnest(coalesce(oi.campaign_images_paths, '{}')) as p(path)
 where k.cliente_id = $1 and coalesce(k.is_test, false) = false
 limit 50;

-- peças geradas pelo pipeline do CRM (opcional)
select a.id, a.group_name, a.format, a.image_url as path_ou_url, a.width, a.height, a.created_at
  from public.ai_campaign_assets a
  join public.ai_campaign_jobs j on j.id = a.job_id
  join public.compras k on k.id = j.compra_id
 where k.cliente_id = $1 and a.status = 'completed'
 order by a.created_at desc
 limit 50;
```
Depois o servidor (nunca o navegador) assina cada `logo_path`/`path` no bucket `onboarding-identity` (e `image_url` em `ai-campaign-assets` quando não for `http`) com validade curta e baixa o arquivo (seção 4).

**Q-D. Celebridades associadas ao cliente**

```sql
-- $1 = clientes.id
with sel as (
  select k.id as compra_id, cc.celebridade_id, cc.principal
    from public.compras k
    join public.compras_celebridades cc on cc.compra_id = k.id
   where k.cliente_id = $1 and coalesce(k.is_test, false) = false
  union all
  select k.id, k.celebridade, true                     -- compra sem linhas na N:N: espelho
    from public.compras k
   where k.cliente_id = $1 and coalesce(k.is_test, false) = false
     and k.celebridade is not null
     and not exists (select 1 from public.compras_celebridades cc where cc.compra_id = k.id)
)
select s.compra_id, s.principal, cr.id as celebridade_id, cr.nome,
       cr."fotoPrincipal", cr."fotoSecundaria", cr."fotoMobile", cr.nivel, cr.ativo
  from sel s
  join public."celebridadesReferencia" cr on cr.id = s.celebridade_id
 order by s.principal desc, cr.nome
 limit 20;
```
Sem `nomeJuridico`, `description` nem `instagram_followers` por padrão (nome jurídico é dado de contrato).

**Q-E. Buscar celebridade por nome**

```sql
-- $1 = termo escapado; usa as extensões unaccent e pg_trgm, que existem (OBS/extensions.tsv)
select cr.id, cr.nome, cr."fotoPrincipal", cr."fotoMobile", cr.nivel, cr.ativo
  from public."celebridadesReferencia" cr
 where coalesce(cr.ativo, true)
   and unaccent(cr.nome) ilike '%' || unaccent($1) || '%' escape '\'
 order by similarity(unaccent(cr.nome), unaccent($1)) desc, cr.nome
 limit 20;
```
Se `unaccent`/`pg_trgm` não estiverem acessíveis ao papel de leitura, cair para `ilike` simples [H]. `ativo is null` é tratado como ativo aqui; confirmar (Q-regra: o `post-turbo-generate` exige `ativo = true`, `EDGE/post-turbo-generate/.../index.ts:230-233`).

**Consultas de contagem para dimensionar (sem PII), a rodar quando houver acesso autorizado:** `select count(*) from public.onboarding_identity;`, `... where brand_palette <> '{}'`, `... from public.onboarding_logo_history where is_active`, `... from public.compras_celebridades`, e quantas compras elegíveis têm identidade/briefing `done`. Servem para saber **quantos clientes teriam marca preenchida** (hoje desconhecido: [H]).

## 7. Riscos de segurança e como o chat deve acessar

### 7.1 O que as migrations/retrato dizem sobre o acesso [F, retrato de 23/09; reconferir]

| Objeto | RLS | Quem lê hoje | Fonte |
|---|---|---|---|
| `clientes` | **ligada**, mas `Public Read clientes USING (true)` para `anon` e `authenticated`; também Insert/Update `true` para `anon` | **a chave pública lê o cadastro com CPF/e-mail/telefone** | `BASE:51293,51305,51321,51595`; `GRANT ALL ... TO anon` `BASE:55056` |
| `compras` | ligada; `Public Read compras USING (true)` a `anon` | idem para vendas | `BASE:51309`, `52459` |
| `onboarding_identity` | **desligada**, `GRANT ALL` a `anon` e `authenticated` | **a chave pública lê e pode escrever** paleta, notas, caminhos de logo | `OBS/tables.tsv` (off); `BASE:57126-57129` |
| `onboarding_briefings` | **desligada**, `GRANT ALL` a `anon` | briefing e `transcript` legíveis por `anon` | `OBS/tables.tsv`; `BASE:57098-57101` |
| `compras_celebridades`, `celebridadesReferencia`, `celebridades` | **desligada**, `GRANT ALL` a `anon` | catálogo aberto (e escrita aberta) | `BASE:56102-56104`, `55044-55046`, `55948-55950`; `OBS/rls_gaps.tsv` (`compras_celebridades` em `sensivel_sem_rls_select_anon`) |
| `onboarding_logo_history` | ligada; 4 policies `authenticated USING/WITH CHECK (true)` | **qualquer usuário logado** lê e altera todos os logos | `BASE:51850-51865` |
| `onboarding_identity_submissions` | ligada, **sem policy** | só `service_role` (fechada) | `BASE:51847`; `OBS/rls_gaps.tsv` |
| Bucket `onboarding-identity` | privado; policies só `service_role` | só servidor | `HIST/20260326100002...sql:4-12` |
| Buckets `celebs*`, `producao-attachments`, `previewLogoCelebridade*` | **públicos** | qualquer pessoa com a URL | `OBS/buckets.tsv`; contrato de `celebs` |
| `chat_media_allow_all_insert` | `WITH CHECK (true)` | qualquer papel envia arquivo a **qualquer** bucket | `OBS/storage_policies.tsv:21` |

Consequência: **hoje seria tecnicamente possível** o chat ler tudo com a chave pública (`anon`). **Não deve**: isso seria usar justamente a brecha que a segurança está tentando fechar (inventário de 26/10: 136 tabelas legíveis por `anon`, cf. Regras da Casa; `docs/supabase/surfaces/access.md`), e qualquer fechamento futuro (onda de RLS, decisão humana C13/CRM-119) **quebraria o chat sem aviso**. O chat será mais um consumidor a mapear.

### 7.2 Recomendação de acesso (PROPOSTA em texto; **nada aplicado**, C13)

1. **Nunca no navegador.** Nenhuma chave do Supabase (nem a publicável) vai para `index.html`. O navegador fala só com o `chat_server.py` local; o servidor fala com o banco. (Hoje o chat já é só `127.0.0.1`; ver `docs/12-memoria-na-vercel.md`, §1, para o risco de subir na Vercel sem login.)
2. **`service_role` NUNCA** neste chat: ignora RLS, lê CPF de todos os clientes. Já houve incidente com chave de serviço em bundle (CRM-1204, `Contexto integracoes-crm`). Se hoje a única via para assinar URL do bucket privado é `service_role`, **não adotar**; ver item 4.
3. **Credencial de leitura mínima e dedicada ao chat** (sugestão: papel novo, p.ex. `design_chat_ro`, ou reutilizar `acelera_design_tool_ro` **se o Kelvin confirmar que é este uso**, Q9): `USAGE` no schema da view e `SELECT` **apenas** nas views/RPC do item 4. Segredo só em variável de ambiente do servidor, fora do repositório (`.gitignore` já ignora `.env`? confirmar), rotacionável, sem log.
4. **Preferir views ou RPCs dedicadas** (proposta), em vez de dar `SELECT` em tabelas com PII:
   - `design.v_cliente_marca` (colunas da Q-B, **sem PII**, já com a regra de compra e elegibilidade decididas em Q1/Q2) e `design.v_cliente_lista` (Q-A);
   - `design.v_cliente_celebridades` (Q-D) e `design.f_buscar_celebridade(text)` (Q-E);
   - `design.v_cliente_logos` entregando **caminhos**, não segredos;
   - **assinatura de URL**: como `onboarding-identity` só deixa `service_role` assinar, a alternativa de menor privilégio é uma **Edge Function** pequena (`design-chat-asset`), que verifica um token próprio do chat, aceita só `{cliente_id, logo|referencia}`, assina com validade de poucos minutos e devolve a URL; ela usa `service_role` **dentro do Supabase**, nunca no chat. Alternativa: policy de `SELECT` em `storage.objects` limitada a esse bucket para o papel do chat (proposta; exige decisão humana).
   - As views devem ser `SECURITY INVOKER` quando possível, `REVOKE ALL FROM PUBLIC, anon, authenticated`, e `GRANT SELECT` só ao papel do chat; se `SECURITY DEFINER`, com `search_path` fixo (regra do agente de banco).
   - **Isto é proposta**; o pacote SQL (DDL + testes de `anon` negado + `EXPLAIN`) só será preparado por tarefa própria e **aplicado por humano** (C13).
5. **Consultas somente leitura:** conexão em modo `READ ONLY`, `statement_timeout` curto, todas parametrizadas, `LIMIT` sempre. O adaptador não tem caminho de escrita (C9: aditivo; o CRM nunca é alterado pelo chat).
6. **Whitelist no adaptador** (seção 2): campos fora da lista nunca chegam ao `client.json`, ao prompt, ao log (`logs/events.jsonl` já não grava imagens) nem ao disco. Um teste automático deve falhar se aparecer CPF/telefone/e-mail no JSON gerado (C3: prova).
7. **Cache e retenção:** baixar logo/imagens para o cache local do chat só enquanto o cliente estiver selecionado; não persistir URL assinada; apagar ao trocar de cliente (LGPD, minimização). Definir retenção (Q7).
8. **Banco do chat separado do CRM:** memória, conversas e `assets` do chat vão para o banco próprio planejado em `docs/12-memoria-na-vercel.md`; o CRM é **fonte só de leitura**.
9. **Falha fechada e visível (C2):** se o banco ficar indisponível ou o cliente não tiver identidade, a UI mostra "marca indisponível/sem identidade cadastrada", nunca paleta vazia como se fosse real; o modo "livre" (sem marca) continua funcionando.
10. **Mapa de consumidores (regra do agente de banco):** registrar o chat como consumidor de `clientes`/`onboarding_*`/`celebridadesReferencia` antes de qualquer onda de fechamento de RLS, para a decisão humana saber que existe.
11. **Verificação antes de implementar (C3/C10):** com o acesso somente leitura que o Kelvin autorizar, rodar (a) catálogo de `information_schema.columns` das tabelas da seção 1 para confirmar o baseline contra produção; (b) as consultas de inventário do agente de banco (políticas `true`, tabelas sem RLS com `SELECT` a `anon`); (c) as contagens da seção 6; (d) teste com compra `is_test`.

### Aprendizados

- **O que eu precisaria saber antes:** a marca do cliente no banco é por **compra** (`onboarding_*.compra_id`), não por cliente; `compras.celebridade` é só o espelho da celebridade principal e a lista completa está em `compras_celebridades`. Os tipos gerados (`packages/types/src/supabase.ts`) estão defasados em relação ao baseline; para DDL, a fonte confiável é `supabase/migrations/20260117000000_crm_preview_baseline.sql` (as migrations antigas viraram `SELECT 1`). O código das Edge Functions de onboarding só aparece em cópias de snapshot (`Comercial/.claude/worktrees/.../edge-snapshots`), não em `crm-acelerai-v2/supabase/functions`.
- **O que deu errado e como percebi:** no zsh, `echo ======` e `--include=*.ts` sem aspas falharam (erro "not found"/"no matches"); passei a quotar e a usar `grep -E` com aspas. A primeira busca por código de onboarding no repositório principal voltou vazia; só achei a implementação procurando em `Comercial/`.
- **O que funcionou e vale repetir:** ler o `grep -n` do baseline por `CREATE TABLE` + `ADD CONSTRAINT ... FOREIGN KEY` + `GRANT`/`CREATE POLICY` para obter colunas, FKs e acesso com número de linha; cruzar com o retrato `docs/supabase/observed/2026-09-23/` (RLS e buckets) e com o código real das Edge Functions (`create-ai-campaign-job`) que já resolve identidade, celebridade, nome da marca e URL assinada, que é o melhor modelo do que o chat precisa. Constatar que o `client.json` inteiro vai ao prompt (`run_comparison.py:50`, `critic.py:107`) é o argumento mais forte para a whitelist.

**Pronto para revisão.**
