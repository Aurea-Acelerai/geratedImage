# 02 — Por que a imagem no chat é melhor que na API

Hipótese do Kelvin/CEO confirmada pelos prompts vazados: **o que o chat tem a mais é o harness, não um modelo melhor.**

## Fluxo no ChatGPT (app)

```
Pedido curto do usuário
  → modelo de raciocínio (contexto + memória + anexos)
  → escreve um prompt detalhado para text2im
  → escolhe size / n / transparent_background / is_style_transfer
  → modelo de imagem gera
  → (opcional) python para anotar / ajustar com precisão
  → resposta sem texto
```

## Fluxo típico via API (o que o Robocop faz hoje)

```
Dados + JSON do cliente
  → template de prompt fixo
  → POST /images/generations
  → resultado
```

É um **workflow de IA** (request → response, linear, sem decisão), não uma **orquestração de agente** (decide, delega, revisa, tenta de novo).

## Diferenças, lado a lado

| Aspecto | ChatGPT (app) | API crua |
|---|---|---|
| Quem escreve o prompt final | Modelo de raciocínio, com contexto | Template estático |
| Contexto do usuário/cliente | Memória + conversa + anexos | Só o que o JSON carrega |
| System prompt | ~85–125 mil caracteres | ~860 caracteres, sem regras de imagem |
| Parâmetros (size, transparente, estilo) | Escolhidos pelo orquestrador | Fixos no código |
| Revisão do resultado | Possível (vê a imagem, pode refazer) | Nenhuma |
| Guardrails | Política de conteúdo, alvo de edição, regras por contexto (ex.: texto/gráfico não via imagegen) | Nenhum além do filtro do modelo |
| Edição iterativa | Nativa (referenced_image_ids) | Precisa ser implementada |

## O que isso significa para os agentes designer

Para chegar na qualidade do chat, o agente precisa de **cinco peças**, que o Robocop hoje não tem:

1. **Contexto**: buscar dados do cliente no banco (marca, paleta, tom, peças entregues, histórico).
2. **Briefing criativo**: um LLM transforma pedido + contexto em prompt de direção de arte (composição, luz, paleta, tipografia, formato).
3. **Parâmetros**: decidir formato, fundo transparente, número de variações.
4. **Geração** com o modelo de imagem.
5. **Revisão (critic loop)**: um segundo passo com visão avalia contra o briefing e a marca; se reprovar, reescreve o prompt e gera de novo (limite de tentativas).

Regras úteis copiadas do comportamento do ChatGPT:
- Gerar direto, sem perguntas desnecessárias.
- Edição só com alvo real (imagem existente); senão pedir.
- Texto legível, gráficos e tabelas **não** vão para imagegen (renderizar em HTML/código).
- Nunca expor argumentos da ferramenta ao usuário.
- Pós-geração enxuta, sem descrever a imagem.

## Pergunta em aberto

Não sabemos qual parte da diferença percebida vem do harness e qual vem de diferenças no modelo/versão de imagem entre chat e API. **O teste em `test/` isola isso**: mesmo modelo de imagem, A = prompt cru, B = com briefing + revisão.
