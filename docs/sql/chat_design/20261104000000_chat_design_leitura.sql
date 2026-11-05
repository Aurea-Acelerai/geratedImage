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
