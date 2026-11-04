# 05 — Evidências: documentação oficial, artigos, pesquisa e relatos de quem usa

Pesquisa feita em 04/11/2026 pelo navegador integrado (a busca web da organização está desativada; Reddit está bloqueado no navegador e não foi lido). Cada afirmação traz o nível de confiança:

- **[Oficial]** documentação ou cookbook do fornecedor.
- **[Prod]** relato de quem usa em produção (comunidade OpenAI, Hacker News, blog técnico).
- **[Pesquisa]** artigo acadêmico.
- **[Inferência]** conclusão minha, sem fonte direta.

Fontes lidas por inteiro ou em trechos extensos estão na seção 8. Artigos de comparação de terceiros sobre "gpt-image-2 vs Nano Banana" apareceram na busca, mas **não foram lidos**; não uso nenhuma afirmação deles.

---

## 1. A pergunta central: por que o chat gera imagem melhor que a API?

### 1.1 O que a OpenAI diz oficialmente
1. **[Oficial]** Na **Responses API**, com a ferramenta `image_generation`, "o modelo principal (por exemplo gpt-5.5) revisa automaticamente o seu prompt para melhorar o desempenho", e o resultado vem no campo `revised_prompt`. Na **Image API** (`/images/generations`), não há esse passo: o texto vai direto ao modelo de imagem.
2. **[Oficial]** A Responses API acrescenta ao Image API: edição multi-turno (`previous_response_id`), imagens por File ID, e o parâmetro `action` (`auto`, `generate`, `edit`) para o modelo decidir entre criar e editar.
3. **[Oficial]** A própria OpenAI lista limitações: latência de até 2 minutos em prompts complexos; texto "ainda pode falhar em posição e nitidez precisa"; **consistência de elementos de marca e personagens recorrentes pode falhar entre gerações**; controle de composição em layouts estruturados é limitado.
4. **[Oficial]** Nenhum documento que li explica o app ChatGPT. O que o app tem a mais está no system prompt vazado (ferramenta `image_gen`, modos Thinking/Instant com busca e código, memória), não na documentação.

### 1.2 O que relatam os desenvolvedores
- **[Prod]** Fórum OpenAI, mai/2025 (`gpt-image-1`): texto de rótulos e uso de imagens de referência saem mais nítidos e corretos na interface web do que na API com `quality=high`, usando o exemplo da própria documentação. Sem resposta oficial.
- **[Prod]** Fórum OpenAI, ago/2025: caricaturas com mesma foto e mesmo prompt; no ChatGPT a identidade facial é preservada, na API o rosto distorce. Um segundo usuário em mar/2026 diz continuar com o problema e suspeita de um modelo mais rápido para a API. O tópico foi **fechado por inatividade** em ago/2026, sem resposta.
- **[Prod]** Fórum OpenAI, out/2025 a fev/2026: o caso mais parecido com o nosso. Quem gera "packshots" de roupa tentou **replicar o chat usando a Responses API com gpt-5 + ferramenta de imagem** e ainda obteve qualidade pior (detalhes da peça errados, luz inconsistente). Outros dois usuários confirmaram com `gpt-image-1.5` (insetos em flores) e relataram erros 500 e inconsistência. Ou seja: **usar a Responses API aproxima, mas não elimina a diferença.**
- **[Prod]** Mesma discussão: um colega com o mesmo prompt "consistentemente" obtinha melhor resultado no chat, o que o autor atribuiu possivelmente a personalização/memória. **Hipótese não confirmada.**
- **[Prod, histórico]** Em 2023, com o DALL·E 3, o padrão se inverteu: a API **reescrevia demais** o prompt e mudava o estilo pedido (ex.: "anime japonês" virava "ukiyo-e"), e o ChatGPT respeitava melhor. Um funcionário da OpenAI reconheceu o problema e disse que ia ajustar para "adicionar detalhe, mas não reescrever sem necessidade". **Lição: reescrever o prompt não é bom por si; reescrever preservando o que o cliente pediu é o que importa.**
- **[Prod]** Hacker News, mai/2026, comentário sobre o tema: modelos de imagem "são só tokens de texto entrando e tokens de imagem saindo"; para melhorar, é preciso "um processo agêntico por cima: estratégia, revisão, nova tentativa", como a diferença entre pedir código one-shot e usar um agente com ferramentas. O autor acredita que Nano Banana e gpt-image-2 já fazem um pouco disso internamente.
- **[Prod]** Blog de um desenvolvedor sobre infográficos com ChatGPT Images 2 (abr/2026), confirmado por um comentário no HN: **no modo Instant o modelo de imagem não tem acesso à web nem executa código, mas não avisa** e inventa dados plausíveis; no modo Thinking sim. Usando a API diretamente, um usuário do HN observou que a imagem parecia usar dados atuais, mas usou dados de 2025.

### 1.3 Conclusão fundamentada
A diferença não vem de um único fator. As evidências sustentam três contribuintes:

1. **Reescrita do prompt por um modelo de raciocínio** (oficial). A Image API não tem; a Responses API tem.
2. **Contexto e ferramentas do ChatGPT**: busca na web, execução de código, memória, instruções de personalização, imagens da conversa (system prompt vazado + relatos). Nada disso existe numa chamada crua.
3. **Possíveis diferenças de serving/versão do modelo entre app e API**: relatadas pelos usuários, **sem confirmação oficial**. O nosso teste A/B/C vai medir isso de forma indireta (se C, via Responses API, ainda ficar abaixo do chat, o resto é harness do app ou serving).

Esse último ponto é um risco real para o projeto: **não dá para garantir paridade total com o app ChatGPT**. A meta realista é "qualidade de produção para a nossa marca", medida por rubrica própria, e não "idêntico ao chat".

---

## 2. Modelos e parâmetros atuais (importante: o teste anterior usava um modelo aposentado)

- **[Oficial]** Modelos atuais: `gpt-image-2.5-sunburst` (base, foco em qualidade e edição precisa) e `gpt-image-2.5-flare` (pequeno, foco em velocidade, qualidade comparável ao gpt-image-2). `gpt-image-1` aparece como **aposentado** e `gpt-image-1.5` como depreciado.
- **[Oficial]** `quality`: `low, medium, high, xhigh, max, auto`. Aumentar qualidade "não garante resultado melhor em todos os prompts". Fluxo recomendado: validar qualidade primeiro, depois reduzir latência; testar qualidade antes de reescrever prompt.
- **[Oficial]** `size`: livre se cada lado ≤ 3840, múltiplo de 16, razão ≤ 3:1, total entre 655.360 e 8.294.400 pixels. Acima de 2560×1440 é experimental.
- **[Oficial]** Transparência: `background="transparent"` + PNG ou WebP; conferir o canal alfa (cabelo, vidro, sombras). Em edições repetir "preserve o fundo transparente".
- **[Oficial]** Pode ser exigida **verificação da organização** para usar os modelos de imagem; recomendado enviar `safety_identifier` (hash do usuário). O parâmetro `user` está depreciado.
- **[Oficial]** Preço: igual para os dois modelos 2.5 por token ($30/M tokens de imagem de saída, $5/M texto de entrada); o custo por imagem varia com qualidade e tamanho. **Cache de entrada só vale na Responses API.** Na Responses API soma-se o custo do modelo principal.
- **[Oficial]** Moderação: `moderation=auto|low`. Erros `image_generation_user_error` (ex.: `moderation_blocked`) **não devem ser repetidos sem alterar prompt/imagem**; erros transitórios (rate limit, 5xx) com backoff.
- **[Prod]** Um desenvolvedor com ~50 mil imagens geradas via API reportou latência média de ~104 s com gpt-image-2 e ~35–40 s com o 2.5 (relato único, em carga dele; a própria OpenAI avisa para medir na sua carga). **Implicação: o agente precisa ser assíncrono (fila + webhook/polling), não uma requisição HTTP síncrona.**

---

## 3. Boas práticas de prompting: onde as fontes concordam e onde divergem

### Concordam (alta confiança)
| Prática | OpenAI [Oficial] | Google [Oficial] | Prod |
|---|---|---|---|
| Ordem cena → assunto → detalhes → restrições, com uso pretendido | ✔ | ✔ (Subject+Action+Context+Composition+Style) | |
| Texto entre aspas, tipografia e posição | ✔ | ✔ | |
| Ser específico em materiais, luz, câmera | ✔ | ✔ | |
| Iterar uma mudança por vez | ✔ | ✔ | ✔ (evitar one-shot) |
| Referências numeradas com papel | ✔ | ✔ (até 14 imagens) | |
| Mencionar formato/proporção pedida | ✔ | ✔ | |
| Prompt narrativo, não lista de palavras-chave | ✔ | ✔ | |

### Divergem (decidir com teste)
- **Negativos.** Google recomenda **enquadramento positivo** ("rua vazia" em vez de "sem carros"). A OpenAI usa listas de exclusão ("no watermark, no extra text, no logos") nos próprios exemplos. Um relato de produção com Nano Banana 2 Lite diz que o modelo insere texto em toda imagem e que os negativos funcionam bem para removê-lo. **Decisão provisória:** descrever positivamente o que queremos e manter uma linha curta de exclusões padrão; medir no teste.
- **Quanto expandir.** O Google/DeepMind: "mesmo prompts curtos geram boas imagens; adicione detalhe aos poucos". A OpenAI: use "briefing criativo" para anúncios, estrutura rotulada para produção. O histórico do DALL·E 3 mostra o risco de expandir demais. **Decisão:** normalizar quando o pedido já é detalhado; expandir só com contexto de marca real.
- **Detalhes de câmera.** OpenAI: especificações são "pistas de aparência, não simulação física". Google: recomenda lente, f-stop, filme. Usar como linguagem de estilo, não como garantia.
- **Modelo pensa antes?** O Google diz que o Nano Banana "usa raciocínio profundo para entender o prompt antes de gerar". O gpt-image tem a reescrita do modelo principal só na Responses API. Para nossa arquitetura, o briefing do diretor de arte cumpre esse papel nos dois.

### Específicos do Google úteis para nós
- **[Oficial]** "Text-first hack": primeiro conversar com o modelo para gerar os conceitos de texto, depois pedir a imagem com esse texto.
- **[Oficial]** Pedir várias variações na mesma chamada (3 mockups, 4 paletas) para comparar.
- **[Oficial]** Dar **nome distinto a cada personagem/objeto** nas referências para manter consistência.
- **[Oficial]** Todas as imagens do Google trazem marca SynthID e credenciais C2PA. Não verifiquei o equivalente da OpenAI. Relevante para entrega a cliente: não remover metadados sem decisão jurídica.

---

## 4. Técnicas validadas por prática (as mais úteis para peças de cliente)

### 4.1 "Underdrawing": texto e números exatos via código
- **[Prod]** Técnica descrita por um desenvolvedor (abr/2026): gerar o layout, números e textos em **SVG/HTML** (determinístico), exportar PNG, entregar ao modelo de imagem como base com a instrução de transformar o visual **preservando os números/títulos exatamente**. Em casos difíceis, o modelo ainda erra um elemento (ex.: um número deformado); então ele **reaplica o texto por cima da arte final, com SVG**, e garante precisão ao custo de uma integração visual um pouco menos natural. Testado com Gemini 3 Pro; o autor reporta que **o ChatGPT Images 2 falhou no mesmo teste sem a técnica**.
- **[Prod]** A discussão no HN (127 comentários) confirma o padrão geral: usar código para o que precisa ser exato e o modelo de imagem para o visual; vários relatam o fluxo inverso e o "não one-shot" (editar manualmente e reenviar para "limpar").
- **Aplicação para nós [Inferência]:** logos, preços, datas, CTAs e QR/códigos **nunca** dependem do modelo. O agente deve gerar a arte sem texto e **compor o texto em HTML/SVG por cima**, ou usar o underdrawing quando o texto precisa ficar integrado à cena. Isso também resolve a nota da OpenAI de que a consistência de elementos de marca pode falhar.

### 4.2 Composição pixel-idêntica
- **[Oficial]** "Se uma região precisa permanecer idêntica pixel a pixel, componha a edição aprovada sobre a imagem original em vez de depender só do prompt." Edições repetidas podem alterar detalhes que se queria preservar.
- **Aplicação [Inferência]:** edições de peças aprovadas (troca de texto, produto) passam por máscara + composição no código; o agente valida com diff de pixels fora da máscara.

### 4.3 Dados factuais em imagem
- **[Prod]** Infográficos gerados "parecem certos" e podem estar errados; o texto tende a sair correto, **gráficos de dados não**. Colocar dados corretos no contexto reduz mas não elimina o erro.
- **Aplicação:** gráficos e dados reais renderizados por código (matplotlib/HTML), nunca pelo modelo de imagem. Isso coincide com a regra da Meta e com a política do agent mode da OpenAI.

---

## 5. Como times de produção constroem agentes de design

**[Prod] Caso Moda** (plataforma de design com agentes, blog da LangChain, mar/2026; é texto publicado pela LangChain sobre um cliente, ou seja, com viés de divulgação):
- Três agentes: **Design Agent**, **Research Agent** (busca conteúdo de fontes como o site da empresa) e **Brand Kit Agent** (extrai cores, fontes, logos e voz de sites, brand books e decks).
- Fluxo **triage → skills → loop principal**: um modelo rápido e barato classifica o formato de saída (post, deck, logo...) e pré-carrega **skills em Markdown** com boas práticas daquele formato; o agente pode carregar mais skills no meio.
- **12–15 ferramentas sempre no contexto**, ~30 sob demanda; cada ferramenta extra custa 50–300 tokens e quebra o cache de prompt, então manter enxuto compensa.
- **Representação compacta do estado** (DSL) em vez de coordenadas cruas, porque LLMs são ruins em coordenadas.
- **Cache de prompt** com pontos de quebra após system prompt e após o bloco de skills.
- **Observabilidade por trace** como principal ciclo de feedback; **não tinham evals formais** ainda ("no roadmap").
- Produto editável: o usuário ajusta o resultado do agente (não é gerar-e-substituir).

**O que aproveitamos [Inferência]:** (1) agente "Brand Kit" separado do designer, alimentando o contexto do cliente; (2) triage barato antes do loop; (3) skills em Markdown por tipo de peça (a nossa taxonomia); (4) poucas ferramentas; (5) traces desde o dia 1; (6) **evals formais desde o início**, onde eles ainda não tinham.

---

## 6. Pesquisa acadêmica sobre reescrita de prompt e revisão

- **[Pesquisa] PromptEnhancer (Tencent Hunyuan, set/2025, CVPR 2026):** um reescritor treinado por RL, desacoplado do gerador, melhora o alinhamento texto-imagem, avaliado por um modelo de recompensa com **taxonomia de 24 pontos de falha** comuns (vinculação de atributos, negação, relações composicionais, contagem, etc.). Testado no HunyuanImage 2.1.
  - **Uso para nós:** reescrita desacoplada do gerador é válida; a taxonomia de falhas serve de **checklist do critic**: vinculação de atributos ("camisa vermelha, calça azul"), negação, contagem, relações espaciais, texto, anatomia. Adicionado à rubrica (doc 04, v2).
- **[Pesquisa] Generate–Critique–Refine** e **VLM-as-a-Judge:** padrão geral de usar um modelo de visão com rubrica para avaliar e dar feedback. As referências encontradas (arXiv 2511.04478 e relacionadas) **não foram lidas por inteiro**; tratamos o padrão como prática comum, não como garantia de melhoria.
- **Riscos conhecidos do critic [Inferência, a validar no teste]:** o mesmo modelo que gera pode ser leniente ao julgar; julgamento por LLM varia entre execuções; por isso a nossa rubrica tem notas por critério e vetos objetivos, e o teste mede **concordância com avaliação humana** (seção 7).

---

## 7. O que muda no nosso projeto (decisões)

| # | Decisão | Base |
|---|---|---|
| 1 | Trocar o modelo do teste para `gpt-image-2.5-sunburst` (qualidade) e `gpt-image-2.5-flare` (rascunho/velocidade); `gpt-image-1` está aposentado | Oficial |
| 2 | Teste com **3 braços**: A) Image API crua; B) nosso harness (briefing + geração + critic) sobre a Image API; **C) Responses API com a ferramenta nativa**, que usa a reescrita da OpenAI | Oficial + relatos |
| 3 | Registrar `revised_prompt` do braço C e comparar com o briefing do braço B | Oficial |
| 4 | Arte **sem texto**; texto, preço, CTA e logo compostos por código (HTML/SVG) ou por underdrawing | Prod + Oficial |
| 5 | Edição de peça aprovada: máscara + composição, validada por diff fora da máscara | Oficial |
| 6 | Dados/gráficos por código, nunca pelo modelo de imagem | Prod + vazados |
| 7 | Execução **assíncrona** (fila), rascunho em `low`, final em `medium/high`; medir custo por imagem **aceita** | Oficial + Prod |
| 8 | `safety_identifier` por cliente; tratar `image_generation_user_error` sem retry cego | Oficial |
| 9 | Conjunto de avaliação fixo (casos reais do CEO) + repetir cada caso ≥ 3 vezes para medir consistência | Oficial (migração) |
| 10 | Rubrica do critic ganha itens de vinculação de atributos, contagem e negação | Pesquisa |
| 11 | Agente "Brand Kit" separado do designer; triage barato; skills por tipo de peça; traces | Moda |
| 12 | Meta realista: qualidade de produção por rubrica, **não paridade garantida com o app ChatGPT** | Relatos |

---

## 8. Fontes consultadas

Documentação e guias oficiais
- OpenAI, Image generation guide (Image API vs Responses API, `revised_prompt`, parâmetros, limitações, moderação, custos): https://developers.openai.com/api/docs/guides/image-generation
- OpenAI, Image prompting (GPT Image 2.5, migração, composição pixel-idêntica): https://developers.openai.com/api/docs/guides/image-prompting
- OpenAI Cookbook, GPT Image Generation Models Prompting Guide (abr/2026): https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide
- Google DeepMind, prompt guide do Gemini Image / Nano Banana: https://deepmind.google/models/gemini-image/prompt-guide/
- Google Cloud, The ultimate Nano Banana prompting guide (mar/2026): https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana

Relatos de uso
- Comunidade OpenAI, "Difference in image quality between ChatGPT and API": https://community.openai.com/t/difference-in-image-quality-between-chatgpt-and-api/1355388
- Comunidade OpenAI, "Chatgpt image generation vs openai gpt-image-1 quality and text?": https://community.openai.com/t/chatgpt-image-generation-vs-openai-gpt-image-1-quality-and-text/1252035
- Comunidade OpenAI, "Discrepancy between Chat and Responses API Image Generation tool output": https://community.openai.com/t/1364399
- Comunidade OpenAI, "Why the Quality of DALL-E3 API is Significantly Lower Compared to the Original": https://community.openai.com/t/492970
- Comunidade OpenAI, "For Dalle-3 API users. Automatic prompt modification is a deep rabbit hole!": https://community.openai.com/t/510258
- Hacker News, "Using underdrawings for accurate text and numbers": https://news.ycombinator.com/item?id=47977990
- Sam Collins, Using "underdrawings" for accurate text and numbers: https://samcollins.xyz/underdrawings
- Inigo Surguy, Accurate infographics with ChatGPT Images 2: https://surguy.net/articles/chatgpt-infographics.html
- Comentários no HN sobre gpt-image-2 via API (latência, org verificada, Nano Banana 2 Lite): busca na API do HN por "gpt-image-2 api" e "nano banana vs gpt image"
- LangChain, How Moda builds production-grade AI design agents: https://www.langchain.com/blog/how-moda-builds-production-grade-ai-design-agents-with-deep-agents

Pesquisa
- PromptEnhancer (arXiv 2509.04545): https://arxiv.org/abs/2509.04545

## 9. Limites desta pesquisa
- Busca web nativa indisponível; usei um buscador via navegador. Reddit bloqueado.
- Páginas de lançamento da OpenAI (ChatGPT Images 2.0/2.5) carregaram sem texto legível; não as usei.
- Artigos de comparação de terceiros e a literatura de VLM-as-a-judge foram apenas listados, não lidos.
- Todos os relatos de comunidade são anedóticos; alguns são de modelos antigos (gpt-image-1, 1.5). Os de 2026 com gpt-image-2/2.5 são poucos.
- Nada foi testado com chave real ainda.
