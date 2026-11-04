# HANDOFF: estado do projeto em 04/11/2026

Para quem for continuar (pessoa ou agente). Leia este arquivo, depois o `README.md`. Não há chaves de API neste repositório e elas não devem entrar nele.

## Objetivo
Os agentes designer da Acelerai/Aurea geram imagens para clientes. O CEO observou que a imagem gerada dentro do chat do ChatGPT é melhor que a gerada por API. O fluxo atual ("Robocop") é um workflow (pedido, resposta); o ChatGPT é um harness de agente (orquestra, revisa, tem regras). Meta: um **clone do chat do ChatGPT via API, com melhorias**: o usuário pede, escolhe referências numa lista (celebridades, peças, marca) em vez de anexar arquivos, e recebe imagem de qualidade equivalente. Interface só de teste, sem design elaborado. Entrega por etapas, mostrando ao CEO "replicamos o GPT".

## O que existe no repositório
- `docs/01` a `07`: mapeamento dos prompts vazados, chat vs API, arquitetura, comparativo de fornecedores, evidências, rastreabilidade, filtro por arquivo.
- `prompts/designer-imagegen.system.md` (v0.4): system prompt do diretor de arte, sem dependência de fornecedor. Parâmetros da ferramenta de imagem em `prompts/profiles/`.
- `prompts/critic.system.md` e `prompts/rubric.json`: critic próprio e rubrica única (critérios, pesos, vetos, nota mínima 8).
- `skills/designer-imagegen/`, `agents/designer.md`: roteiro e agente.
- `test/run_comparison.py`: teste A (pedido cru) / B (nosso harness) / N (B com cores por nome) / C (Responses API nativa). `test/critic.py`: critic e calibração. `test/analyze.py`: análise com avaliação humana cega. `test/eval_set.json` e `test/client_71.json`: 6 casos e cliente fictício.
- `test/results/piloto-caso5/` e `test/results/rodada1/`: resultados já gerados.

## Resultados até agora (gpt-image-2.5-sunburst, 1 geração por braço)
Nos 4 casos em que A e B geraram (1, 3, 4, 5): B média 8,91 (4 de 4 aprovadas), A média 7,23 (1 de 4). O A vazou texto indevido ("Cliente Exemplo 71") em 3 casos. Caso 2 (banner 1536x1024) falhou nos dois braços e caso 6 braço B falhou na geração (2 tentativas cada).
**Limites:** uma geração por braço; notas do critic aplicado por modelo, sem calibração e sem avaliação humana cega; o prompt do A é suposto, não o real do Robocop; **nunca comparamos com o ChatGPT de verdade.**

## Decisões já tomadas
- Não copiar o "Depiction Protocol" (nunca recusar, delegar segurança): mantemos julgamento próprio.
- Texto exato, logo, preço e dados saem por código, não do modelo de imagem.
- Edição de peça aprovada: máscara e composição por código. Pessoa real exige foto de referência.
- Máximo de 2 ciclos de correção; custo medido por imagem aceita.

## Próximos passos (clone do chat)
1. **Braço D: o ChatGPT de verdade.** Rodar os mesmos pedidos no app, salvar imagem e o prompt que ele mostra, comparar com o nosso briefing.
2. **Conversa em vários turnos:** histórico e edição da imagem anterior.
3. **Referências e edição:** endpoint de edição com imagens de entrada (seleção de celebridade/peça pela interface). O modelo pode recusar rosto de pessoa real; confirmar direitos de uso das imagens.
4. **Regras invioláveis por cliente** no contexto, e o critic compara original e gerada contra elas (o colega descreveu um comparador, possivelmente Gemini, a confirmar). O critic já aceita várias imagens e qualquer backend (adaptador `vlm`).
5. **Segunda via:** Responses API com o nosso system prompt como instruções (braço C). Pode ser o clone mais barato de manter.
6. Interface mínima: já existe uma tentativa de outra sessão em `.claude/worktrees/image-prompt-test-interface-3bc83c/test/ui` e `ui_server.py` (fora do GitHub; não foi verificada).
7. Ligar `get_client` ao banco real; incorporar a documentação do "Ive"; calibrar o critic com exemplos bom/ruim do CEO (`test/calibration/README.md`); implementar `compose_text_overlay`, `composite_with_mask`, `render_chart`.

## Como rodar
```bash
cd test && python3 -m venv .venv && source .venv/bin/activate && pip install openai
read -s "OPENAI_API_KEY?Chave: "; echo; export OPENAI_API_KEY    # no terminal, nunca em arquivo nem no chat
python critic.py --self-test
python run_comparison.py --case 5 --arms ABNC
python analyze.py out/<data>
```
Confirme os nomes de modelo na conta (`IMAGE_MODEL`, `TEXT_MODEL`, `RESPONSES_MODEL`). A organização pode precisar de verificação para modelos de imagem.

## Pessoas e divisão
Kelvin: conexão dos agentes ao banco (dados do cliente, peças entregues). Colega: qualidade da imagem e comparador de imagens. Documentação do "Ive" (agentes designer) a incorporar.

## Avisos
- Os testes anteriores foram gerados pela ferramenta de imagem do Figma (arquivo "geratedImage - testes de prompt", plano da equipe do Kelvin), pois o ambiente em nuvem não alcança a OpenAI. Cada imagem consome crédito de IA do Figma.
- As imagens do Figma expiram em 7 dias; as cópias estão em `test/results/`.
- Os arquivos `tmp_obj_*` e locks renomeados dentro de `.git/` são resíduo inofensivo de git em pasta sem permissão de apagar.
