# chat_design: SQL validado, ainda NÃO aplicado no banco do CRM

Migrations (`20261104000000_chat_design_leitura.sql`, `20261104000100_chat_design_papel.sql`) e `down.sql`, extraídos de `docs/proposta-acesso-leitura-chat.md`.

Validação feita em 05/11/2026 num Postgres 17 descartável com dados 100% fictícios (tabelas com os tipos do baseline do CRM): 41 verificações de segurança passaram (papel sem leitura em `public`, sem grants a `anon`/`authenticated`, allowlist de colunas, elegibilidade a-h, busca com `%`/`_`/`\`/aspas/10 mil caracteres, `search_path`, `pessoa_fisica`, paleta, celebridades), e sobe, desce e sobe de novo. Duas mutações plantadas (view com CPF; grant a `anon`) reprovam os testes.

Rodar: subir um Postgres vazio, aplicar `teste_00_fixture_ficticio.sql`, as duas migrations, `teste_10_seed_ficticio.sql` e `bash teste_20_seguranca.sh` (ajuste host/porta no script).

**Não aplicado** no banco do CRM de produção (`awqtzoefutnfmnbomujt`): essa conta/CLI não tem acesso a esse projeto, só ao staging, que está defasado. Quem tem acesso aplica as migrations (nunca pelo painel) e roda a seção 4.2 da proposta com o papel novo. O provedor do chat continua desligado por padrão.

## Como o chat se conecta (opção B, decidida em 05/11/2026): Postgres direto, somente leitura
Variáveis do servidor (nunca no repositório): `CHAT_DB_ENABLED=1`, `CHAT_DB_DSN=postgresql://chat_design_ro.<ref>:<senha>@<host-do-pooler>:6543/postgres` (TLS obrigatório; só o papel `chat_design_ro`; host `*.supabase.co`, `*.pooler.supabase.com` ou `CHAT_DB_HOST`), e para os bytes dos logos `SUPABASE_URL` + `CHAT_DESIGN_ASSET_KEY` (Edge Function `chat-design-asset`, ainda a criar). Sem `CHAT_DB_DSN` o caminho antigo (REST) continua valendo; sem nada, o provedor fica desligado.
O `PgTransport` só roda 4 consultas fixas e parametrizadas (3 funções e a view de logos) em transação READ ONLY. Testado com o driver real (`pg8000`) contra o Postgres descartável e, sem banco, em `test/test_pg_transport.py` (28 verificações, parte da suíte).

## Função dos logos (`edge/chat-design-asset`), publicada em produção em 05/11/2026
Entrega os bytes do logo (sem URL assinada). Só atende com a chave certa, só para caminhos que constam em `chat_design.vw_chat_logos_cliente` (cliente elegível), só PNG/JPEG/WEBP pela assinatura, até 10 MiB. Testes: `deno test --no-check --no-remote core_test.ts` (8 testes, parte da suíte quando há `deno`).
**O projeto do CRM está no limite de 100 segredos do Supabase**, então a função NÃO usa segredo: guarda só o SHA-256 da chave em `key_hash.ts` (gerado no deploy, fora do repositório; ou a variável `CHAT_DESIGN_ASSET_KEY_SHA256`). A chave em si fica só na Vercel (`CHAT_DESIGN_ASSET_KEY`, sensível). Para trocar a chave: gerar outra, publicar novo `key_hash.ts` com o hash dela e atualizar a variável na Vercel.
Deploy: `supabase functions deploy chat-design-asset --project-ref awqtzoefutnfmnbomujt --no-verify-jwt --use-api` a partir de uma pasta com `index.ts`, `core.ts` e `key_hash.ts`.
