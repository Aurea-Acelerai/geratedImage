---
name: designer-imagegen
description: Gerar ou editar peças visuais de qualidade profissional para clientes, com contexto de marca do banco e fluxo briefing, geração e revisão. Use em pedidos de criar, editar ou variar imagem/peça de design para um cliente.
---

# Designer Imagegen

A skill aplica o system prompt consolidado em `prompts/designer-imagegen.system.md` (fonte única das regras). Resumo operacional:

1. **Contexto:** `get_client` antes de tudo. Sem marca, não gerar.
2. **Decidir:** imagem raster só quando for foto/ilustração/cena/fundo/mockup. Gráfico, tabela, texto longo, logo oficial e entidade real não vão para imagegen.
3. **Classificar:** `use_case` (taxonomia) e `role` (hero ou cell).
4. **Briefing:** prompt em inglês, autocontido, no schema rotulado (Use case, Asset type, Primary request, Scene, Subject, Style, Composition, Lighting, Palette, Text verbatim, Constraints, Avoid). Pedido detalhado: normalizar. Pedido genérico: acrescentar só o que melhora, usando o contexto do cliente. Nunca inventar personagens, marcas ou slogans.
5. **Parâmetros:** size conforme o contêiner, quality low para rascunho e medium/high para final, n=1, transparente só para recortes.
6. **Gerar** uma peça por chamada; série com referências e prefixo de consistência.
7. **Revisar** com a rubrica (nota ≥ 8 e sem veto), uma correção por ciclo, máximo 2 ciclos.
8. **Entregar** sem sobrescrever (`-v2`), registrar no banco, responder em até duas frases.

Rubrica e comparativo entre fornecedores: `docs/04-comparativo-fornecedores.md`.
