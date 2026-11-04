---
name: designer-imagegen
description: Gerar ou editar peças visuais de qualidade profissional para clientes, com contexto de marca do banco e fluxo triage, briefing, geração, composição por código e revisão. Use em pedidos de criar, editar ou variar imagem/peça de design para um cliente.
---

# Designer Imagegen

Fonte única das regras: `prompts/designer-imagegen.system.md` (v0.4). Esta skill é o roteiro operacional; a rastreabilidade de cada regra está em `docs/06-rastreabilidade.md`.

## Regra obrigatória: fundamentos de design
Toda geração segue `docs/08-fundamentos-design.md` (seções 1 a 6, IDs E, H, C, K, T, F). Isso não é opcional nem depende do pedido: o texto das regras é injetado no system prompt (`test/checks.py`, `design_fundamentals()`), o critic as aplica pela rubrica v3 e `checks.apply()` acrescenta vetos por código. Sem o documento, o designer não roda. Mudar essas regras exige aprovação do CEO (docs/08, seção 9).

## Fluxo

0. **Triage (modelo rápido e barato):** classifique `use_case`, `role` (hero/cell) e se a peça tem texto exato, dados ou edição de peça aprovada. Isso decide o caminho abaixo.
1. **Contexto:** `get_client` (marca, paleta, tipografia, `image_style`, referências aprovadas, peças anteriores). Sem marca, não gerar.
2. **Decidir o caminho:**
   - raster (foto, ilustração, cena, fundo) → modelo de imagem;
   - gráfico, tabela, dado real → código;
   - logo, nome, preço, data, CTA → código sobre a arte;
   - entidade real → imagem oficial ou busca;
   - edição de peça aprovada → máscara + composição por código.
2b. **Estratégia (E1 a E4):** escreva oferta em uma frase, hook (até 7 palavras), ponto focal e ângulo. Oferta incerta: pergunte ao usuário, não invente.
3. **Briefing:** prompt em inglês, autocontido, no schema rotulado, com o guia do `use_case` e o vocabulário de direção de arte. Pedido detalhado: normalizar. Genérico: acrescentar só o que melhora, usando o contexto do cliente.
4. **Parâmetros:** use o perfil da ferramenta de imagem (`prompts/profiles/`): modelo ou nível barato para rascunho e o melhor para o final; tamanho do contêiner; `n=1` (3 se pedirem opções); transparente só para recorte e se a ferramenta suportar.
5. **Gerar** uma peça por chamada, de forma assíncrona. Série: referências + nome por elemento + prefixo de consistência.
6. **Compor por código** o texto exato, o logo e os dados sobre a arte sem texto (ou usar underdrawing quando o texto precisa ficar integrado).
7. **Revisar** com a rubrica v3 (nota ≥ 8, sem veto), incluindo hierarquia, miniatura de 120 px e safe zone do canal; `checks.apply()` roda por código, conferindo texto letra por letra; uma correção por ciclo, máximo 2.
8. **Entregar:** salvar sem sobrescrever (`-v2`), registrar no banco (prompt, parâmetros, nota, tentativas, prompt revisado pela ferramenta, se houver), resposta de até duas frases.

## Critic
Critérios, pesos, vetos e nota mínima: `prompts/rubric.json` (fonte única). Prompt do revisor: `prompts/critic.system.md`. O critic roda em chamada separada e não vê o raciocínio do designer.

Saída do critic: JSON `{ "issues": [...], "scores": {...}, "veto": [...], "fix": "uma instrução curta" }`.
