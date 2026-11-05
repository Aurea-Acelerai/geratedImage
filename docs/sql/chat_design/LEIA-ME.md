# chat_design: SQL validado, ainda NÃO aplicado no banco do CRM

Migrations (`20261104000000_chat_design_leitura.sql`, `20261104000100_chat_design_papel.sql`) e `down.sql`, extraídos de `docs/proposta-acesso-leitura-chat.md`.

Validação feita em 05/11/2026 num Postgres 17 descartável com dados 100% fictícios (tabelas com os tipos do baseline do CRM): 41 verificações de segurança passaram (papel sem leitura em `public`, sem grants a `anon`/`authenticated`, allowlist de colunas, elegibilidade a-h, busca com `%`/`_`/`\`/aspas/10 mil caracteres, `search_path`, `pessoa_fisica`, paleta, celebridades), e sobe, desce e sobe de novo. Duas mutações plantadas (view com CPF; grant a `anon`) reprovam os testes.

Rodar: subir um Postgres vazio, aplicar `teste_00_fixture_ficticio.sql`, as duas migrations, `teste_10_seed_ficticio.sql` e `bash teste_20_seguranca.sh` (ajuste host/porta no script).

**Não aplicado** no banco do CRM de produção (`awqtzoefutnfmnbomujt`): essa conta/CLI não tem acesso a esse projeto, só ao staging, que está defasado. Quem tem acesso aplica as migrations (nunca pelo painel) e roda a seção 4.2 da proposta com o papel novo. O provedor do chat continua desligado por padrão.
