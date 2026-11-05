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
