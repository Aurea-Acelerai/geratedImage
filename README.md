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

## Fontes de design, estilos, gates e critic em camadas
- `docs/fontes/`: as duas fontes do Kelvin (roadmap "nível Apple" e a skill de direção de arte), cópias sem edição. **Estudo, conflitos e decisões: `docs/09-mapa-fontes-design.md`.**
- `prompts/estilos.json` + `skills/design-estilos/`: catálogo de 14 estilos, **gerado** da fonte por `test/gen_estilos.py` (`--check` confere a sincronia).
- `test/qa_gates.py`: os 12 gates de QA sobre a especificação de uma peça (PASSA / FALHA / NAO_VERIFICAVEL, veredito REVISAR / REFAZER).
- **Critic em camadas:** o modelo da OpenAI como juiz, com base neutra e pacotes por caso de uso (marketing, brand, text, edit, estilos) em `prompts/rubric.json` v4 (v3 em `rubric.v3.json`). Imagem livre não é julgada por critérios de marketing.

## Chat estilo ChatGPT (cliente, logo, referências e iteração)
```bash
cd test
./run_chat.sh                 # pede a chave (sem eco), sobe o servidor e abre http://127.0.0.1:8766
./run_chat.sh --mock          # sem API: imagens falsas, só para ver a interface
```
Envie a logo, peças e referências do cliente (ficam em `test/clients/<id>/`, fora do git; logo em **PNG**), clique nelas para anexar ao pedido (ou arraste e cole na caixa de mensagem) e converse. "Editar esta imagem" usa a imagem anterior como alvo (`/images/edits`).

- **Progresso ao vivo:** cada etapa aparece (skills, briefing, tentativa, revisão, correção) com a imagem de cada tentativa; dá para ampliar qualquer imagem. Atualizar a página no meio não perde nada.
- **Modelos:** a barra lateral lista os modelos da sua conta e um aviso aparece se `IMAGE_MODEL`/`TEXT_MODEL` não existirem nela (o `HANDOFF` pede para confirmar). Troque pelo seletor ou pelas variáveis de ambiente.
- **Contexto inteiro (estilo ChatGPT):** as imagens anexadas ficam **na conversa** (gravadas no servidor) até você soltar; citar o nome de uma imagem da biblioteca ("Rodrigo") a anexa sozinha; a IA recebe a **transcrição inteira**. Detalhes e regras rígidas: `docs/11-harness-estilo-chatgpt.md`.
- **Buscar na web:** painel na lateral (Wikimedia Commons, com licença e autor) para logos e fotos; também dá para colar o link de uma imagem. O designer sugere a busca quando falta uma referência.
- **Chave da OpenAI:** se o servidor subir sem chave, a tela mostra um campo para colá-la uma vez (opcionalmente guardada no Keychain do Mac); nunca passa pelo chat nem por arquivo do projeto.
- **Modo livre (padrão):** qualquer imagem, sem marca: nada do cliente (setor, paleta, estilo) entra no briefing, e o pedido do usuário manda. **Modo com marca:** aplica o cliente só onde o pedido é omisso. Pedido sem assunto ("quero ver a imagem") faz o designer perguntar em vez de inventar.
- **Melhorias da aplicação (cada uma liga/desliga):** designer reescreve o briefing, skills de design, critic com correção, e "comparar com o GPT puro" (gera também só o seu texto, lado a lado, na mesma régua do critic). Tudo desligado = o GPT sozinho com o seu texto. A resposta mostra "Seu pedido", "O que a aplicação fez" e o briefing enviado ao modelo.
- **Pipeline por mensagem:** designer (com `docs/08` e as skills do pedido; skills de marketing só em peça de marketing) → imagem → checagens por código → critic (rubrica v3) → até 2 correções.
- **Sem chave:** só o briefing sai, via CLI `claude`.
- **Limite:** logo e texto exato ainda não são compostos por código; o critic reprova logo redesenhado (`logo_inventado`).
- **Teste sem custo do caminho real:** `cd test && python3 e2e_chat.py`. Sobe a OpenAI falsa (`fake_openai.py`) e o chat numa pasta temporária (`CHAT_DATA_DIR`), sem tocar em `test/clients` e `test/chat_out` (o seu uso real). Prova que as requisições são montadas, as respostas tratadas e que modos e melhorias se comportam; não valida a API real. **Nunca apague `test/clients` nem `test/chat_out`**: guardam as suas imagens e a biblioteca.

## Interface rápida para testar o system prompt
```bash
cd test
export OPENAI_API_KEY=...            # chave de teste
python3 ui_server.py                   # abre http://127.0.0.1:8765  (sem dependências)
python3 ui_server.py --mock            # sem API, só para ver a UI (dados falsos)
```
Sem `OPENAI_API_KEY`, a interface usa o **Claude (Sonnet) via CLI `claude`**, com o seu login, para escrever o briefing; imagem e critic ficam desligados (precisam da chave da OpenAI). Em lote, sem interface: `python3 run_briefings_claude.py` (os 6 casos, saída em `test/out/`).
Escolha um caso (ou escreva um pedido), edite o JSON do cliente e clique em **Rodar**: briefing do system prompt → imagem → critic. Dá para editar o prompt final e regerar, aplicar a correção sugerida pelo critic e comparar com o prompt cru (braço A). O `prompts/designer-imagegen.system.md` é relido a cada execução: edite e rode de novo, sem reiniciar.

## Adapter da OpenAI Images, testes e CI
`test/provider.py` é a camada única das chamadas de imagem (validação contra `test/provider_capabilities.json`, retry só para erro seguro, Retry-After, orçamento por sessão `IMAGE_BUDGET_SESSION` e por mensagem `IMAGE_BUDGET_TASK`, trace sem prompt). Testes: `cd test && sh run_tests.sh` (sem chave, sem custo; o mesmo comando roda no CI). **Auditoria, limites e plano: `docs/13-auditoria-harness-geral.md`.** Nada disso foi medido com a API real.

## Pendências
- Ligar `get_client` ao banco real (Kelvin).
- Incorporar a documentação do "Ive" na skill.
- Calibrar o limiar do critic com exemplos "bom/ruim" do CEO.
- Rodar o teste com chave real e anexar o resultado (a organização pode precisar de verificação para usar modelos de imagem).
- Implementar composição de texto/logo por código (HTML/SVG) e a validação de pixels fora da máscara em edições.
- Definir o conjunto de avaliação com casos reais do CEO e a nota mínima de aprovação.
