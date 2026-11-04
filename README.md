# imagegen-harness

Objetivo: levar a geração de imagem dos nossos agentes designer à qualidade do ChatGPT (chat), replicando o harness (contexto → briefing → geração → revisão) em vez de chamar a API de imagem diretamente.

| Pasta | Conteúdo |
|---|---|
| `docs/01-mapeamento-system-prompts.md` | O que os prompts vazados da OpenAI dizem sobre imagem |
| `docs/02-chat-vs-api.md` | Por que chat > API e o que falta no workflow atual |
| `docs/03-arquitetura-agente-designer.md` | Arquitetura proposta (tools, guardrails, fluxo) |
| `docs/04-comparativo-fornecedores.md` | OpenAI, Meta, Google, xAI, Mistral, Anthropic: o que absorver e o que não copiar; rubrica de revisão |
| `docs/05-evidencias-docs-artigos-comunidade.md` | **Documentação oficial, artigos, pesquisa e relatos de quem usa**, com nível de confiança e decisões |
| `docs/06-rastreabilidade.md` | **Cada ponto analisado × onde foi aplicado (aplicado / parcial / fora / pendente)** |
| `docs/07-filtro-por-arquivo.md` | **O que saiu de cada arquivo do repositório vazado, onde entrou e o que foi descartado** |
| `prompts/designer-imagegen.system.md` | **System prompt consolidado (v0.4) para revisão**, independente de fornecedor de imagem |
| `prompts/critic.system.md`, `prompts/rubric.json` | **Critic nosso** (prompt do revisor) e fonte única da rubrica, pesos, vetos e nota mínima |
| `test/critic.py`, `test/calibration/` | Código do critic e calibração contra avaliação humana (`python critic.py --calibrate`) |
| `prompts/profiles/` | Perfil da ferramenta de imagem (modelos, tamanhos, erros): `openai-gpt-image-2.5.md` e `_template.md` para outras ferramentas |
| `skills/designer-imagegen/SKILL.md`, `agents/designer.md` | Skill e agente |
| `test/` | Teste A/B/C com 6 casos e planilha de avaliação humana cega |

## Rodar o teste
Braços: **A** Image API crua · **B** nosso harness (briefing + critic) · **C** Responses API com a ferramenta nativa (reescrita da OpenAI).
```bash
cd test
pip install openai
python run_comparison.py --dry-run --all     # valida o fluxo sem custo
export OPENAI_API_KEY=...                     # chave de teste, nunca commitar
python run_comparison.py --case 5 --arms ABNC # um caso primeiro, para conferir custo e acesso aos modelos
python run_comparison.py --all --arms ABNC    # 6 casos
python run_comparison.py --all --repeats 3    # depois, para medir consistência
# avaliação cega: abra out/<timestamp>/blind/avaliar.html e preencha blind/ratings.csv (não abra key.json antes)
python analyze.py out/<timestamp>             # tabela por braço: nota humana, aprovação, critic, gerações por peça
```
Braço extra **N**: igual ao B, mas com cores por nome em vez de código hex (testa se o hex atrapalha). `--arms` escolhe quais braços rodar.
Os modelos padrão (`gpt-image-2.5-sunburst`, `gpt-5.5`) seguem a documentação da OpenAI de nov/2026; confirme na conta e ajuste por variável de ambiente. O critic é um LLM: a decisão final usa a nota humana.

## Regras de design (valem em toda geração)
`docs/08-fundamentos-design.md` define as regras. Elas entram no system prompt do designer (`{{design_fundamentals}}`), na rubrica v3 do critic (`prompts/rubric.json`; a v2 fica em `rubric.v2.json`) e em checagens por código (`test/checks.py`). Teste offline: `cd test && python3 checks.py --self-test && python3 run_comparison.py --dry-run`.

## Skills de design
`skills/design-*` aprofundam cada regra de `docs/08` (7 skills: estratégia, hierarquia/composição, cor/contraste/craft, tipografia/texto, formato/canal, série/marca, movimento/vídeo). `test/skills_router.py` escolhe as skills por pedido e as injeta no system prompt (`{{design_skills}}`, versão compacta); a seção "Revisão (critic)" de cada skill vai para o critic. Teste: `cd test && python3 skills_router.py --self-test` (checa que toda regra do `docs/08` tem aprofundamento). Para medir o efeito: rode o teste com `DESIGN_SKILLS=off` e sem.

## Chat estilo ChatGPT (cliente, logo, referências e iteração)
```bash
cd test
read -s "OPENAI_API_KEY?Chave: "; echo; export OPENAI_API_KEY
python3 chat_server.py            # http://127.0.0.1:8766   (--mock para ver sem API)
```
Envie a logo, peças e referências do cliente (ficam em `test/clients/<id>/`, fora do git), clique nelas para anexar ao pedido e converse. "Editar esta imagem" usa a imagem anterior como alvo (`/images/edits`). Cada resposta passa pelo designer (com `docs/08`), checagens por código e critic, com até 2 correções. Limite: logo e texto exato ainda não são compostos por código; o critic reprova logo redesenhado (`logo_inventado`).

## Interface rápida para testar o system prompt
```bash
cd test
export OPENAI_API_KEY=...            # chave de teste
python3 ui_server.py                   # abre http://127.0.0.1:8765  (sem dependências)
python3 ui_server.py --mock            # sem API, só para ver a UI (dados falsos)
```
Sem `OPENAI_API_KEY`, a interface usa o **Claude (Sonnet) via CLI `claude`**, com o seu login, para escrever o briefing; imagem e critic ficam desligados (precisam da chave da OpenAI). Em lote, sem interface: `python3 run_briefings_claude.py` (os 6 casos, saída em `test/out/`).
Escolha um caso (ou escreva um pedido), edite o JSON do cliente e clique em **Rodar**: briefing do system prompt → imagem → critic. Dá para editar o prompt final e regerar, aplicar a correção sugerida pelo critic e comparar com o prompt cru (braço A). O `prompts/designer-imagegen.system.md` é relido a cada execução: edite e rode de novo, sem reiniciar.

## Pendências
- Ligar `get_client` ao banco real (Kelvin).
- Incorporar a documentação do "Ive" na skill.
- Calibrar o limiar do critic com exemplos "bom/ruim" do CEO.
- Rodar o teste com chave real e anexar o resultado (a organização pode precisar de verificação para usar modelos de imagem).
- Implementar composição de texto/logo por código (HTML/SVG) e a validação de pixels fora da máscara em edições.
- Definir o conjunto de avaliação com casos reais do CEO e a nota mínima de aprovação.
