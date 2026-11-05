export PATH=/opt/homebrew/opt/postgresql@17/bin:$PATH
H="-h 127.0.0.1 -p 55432 -q -t -A -v ON_ERROR_STOP=0"
fail=0; ok(){ echo "OK   $1"; }; ko(){ echo "FALHA $1"; fail=1; }
su() { psql $H -d postgres -U postgres -c "$1" 2>&1; }
ro() { psql $H -d postgres -U chat_design_ro -c "$1" 2>&1; }
chk(){ [ "$2" = "$3" ] && ok "$1" || ko "$1 (obtido='$2' esperado='$3')"; }
# 4.2.2 papel não lê public nem escreve
for t in clientes compras leads onboarding_identity '"celebridadesReferencia"'; do
  r=$(ro "select 1 from public.$t limit 1"); echo "$r" | grep -q "permission denied" && ok "ro nao le public.$t" || ko "ro LE public.$t: $r"; done
for q in "insert into chat_design.vw_chat_clientes_elegiveis(cliente_id) values (gen_random_uuid())" "update public.clientes set nome='x'" "delete from public.compras" "create table public.t(x int)" "create table chat_design.t(x int)" "set role postgres"; do
  r=$(ro "$q"); echo "$r" | grep -qiE "permission denied|read-only|cannot|must be|not allowed|violates" && ok "ro bloqueado: ${q:0:45}" || ko "ro EXECUTOU: $q -> $r"; done
r=$(ro "select 1 from chat_design.vw_chat_compra_vigente limit 1"); echo "$r" | grep -q "permission denied" && ok "vw_chat_compra_vigente interna negada" || ko "compra_vigente acessivel: $r"
# 4.2.3 privilégios por catálogo
r=$(su "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('public','bi','storage','auth') and c.relkind in ('r','v','m','p') and has_table_privilege('chat_design_ro',c.oid,'SELECT')"); chk "ro sem SELECT em public/bi/storage/auth" "$r" "0"
# 4.2.4 anon/authenticated
r=$(su "select count(*) from (select has_schema_privilege(x,'chat_design','USAGE') p from unnest(array['anon','authenticated']) x) q where p"); chk "anon/authenticated sem USAGE em chat_design" "$r" "0"
r=$(su "select count(*) from information_schema.table_privileges where table_schema='chat_design' and grantee in ('anon','authenticated','PUBLIC')"); chk "sem grants a anon/authenticated/PUBLIC nas views" "$r" "0"
r=$(su "select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='chat_design' and (has_function_privilege('anon',p.oid,'EXECUTE') or has_function_privilege('authenticated',p.oid,'EXECUTE') or has_function_privilege('public',p.oid,'EXECUTE'))"); chk "funcoes sem EXECUTE a anon/authenticated/PUBLIC" "$r" "0"
# 4.2.5 allowlist de colunas
r=$(su "select string_agg(table_name||'.'||column_name,',') from information_schema.columns where table_schema='chat_design' and column_name ~* 'cpf|cnpj|email|telefone|celular|endereco|cep|valor|preco|nascimento|observ|notes|transcript|brief_text|audio|signatario|razao'"); chk "nenhuma coluna proibida em chat_design" "$r" ""
# 4.2.6 elegibilidade
r=$(su "select string_agg(right(cliente_id::text,2),',' order by cliente_id) from chat_design.vw_chat_clientes_elegiveis"); chk "elegiveis = a,c,h(11),i(12)" "$r" "0a,0c,11,12"
r=$(su "select right(compra_id::text,2) from chat_design.vw_chat_clientes_elegiveis where right(cliente_id::text,2)='11'"); chk "(h) vale a mais recente elegivel" "$r" "21"
r=$(su "select right(compra_id::text,2) from chat_design.vw_chat_clientes_elegiveis where right(cliente_id::text,2)='12'"); chk "(h) recente inelegivel -> vale a anterior" "$r" "31"
# 4.2.7 logos
r=$(su "select count(*) from chat_design.vw_chat_logos_cliente where storage_path ~* 'http' or storage_path ~ '\.\.' or storage_path like '/%'"); chk "logos sem http/../abs" "$r" "0"
r=$(su "select count(*) from chat_design.vw_chat_logos_cliente"); chk "logos validos: 1 logo + 1 referencia" "$r" "2"
# 4.2.8 funções
r=$(ro "select count(*) from chat_design.buscar_cliente_chat('%')"); chk "q='%' nao vaza tudo" "$r" "1"
r=$(ro "select count(*) from chat_design.buscar_cliente_chat('_')"); chk "q='_' literal" "$r" "1"
r=$(ro "select count(*) from chat_design.buscar_cliente_chat('\\')"); chk "q='\\' literal" "$r" "1"
r=$(ro "select count(*) from chat_design.buscar_cliente_chat('x'' or 1=1 --')"); chk "q com aspas/SQL" "$r" "0"
big=$(python3 -c "print('a'*10000)"); r=$(ro "select count(*) from chat_design.buscar_cliente_chat('$big')"); chk "q 10k chars" "$r" "0"
for l in 0 -5 null 10000; do r=$(ro "select count(*) between 1 and 50 from chat_design.buscar_cliente_chat(null, $l)"); chk "limite $l entre 1 e 50" "$r" "t"; done
r=$(ro "select nome_exibicao from chat_design.buscar_cliente_chat('marca a premium')"); chk "busca sem acento/caixa" "$r" "Marca A Premium"
# search_path injection
su "create schema evil; create function evil.unaccent(text) returns text language sql as \$\$select 'HACK'::text\$\$; grant usage on schema evil to public;" >/dev/null
r=$(psql $H -d postgres -U chat_design_ro -c "set search_path=evil,public; select count(*) from chat_design.buscar_cliente_chat('marca')" 2>&1 | tail -1); chk "injecao de search_path nao altera" "$r" "1"
# 4.2.8b pessoa_fisica
r=$(su "select string_agg(right(cliente_id::text,2)||'='||coalesce(pessoa_fisica::text,'null'),',' order by cliente_id) from chat_design.vw_chat_identidade_cliente where right(cliente_id::text,2) in ('0a','0c')"); chk "pessoa_fisica a=false c=true" "$r" "0a=false,0c=true"
r=$(su "select count(*) from chat_design.vw_chat_identidade_cliente i where to_jsonb(i)::text ~ '(12345678901|11111111000111|@fake|1190000)'"); chk "nenhum CPF/CNPJ/email/telefone na saida" "$r" "0"
r=$(su "select count(*) from chat_design.vw_chat_identidade_cliente i where to_jsonb(i)::text ~ 'SEGREDO'"); chk "sem notes/brief_text na saida" "$r" "0"
# 4.2.9 paleta
r=$(ro "select array_to_string(paleta,',') from chat_design.carregar_cliente_chat('c0000000-0000-0000-0000-00000000000a')"); chk "paleta so hex" "$r" "#FF0000,#00ff00"
r=$(ro "select paleta is null from chat_design.carregar_cliente_chat('c0000000-0000-0000-0000-00000000000c')"); chk "paleta ausente = NULL" "$r" "t"
# celebridades
r=$(su "select count(*) from chat_design.vw_chat_celebridades_cliente"); chk "celebridades do cliente: so ativo=true" "$r" "1"
r=$(ro "select count(*) from chat_design.buscar_celebridade_chat('celebridade')"); chk "catalogo: so ativo=true" "$r" "1"
r=$(su "select count(*) from chat_design.vw_chat_celebridades_cliente where uso_permitido<>'somente_exibicao' or aviso_direito_imagem is null"); chk "celebridade somente_exibicao com aviso" "$r" "0"
exit $fail
