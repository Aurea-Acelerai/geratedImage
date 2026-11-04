# 12. Memória e dados se o chat subir na Vercel (plano, 04/11/2026)

Pergunta: "se subir na Vercel, melhore essa questão da memória". Resposta curta: **a lógica de memória (transcrição, arquivos da conversa, apelidos, resolvedor) continua valendo; o que muda é onde ela é guardada e como as gerações demoradas rodam.** Hoje tudo vive em arquivos locais e em memória do processo, e isso não sobrevive numa função serverless.

## 1. O que quebra na Vercel

| Hoje | Problema na Vercel | Confiança |
|---|---|---|
| Servidor `http.server` de um processo só | A Vercel roda Python como **função** (FastAPI, Flask ou Django viram uma função só); `http.server` não é um padrão suportado. Precisa virar uma app ASGI/WSGI ou rotas em Node | alta (documentação) |
| `test/clients`, `test/chat_out`, `test/conversations`, `test/logs` em disco | Funções são efêmeras e cada instância é isolada: arquivos gravados somem entre chamadas e deploys. A busca não trouxe uma frase explícita sobre o sistema de arquivos | média (regra geral de serverless; **confirmar**) |
| `JOBS` em memória e `threading.Thread` | A função termina quando responde; o job se perde e outra instância não o conhece | alta |
| Geração de 20 a 70 s por mensagem (briefing + imagem + critic + correções) | Cada função tem `maxDuration` configurável por arquivo (a documentação mostra exemplos de 60 s até 1800 s). **O teto do seu plano precisa ser conferido** | alta no mecanismo; **teto do plano não verificado** |
| Chave da OpenAI no navegador e Keychain | Não existe Keychain na Vercel. A chave vira variável de ambiente do projeto | alta |
| Guarda "só 127.0.0.1" | Na internet qualquer pessoa com a URL gastaria a chave e veria a biblioteca. **Exige login** | alta |
| Download de URL e busca na web pelo servidor | Continua precisando das travas contra SSRF (já existem) | alta |

## 2. Arquitetura de memória para a nuvem

**Banco: Supabase Postgres** (já conectado ao seu ambiente). **Arquivos: Supabase Storage ou Vercel Blob** (a Vercel Blob tem acesso `private` e SDK Python com `put_blob` e `stream_blob`).

| Tabela | Substitui | Campos principais |
|---|---|---|
| `orgs`, `users`, `clients` | `clients/<id>/client.json` | dono, marca (paleta, estilo, tom) |
| `assets` | `assets.json` + `assets/` | cliente, tipo, nome, **apelido**, origem, licença, caminho no storage, dono |
| `conversations` | `conversations/<cliente>/<id>.json` | cliente, criada em, `carry` (instruções duradouras), resumo rolante |
| `turns` | `turns` dentro do JSON | conversa, n, pedido original, pedido resolvido, intenção, briefing final, imagem, nota, vetos, avisos, pergunta |
| `conversation_files` | `conv["files"]` | conversa, asset |
| `generated_images` | `chat_out/` | conversa, turno, caminho, nota |
| `jobs` e `job_events` | `JOBS` e `logs/events.jsonl` | estado, passos, erro, API usada |

O que **não muda**: `memory_text`, o resolvedor (`prompts/memory.system.md`), `resolve_files`, `alias_matches`, as regras rígidas e o critic em camadas. Só a camada de leitura e escrita troca. Por isso o primeiro passo é isolar o armazenamento atrás de uma interface (`Store`), com `FileStore` (hoje) e `SupabaseStore` (nuvem), e rodar o mesmo teste ponta a ponta nos dois.

**Segurança que a nuvem exige:** autenticação, linhas por usuário/organização (RLS), URLs assinadas para as imagens, e as fotos de pessoas reais com **retenção, consentimento e endpoint de exclusão** (decisão do CEO; envolve LGPD).

## 3. Gerações longas sem perder o estado

O pipeline vira **passos curtos**, cada um dentro do limite de uma função, com o estado no banco:
1. resolver contexto, 2. briefing, 3. imagem, 4. critic, 5. correção (repete 3 e 4).
O navegador consulta `/api/job` (já é assim). Para encadear sem depender de uma conexão aberta, as opções são: funções com `waitUntil`; um fluxo durável (Vercel Workflow/filas); ou um worker fora da Vercel só para geração. Recomendação: começar com **um passo por função** e `maxDuration` ajustado, e migrar para fluxo durável se os tempos passarem do teto.

## 4. Melhorias de memória que só fazem sentido com banco

1. **Resumo rolante:** depois de N turnos, resumir os antigos e manter a transcrição só dos recentes (hoje a transcrição vai inteira até 40 turnos; custa tokens).
2. **Memória do cliente, entre conversas:** registro de **entidades** (pessoas, produtos, marcas) com nome canônico, apelidos e imagens de referência. Citar "Rodrigo" em qualquer conversa nova do cliente anexa a foto, como hoje, mas sem depender da biblioteca solta.
3. **Peças anteriores como referência:** "faça como a peça de março" por busca (pgvector é opcional; começar por título, data e nota).
4. **Aprendizado com decisão humana:** guardar aprovadas e reprovadas **com motivo** (já planejado em `docs/09`), agora numa tabela consultável pelo curador.
5. **Auditoria:** `job_events` com a API usada em cada passo (hoje está em `logs/events.jsonl`).

## 5. Ordem de trabalho

1. Interface `Store` + `FileStore` com os mesmos testes (sem mudar o comportamento).
2. `SupabaseStore` (tabelas e Storage) e testes contra um projeto de desenvolvimento.
3. Porte do servidor para função (FastAPI) e página estática; jobs em passos.
4. Login e RLS; chave da OpenAI como variável de ambiente; limite de uso por usuário.
5. Resumo rolante e memória de entidades do cliente.

## 6. Decisões que dependem de vocês

| ID | Decisão | Minha recomendação |
|---|---|---|
| V1 | Quem entra: só o time (login da empresa) ou também clientes? | só o time no início |
| V2 | Onde guardar imagens: Supabase Storage ou Vercel Blob? | Supabase Storage (banco e arquivos no mesmo lugar, RLS única) |
| V3 | Plano da Vercel e o teto de `maxDuration` | conferir antes de escolher entre função única e fluxo durável |
| V4 | Retenção das fotos de pessoas reais | definir com o CEO antes de subir |
