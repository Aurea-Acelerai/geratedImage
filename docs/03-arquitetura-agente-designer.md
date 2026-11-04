# 03 — Arquitetura proposta: agente designer com harness (v2)

Revisada com as evidências do doc 05 (documentação oficial, relatos de produção, caso Moda).

```
"Cria uma peça para o cliente 71"
        │
        ▼
┌───────────────────┐
│ 0. Triage         │  modelo rápido: use_case, role, tem texto exato? dados? edição de peça aprovada?
└─────────┬─────────┘  → escolhe skills do tipo de peça
          ▼
┌───────────────────┐
│ 1. Contexto       │  get_client + Brand Kit Agent (cores, fontes, logo, voz, estilo aprovado)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 2. Briefing       │  LLM diretor de arte: pedido + contexto → prompt no schema + parâmetros
└─────────┬─────────┘  (normaliza se detalhado; expande só com contexto de marca)
          ▼
┌───────────────────┐
│ 3. Geração        │  fila assíncrona; rascunho em flare/low, final em sunburst/medium+
│    (assíncrona)   │  arte SEM texto; uma peça por chamada
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 4. Composição     │  código: texto exato, logo, preço, CTA (HTML/SVG), gráficos (render_chart),
│    por código     │  edição por máscara + composição; underdrawing quando o texto é integrado
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 5. Revisão        │  VLM com rubrica v2; texto letra por letra; checagem de pixels fora da máscara
│    (critic)       │  < 8 ou veto → uma correção → volta ao 2 (máx. 2 ciclos)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 6. Entrega        │  storage versionado (-v2), registro no banco, revised_prompt, custo por imagem aceita
└───────────────────┘
```

## Ferramentas (12 a 15 ativas; o resto sob demanda)

| Tool | Função |
|---|---|
| `get_client(id)`, `get_brand_kit(id)` | Dados e identidade do cliente |
| `get_deliveries(id, periodo)` | Peças entregues e o que ressaltou |
| `generate_image(prompt, size, quality, n, background)` | Geração (Image API) |
| `edit_image(image, mask?, prompt)` | Edição |
| `composite_with_mask(original, edited, mask)` | Mantém pixels aprovados idênticos |
| `compose_text_overlay(image, spec)` | Texto, logo e CTA por código |
| `render_chart(data, style)` | Gráficos e tabelas por código |
| `search_reference_image(query)` | Entidade real em vez de gerar |
| `review_image(image, briefing)` | Critic com rubrica |
| `save_asset(...)` | Storage e registro |

## Guardrails
1. Texto exato, logo, preços, datas e dados reais **nunca** dependem do modelo de imagem.
2. Gráficos, tabelas e infográficos de dados são renderizados por código a partir do banco.
3. Edição de peça aprovada: máscara + composição, validada por diff fora da máscara.
4. Pessoa real exige foto de referência fornecida.
5. Elementos fixos da marca entram como referência ou composição (a OpenAI avisa que a consistência de marca pode falhar entre gerações).
6. Argumentos de ferramenta nunca vão ao usuário; erro de moderação não é repetido sem mudar o pedido.
7. Máximo de 2 ciclos de revisão; custo medido por imagem **aceita**.

## Duas formas de implementar
- **Agente com tool-use** (recomendado a médio prazo): loop com as tools acima, triage barato e skills por tipo de peça.
- **Workflow com passos fixos + critic**: previsível e barato; é o que o teste faz. Fase 1.

## Observabilidade e avaliação (desde o dia 1)
- Trace de cada execução (prompt, `revised_prompt`, parâmetros, nota, tentativas, custo, latência).
- Conjunto de avaliação fixo (`test/eval_set.json`), repetido ≥ 3 vezes por caso, com avaliação humana cega (`ratings.csv`).
- O caso Moda reporta não ter avaliações formais; aqui elas entram antes de ir a produção.

## Dependências e pendências
- Banco/API de clientes: conexão dos agentes (Kelvin).
- Documentação do "Ive": incorporar às skills por tipo de peça.
- Definir a nota mínima de aprovação com exemplos "bom/ruim" do CEO.
- Verificação da organização na OpenAI e `safety_identifier` por cliente.
