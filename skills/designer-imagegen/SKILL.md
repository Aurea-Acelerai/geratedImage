---
name: designer-imagegen
description: Gerar ou editar peças visuais de qualidade profissional para clientes, com contexto de marca do banco e fluxo triage, briefing, geração, composição por código e revisão. Use em pedidos de criar, editar ou variar imagem/peça de design para um cliente.
---

# Designer Imagegen

Fonte única das regras: `prompts/designer-imagegen.system.md` (v0.3). Esta skill é o roteiro operacional; a rastreabilidade de cada regra está em `docs/06-rastreabilidade.md`.

## Fluxo

0. **Triage (modelo rápido e barato):** classifique `use_case`, `role` (hero/cell) e se a peça tem texto exato, dados ou edição de peça aprovada. Isso decide o caminho abaixo.
1. **Contexto:** `get_client` (marca, paleta, tipografia, `image_style`, referências aprovadas, peças anteriores). Sem marca, não gerar.
2. **Decidir o caminho:**
   - raster (foto, ilustração, cena, fundo) → modelo de imagem;
   - gráfico, tabela, dado real → código;
   - logo, nome, preço, data, CTA → código sobre a arte;
   - entidade real → imagem oficial ou busca;
   - edição de peça aprovada → máscara + composição por código.
3. **Briefing:** prompt em inglês, autocontido, no schema rotulado, com o guia do `use_case` e o vocabulário de direção de arte. Pedido detalhado: normalizar. Genérico: acrescentar só o que melhora, usando o contexto do cliente.
4. **Parâmetros:** flare para rascunho, sunburst para final; `quality` low→medium/high; size do contêiner; `n=1` (3 se pedirem opções); transparente só para recorte.
5. **Gerar** uma peça por chamada, de forma assíncrona. Série: referências + nome por elemento + prefixo de consistência.
6. **Compor por código** o texto exato, o logo e os dados sobre a arte sem texto (ou usar underdrawing quando o texto precisa ficar integrado).
7. **Revisar** com a rubrica (nota ≥ 8, sem veto), conferindo texto letra por letra; uma correção por ciclo, máximo 2.
8. **Entregar:** salvar sem sobrescrever (`-v2`), registrar no banco (prompt, parâmetros, nota, tentativas, `revised_prompt` se houver), resposta de até duas frases.

## Rubrica do critic (doc 04, v2)
Assunto 2 · estilo 1 · composição 1 · cor/contraste/foco 2 · texto 2 · defeitos 1 · formato 0,5 · invariantes/série 0,5 · **vinculação de atributos, contagem e negações 1** · veto: logo inventado, watermark, texto indevido, pessoa real sem referência, dado inventado.

Saída do critic: JSON `{ "scores": {...}, "veto": [...], "issues": [...], "fix": "uma instrução curta" }`.
