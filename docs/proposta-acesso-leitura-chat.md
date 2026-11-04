# Proposta de acesso de leitura para o chat de design (views, RPC, papel e URLs)

Data: 04/11/2026. Autor: eng-banco. **PROPOSTA em texto: nada foi aplicado, nada foi conectado em produção, nenhuma credencial foi usada (C13).** Quem aplica é um humano. Status: **pronto para revisão**, não aprovado (C16). **Revisão 2 (04/11/2026):** decisões abertas fechadas pelo padrão recomendado (seção 0.1). **A aprovação para APLICAR no banco continua sendo de um humano (C13); nada foi aplicado.**

Base: `docs/fontes-de-dados-clientes.md` (mapa por código). Aliases: `BASE` = `/Users/kelvin.wendell/Documents/GitHub/crm-acelerai-v2/supabase/migrations/20260117000000_crm_preview_baseline.sql`; `OBS` = `.../crm-acelerai-v2/docs/supabase/observed/2026-09-23/`; `EDGE` = `/Users/kelvin.wendell/Documents/GitHub/Comercial/.claude/worktrees/crm-889-plano-conclusao/Projetos/crm-acelerai-v2/supabase/edge-snapshots/`. **[F]** fato com arquivo:linha; **[H]** hipótese.

**Aviso de frescor (C10):** o retrato do schema tem **mais de 6 semanas** (23/09/2026) e o baseline é um dump de "preview". Antes de aplicar, reconferir por consulta somente leitura: colunas (`information_schema.columns`), FKs, RLS, grants, existência dos papéis e do schema `chat_design` (seção 4.0).

Decisões do Kelvin já tomadas (C8): marca = identidade da compra **mais recente elegível** (assinada e paga, sem cancelada nem teste); só clientes elegíveis existem para o chat; acesso **somente** por views/RPC de leitura mínima, servidor local apenas; celebridades só para consultar e mostrar (nome e foto de referência com aviso de direito de imagem), **sem gerar semelhança**; chat somente leitura no CRM.

### 0.1 Decisões do Kelvin em 04/11/2026: "seguir o recomendado"

Registro: o usuário respondeu "siga com o recomendado" às perguntas abertas. Isso fecha as decisões de **desenho** abaixo; **não** é aprovação para aplicar SQL no banco (isso é um humano, C13). Nada foi aplicado.

| # | Tema | Decisão |
|---|---|---|
| 1 | "Paga" | `checkout_status in ('pago','parcialmente_pago')` **ou** `vendaaprovada is true`, alinhado à R-VENDA-PAGO do CRM (`pago` ou `parcialmente_pago`, contexto `crm-acelerai-v2` do cofre) e ao enum [F: `BASE:280-287`]. "Assinada" = `clicksign_status = 'Assinado'` |
| 2 | URL de logo privado | Edge Function `chat-design-asset` devolve **bytes**, nunca URL; protegida por **segredo de função**. Rotação do segredo e da senha do papel: humano do time de plataforma. **Responsável: EM ABERTO (pendência)** |
| 3 | `carregar_cliente_chat` | `returns table(...)` **explícito** (sem `setof` da view) |
| 4 | Celebridade `ativo IS NULL` | **não** conta como ativa (conservador): filtro `ativo is true` |
| 5 | Q3 nome exibido | `brand_display_name` > `nome_fantasia` > `nome`; `nome_origem` exposto; novo `pessoa_fisica boolean` sinaliza possível pessoa física para o chat **não tratá-la como marca** |
| 6 | Q4 setor/tipografia | **o banco prevalece**; edição local só **acrescenta** campo ausente e nunca sobrescreve o que veio do banco (regra do provedor/UI, não do banco) |
| 7 | Q5 entregas e referências aprovadas | **fora desta versão**; o chat mostra "não disponível", sem inventar |
| 8 | Q7 base legal ao enviar logo/fotos à OpenAI/Anthropic; Q8 `LogoClientes`/`previewLogoClientes` | **PENDENTES** (humano/jurídico); não bloqueiam o desenvolvimento, **bloqueiam ligar o provedor em produção** (seção 6) |

**Mudanças de contrato desta revisão** (o eng-backend precisa saber): (a) nova coluna `pessoa_fisica boolean` logo após `nome_origem` em `vw_chat_clientes_elegiveis`, `vw_chat_identidade_cliente`, `buscar_cliente_chat` e `carregar_cliente_chat`; (b) `carregar_cliente_chat` passa a `returns table` explícito (mesmas colunas da identidade); (c) elegibilidade inclui `parcialmente_pago`; (d) celebridades só com `ativo is true`. Nenhum nome de objeto mudou.

## 0. CONTRATO (nomes exatos para o eng-backend)

Schema novo: **`chat_design`** (não é o `public`; não deve entrar na lista de schemas expostos da API REST [H: a lista de produção não é legível pelo repositório, `supabase/config.toml:7-9` não a define]). Papel: **`chat_design_ro`**. Acesso do servidor local: conexão Postgres direta com esse papel (variável de ambiente do servidor, fora do repositório e do navegador), em transação `READ ONLY`. O provedor **só** usa os objetos abaixo, **nunca** tabelas de `public`.

| Objeto | Tipo | Colunas / assinatura (ordem e tipos finais) |
|---|---|---|
| `chat_design.vw_chat_clientes_elegiveis` | view | `cliente_id uuid`, `compra_id uuid`, `nome_exibicao text`, `nome_origem text` (`brand_display_name`\|`nome_fantasia`\|`nome`), `pessoa_fisica boolean` (nulo = indeterminado), `setor text`, `subsegmento text`, `tem_identidade boolean`, `atualizado_em timestamptz` |
| `chat_design.vw_chat_identidade_cliente` | view | `cliente_id uuid`, `compra_id uuid`, `nome_exibicao text`, `nome_origem text`, `pessoa_fisica boolean`, `setor text`, `subsegmento text`, `paleta text[]` (só hex válido), `tipografia text`, `tom text`, `publico_alvo text`, `descricao_marca text`, `site_url text`, `instagram_handle text`, `atualizado_em timestamptz` |
| `chat_design.vw_chat_logos_cliente` | view | `cliente_id uuid`, `compra_id uuid`, `item_id uuid`, `tipo text` (`logo`\|`referencia`), `storage_bucket text` (sempre `onboarding-identity`), `storage_path text`, `mime_type text`, `tamanho_bytes bigint`, `ativo boolean`, `ordem integer`, `enviado_em timestamptz` |
| `chat_design.vw_chat_celebridades_cliente` | view | `cliente_id uuid`, `compra_id uuid`, `celebridade_id uuid`, `nome text`, `principal boolean`, `foto_principal_url text`, `foto_mobile_url text`, `aviso_direito_imagem text`, `uso_permitido text` (constante `somente_exibicao`) |
| `chat_design.buscar_cliente_chat(q text, limite integer default 20)` | função (`SECURITY INVOKER`, `STABLE`, lê só as views) | `returns table(cliente_id uuid, nome_exibicao text, nome_origem text, pessoa_fisica boolean, setor text, tem_identidade boolean)`; `limite` limitado a 1..50 |
| `chat_design.carregar_cliente_chat(p_cliente_id uuid)` | função (`SECURITY INVOKER`, `STABLE`, lê só as views) | `returns table(cliente_id uuid, compra_id uuid, nome_exibicao text, nome_origem text, pessoa_fisica boolean, setor text, subsegmento text, paleta text[], tipografia text, tom text, publico_alvo text, descricao_marca text, site_url text, instagram_handle text, atualizado_em timestamptz)` (mesmas colunas e ordem da view, declaradas explicitamente); 0 ou 1 linha |
| `chat_design.buscar_celebridade_chat(q text, limite integer default 20)` | função (`SECURITY INVOKER`, `STABLE`, lê só as views) | `returns table(celebridade_id uuid, nome text, foto_principal_url text, foto_mobile_url text, aviso_direito_imagem text, uso_permitido text)`; `limite` 1..50 |
| Edge Function `chat-design-asset` | HTTP POST | entrada `{ "storage_path": text }`; saída **bytes da imagem** (não URL) com `Content-Type`; ver seção 3 |

Regras do contrato:
- Nenhuma coluna de PII, financeiro ou texto livre do cliente em nenhum objeto (allowlist, seção 1.1).
- `storage_path` é caminho relativo ao bucket; **nunca URL**.
- Cliente sem identidade: `tem_identidade = false` e campos de marca `NULL` (nunca string vazia nem `{}`); o provedor mostra "indisponível" (C2).
- `nome_origem` e `pessoa_fisica` (Q3 fechada): quando `pessoa_fisica` é verdadeiro, o chat não trata o nome como marca nem o envia a provedor de IA como nome de marca. `pessoa_fisica` é **[H]**: `true` se há `cpf` e não há `cnpj`; `false` se há `cnpj`; nulo se nenhum; o CPF **nunca** sai da view, só o booleano.
- Q4: o banco prevalece; o provedor mescla edição local só em campos que vieram `NULL`.
- Q5: nada de entregas nem referências aprovadas no contrato; a UI mostra "não disponível".
- `descricao_marca` é **[H]** (origem escolhida por padrão, revisável): origem proposta `briefing_json->>'mensagem_central'` limitada a 600 caracteres.
- Todas as listas têm `LIMIT`; a ordenação é determinística.

## 1. DDL proposto (não aplicar; revisão humana)

Convenções (regras do agente de banco): migration única e reversível, `lock_timeout` curto, nomes qualificados, `search_path` fixo nas funções, nenhum `USING (true)`, nada altera objeto existente (aditivo, C9).

### 1.1 Justificativa do modelo de segurança

- **Views sem `security_invoker`** (rodam como o dono, `postgres`): é deliberado e é o limite de segurança. Com `security_invoker = true` o papel do chat precisaria de `SELECT` em `clientes`/`compras`, o que reabre CPF, e-mail e telefone. Aqui a **lista de colunas da view é a barreira** (a view não projeta nenhuma coluna de PII). Precedente: as views `bi.*` do próprio banco são do `postgres` [F: `BASE:29544`, `GRANT ... bi_readonly` `BASE:55040`]. Dono `postgres` ignora RLS das tabelas base [H: confirmar `rolbypassrls` do dono e se alguma tabela usa `FORCE ROW LEVEL SECURITY`; teste 4.2 cobre]. Risco registrado em 5.
- **Funções `SECURITY INVOKER`** (nenhuma `DEFINER`), com `SET search_path = ''`, objetos qualificados, `STABLE`, `REVOKE ... FROM PUBLIC` e `GRANT EXECUTE` só ao `chat_design_ro`. Justificativa: leem **só as views** `chat_design.vw_*` (o papel já tem `SELECT` nelas), então não precisam de privilégio extra; o escape do `ilike` é feito dentro da função. Fixar `search_path` evita escalada por objeto homônimo (regra do agente de banco).
- Sem `BYPASSRLS`, sem `SUPERUSER`, sem herança.

### 1.2 DDL

```sql
-- 20261104000000_chat_design_leitura.sql  (PROPOSTA - NÃO APLICAR; humano aplica após reconferir o schema)
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

create schema if not exists chat_design;
revoke all on schema chat_design from public, anon, authenticated;

-- Compra mais recente elegível por cliente (regra decidida: Q1/Q2).
-- Elegibilidade = assinada E (pago/parcialmente_pago OU venda aprovada), não cancelada, não teste (decisão 04/11: R-VENDA-PAGO).
-- [F] EDGE/list-onboarding-eligible-purchases/.../index.ts:94-98 ; BASE:4859-4863 (crm_compra_nao_cancelada)
create or replace view chat_design.vw_chat_compra_vigente as
select distinct on (k.cliente_id)
       k.cliente_id,
       k.id           as compra_id,
       k.segmento     as compra_segmento,
       k.subsegmento  as compra_subsegmento,
       k.celebridade  as compra_celebridade
  from public.compras k
 where k.cliente_id is not null
   and k.clicksign_status = 'Assinado'
   and (k.checkout_status in ('pago', 'parcialmente_pago') or k.vendaaprovada is true)
   and public.crm_compra_nao_cancelada(k.cancelado, k.vendarecusada)
   and coalesce(k.is_test, false) = false
 order by k.cliente_id, k.created_at desc, k.id desc;
-- created_at é "SP naïve" (BASE:2061-2075); serve só para ordenar, nunca para exibir.

create or replace view chat_design.vw_chat_clientes_elegiveis as
select c.id as cliente_id,
       v.compra_id,
       coalesce(nullif(btrim(oi.brand_display_name), ''), nullif(btrim(c.nome_fantasia), ''), c.nome) as nome_exibicao,
       case when nullif(btrim(oi.brand_display_name), '') is not null then 'brand_display_name'
            when nullif(btrim(c.nome_fantasia), '')       is not null then 'nome_fantasia'
            else 'nome' end as nome_origem,                       -- H: precedência pendente (Q3)
       case when nullif(btrim(c.cnpj), '') is not null then false
            when nullif(btrim(c.cpf),  '') is not null then true
            else null end as pessoa_fisica,   -- H: heurística; só o booleano sai
       sg.nome  as setor,
       ssg.nome as subsegmento,
       (oi.id is not null and cardinality(oi.brand_palette) > 0) as tem_identidade,
       oi.updated_at as atualizado_em
  from chat_design.vw_chat_compra_vigente v
  join public.clientes c                 on c.id = v.cliente_id
  left join public.onboarding_identity oi on oi.compra_id = v.compra_id
  left join public.segmentos sg          on sg.id  = coalesce(v.compra_segmento, c.segmento)
  left join public.subsegmento ssg       on ssg.id = coalesce(v.compra_subsegmento, c.subsegmento);

create or replace view chat_design.vw_chat_identidade_cliente as
select c.id as cliente_id,
       v.compra_id,
       coalesce(nullif(btrim(oi.brand_display_name), ''), nullif(btrim(c.nome_fantasia), ''), c.nome) as nome_exibicao,
       case when nullif(btrim(oi.brand_display_name), '') is not null then 'brand_display_name'
            when nullif(btrim(c.nome_fantasia), '')       is not null then 'nome_fantasia'
            else 'nome' end as nome_origem,
       case when nullif(btrim(c.cnpj), '') is not null then false
            when nullif(btrim(c.cpf),  '') is not null then true
            else null end as pessoa_fisica,   -- H: heurística; só o booleano sai
       sg.nome  as setor,
       ssg.nome as subsegmento,
       -- só hex #RRGGBB; array vazio vira NULL (C2: ausência não é "sem cores")
       nullif(array(select p from unnest(coalesce(oi.brand_palette, '{}')) p
                     where p ~ '^#[0-9A-Fa-f]{6}$'), '{}') as paleta,
       coalesce(nullif(btrim(oi.font_choice), ''), nullif(btrim(ej.detected_font), '')) as tipografia, -- H: Q4
       left(b.briefing_json ->> 'tom_voz', 200)          as tom,
       left(b.briefing_json ->> 'publico_alvo', 400)     as publico_alvo,
       left(b.briefing_json ->> 'mensagem_central', 600) as descricao_marca,   -- H: Q4
       oi.site_url,
       oi.instagram_handle,
       oi.updated_at as atualizado_em
  from chat_design.vw_chat_compra_vigente v
  join public.clientes c                  on c.id = v.cliente_id
  left join public.onboarding_identity oi on oi.compra_id = v.compra_id
  left join public.onboarding_briefings b on b.compra_id = v.compra_id and b.status = 'done'
  left join lateral (select e.detected_font from public.onboarding_enrichment_jobs e
                      where e.compra_id = v.compra_id and e.detected_font is not null
                      order by e.created_at desc limit 1) ej on true
  left join public.segmentos sg           on sg.id  = coalesce(v.compra_segmento, c.segmento)
  left join public.subsegmento ssg        on ssg.id = coalesce(v.compra_subsegmento, c.subsegmento);
-- Fora de propósito: campaign_notes, brief_text, transcript, audio_path, citations_json, qualquer coluna de clientes/compras/leads além das citadas.

create or replace view chat_design.vw_chat_logos_cliente as
select v.cliente_id, v.compra_id, h.id as item_id, 'logo'::text as tipo,
       'onboarding-identity'::text as storage_bucket, h.logo_path as storage_path,
       h.mime_type, h.size_bytes as tamanho_bytes, h.is_active as ativo,
       case when h.is_active then 0 else 1 end as ordem, h.uploaded_at as enviado_em
  from chat_design.vw_chat_compra_vigente v
  join public.onboarding_logo_history h on h.compra_id = v.compra_id
 where h.logo_path ~ '^[0-9a-fA-F-]{36}/[A-Za-z0-9_./-]+$' and h.logo_path !~ '\.\.'
union all
select v.cliente_id, v.compra_id, null::uuid, 'referencia',
       'onboarding-identity', p.path, null, null, false, 2 + p.n::integer, oi.updated_at
  from chat_design.vw_chat_compra_vigente v
  join public.onboarding_identity oi on oi.compra_id = v.compra_id
  cross join lateral unnest(coalesce(oi.campaign_images_paths, '{}')) with ordinality as p(path, n)
 where p.path ~ '^[0-9a-fA-F-]{36}/[A-Za-z0-9_./-]+$' and p.path !~ '\.\.';
-- H: os caminhos de campaign_images_paths seguem {compra_id}/... (a convenção de logo é F: EDGE/save-onboarding-identity/.../index.ts:222); validar por consulta.

create or replace view chat_design.vw_chat_celebridades_cliente as
select v.cliente_id, v.compra_id, cr.id as celebridade_id, cr.nome, s.principal,
       cr."fotoPrincipal" as foto_principal_url, cr."fotoMobile" as foto_mobile_url,
       'Foto de referência do catálogo. O uso da imagem para criar peças depende de autorização de direito de imagem e não é permitido neste chat.'::text as aviso_direito_imagem,
       'somente_exibicao'::text as uso_permitido
  from chat_design.vw_chat_compra_vigente v
  join lateral (
        select cc.celebridade_id, cc.principal from public.compras_celebridades cc where cc.compra_id = v.compra_id
        union all
        select v.compra_celebridade, true
         where v.compra_celebridade is not null
           and not exists (select 1 from public.compras_celebridades cc where cc.compra_id = v.compra_id)
       ) s on true
  join public."celebridadesReferencia" cr on cr.id = s.celebridade_id
 where cr.ativo is true;   -- decisão 04/11: ativo NULL NÃO conta (conservador; igual ao post-turbo [F]: EDGE/post-turbo-generate/.../index.ts:230-233)

create or replace view chat_design.vw_chat_catalogo_celebridades as
select cr.id as celebridade_id, cr.nome,
       cr."fotoPrincipal" as foto_principal_url, cr."fotoMobile" as foto_mobile_url,
       'Foto de referência do catálogo. O uso da imagem para criar peças depende de autorização de direito de imagem e não é permitido neste chat.'::text as aviso_direito_imagem,
       'somente_exibicao'::text as uso_permitido
  from public."celebridadesReferencia" cr
 where cr.ativo is true;

-- RPC de leitura: SECURITY INVOKER lendo SÓ as views acima (menor privilégio).
create or replace function chat_design.buscar_cliente_chat(q text default null, limite integer default 20)
returns table(cliente_id uuid, nome_exibicao text, nome_origem text, pessoa_fisica boolean, setor text, tem_identidade boolean)
language sql stable security invoker set search_path = ''
as $$
  select e.cliente_id, e.nome_exibicao, e.nome_origem, e.pessoa_fisica, e.setor, e.tem_identidade
    from chat_design.vw_chat_clientes_elegiveis e
   where nullif(btrim(q), '') is null
      or public.unaccent(e.nome_exibicao)
         ilike '%' || replace(replace(replace(public.unaccent(btrim(q)), '\', '\\'), '%', '\%'), '_', '\_') || '%' escape '\'
   order by e.nome_exibicao
   limit greatest(1, least(coalesce(limite, 20), 50));
$$;

create or replace function chat_design.carregar_cliente_chat(p_cliente_id uuid)
returns table(cliente_id uuid, compra_id uuid, nome_exibicao text, nome_origem text, pessoa_fisica boolean,
              setor text, subsegmento text, paleta text[], tipografia text, tom text, publico_alvo text,
              descricao_marca text, site_url text, instagram_handle text, atualizado_em timestamptz)
language sql stable security invoker set search_path = ''
as $$
  select i.cliente_id, i.compra_id, i.nome_exibicao, i.nome_origem, i.pessoa_fisica, i.setor, i.subsegmento,
         i.paleta, i.tipografia, i.tom, i.publico_alvo, i.descricao_marca, i.site_url, i.instagram_handle, i.atualizado_em
    from chat_design.vw_chat_identidade_cliente i
   where i.cliente_id = p_cliente_id
   limit 1;
$$;

create or replace function chat_design.buscar_celebridade_chat(q text, limite integer default 20)
returns table(celebridade_id uuid, nome text, foto_principal_url text, foto_mobile_url text, aviso_direito_imagem text, uso_permitido text)
language sql stable security invoker set search_path = ''
as $$
  select c.celebridade_id, c.nome, c.foto_principal_url, c.foto_mobile_url, c.aviso_direito_imagem, c.uso_permitido
    from chat_design.vw_chat_catalogo_celebridades c
   where nullif(btrim(q), '') is not null
     and public.unaccent(c.nome)
         ilike '%' || replace(replace(replace(public.unaccent(btrim(q)), '\', '\\'), '%', '\%'), '_', '\_') || '%' escape '\'
   order by public.similarity(public.unaccent(c.nome), public.unaccent(btrim(q))) desc, c.nome
   limit greatest(1, least(coalesce(limite, 20), 50));
$$;
commit;
```

Notas sobre o DDL:
- `public.unaccent` e `public.similarity` dependem das extensões `unaccent` e `pg_trgm`, que existem no schema `public` [F: `OBS/extensions.tsv`]. Se o papel não alcançar, cair para `ilike` simples [H].
- `carregar_cliente_chat` usa `returns table` explícito (decisão 04/11): o contrato não muda se a view ganhar coluna; se a view mudar uma coluna listada, a função precisa ser recriada junto.
- A função `buscar_cliente_chat` **não lista todos** com `q` nulo se a decisão humana preferir exigir termo; hoje lista os primeiros `limite` por nome.
- `vw_chat_compra_vigente` é objeto interno; **não** entra no contrato nem recebe `GRANT` ao papel (as views que a usam rodam como dono). Se for dada `SELECT` a ele, a regra de elegibilidade fica consultável; sem risco de PII (só uuids).
- Índices: já existem `compras_cliente_id_idx` e `idx_compras_cliente` [F: `BASE:46826,47390`], `idx_compras_celebs_compra` [F: `BASE:47378`], `onboarding_identity_compra_id_key` (UNIQUE) [F: `BASE:45781`]. Não propus índice novo; validar com `EXPLAIN` com volume (4.3). Se precisar, `CREATE INDEX CONCURRENTLY` em migration própria.

## 2. Papel dedicado `chat_design_ro`

```sql
-- 20261104000100_chat_design_papel.sql  (PROPOSTA - NÃO APLICAR). Senha: definida pelo humano no cofre de segredos, nunca em SQL versionado.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'chat_design_ro') then
    create role chat_design_ro login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls connection limit 5;
  end if;
end $$;
alter role chat_design_ro set search_path = chat_design, pg_catalog;
alter role chat_design_ro set default_transaction_read_only = on;
alter role chat_design_ro set statement_timeout = '8s';
alter role chat_design_ro set idle_in_transaction_session_timeout = '15s';

-- fechar o que existe por padrão
revoke all on all tables    in schema public from chat_design_ro;
revoke all on all functions in schema public from chat_design_ro;
revoke all on all sequences in schema public from chat_design_ro;
revoke create on schema public from chat_design_ro;
revoke all on all tables in schema chat_design from chat_design_ro;
revoke all on all functions in schema chat_design from public;     -- função nasce com EXECUTE a PUBLIC

-- o mínimo
grant usage on schema chat_design to chat_design_ro;
grant select on chat_design.vw_chat_clientes_elegiveis, chat_design.vw_chat_identidade_cliente,
                chat_design.vw_chat_logos_cliente, chat_design.vw_chat_celebridades_cliente,
                chat_design.vw_chat_catalogo_celebridades to chat_design_ro;
grant execute on function chat_design.buscar_cliente_chat(text, integer),
                          chat_design.carregar_cliente_chat(uuid),
                          chat_design.buscar_celebridade_chat(text, integer) to chat_design_ro;
-- como as funções são SECURITY INVOKER lendo views do dono, o papel NÃO precisa de GRANT em public.*
-- exceto EXECUTE nas funções de extensão usadas (unaccent/similarity) e USAGE em public:
grant usage on schema public to chat_design_ro;                    -- necessário só para resolver unaccent/similarity
grant execute on function public.unaccent(text), public.similarity(text, text) to chat_design_ro;
```

Pontos:
- Precedente de papéis somente leitura com login no mesmo banco: `portal_reader`, `bi_readonly`, `atendy_readonly`, `aurea_recall_ro`, `acelera_design_tool_ro` [F: `BASE:25-30`]. **Q9 resolvida pelo Kelvin: papel novo, não reutilizar `acelera_design_tool_ro`** (esse tem `SELECT` em `compras`/`leads`, mais do que o chat deve ter).
- `ALTER DEFAULT PRIVILEGES` do projeto concedem a `anon`/`authenticated`/`service_role` em objetos novos [F: `OBS` 39 entradas de default ACL, `docs/supabase/surfaces/access.md`]; **não** concedem ao `chat_design_ro`, mas o teste 4.2 verifica `has_table_privilege` em todas as tabelas de `public`.
- As views novas **não** podem herdar `GRANT` a `anon`/`authenticated` por default privileges: após criar, `revoke all on all tables in schema chat_design from anon, authenticated` e verificar (teste 4.2). [H: o schema novo pode ter default ACL próprio herdado do dono; reconferir com `pg_default_acl`.]
- Conexão: pooler/Postgres direto com TLS; `connection limit 5`. Rotação: senha rotacionável sem mudar o código (variável de ambiente). IP allowlist se o projeto permitir [H].

## 3. URLs de logo e foto sem expor `service_role`

### 3.1 O problema [F]
O bucket `onboarding-identity` é privado e só tem policies de `service_role` (`HIST/20260326100002_onboarding_identity_storage.sql:4-12`). URL assinada **não se revoga** (só expira) [F: `docs/supabase/surfaces/storage.md:118-121`] e o CRM hoje assina por **7 dias** [F: `EDGE/create-ai-campaign-job/.../index.ts:265-267`, `admin-upload-logo/.../index.ts:131-133`]. O papel `chat_design_ro` é de banco; a API de Storage autentica por JWT, não por papel de banco, então **uma policy em `storage.objects` para `chat_design_ro` não resolve** [H].

### 3.2 Decisão (04/11): Edge Function pequena que devolve os BYTES, não a URL
`chat-design-asset` (nova, só leitura):
1. Aceita `POST {storage_path}` do servidor local do chat. Autenticação própria: cabeçalho com segredo longo comparado em tempo constante (`x-chat-design-key`), segredo guardado nos *secrets* da função e no `.env` do servidor local. Implantar com `--no-verify-jwt` **mais** essa verificação própria (lição do contexto `integracoes-crm`: `verify_jwt` ligado dá "401 com logs vazios"; identidade por cabeçalho forjável como `x-operator-email` é anti-padrão, então o segredo é o único fator e deve ser tratado como credencial). Alternativa mais forte, [H]: token curto assinado (HMAC com timestamp) em vez de segredo fixo.
2. Valida `storage_path` contra **a própria view** (`select 1 from chat_design.vw_chat_logos_cliente where storage_path = $1`), ou seja, só serve arquivo que o chat já pode listar (elegível, compra vigente). Rejeita `..`, caminho absoluto, bucket diferente.
3. Baixa o objeto com `service_role` **dentro da função** (a chave nunca sai do Supabase) e devolve os bytes; limite 10 MiB; allowlist de MIME `image/png`, `image/jpeg`, `image/webp`. **SVG: rejeitar** ou rasterizar (há 1 SVG no bucket [F: `OBS/storage_objects.tsv`]; SVG pode conter script/links externos).
4. Não grava log com caminho completo nem conteúdo; registra apenas contagem e código de resposta; limite de taxa por segredo.
Vantagem: **nenhuma URL assinada de 7 dias existe**; nada para revogar; o servidor local recebe o arquivo, usa e descarta (retenção: Q7).

Alternativas descartadas: (a) dar `service_role` ao chat (ignora RLS, vide CRM-1204); (b) URL assinada de validade curta pela mesma função (mais simples, mas a URL vale até expirar e passa pelo log/rede; aceitável só com ≤ 120 s se o Kelvin preferir); (c) abrir o bucket (público, qualquer um com a URL lê).

### 3.3 Fotos de celebridade (buckets públicos)
- As URLs já são públicas e estão em `celebridadesReferencia."fotoPrincipal"/"fotoMobile"` [F: `BASE:29384-29409`; buckets `celebs*` públicos, `OBS/buckets.tsv`]. A view devolve a URL tal como está.
- O provedor deve **validar o host** (apenas `<ref do projeto>.supabase.co`) e o prefixo `/storage/v1/object/public/celebs` (`celebs`, `celebs-corpo`, `celebs-final`, `celebs-total`) antes de baixar: a coluna é texto livre, e o chat já tem proteção SSRF a manter. Conteúdo de bucket público não é confiável (a policy `chat_media_allow_all_insert` deixa qualquer papel enviar [F: `OBS/storage_policies.tsv:21`]): validar tipo e tamanho.
- Miniatura: trocar `/storage/v1/object/public/` por `/storage/v1/render/image/public/` com `width`/`height` [F: `apps/crm-shell/src/features/proposta/lib/thumb-url.ts:2,16`]; foto original pesa ~2,8 MiB em média.
- **Uso**: só exibir com o `aviso_direito_imagem`. O chat **não** pode anexar essas fotos como entrada de geração nem tipá-las como `pessoa` (decisão Q6). Sugestão de teste automático no chat: nenhuma imagem com `uso_permitido='somente_exibicao'` chega a `inputs` do gerador.

## 4. Plano de teste, validação e rollback

### 4.0 Pré-requisitos (reconferir, 6+ semanas de defasagem)
Consultas somente leitura no banco alvo (staging **e** produção, por humano ou sob autorização): colunas e tipos das tabelas citadas em `fontes-de-dados-clientes.md`; existência de `public.crm_compra_nao_cancelada`; extensões `unaccent`/`pg_trgm` e em qual schema; `rolbypassrls` do dono das views; tabelas com `FORCE ROW LEVEL SECURITY`; lista de schemas expostos pela API; `pg_default_acl`; formato real de `brand_palette` e de `campaign_images_paths` (contagens, sem listar registros).

### 4.1 Ambiente
O staging está **atrás da produção** (90 x 655 migrations, dados de julho) [F: contexto `integracoes-crm` do cofre, 28/10; reconferir]. Não validar no staging sem sincronizar o schema. Preferir um **branch do Supabase ou banco local** com o baseline `BASE` e **seed fictício** (nunca dado real; C12): ver `supabase/seed.sql` como ponto de partida [H]. Nunca testar com lead real (R-LEAD-TESTE).

### 4.2 Testes de segurança (pass/fail)
1. A migration sobe, desce e sobe de novo (`down` em 4.4).
2. Como `chat_design_ro`: `select` em `public.clientes`, `compras`, `leads`, `onboarding_identity`, `celebridadesReferencia` **falha** (`permission denied`); `insert/update/delete` em qualquer objeto falha; `set role`/`create` falha.
3. `has_table_privilege('chat_design_ro', c.oid, 'SELECT')` falso para **todas** as tabelas e views de `public`, `bi`, `storage`, `auth`.
4. `anon` e `authenticated` **não** têm `USAGE` em `chat_design` nem `SELECT` nas views (inventário abaixo) e chamada pela API REST retorna negado/404.
5. **Allowlist por catálogo:** a lista de colunas de `chat_design.*` (via `information_schema.columns`) é exatamente a do contrato (seção 0). Teste falha se aparecer coluna cujo nome case com `cpf|cnpj|email|telefone|celular|endereco|cep|valor|preco|nascimento|observ|notes|transcript|brief_text|audio|signatario|razao`.
6. Elegibilidade (fixtures fictícias): (a) cliente com 1 compra assinada+paga entra; (b) só assinada sem pagamento fora; (b2) assinada com `checkout_status='parcialmente_pago'` entra; (c) só paga sem assinatura fora; (d) cancelada (`cancelado` não nulo) fora; (e) `vendarecusada` fora; (f) `is_test` fora; (g) duas elegíveis: vale a de `created_at` maior (e desempate por `id`); (h) a compra mais recente é inelegível e a anterior é elegível: vale a anterior elegível.
7. Saída de `vw_chat_logos_cliente` nunca contém `http`; caminho com `..` ou fora do padrão não aparece.
8. Funções: `q` com `%`, `_`, `\`, aspas e 10 mil caracteres não vaza nem quebra; `limite` 0, negativo, nulo e 10000 são limitados a 1..50; injeção de `search_path` (criar objeto homônimo em schema gravável) não altera o resultado.
8b. `pessoa_fisica`: cliente só com CPF = true, com CNPJ = false, sem nenhum = nulo; nenhum CPF/CNPJ aparece em coluna alguma.
9. `paleta` só tem hex `#RRGGBB`; ausência retorna `NULL`, não `{}` (C2).
10. Inventário do agente de banco, sem regressão: tabelas de `public` sem RLS legíveis por `anon`; políticas `true`; funções `SECURITY DEFINER` sem `search_path`. **A migration não pode aumentar nenhuma lista.**

### 4.3 Desempenho
`EXPLAIN (ANALYZE, BUFFERS)` de `buscar_cliente_chat` e `carregar_cliente_chat` com seed de volume realista (dezenas de milhares de clientes/compras; volume real é [H] desconhecido: rodar `count(*)` autorizado). O `distinct on` por cliente sobre `compras` sem filtro de cliente pode varrer a tabela; se o plano mostrar varredura completa que cresce, alternativas: `lateral` por cliente, ou índice parcial `CREATE INDEX CONCURRENTLY` em migration própria (decisão do humano). Contar consultas por operação (nenhum N+1).

### 4.4 Rollback (down)
```sql
begin;
revoke all on schema chat_design from chat_design_ro;
drop function if exists chat_design.buscar_celebridade_chat(text, integer);
drop function if exists chat_design.carregar_cliente_chat(uuid);
drop function if exists chat_design.buscar_cliente_chat(text, integer);
drop view if exists chat_design.vw_chat_catalogo_celebridades, chat_design.vw_chat_celebridades_cliente,
     chat_design.vw_chat_logos_cliente, chat_design.vw_chat_identidade_cliente,
     chat_design.vw_chat_clientes_elegiveis, chat_design.vw_chat_compra_vigente;
drop schema if exists chat_design;
reassign owned by chat_design_ro to postgres; drop owned by chat_design_ro;  -- só se o papel for removido
drop role if exists chat_design_ro;
commit;
```
Como tudo é **aditivo** (schema, views, funções e papel novos; nada em `public` é alterado), o rollback não afeta outros consumidores. Rollback da Edge Function: desimplantar a função e rotacionar o segredo. Plano de contenção: revogar `LOGIN` do papel (`alter role chat_design_ro nologin`) bloqueia o chat sem apagar nada.

### 4.5 Aplicação em produção (para o humano)
Janela comum (a migration é rápida e não bloqueia tabelas existentes; só `CREATE`); aplicar primeiro no branch/staging sincronizado; só então produção, com migration versionada (nunca pelo painel). Pós-aplicação: repetir 4.2 com a chave pública e com o papel novo; registrar o chat como consumidor no mapa de consumidores.

## 5. Riscos e decisões que o humano precisa tomar antes de aplicar

**Riscos**
1. **Views do dono contornam RLS.** A allowlist de colunas é a única barreira. Um `SELECT *` futuro numa view nova ou uma coluna adicionada ao SELECT quebra isso: o teste 4.2.5 é obrigatório no CI do banco. Mitigação: colunas explícitas, revisão de qualquer mudança nas views.
2. **Texto de IA no briefing pode conter PII** (`tom_voz`, `publico_alvo`, `mensagem_central` vêm de `briefing_json` gerado a partir de texto/áudio do cliente) [H]. Cortei por tamanho; o provedor deve aplicar filtro de CPF/telefone/e-mail antes de enviar a provedor de IA. Reavaliar quando Q4/Q7 fecharem.
3. **O nome pode ser pessoa física** (`clientes.nome` quando falta `nome_fantasia`/`brand_display_name`); `nome_origem` sinaliza, mas o chat decide o que mostrar (Q3).
4. **Segredo da Edge Function** é credencial: segredo fixo vaza em log/ambiente; preferir token curto assinado [H]. O servidor local não pode ir à Vercel sem login (`docs/12-memoria-na-vercel.md`, §1).
5. **Nenhuma proteção contra fechamento futuro de RLS é necessária para o chat** (usa views do dono), mas **qualquer mudança nas tabelas base** (renomear coluna, mudar `clicksign_status`) quebra as views: registrar o chat como consumidor; mudanças de schema nessas tabelas passam por expandir e contrair.
6. **Realtime/API:** se `chat_design` for exposto pela API REST por engano, as views ficam alcançáveis por `anon`; verificar a lista de schemas expostos e o `GRANT` de `anon` (4.2.4).
7. **Elegibilidade** inclui `parcialmente_pago` (decisão 04/11): compra assinada pode ter pagamento ainda incompleto; vale sempre a compra mais recente.
8. **Qualidade de dados:** 43 objetos em `onboarding-identity` no retrato de 23/09 [F: `OBS/storage_objects.tsv`] sugere que **poucos clientes têm identidade**; esperar muitos `tem_identidade = false`. [H] dimensionar por contagem autorizada.

**Decisões de desenho: fechadas** em 04/11/2026 ("seguir o recomendado", seção 0.1). **Ainda é do humano:** (a) **aprovar a aplicação** do schema `chat_design`, do papel `chat_design_ro` e da Edge Function, em branch/staging e depois em produção (C13); (b) definir quem rotaciona o segredo da função e a senha do papel, e onde ficam no cofre; (c) restrição de IP no Postgres, se a plataforma permitir; (d) confirmar que `chat_design` não está em uso e que não é exposto na API REST.

## 6. Pendências antes de produção

| Pendência | Quem decide | Bloqueia desenvolvimento? | Bloqueia ligar o provedor em produção? |
|---|---|---|---|
| **Aprovação para aplicar** DDL, papel e função (C13) | humano (plataforma/segurança) | não | **sim** |
| **Responsável pela rotação** do segredo da Edge Function e da senha de `chat_design_ro` (**EM ABERTO**) | time de plataforma | não | **sim** |
| **Q7** base legal e consentimento para enviar logo/fotos de cliente à OpenAI/Anthropic; retenção do cache local | jurídico/DPO | não | **sim** |
| **Q8** o que são `LogoClientes` e `previewLogoClientes` (fora desta proposta) | Kelvin/produto | não | não (só se virarem fonte de logo) |
| Reconferir o schema por consulta (seção 4.0), contagens de clientes com identidade e validar `pessoa_fisica` | eng-banco com acesso autorizado | não | **sim** |
| Q5 entregas e referências aprovadas | Kelvin | não | não (UI mostra "não disponível") |
| Direito de imagem de celebridade (só exibição, com aviso) | Kelvin/jurídico | não | não enquanto só exibir |

### Aprendizados

- **O que eu precisaria saber antes:** como as views do dono do banco ignoram RLS, a barreira de segurança passa a ser a lista de colunas, e um teste de catálogo por nomes proibidos é obrigatório. Uma policy em `storage.objects` para um papel de banco não ajuda a assinar URL, porque a Storage API autentica por JWT; por isso a Edge Function que devolve bytes é a opção mais simples e que não cria URL irrevogável. O `config.toml` do repositório não define os schemas expostos pela API; a lista de produção precisa ser conferida por consulta.
- **O que deu errado e como percebi:** nada falhou nesta tarefa; apenas reavaliei a primeira ideia de `SECURITY DEFINER` nas funções e a troquei por `SECURITY INVOKER` lendo as views, que dá o mesmo resultado com menos privilégio.
- **O que funcionou e vale repetir:** reusar o padrão de views no schema separado (`bi.*`) e papéis `*_ro` já existentes no banco como precedente; escrever o contrato (nomes e tipos) antes do DDL, para o eng-backend implementar em paralelo; transformar a allowlist em teste de catálogo.

**Pronto para revisão.**
