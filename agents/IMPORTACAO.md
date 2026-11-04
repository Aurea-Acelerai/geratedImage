# Importação de agentes do Obsidian (registro)

Sincronização unidirecional Obsidian → repositório por `tools/obsidian_sync.py` (dry-run por padrão; `--source` explícito; manifesto com hashes; sem sobrescrita nem exclusão; contenção de caminho; recusa arquivo com cara de segredo). Lista de permissão: `agents/obsidian-sync.json`. Originais em `agents/obsidian-origin/` (**ignorados pelo git**; só `MANIFEST.json` e `SYNC_LOG.jsonl` são versionados, para provar o que foi lido sem publicar as notas). Comando:

```bash
python3 tools/obsidian_sync.py --source "<pasta do vault>"          # dry-run
python3 tools/obsidian_sync.py --source "<pasta do vault>" --apply  # grava o que é seguro
```

Os agentes ativos são as **adaptações** em `.claude/agents/`. Os originais não são ativados.

## Inventário (04/11/2026)

| Origem (nota no vault) | sha256 (12 primeiros) | Destino | Decisão |
|---|---|---|---|
| `Agentes/API e Integrações/01 - Agente Guardião de API.md` (`eng-api`, sonnet, Read/Grep/Glob/Bash/Write/Edit) | `766947fb747a` | `.claude/agents/especialista-apis.md` | Adaptado e reduzido a um consumidor (API de imagens OpenAI) |
| `Agentes/Qualidade e Testes/01 - Agente QA Revisor.md` (`eng-qa-revisor`, opus, Read/Grep/Glob/Bash/Write) | `4ebb8185969e` | `.claude/agents/engenheiro-qualidade.md` | Adaptado; absorveu o papel de avaliador/benchmark |
| (não existe no vault) | — | `.claude/agents/diretor-de-arte.md` | **Criado**: o vault não tem agente de direção de arte |
| `Agentes/Arquitetura e Engenharia/01 - Agente Arquiteto de Software.md` (`eng-arquiteto`) | — | — | **Não importado**: li só o cabeçalho; revisão de arquitetura fica com a sessão principal e o `engenheiro-qualidade` até haver necessidade |
| `.agents/agentes/00…15` (operação de segurança) | — | — | **Não importados**: declaram ferramentas que não existem no Claude Code (`ler_codigo`, `abrir_sessoes`, `gitleaks`…) e miram outros sistemas |

Orquestrador: papel da sessão principal (sem agente próprio). Os papéis de contexto, desempenho e segurança ficam para quando houver trabalho que os exija.

## O que foi alterado nas adaptações

Removido nos dois agentes importados: contrato comum e seção de aprendizado contínuo (dependem de `MEMORY.md`, `memory_flow.py`, `eng-curador`, Regras da Casa), referências a `docs/work/<ID>`, `docs/agentes/*`, `docs/api/*`, Linear, Supabase, RLS, Edge Functions, parceiros de pagamento e "Operação de Segurança"; as fases N0 a N4; os casos reais do vault (dados internos de incidentes). Mantido: os princípios (evidência própria, correção incompleta, mutação manual em cópia descartável, contrato antes do acidente, severidade honesta). Acrescentado: regra de orçamento (nenhuma chamada paga à API), `sh test/run_tests.sh`, avaliação de imagem separada por dimensão, "paridade ainda não demonstrada" sem baseline externo.

**Ferramentas:** só nomes reais do Claude Code. `especialista-apis` é somente leitura + web; `engenheiro-qualidade` lê e roda comandos, sem `Write`/`Edit`; `diretor-de-arte` só lê. O frontmatter não restringe caminhos de `Bash`; a regra "não deixa código alterado" é instrução, verificada pelo `git status` da sessão principal.

## Pendências
- `agents/designer.md` (agente **de produto**, não do Claude Code) lista ferramentas que ainda não existem no código (`composite_with_mask`, `compose_text_overlay`, `render_chart`, `get_brand_kit`…). Não deve ser lido como capacidade implementada (ver `HANDOFF.md`, passo 7).
- O "Ive" citado no `HANDOFF.md` não foi localizado no vault por nome.
