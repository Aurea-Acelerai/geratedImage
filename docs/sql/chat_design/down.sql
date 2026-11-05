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
