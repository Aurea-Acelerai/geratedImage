# 03 — Arquitetura proposta: agente designer com harness

```
"Cria uma peça para o cliente 71"
        │
        ▼
┌───────────────────┐
│ 1. Contexto       │  tool: get_client(71) → marca, paleta, tom, peças entregues
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 2. Briefing       │  LLM (texto): pedido + contexto → briefing de direção de arte
│    (art director) │  → prompt final + size + n + transparent_background
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 3. Geração        │  tool: generate_image (gpt-image) / edit_image
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 4. Revisão        │  LLM com visão: nota 0–10 contra briefing + marca + guardrails
│    (critic)       │  < limiar → feedback → volta ao passo 2 (máx. 2 ciclos)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 5. Entrega        │  salva no storage, registra no banco, responde curto
└───────────────────┘
```

## Ferramentas do agente

| Tool | Função |
|---|---|
| `get_client(id)` | Dados do cliente no banco (marca, paleta, logo, tom, histórico) |
| `get_deliveries(id, periodo)` | Quantas peças foram entregues, o que ressaltou |
| `generate_image(prompt, size, n, transparent_background)` | Geração |
| `edit_image(image_id, prompt)` | Edição com alvo real |
| `review_image(image, briefing)` | Critic com visão |
| `save_asset(...)` | Storage + registro |

## Guardrails (herdados do harness do ChatGPT)

1. Não gerar com texto longo, tabelas ou gráficos dentro da imagem; esses vão para HTML/código e exportam como imagem.
2. Logos e marcas reais do cliente: usar o arquivo oficial, nunca pedir para o modelo "desenhar" o logo.
3. Edição exige imagem-alvo existente.
4. Pessoa real exige foto de referência fornecida.
5. Argumentos da ferramenta nunca vão para o usuário.
6. Máximo de 2 ciclos de revisão (controle de custo e latência).

## Duas formas de implementar

- **Agente com tool-use** (recomendado): um loop com as tools acima; o próprio modelo decide quando revisar. Mais próximo do ChatGPT.
- **Workflow com passos fixos + critic**: mais previsível e barato, menos flexível. Serve como fase 1 (é o que o teste faz).

## Dependências e pendências

- Banco/API de clientes: o Kelvin está resolvendo a conexão dos agentes com o banco.
- Documentação do "Ive" (agentes designer): incorporar na skill `designer-imagegen` quando chegar.
- Definir o limiar de aprovação do critic com exemplos reais do CEO ("bom" vs "ruim").
