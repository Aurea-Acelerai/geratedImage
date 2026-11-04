# geratedImage: instruções para agentes

Harness conversacional de geração e edição de imagens (qualquer tipo de imagem, não só marketing). Provedor de imagens: API da OpenAI. Leia `HANDOFF.md`, `README.md` e `docs/13-auditoria-harness-geral.md` (estado real, limites e plano).

## Comandos
```bash
cd test && sh run_tests.sh              # tudo, sem chave, sem rede de verdade, sem custo (é o comando do CI)
python3 -I test/test_provider.py        # adapter da OpenAI
python3 -I test/test_runner.py          # preflight e laço de decisão
python3 -I test/test_obsidian_sync.py   # sincronização Obsidian -> repositório
./test/run_chat.sh --mock               # chat local sem API
```
Python 3.9+ só com stdlib; Pillow é opcional (sem ele os testes de edição localizada são pulados: rode também com um venv que tenha Pillow quando tocar em `regionedit`).

## Regras
- **Nenhuma chamada paga à API real sem orçamento aprovado pelo usuário** (número de chamadas e modelo). Testes usam `test/fake_openai.py` ou transporte injetado.
- **Chaves e dados:** nunca commitar `.env`, chaves, notas privadas do Obsidian nem imagens de clientes. `test/clients/` e `test/chat_out/` guardam uso real: nunca apagar.
- **Versões de imagem:** toda geração grava pai, modelo, parâmetros e versão do prompt (`test/versions.py`, `POST /api/lineage`). Ao criar um novo ponto que gera ou edita imagem, marque a base com `src_image_id` e grave a versão.
- **Execução pelo Runner** (`test/runner.py`): preflight leve antes de gastar texto ou imagem, decisão explícita (aceita, repara, escalona, para) e trace. O prazo total de produção (`CHAT_DEADLINE_S`) entra como portões (`review_gate`, `repair_gate`); corte por prazo não é "escalado". Não há flag para pular o preflight; a suíte de testes não roda dentro de requisição.
- **Chamadas de texto** (briefing, critic, resolvedor, pesquisa) só por `ui.openai_post`, que usa `OpenAIText`: retry seguro e orçamento de texto por sessão e por tarefa (`TEXT_BUDGET_*`). Não capture exceção em volta dessas chamadas sem repassar as falhas locais (`_fatal`: orçamento, validação, chave).
- **Chamadas de imagem só pelo adapter** `test/provider.py` (validação contra `test/provider_capabilities.json`, retry só para erro seguro, orçamento). Sem fallback de edição para geração. Regra de modelo/tamanho/parâmetro só entra com fonte oficial e data.
- **Teste de verdade:** afirme comportamento (o que foi enviado, quantas vezes, que erro saiu), não que um mock foi chamado. O preflight de produção é leve; a suíte de testes não roda dentro de requisição.
- **Não afirmar** paridade com o ChatGPT sem comparação cega com baseline obtido legitimamente. Hoje: "paridade ainda não demonstrada". Não documentar como existente o que é só contrato ou TODO.
- Sem push, deploy, migração destrutiva ou troca de credenciais sem autorização do usuário.

## Agentes (`.claude/agents/`)
`especialista-apis` (contrato com a API de imagens, somente leitura), `engenheiro-qualidade` (revisão independente e avaliação; roda testes), `diretor-de-arte` (aderência ao pedido, somente leitura). Origem, alterações e pendências: `agents/IMPORTACAO.md`. A sessão principal orquestra: cada delegação leva objetivo, escopo, arquivos permitidos, contexto, entregáveis e critério de aceite; agentes não editam os mesmos arquivos ao mesmo tempo (usar worktree).
