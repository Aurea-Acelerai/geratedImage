# 06 — Rastreabilidade: o que foi analisado e onde foi aplicado

Estado: prompt v0.3, skill, agente, arquitetura v2 e teste. **Aplicado** = está escrito no prompt/skill/agente/arquitetura. **Parcial** = só em parte. **Fora** = decisão de não aplicar. **Pendente** = depende de implementação ou de teste com chave real.

Importante: "aplicado" significa escrito nos documentos. **Nada foi validado com geração real** (o teste só rodou em dry-run e com cliente simulado). A eficácia de cada regra ainda precisa do teste A/B/C.

## 1. Prompts vazados

| Fonte | Ponto de melhoria | Onde | Status |
|---|---|---|---|
| OpenAI app (`image_gen`) | Gerar direto, sem reconfirmar | Prompt §4 (regras), skill | Aplicado |
| | Edição só com alvo real | Prompt §2 | Aplicado |
| | Pessoa real exige foto de referência | Prompt §2 | Aplicado |
| | Nunca expor argumentos da ferramenta; resposta enxuta | Prompt §7 | Aplicado |
| | Recusar sem sugerir contornos | Prompt §8 | Aplicado |
| | Python para anotar com precisão | Camada de composição por código | Aplicado |
| OpenAI agent mode | Não usar imagegen para gráficos, tabelas, texto longo, entidades reais | Prompt §2 e regra 11 | Aplicado |
| OpenAI Codex skill | Taxonomia de casos de uso | Prompt §3 (+ `social-post`, `hero-banner`) | Aplicado |
| | Schema rotulado de prompt | Prompt §4 | Aplicado |
| | Normalizar vs. expandir; lista do que não acrescentar | Prompt §4 regras 1–3 | Aplicado |
| | Texto verbatim, soletrar palavras difíceis | Prompt §4 regra 7 | Aplicado (com composição por código) |
| | Edição: "change only X", invariantes, rotular imagens | Prompt §4 regra 9 | Aplicado |
| | Iterar uma mudança por vez | Prompt §6 | Aplicado |
| | Dicas por tipo de peça e de edição | Prompt "Guia por tipo de peça" | Aplicado (v0.3) |
| | Uma chamada por ativo; `n` só para variações | Prompt regra 10 | Aplicado |
| | Salvar sem sobrescrever; reportar prompt final | Prompt §7, arquitetura passo 6 | Aplicado |
| | Código vs. bitmap (logo/ícone casado com vetor) | Prompt §2 | Aplicado |
| | Rascunho `low`, final maior; tamanhos válidos | Prompt §5 | Aplicado |
| | Não trocar de modelo sem pedir | Prompt §5 | Aplicado (v0.3) |
| | Biblioteca de prompts de exemplo (`sample-prompts.md`) | — | **Pendente:** viraria a biblioteca de exemplos por tipo de peça nas skills |
| Meta | Diretiva de arte em 7 partes (medium, assunto, composição, cor, qualidade, proporção, exclusões) | Prompt §4 regras 4–6, 8 | Aplicado |
| | Medium único e consistente no conjunto | Prompt regra 4 | Aplicado |
| | Composição por papel (hero vs. célula) | Prompt §3 e §4 | Aplicado |
| | Anti-lavado, contraste, foco | Prompt regra 5 + rubrica | Aplicado |
| | Resolução mínima, proporção do contêiner | Prompt §5 | Aplicado |
| | Buscar entidade real em vez de gerar | Prompt §2, ferramenta `search_reference_image` | Aplicado |
| | Ajustar vestuário à cena | Prompt "Vocabulário" | Aplicado (v0.3) |
| | Subagente que expande o detalhe visual | Etapa 2 (briefing) | Aplicado (arquitetura) |
| | Snapshot para sequências (`resume_from_snapshot_id`) | Equivalente: referências + prefixo de consistência | Parcial |
| Google (Gemini) | Consistência: referências, prefixo de consistência | Prompt regra 10 | Aplicado |
| | Nomear cada elemento recorrente | Prompt regra 10 | Aplicado (v0.2) |
| | Query como frase nominal, sem embelezar | Normalização (regras 1–3) | Aplicado |
| | Não repetir a mesma chamada que falhou | Prompt §6 e §7 | Aplicado |
| | Proporção explícita | Prompt §5 | Aplicado |
| | Variações na mesma chamada | Prompt "Guia por tipo" (`n=3` em opções) | Aplicado (v0.3) |
| xAI | Separar one-shot de pipeline | Arquitetura (rascunho assíncrono vs. fluxo completo) | Parcial |
| | Edição com imagem-base + até 4 referências, ancorada na base | Prompt regra 9 (papéis das imagens) | Parcial |
| Mistral | Prompt autocontido, em inglês, sem contexto implícito | Prompt §4 | Aplicado |
| Anthropic | Carregar a skill antes de agir | Skill + agente | Aplicado |
| Gemini/Meta | "Depiction Protocol" (nunca recusar, delegar segurança) | Prompt §8 | **Fora** (decisão registrada no doc 04) |

## 2. Documentação oficial, cookbook, artigos e relatos (doc 05)

| Fonte | Ponto | Onde | Status |
|---|---|---|---|
| Docs OpenAI | `revised_prompt` e reescrita só na Responses API | Teste, braço C | Aplicado (a medir) |
| | Modelos atuais (2.5 sunburst/flare); `gpt-image-1` aposentado | Prompt §5, teste | Aplicado |
| | `quality` até `max`; subir qualidade antes de reescrever | Prompt §5 | Aplicado |
| | `safety_identifier`; verificação da organização | Prompt §5, arquitetura | Aplicado |
| | Erros: `image_generation_user_error` sem retry cego; backoff | Prompt §6 | Aplicado |
| | Componha a edição aprovada sobre o original (pixel-idêntico) | Prompt regra 9, ferramenta `composite_with_mask` | Aplicado; **ferramenta ainda a implementar** |
| | Medir custo por imagem aceita; repetir para consistência; baseline | Teste (`--repeats`, `eval_set.json`), arquitetura | Aplicado |
| | Latência até 2 min | Arquitetura (assíncrona), prompt §5 | Aplicado |
| Cookbook OpenAI | Pessoas, cenas amplas, transparência, brief criativo para anúncios | Prompt "Vocabulário" e "Guia por tipo" | Aplicado (v0.3) |
| Google DeepMind / Cloud | Direção de arte: luz, lente, filme, materialidade | Prompt "Vocabulário" | Aplicado (v0.3) |
| | Verbo forte no início; texto primeiro | Prompt "Vocabulário" | Aplicado (v0.3) |
| | Enquadramento positivo | Prompt regra 8 | Aplicado (a medir; a OpenAI usa exclusões) |
| Relatos / HN | Underdrawing e composição de texto por código | Prompt regra 7, ferramenta `compose_text_overlay` | Aplicado; **ferramenta a implementar** |
| | Dados e gráficos por código | Prompt regra 11, `render_chart` | Aplicado; **ferramenta a implementar** |
| | Modo Instant sem web/código; dados vêm do contexto | Prompt regra 11 | Aplicado |
| | Não reescrever demais (histórico DALL·E 3) | Prompt regras 1–3 | Aplicado |
| Moda / LangChain | Triage → skills por tipo → loop | Arquitetura passo 0, skill | Aplicado (desenho); implementação pendente |
| | Agente Brand Kit separado | Arquitetura passo 1, `get_brand_kit` | Aplicado (desenho); implementação pendente |
| | Poucas ferramentas (12–15) | Agente, arquitetura | Aplicado |
| | Cache de prompt | — | **Pendente** (implementação) |
| | Traces e avaliações desde o início | Arquitetura "Observabilidade" | Aplicado (desenho); implementação pendente |
| PromptEnhancer | Taxonomia de falhas (vinculação, negação, contagem) | Rubrica v2 (doc 04, prompt §6, teste) | Aplicado |
| Pesquisa VLM-as-judge | Generate–critique–refine | Etapa 5 (critic): `prompts/critic.system.md`, `prompts/rubric.json`, `test/critic.py` | Aplicado; **eficácia a medir** (critic pode ser leniente) |
| | Critic independente do designer; evidência antes da nota; em dúvida a nota menor; falha explícita se o JSON for inválido | `prompts/critic.system.md`, `test/critic.py` | Aplicado (v0.1, sem calibração) |
| | Calibrar contra avaliação humana e escolher o limiar pela falsa aprovação | `test/critic.py --calibrate`, `test/calibration/` | Aplicado (código); **pendente:** exemplos reais do CEO |

## 3. O que continua sem prova
1. Qual parte da diferença chat × API vem do harness e qual vem do serving do app: o teste A/B/C mede isso indiretamente.
2. Se o enquadramento positivo supera as listas de exclusão para o gpt-image-2.5.
3. Se o critic concorda com a avaliação humana (por isso o `ratings.csv` cego).
4. Se o custo do ciclo de revisão compensa em peças aceitas.
