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
python run_comparison.py --all --repeats 3    # 6 casos x 3 repetições x 3 braços
# abre out/<timestamp>/report.html e preencha ratings.csv (avaliação humana cega)
```
Os modelos padrão (`gpt-image-2.5-sunburst`, `gpt-5.5`) seguem a documentação da OpenAI de nov/2026; confirme na conta e ajuste por variável de ambiente. O critic é um LLM: a decisão final usa a nota humana.

## Pendências
- Ligar `get_client` ao banco real (Kelvin).
- Incorporar a documentação do "Ive" na skill.
- Calibrar o limiar do critic com exemplos "bom/ruim" do CEO.
- Rodar o teste com chave real e anexar o resultado (a organização pode precisar de verificação para usar modelos de imagem).
- Implementar composição de texto/logo por código (HTML/SVG) e a validação de pixels fora da máscara em edições.
- Definir o conjunto de avaliação com casos reais do CEO e a nota mínima de aprovação.
