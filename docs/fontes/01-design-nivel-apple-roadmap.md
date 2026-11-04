> **Fonte do usuário, copiada em 04/11/2026. Não editar.** Esta cópia **não inclui a seção 9 (referências, 90 URLs com rótulo de confiabilidade)**, que continua com o autor; o restante é o texto original. Estudo e mapeamento em `docs/09-mapa-fontes-design.md`; regras derivadas em `docs/08-fundamentos-design.md` e `skills/design-*`.

# Design Nível Apple — Roadmap Completo
### Craft, sistema, performance e carreira para banners de social e tráfego pago

> **Como usar este documento.** Ele está dividido em 6 blocos: (1) o modelo mental que define "nível Apple", (2) o mapa das 12 camadas de competência, (3) as especificações técnicas que quase ninguém mapeia, (4) percepção e semiótica, (5) performance e produção em escala, (6) roadmap de 12 meses + diagnóstico de gaps. As tabelas foram feitas para virar checklist operacional. As referências estão no final, com rótulo de confiabilidade.

---

## 1. O modelo mental: o que "nível Apple" significa em tráfego

Nível Apple não é fazer peça silenciosa e bonita. É fazer peça em que **nada é acidental**. A Apple formaliza isso em três princípios do Human Interface Guidelines:

- **Clareza** — hierarquia construída com ordem, espaçamento e contraste; legibilidade em todos os tamanhos.
- **Deferência** — o conteúdo lidera; a interface (o "chrome") recua; decoração não compete com função.
- **Profundidade** — camadas e movimento comunicam estrutura e hierarquia.

Aplicado a banner de social e tráfego, o princípio operacional é **clareza agressiva**: uma hierarquia tão inequívoca que funciona em 1,5 segundo, no mudo, na mão, num celular em movimento.

| Nível | O que faz | O que mede | Erro típico |
|---|---|---|---|
| Amador | Enche a peça de elementos | Se ficou "chamativo" | Decorar em vez de comunicar |
| Bom designer | Hierarquia correta, marca aplicada | Se o cliente aprovou | Otimiza para aprovação, não para resultado |
| Nível Apple | Hierarquia óbvia em 1 frame + sistema que escala | Hook rate, hold rate, CTR, CPL | Nenhum — cada elemento tem função declarada |

A virada de chave é sair de **output** (a peça entregue) para **outcome** (o efeito da peça). O júnior pergunta "ficou bonito?"; o sênior pergunta "resolveu o problema?".

---

## 2. O mapa das 12 camadas

A formação típica cobre 4 dessas camadas. Um designer de elite opera todas e sabe qual delas decide cada peça.

| # | Camada | O que dominar | Como é testada |
|---|---|---|---|
| 1 | Percepção (Gestalt) | Proximidade, similaridade, fechamento, região comum, figura-fundo, continuidade, simetria/prägnanz | O olho agrupa o que você quer? |
| 2 | Composição | Peso visual, balanceamento, ponto focal único, espaço negativo, terços e diagonais | A peça em miniatura ainda funciona? |
| 3 | Tipografia | Escala, tamanho óptico, tracking, entrelinha, kerning, hierarquia, famílias | Teste dos 3 níveis sem cor |
| 4 | Cor | Modelos (sRGB/P3/CMYK), contraste, temperatura, saturação como orçamento, papéis | Contraste medido, não "achado" |
| 5 | Imagem e direção de arte | Luz, sombra, perspectiva, enquadramento, styling, retoque, coerência de fonte de luz | Composição integrada vs. colagem |
| 6 | Semiótica e repertório | Códigos culturais, história do design, referências indexadas por princípio | Você nomeia *por que* funciona |
| 7 | Estratégia e copy | Público, oferta, proposta de valor, hook, CTA, consciência de funil | A peça sem texto ainda comunica? |
| 8 | Sistema e marca | Tokens, grid por formato, componentes, governança, escala de produção | 50 peças parecem irmãs |
| 9 | Movimento e som | Easing, timing, stagger, ritmo, áudio, kinetic type | A animação explica ou decora? |
| 10 | Produção técnica | Especificações, sangria, perfis de cor, exportação, nomenclatura, versionamento | Arquivo aprovado sem retrabalho |
| 11 | Performance e mídia | Hook rate, hold rate, CTR, CPL, fadiga criativa, teste, matriz de criativos | A peça conecta a um número |
| 12 | Processo, negócio e ética | Briefing, crítica, apresentação, precificação, IA, direitos de uso | Você lidera decisão, não executa tarefa |

**Regra de investimento:** a maioria investe 90% do tempo nas camadas 2–5 e zero nas camadas 6, 7, 8, 10, 11 e 12 — que são justamente as que separam "bom designer" de "designer de referência".

---

## 3. Especificações técnicas (as constantes do sistema)

### 3.1 Tipografia

A Apple trata tipografia como sistema, não como escolha de fonte: as fontes do sistema têm **tamanhos ópticos dinâmicos** que interpolam o desenho do glifo conforme o tamanho, e o tracking muda em cada ponto da escala.

Tabela de tracking de referência (SF Pro):

| Tamanho | Tracking |
|---|---|
| 12pt | 0 |
| 13pt | −0,08 |
| 14pt | −0,15 |
| 16pt | −0,31 |
| 17pt | −0,43 |

Regras práticas:
- Quanto maior o título, **mais negativo** o tracking; texto pequeno pede tracking **positivo**.
- Entrelinha de display: 1,05–1,15. Corpo: 1,4–1,6.
- Máximo 2 famílias por peça; varie peso, não família.
- Nunca justifique texto curto (cria rios e buracos).
- Mínimos digitais: corpo ≥16px, headline ≥32px.

### 3.2 Contraste e acessibilidade (WCAG)

| Tipo de texto | Mínimo (AA) | Enhanced (AAA) |
|---|---|---|
| Texto normal | 4,5:1 | 7:1 |
| Texto grande (≥18pt ou ≥14pt negrito) | 3:1 | 4,5:1 |

Trabalhe com **AA como piso**, não como meta.

### 3.3 Impressão (flyer)

| Item | Especificação |
|---|---|
| Sangria | 3mm em todos os lados |
| Zona segura interna | 3mm adicionais |
| Cor | CMYK (com prova quando houver cor crítica de marca) |
| Resolução | 300dpi no tamanho final colocado |
| PDF | Fontes embutidas ou em curvas; transparências achatadas |
| Exemplo A5 | 148×210mm → documento 154×216mm |

### 3.4 Social / Meta

| Item | Especificação |
|---|---|
| Formato default | 9:16 vertical (1:1 e 16:9 recortam mal em mobile) |
| Safe zone 9:16 | ~14% topo, ~35% base, ~6% laterais |
| Regra dos 20% de texto | **Não existe mais** — removida pela Meta em setembro de 2020 |
| Duração | Reels/Stories 15–30s; Feed 30–60s; >90s raramente compensa |
| Áudio | Projete para consumo no mudo — tudo que importa escrito na tela |
| Densidade | Máx. 7 palavras por linha; 3 linhas em anúncio |

### 3.5 Anatomia e checklist de aceite (banner/flyer)

| Dimensão | Padrão |
|---|---|
| Zonas | Topo: logo/value prop — Meio: mensagem + visual — Base: CTA |
| Ponto focal | Um só, declarado antes de desenhar |
| CTA | Um só, alto contraste, área terminal, mínimo 44px de toque, verbo + benefício (nunca "clique aqui") |
| Conceito | Uma ideia por peça; detalhe vai para a landing page |
| Marca | Âncoras fixas (logo, tipo, espaçamento) + master editável |
| Contraste | 4,5:1 texto / 3:1 texto grande |
| Teste final | 120px de largura, celular, brilho 50% |

As 7 perguntas de revisão (Adobe): qual o objetivo, qual a hierarquia, como está o layout, a tipografia está legível, cor e contraste funcionam, a peça é coerente com a marca, ela cabe no comportamento da plataforma.

### 3.6 Pipeline e governança

- Nomenclatura: `campanha_formato_conceito_versao`.
- Sempre master editável + export + assets aprovados com data.
- Adaptação por formato ≠ redimensionamento mecânico: cada formato exige hierarquia própria.
- Versionamento e arquivo de peças reprovadas **com motivo** (material de treino mais valioso do time).

---

## 4. Percepção e semiótica: por que uma peça "parece caro"

Nível Apple é percepção controlada. Os mecanismos são conhecidos e treináveis.

| Princípio (Gestalt) | O que faz | Uso em banner |
|---|---|---|
| Proximidade | Agrupa por distância, sem precisar de borda ou linha | Separa oferta de CTA sem caixas |
| Similaridade | Cria ritmo e família visual | Série de selos, ícones, chips |
| Fechamento | O cérebro completa a forma | Autoriza minimalismo e recorte ousado |
| Região comum | Elementos dentro do mesmo contorno viram um grupo | Card de preço, bloco de prova |
| Figura-fundo | Separação instantânea entre sujeito e fundo | Decisiva em fundo fotográfico |
| Continuidade | O olho segue linhas e direções | Direção do olhar do modelo até a oferta |
| Prägnanz | A leitura mais simples vence | Se a peça precisa ser decifrada, perdeu |

Sinais objetivos de "craft caro":
- Uma única fonte de luz coerente em todos os elementos.
- Sombras com opacidade e raio proporcionais à escala do objeto.
- Grão/textura sutil unificando camadas.
- Alinhamentos ópticos corrigidos (não matemáticos).
- Vocabulário curto repetido com precisão — restrição, não variedade.

### 4.1 Efeitos: onde está a técnica real

"Efeito" profissional quase nunca é filtro; é **construção de profundidade e percepção**: layering com sombra/blur coerentes, grão para tirar o aspecto plástico, blend modes para unificar colagem, e tipografia como elemento gráfico (type collage, letterforms elásticas, tipografia cinética).

### 4.2 Motion: timing e easing

| Tipo de movimento | Duração |
|---|---|
| Feedback imediato (hover, press, toggle) | 80–150ms |
| Mudança de estado pequena (tooltip, menu) | 150–250ms |
| Transição padrão (drawer, modal, seção) | 220–400ms |
| Transformação estrutural / tela cheia | 350–650ms |
| Movimento narrativo / hero de campanha | 700–1200ms (raramente mais) |

Regras de curva:
- **ease-out** para entradas (chega rápido, assenta devagar).
- **ease-in** para saídas.
- **ease-in-out** para reposicionamento na tela.
- **linear** só para loops contínuos (spinner, progress bar, marquee).
- Saídas ~70–80% da duração da entrada.
- Stagger de 40–80ms entre itens; sequência total ≤600–800ms.

---

## 5. Performance e produção em escala

### 5.1 Estrutura de criativo

`Hook (0–1,5s) → problema → mecanismo/diferencial → prova → oferta → CTA`, com re-hook visual por volta dos 7s.

Tipos de hook que funcionam: interrupção de padrão, afirmação numérica específica, pergunta direta, antes/depois, demonstração do produto em uso, prova social. **Nunca abra com logo.**

### 5.2 Métricas e diagnóstico

| Métrica | Baseline | Bom | Topo | O que significa |
|---|---|---|---|---|
| Hook rate (views 3s ÷ impressões) | 20–25% | 30%+ | 30–45% | Primeiro frame funciona |
| Hold rate (15s) | — | — | — | Estrutura sustenta atenção |
| CTR | varia por canal | — | — | Interesse gerado |
| CPL/CPA | meta do negócio | — | — | Eficiência real |
| Frequência | <2–3 | — | — | Acima: fadiga, troque conceito |

Diagnósticos de bolso:
- **CTR alto + conversão baixa** → a peça promete o que a página não entrega.
- **CTR baixo + conversão alta** → problema de hook/primeira impressão, não de oferta.

### 5.3 Volume e teste

- **15–20 ativos conceitualmente distintos** por campanha Advantage+ (não 20 recortes da mesma ideia).
- Teste com hipótese declarada, **uma variável por vez**, duração pré-definida, ~100 conversões por variante e 95% de confiança.
- Cerca de 65% de quem assiste aos 3 primeiros segundos chega aos 10 — o gargalo é sempre o início.
- Banners animados/HTML5 tendem a superar estáticos em CTR; use quando o canal permitir.

### 5.4 Matriz de criativos (modelo de produção)

| Eixo | Exemplos |
|---|---|
| Ângulo | Dor, desejo, prova, comparação, urgência, educação |
| Formato | 1:1, 4:5, 9:16, 16:9 |
| Tratamento | Foto, tipografia dominante, colagem, 3D, UGC |
| Hook | Claim numérico, pergunta, demonstração, antes/depois |

Regra: varie **ângulo** antes de variar tratamento. Trocar cor não é teste de conceito.

### 5.5 Erros previsíveis (checklist negativo)

- Layout sobrecarregado — mensagens, imagens e logos competindo.
- Hierarquia fraca — não se sabe o que olhar primeiro.
- Texto ilegível no tamanho renderizado.
- CTA que se mistura ao fundo ou é vago.
- Contraste insuficiente.
- Redimensionamento mecânico entre placements.
- Imagem genérica/banco de imagem óbvio.
- Marca inconsistente entre peças da mesma campanha.
- Animação decorativa que distrai do CTA.
- Promessa que a landing page não cumpre (infla CTR, destrói conversão).
- Texto gerado dentro de imagem por IA sem revisão (caracteres deformados).

---

## 6. Roadmap de 12 meses

| Fase | Semanas | Entregável | Gate para avançar |
|---|---|---|---|
| N1 Fundamento | 1–6 | 10 peças reconstruídas + caderno de tipografia e cor | Hierarquia, safe zone e contraste corretos sem consultar |
| N2 Craft | 7–14 | 20 peças originais, 3 famílias visuais distintas | Peça legível em miniatura de 120px |
| N3 Sistema | 15–22 | Tokens, grid por formato, 6 componentes, 3 templates | Produzir 20 peças coerentes em 2h |
| N4 Motion | 23–34 | 10 vídeos 9:16 com 3 hooks cada | Hook rate ≥25% e timing dentro das tabelas |
| N5 Performance | 35–44 | Painel de criativo + 3 ciclos de teste documentados | Melhora mensurável em CTR ou CPL |
| N6 Autoridade | 45–52 | Manifesto de design + 3–5 cases profundos | Portfólio passa no teste de contratação |

### 6.1 Portfólio (N6)

3 a 5 cases profundos valem mais que 12 rasos. Estrutura recomendada:
- **Primeiros 30%** — problema em termos de negócio e posicionamento.
- **40%** — 2 a 3 decisões críticas, alternativas consideradas, o que foi descartado e por quê.
- **Fecho** — resultado mensurável + reflexão honesta sobre o que não funcionou.

### 6.2 Rituais permanentes

- Crítica semanal de 30 min, pauta fixa: *o que o olho vê primeiro / o que a peça pede / o que pode sair*.
- Biblioteca de referências indexada **por princípio**, não por estilo.
- Arquivo de peças reprovadas com motivo.
- Teste de subtração mensal: remover 30% dos elementos e defender o que sobrou.

---

## 7. Diagnóstico: onde aprimorar primeiro

### 7.1 Ranking de alavancagem

| Prioridade | Camada | Gap típico | Retorno | Esforço |
|---|---|---|---|---|
| 1 | Estratégia, oferta e hook (7 + 11) | Peça nasce do briefing, não de hipótese de comportamento | Multiplica tudo que você já sabe | Alto |
| 2 | Hierarquia e legibilidade no tamanho real (2 + 3) | Aprovado no zoom 200%, ilegível no feed | Imediato e barato | Baixo |
| 3 | Adaptação por formato (10) | Um master reduzido para todos os placements | Evita perda silenciosa | Baixo |
| 4 | Motion e hook visual (9) | Animação decorativa em vez de explicativa | Alto em tráfego frio | Médio |
| 5 | Apresentação e racional (12) | Entrega arquivo, não argumento | É o que bloqueia promoção | Baixo |
| 6 | Repertório e tendências (6) | Copiar estilo sem entender princípio | Diferencia, mas não corrige base | Contínuo |

### 7.2 Scorecard (0 a 2 por item)

- Consigo escrever a oferta em uma frase antes de abrir o Figma.
- Minha peça tem 3 níveis de hierarquia com salto de escala real.
- Testo toda peça a 120px e no celular antes de entregar.
- Meu CTA descreve o benefício, não "saiba mais".
- Cada formato tem adaptação de hierarquia, não redução.
- Sei o contraste medido (4,5:1 / 3:1) das minhas peças.
- Uso grid e escala de espaçamento definidos, não valores arbitrários.
- Tenho tokens e componentes que geram 20 peças coerentes.
- Sei o hook rate e o CTR das minhas últimas peças.
- Consigo nomear por que cada decisão visual foi tomada, em uma frase.
- Tenho cadência de teste com hipótese e métrica pré-registrada.
- Entrego com racional escrito e defendo em reunião.

**Leitura:** 0–8 = ainda em output (foque itens 1, 2, 3 e 10). 9–16 = nível sólido (foque sistema, teste e motion). 17–24 = já opera em outcome (foque autoridade: manifesto, cases, liderança de crítica).

### 7.3 Plano de 30 dias

| Semana | Foco | Entrega |
|---|---|---|
| 1 | Oferta e hierarquia | Oferta em 1 frase + hook em ≤7 palavras; refazer 5 peças antigas e comparar hook rate/CTR |
| 2 | Legibilidade real | Passe o portfólio no teste 120px + celular + brilho 50%; refaça as reprovadas |
| 3 | Adaptação por formato | 1 conceito em 4 formatos com hierarquia redesenhada, documentando o que mudou |
| 4 | Teste e racional | 1 teste de variável única, duração pré-definida; case de 1 página (problema, hipótese, decisão, resultado) |

---

## 8. Repertório 2026 (para diferenciar, não para copiar)

Tendências observadas nas fontes consultadas, com a ressalva de que tendência é camada 6 — diferencia, mas não corrige fundamento:

- Minimalismo arrojado com impacto (espaço negativo + cor forte).
- Hipercor / paletas hipersaturadas.
- Tipografia expressiva e elástica, letterforms exageradas.
- Layouts modulares e composição tipo bento.
- Colagem e mídia mista, scrapbook estruturado.
- 3D vetorial e 3D universalizado.
- Reação anti-polimento: grunge, neo-retro, imperfeição intencional, rabiscos.
- Realismo ambiental e híbridos humano + IA (99% dos criadores brasileiros já usam IA; ~metade usa diariamente).

---

## 10. Resumo executivo (1 página)

1. **Base inegociável:** hierarquia em 3 níveis, um ponto focal, contraste medido (4,5:1 / 3:1), safe zones respeitadas.
2. **Diferencial real:** sistema (tokens, componentes, grid por formato) — 20 peças coerentes em 2h.
3. **Multiplicador:** oferta clara + hook em 1,5s; 15–20 ativos conceitualmente distintos por campanha.
4. **Prova:** hook rate ≥25–30%, hold rate, CTR e CPL; teste de uma variável com 95% de confiança.
5. **Autoridade:** manifesto de design + 3–5 cases com problema, decisão e resultado.
6. **Erro a evitar:** estudar tendência e efeito antes de dominar oferta, hierarquia no tamanho real e adaptação por formato.
