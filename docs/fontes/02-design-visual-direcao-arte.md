> **Fonte do usuário, copiada integralmente em 04/11/2026. Não editar.** Estudo, conflitos e decisões em `docs/09-mapa-fontes-design.md`. O catálogo de estilos (seção 5) vive como dados em `prompts/estilos.json` e como skill em `skills/design-estilos/`.

---
name: design-visual-direcao-arte
version: 1.0.0
description: Skill de direcao de arte e UI para banners, flyers, pecas de social e criativos de trafego pago. Cobre fundamentos, especificacoes tecnicas, catalogo de 14 estilos visuais, compilador de prompts e gates de QA.
when_to_use: >
  Use quando a tarefa envolver criar, criticar, adaptar ou especificar peca visual
  (banner, flyer, criativo de social, landing, dashboard mockup), escolher um estilo
  visual, escrever prompt de geracao de imagem/UI, ou revisar qualidade de design.
triggers:
  - banner
  - flyer
  - criativo
  - social ads
  - landing page
  - dashboard UI
  - dark mode
  - glassmorphism
  - neo-brutalism
  - bento
  - prompt de design
outputs:
  - especificacao de peca
  - justificativa de decisao
  - checklist de QA preenchido
  - prompt corrigido
license: uso interno
---

# SKILL: Direcao de Arte Visual para Banners, Social e UI

Este documento e um **contrato de operacao** para um agente de IA. Nao e um artigo: e um conjunto de regras verificaveis, tabelas de decisao e filtros de qualidade. Leia inteiro antes de produzir qualquer saida.

---

## 0. Contrato de operacao

### 0.1 O que o agente deve fazer sempre

1. **Coletar 4 entradas antes de desenhar**: oferta em 1 frase, formato/proporcao, publico e nivel de consciencia, ativo de marca (logo, cores, fonte).
2. **Declarar o ponto focal** antes de qualquer decisao visual.
3. **Escolher 1 estilo** do catalogo (secao 4) e nomear o mecanismo que justifica a escolha.
4. **Emitir especificacao**, nao opiniao: cores em HEX, escala tipografica em px, spacing, raio, sombra.
5. **Escrever o racional**: 1 frase por decisao critica, no formato "escolhi X porque Y, abri mao de Z".
6. **Rodar os gates de QA** (secao 8) e reportar PASSA/FALHA item por item.

### 0.2 O que o agente nunca deve fazer

- Inventar metrica, benchmark ou dado de performance.
- Usar "bonito", "moderno", "clean" como justificativa.
- Escolher estilo por moda sem declarar o trade-off.
- Gerar texto dentro de imagem gerada por IA e considerar finalizado.
- Aprovar peca sem testar contraste e sem testar em tamanho reduzido.
- Alterar mais de uma variavel por rodada de teste.

### 0.3 Formato de resposta obrigatorio

```
OFERTA: ...
PONTO FOCAL: ...
ESTILO: <slug do catalogo> — mecanismo: ...
ESPECIFICACAO: (tabela)
RACIONAL: (1 frase por decisao)
QA: (tabela item / criterio / resultado)
RISCOS: (o que pode falhar e como detectar)
```

---

## 1. Pipeline de decisao (5 passos, nesta ordem)

| Passo | Pergunta | Saida |
|---|---|---|
| 1 | Qual e a unica acao desejada? | Oferta em 1 frase + CTA |
| 2 | Onde isso sera visto? | Proporcao, safe zone, tempo de leitura |
| 3 | Quem le e em que estado? | Nivel de consciencia, tolerancia a ruido |
| 4 | Qual estilo serve essa combinacao? | Slug + mecanismo + risco aceito |
| 5 | Como provo que funcionou? | Metrica + hipotese + variavel unica |

Regra dura: **nunca pule do passo 2 para o 4**. A causa mais comum de peca ruim e escolher estilo antes de saber onde ela vai aparecer.

---

## 2. Regras invariantes (nao negociaveis)

Estas 12 regras valem para qualquer estilo, formato ou cliente. Violacao = peca reprovada.

1. Um ponto focal por peca; se houver dois, um deles e subordinado por escala.
2. Hierarquia com 3 niveis e salto de escala de no minimo 2,5x entre headline e corpo.
3. Contraste de texto: >=4,5:1 normal; >=3:1 para texto grande (>=18pt ou >=14pt negrito).
4. Maximo 2 familias tipograficas; variacao por peso, nao por fonte.
5. Maximo 7 palavras por linha; 3 linhas por bloco em anuncio.
6. Um unico CTA, com verbo + beneficio; proibido "clique aqui", "saiba mais" isolado.
7. Safe zone 9:16: 14% topo, 35% base, 6% laterais.
8. Contraste e testado no **pior caso** do fundo (ponto mais claro e mais escuro).
9. Toda transparencia/blur precisa de fallback legivel e scrim atras do texto.
10. Uma unica fonte de luz por peca (vale para sombra, relevo, isometrico).
11. Espacamento apenas de uma escala fixa (4/8/12/16/24/32/48/64).
12. Toda peca passa no teste 120px + celular + brilho 50% antes de sair.

---

## 3. Constantes tecnicas

### 3.1 Tipografia

| Item | Valor |
|---|---|
| Tracking em display grande | negativo (referencia SF Pro: -0,31 a 17pt; -0,43 a 17pt+) |
| Tracking em texto pequeno | positivo |
| Entrelinha display | 1,05-1,15 |
| Entrelinha corpo | 1,4-1,6 |
| Corpo minimo digital | 16px |
| Headline minima digital | 32px |
| Escala recomendada | 1,25 / 1,333 / 1,5 |

### 3.2 Acessibilidade

| Tipo de texto | AA | AAA |
|---|---|---|
| Normal | 4,5:1 | 7:1 |
| Grande (>=18pt / >=14pt bold) | 3:1 | 4,5:1 |

### 3.3 Impressao (flyer)

| Item | Valor |
|---|---|
| Sangria | 3mm todos os lados |
| Zona segura | 3mm adicionais |
| Cor | CMYK |
| Resolucao | 300dpi no tamanho final |
| PDF | fontes embutidas ou em curvas, transparencia achatada |

### 3.4 Social / Meta

| Item | Valor |
|---|---|
| Formato default | 9:16 |
| Safe zone | 14% topo / 35% base / 6% laterais |
| Regra dos 20% de texto | nao existe desde setembro de 2020 |
| Duracao video | Reels/Stories 15-30s; Feed 30-60s |
| Consumo | projetar para mudo; informacao critica na tela |
| Volume de teste | 15-20 ativos conceitualmente distintos |
| Hook | primeiros 1,5s decidem; nunca abrir com logo |
| Re-hook | ~7s |

### 3.5 Easing e duracao

| Movimento | Duracao | Curva |
|---|---|---|
| Feedback imediato | 80-150ms | ease-out |
| Mudanca pequena | 150-250ms | ease-out |
| Transicao padrao | 220-400ms | ease-in-out |
| Transformacao de tela | 350-650ms | ease-in-out |
| Hero narrativo | 700-1200ms | ease-in-out |
| Saida | 70-80% da entrada | ease-in |
| Loop continuo | livre | linear |

Stagger entre itens: 40-80ms; sequencia total <=600-800ms.

---

## 4. Catalogo de estilos (14 fichas)

| Slug | Familia | Mecanismo | Melhor uso | Risco principal |
|---|---|---|---|---|
| dark_cyberpunk | material_luz | luz emitida em fundo escuro | gaming, tech, cripto | halation em texto neon |
| glassmorphism | material_translucido | blur + borda + scrim | badge, card sobre imagem | contraste variavel |
| minimal_flat | estrutura | subtracao + grid | SaaS, B2B, oferta | nada esconde erro |
| neo_brutalism | estrutura | contorno duro + cor de choque | marca jovem, social | sopa visual em tamanho pequeno |
| material3 | sistema | cor tonal + elevacao tonal | Android, dashboard | cor de marca substituindo semantica |
| skeuomorphism | material_realista | textura + relevo | audio, nostalgia | luz incoerente |
| aurora | material_gradiente | mesh gradient | saude, hero emocional | contraste imprevisivel |
| typographic | estrutura_tipo | tipo como arquitetura | agencia, hook de social | ilegivel sem craft |
| retro_pixel | estrutura_limite | grade de pixel | games, cultura dev | mistura com vetor suave |
| brutalism | anti_estilo | ausencia de estilo | galeria, dev tools | lido como amadorismo |
| isometric | tecnica_apresentacao | projecao 30 graus | logistica, processo | angulo inconsistente |
| claymorphism | material_volume | volume inflado | educacao, wellness | contraste baixo |
| bento | estrutura_grid | grid modular assimetrico | feature showcase, social | assimetria sem hierarquia |
| neumorphism | material_volume | sombra dupla no mesmo tom | acento apenas | hostil a acessibilidade |

### 4.1 Regras de aplicacao por estilo

**dark_cyberpunk** — preto profundo, nunca #000 em area grande; neon <=10% da area; neon jamais em corpo de texto; glow so em accent e CTA; numerais tabulares.

**glassmorphism** — o painel herda a cor do que esta atras; medir contraste no pior caso; scrim >=35%; `backdrop-filter` com fallback opaco; nunca para dados densos. Referencia normativa: material e camada funcional, nao camada de conteudo (Apple HIG).

**minimal_flat** — profundidade por cor de superficie, nao gradiente; escala tipografica obrigatoria; espaco em branco como elemento ativo.

**neo_brutalism** — sombra offset solida com 0 blur; contorno 2-4px; maximo 3-4 elementos; 2-3 cores em choque.

**material3** — elevacao por tonal surface; sombra so em FAB/dialogo/sheet; papeis de cor fixos (primary, secondary, tertiary, error); cor semantica nunca substituida por marca; niveis de contraste selecionaveis.

**skeuomorphism** — uma fonte de luz; highlight interno coerente; textura com escala realista (nao repeticao visivel).

**aurora** — gradiente e fundo, nunca conteudo; testar nos extremos; scrim para texto; 3-5 blobs no maximo.

**typographic** — display >=4x o corpo; tracking negativo proporcional; 1 cor para 1 palavra-chave; imagem opcional.

**retro_pixel** — paleta de 8-16 cores; fontes bitmap em multiplos de 8px; dithering em vez de blur; zero vetor suave.

**brutalism** — Times/mono, azul de link, layout quebrado com intencao; usar apenas quando o publico compartilha o codigo.

**isometric** — 30 graus consistentes; uma direcao de luz; grid axonometrico; objetos de altura multipla de 8.

**claymorphism** — raio 24-40px; sombra externa suave + interna clara; pastel sempre com texto escuro; evitar marca seria.

**bento** — celulas com superficie propria; hierarquia interna por peso; 1 cor por grupo; assimetria precisa de ancora visual.

**neumorphism** — nao usar como interface inteira; texto >=7:1; interativos exigem cor de acento + foco visivel; sempre oferecer alternativa com contraste.

---

## 5. Bloco consumivel por maquina

```json
{
  "dark_cyberpunk": {
    "family": "material_luz",
    "mecanismo": "luz emitida em fundo escuro",
    "surface": "#0B0D10 a #14161A (nunca #000 em área grande)",
    "text": "#F5F7FA / #C7CCD4",
    "accent": "1 neon (ciano, magenta ou verde-limão), ate 10% da area",
    "shadow": "glow apenas em accent e CTA; nunca em corpo de texto",
    "type": "sans geometrica/tecnica, tracking neutro, numerais tabulares",
    "risco": "halation: neon sobre preto engrossa glifos e derruba legibilidade",
    "melhor_uso": "gaming, tech, cripto, dev tools",
    "evitar": "varejo, oferta de preco, publico 45+"
  },
  "glassmorphism": {
    "family": "material_translucido",
    "mecanismo": "blur de fundo + borda clara + scrim",
    "surface": "preenchimento branco 8-20% + backdrop-blur 12-24px",
    "text": "branco puro sobre scrim >=35% de opacidade",
    "accent": "gradiente vivo apenas atras do vidro",
    "shadow": "borda 1px branca 20-35% + sombra suave ampla",
    "type": "sans humanista, peso medio, sem texto <14px",
    "risco": "contraste variavel: nao existe valor unico, precisa do pior caso",
    "melhor_uso": "badge, selo, card de controle sobre imagem",
    "evitar": "tabela densa, texto pequeno, fundo cinza chapado (efeito desaparece)"
  },
  "minimal_flat": {
    "family": "estrutura",
    "mecanismo": "subtracao + grid + escala tipografica",
    "surface": "#FFFFFF / #F6F7F9",
    "text": "#0F1115",
    "accent": "1 cor solida, uso semantico",
    "shadow": "quase nenhuma; separacao por cor de superficie",
    "type": "sans neutra (Helvetica/Inter-like), escala 1.25-1.333",
    "risco": "sem efeito para esconder erro: toda falha aparece",
    "melhor_uso": "SaaS, B2B, conversao, oferta",
    "evitar": "marca que precisa de personalidade forte"
  },
  "neo_brutalism": {
    "family": "estrutura",
    "mecanismo": "contorno duro + sombra sem blur + cor de choque",
    "surface": "bege, off-white ou cor chapada saturada",
    "text": "#000 puro",
    "accent": "2-3 cores em choque (amarelo, rosa, ciano)",
    "shadow": "offset 4-8px solido, 0 blur",
    "type": "grotesca pesada ou mono; tracking apertado",
    "risco": "sopa visual em tamanho pequeno",
    "melhor_uso": "creator economy, moda, marca jovem, hook de feed",
    "evitar": "institucional, saude, financeiro tradicional"
  },
  "material3": {
    "family": "sistema",
    "mecanismo": "cor tonal gerada + elevacao por superficie tonal",
    "surface": "tonal surface 1-5 (elevacao por cor, nao sombra)",
    "text": "on-surface / on-surface-variant",
    "accent": "primary/secondary/tertiary + error semantico",
    "shadow": "reservada a FAB, dialogo, sheet",
    "type": "Google Sans/Roboto-like, escala M3",
    "risco": "usar marca no lugar de cor semantica de erro/sucesso",
    "melhor_uso": "produto Android, app de sistema, dashboard",
    "evitar": "marca com paleta proprietaria rigida"
  },
  "skeuomorphism": {
    "family": "material_realista",
    "mecanismo": "textura + relevo + sombra realista",
    "surface": "couro, papel, metal, madeira",
    "text": "serif/sans com emboss discreto",
    "accent": "dourado, metalico",
    "shadow": "multiplas camadas + highlight interno",
    "type": "serif classica ou sans humanista",
    "risco": "incoerencia de fonte de luz entre elementos",
    "melhor_uso": "audio, instrumentos, nostalgia, citacao",
    "evitar": "produto digital moderno, mobile first"
  },
  "aurora": {
    "family": "material_gradiente",
    "mecanismo": "mesh gradient difuso organico",
    "surface": "3-5 blobs desfocados, pastel ou saturado",
    "text": "branco/preto com scrim",
    "accent": "derivado do gradiente",
    "shadow": "nenhuma; profundidade vem do blur",
    "type": "sans leve, titulos finos grandes",
    "risco": "contraste imprevisivel no ponto mais claro do gradiente",
    "melhor_uso": "saude, meditacao, fintech emocional, hero de landing",
    "evitar": "dados, texto longo"
  },
  "typographic": {
    "family": "estrutura_tipo",
    "mecanismo": "tipografia como arquitetura",
    "surface": "monocromatico (preto/branco) ou 1 cor",
    "text": "display em escala extrema (>=4x o corpo)",
    "accent": "1 cor para 1 palavra-chave",
    "shadow": "nenhuma",
    "type": "grotesca de display + texto em peso leve",
    "risco": "vira ilegivel sem dominio de tamanho optico e tracking",
    "melhor_uso": "agencia, midia, manifesto, hook de social",
    "evitar": "quando ha imagem de produto obrigatoria"
  },
  "retro_pixel": {
    "family": "estrutura_limite",
    "mecanismo": "grade de pixel + paleta limitada",
    "surface": "paleta de 8-16 cores",
    "text": "bitmap/pixel font em multiplos de 8px",
    "accent": "1-2 cores de destaque",
    "shadow": "dithering, nunca blur",
    "type": "pixel exclusivamente",
    "risco": "misturar pixel com vetor suave",
    "melhor_uso": "games indie, cultura dev, nostalgia 90s",
    "evitar": "leitura longa, legibilidade pequena"
  },
  "brutalism": {
    "family": "anti_estilo",
    "mecanismo": "ausencia deliberada de estilo",
    "surface": "branco/cinza padrao",
    "text": "#000, Times ou mono padrao",
    "accent": "azul de link (#0000EE)",
    "shadow": "nenhuma",
    "type": "default do sistema, tamanhos sem escala",
    "risco": "lido como amadorismo por publico nao iniciado",
    "melhor_uso": "galeria, arte, dev tools, portfolio",
    "evitar": "trafego pago de varejo"
  },
  "isometric": {
    "family": "tecnica_apresentacao",
    "mecanismo": "projecao axonometrica 30 graus",
    "surface": "fundo neutro para destacar objetos",
    "text": "sans neutra, pouca quantidade",
    "accent": "2-4 cores para categorias",
    "shadow": "sombra suave sob os objetos, 1 direcao de luz",
    "type": "sans geometrica",
    "risco": "angulos inconsistentes quebram a ilusao",
    "melhor_uso": "logistica, smart city, infraestrutura, processo",
    "evitar": "retrato, emocao, storytelling humano"
  },
  "claymorphism": {
    "family": "material_volume",
    "mecanismo": "volume inflado + sombra interna e externa",
    "surface": "pastel 3D, cantos 24-40px",
    "text": "sans arredondada, peso medio",
    "accent": "pastel saturado",
    "shadow": "externa suave + interna clara (luz superior)",
    "type": "sans rounded",
    "risco": "contraste baixo por natureza do pastel",
    "melhor_uso": "educacao, infantil, wellness, onboarding",
    "evitar": "marca seria, dados, B2B"
  },
  "bento": {
    "family": "estrutura_grid",
    "mecanismo": "grid modular assimetrico",
    "surface": "cards com superficie propria",
    "text": "hierarquia por peso dentro de cada celula",
    "accent": "1 cor por grupo de celulas",
    "shadow": "sutil ou nenhuma",
    "type": "sans neutra, escala consistente entre celulas",
    "risco": "assimetria sem hierarquia vira bagunca",
    "melhor_uso": "feature showcase, landing, social multiargumento",
    "evitar": "conteudo unico e simples"
  },
  "neumorphism": {
    "family": "material_volume",
    "mecanismo": "sombra clara + escura sobre o mesmo tom",
    "surface": "tom unico #E0E5EC-like",
    "text": "cinza escuro, >=7:1 recomendado",
    "accent": "obrigatorio em interativos (senao nao ha affordance)",
    "shadow": "2 sombras opostas, blur 8-20px",
    "type": "sans neutra",
    "risco": "hostil a acessibilidade por design: contraste baixo estrutural",
    "melhor_uso": "acento, toggle decorativo, nao interface inteira",
    "evitar": "texto pequeno, dados, qualquer fluxo critico"
  }
}
```

---

## 6. Compilador de prompt

### 6.1 Template

```
[OBJETIVO] + [ESTILO: nomear o MECANISMO, nao so o nome] + [SISTEMA: grid, paleta com papeis, tipografia e peso] + [RESTRICOES: sem texto renderizado, area limpa para copy, contraste medido, uma fonte de luz] + [PROPORCAO NUMERICA] + [NEGATIVE PROMPT]
```

### 6.2 Anti-padroes de prompt (remover)

| Ruido | Por que remover |
|---|---|
| "8k", "4k", "high quality" | nao controla decisao visual |
| "trending on Dribbble" | enviesa para mockup decorativo |
| "wide format" | vago; usar 16:9, 4:5, 9:16 |
| "beautiful UI" | nao e criterio verificavel |
| texto descritivo dentro da imagem | sai deformado; montar tipo depois |

### 6.3 Exemplo ruim vs. bom

RUIM:
`Cyberpunk dashboard, 8k, trending on Dribbble, neon, high quality, wide format`

BOM:
`Cybersecurity operations dashboard UI, dark theme with near-black surfaces (#0B0D10) and a single neon accent used on <=10% of the area, elevation via tonal surface color instead of drop shadows, 12-column grid, 8px spacing scale, tabular numerals for data, no glow on body text, no decorative elements, empty state, no text labels rendered, 16:9, negative: gibberish text, glow bleed, oversaturated background`

### 6.4 Regra de finalizacao

Gerar com IA apenas **layout, clima e composicao**. Tipografia, preco, selo, logo e CTA sao montados manualmente. Texto dentro de imagem gerada e sempre provisorio.

---

## 7. Modelos de saida

### 7.1 Especificacao de peca (preencher)

| Campo | Valor |
|---|---|
| Objetivo | |
| Formato | |
| Ponto focal | |
| Estilo (slug) | |
| Fundo | |
| Superficie | |
| Texto | |
| Acento | |
| Tipografia | |
| Grid / spacing | |
| Sombras | |
| CTA | |
| Metrica de sucesso | |

### 7.2 Racional (3 linhas)

- Escolhi `<decisao>` porque `<motivo ligado ao objetivo>`.
- Abri mao de `<alternativa>` porque `<custo maior que beneficio>`.
- O risco aceito e `<risco>`; detecto se falhar por `<sinal observavel>`.

---

## 8. Gates de QA (binario)

| # | Gate | Criterio | Resultado |
|---|---|---|---|
| 1 | Ponto focal unico | 1 elemento domina por escala ou contraste | PASSA/FALHA |
| 2 | Hierarquia | 3 niveis, salto >=2,5x | PASSA/FALHA |
| 3 | Contraste texto | >=4,5:1 normal, >=3:1 grande | PASSA/FALHA |
| 4 | Contraste no pior caso | testado no ponto extremo do fundo | PASSA/FALHA |
| 5 | Legibilidade 120px | texto lido em miniatura | PASSA/FALHA |
| 6 | Safe zone | respeitada por formato | PASSA/FALHA |
| 7 | CTA | 1, verbo + beneficio, alto contraste | PASSA/FALHA |
| 8 | Tipografia | <=2 familias, escala coerente | PASSA/FALHA |
| 9 | Luz | uma fonte coerente | PASSA/FALHA |
| 10 | Fallback de transparencia | legivel sem blur | PASSA/FALHA |
| 11 | Densidade | <=7 palavras por linha | PASSA/FALHA |
| 12 | Marca | ancoras aplicadas, master editavel | PASSA/FALHA |

Uma falha = peca volta para revisao. Duas falhas na mesma dimensao = refazer do zero.

---

## 9. Rubrica de avaliacao (0-5)

| Nota | Descricao |
|---|---|
| 0 | Sem hierarquia, ilegivel, sem relacao com oferta |
| 1 | Estilo aplicado por moda, sem mecanismo declarado |
| 2 | Correto nos fundamentos, generico |
| 3 | Hierarquia clara, sistema consistente, especificacao completa |
| 4 | Craft alto: luz coerente, tipografia precisa, contraste no pior caso resolvido |
| 5 | Nivel referencia: nada acidental, racional defensavel, escala em 20+ pecas |

Nota 5 exige evidencia: peca + racional + metrica + consistencia entre pecas.

---

## 10. Anti-padroes (catalogo de falhas)

| Falha | Sintoma | Correcao |
|---|---|---|
| Estilo antes do briefing | peca bonita, oferta invisivel | voltar ao passo 1 do pipeline |
| Glass em tudo | texto ilegivel sobre imagem clara | scrim + superficie opaca para dados |
| Neon em texto | glifos engrossados, halation | neon so em accent |
| Neumorphism em fluxo critico | usuario nao identifica botao | acento + foco visivel |
| Sombra dura em tamanho pequeno | sopa visual | reduzir elementos |
| Gradiente atras de texto | contraste imprevisivel | scrim ou area calma |
| Redimensionamento mecanico | hierarquia quebrada por formato | redesenhar por formato |
| Prompt com "8k/Dribbble" | mockup decorativo | reescrever pelo template 6.1 |
| Texto gerado por IA | caracteres deformados | montar tipo manualmente |
| CTA generico | "clique aqui" | verbo + beneficio |

---

## 11. Glossario operacional

| Termo | Definicao |
|---|---|
| Mecanismo | a causa fisica/perceptual que produz o efeito do estilo |
| Scrim | camada semitransparente atras do texto para garantir contraste |
| Tonal surface | elevacao comunicada por cor de superficie, nao por sombra |
| Safe zone | area que a interface da plataforma nao cobre |
| Hook | primeiro frame/linha que interrompe o scroll |
| Hook rate | views de 3s / impressoes |
| Hold rate | retencao em 15s |
| Pior caso de contraste | ponto mais claro ou mais escuro do fundo da peca |
| Stagger | atraso progressivo entre entradas de elementos |
| Fallback | versao legivel quando blur/transparencia falha |

---

## 12. Referencias normativas e de apoio

| Fonte | Uso neste documento |
|---|---|
| Apple HIG - Design principles | clareza, deferencia, profundidade |
| Apple HIG - Materials | material como camada de hierarquia |
| Apple HIG - Typography | tamanhos opticos e tracking |
| Apple - Liquid Glass (WWDC25) | vidro como camada funcional, nao de conteudo |
| Material Design 3 - color / dynamic color | papeis de cor, elevacao tonal, semantica |
| W3C WCAG 1.4.3 / 1.4.6 | 4,5:1, 3:1, 7:1 |
| MDN - Color contrast | tabela AA/AAA |
| Figma - Motion: easing | curvas e fisica |
| Solopress / Paperlust | sangria 3mm, CMYK, 300dpi |
| Predis / Showfolk | specs Meta, fim da regra dos 20% |
| LeadSync / Gyrify | pratica de teste, hook, significado de metricas |
| Farvist / Typenorm | falhas e correcoes do glassmorphism |
| Setproduct / Digital Kulture | falha de acessibilidade do neumorphism |
| Divmagic | bento grids em 2026 |

Lista completa com URL e nivel de confiabilidade: ver `design-nivel-apple-roadmap.md`, secao 9.

---

## 13. Instrucoes de aprendizagem para o agente

1. Ler secoes 0, 2 e 8 antes de qualquer geracao. Elas sao restricoes, nao contexto.
2. Ao escolher estilo, citar o `slug` e o `mecanismo`; nunca apenas o nome popular.
3. Ao receber pedido vago, fazer no maximo 2 perguntas: oferta e formato. Depois assumir o resto e declarar a suposicao.
4. Ao revisar peca existente, responder no formato: gate reprovado, evidencia, correcao minima.
5. Ao escrever prompt de imagem, aplicar secao 6 integralmente e remover os anti-padroes da 6.2.
6. Nunca afirmar resultado de performance sem dado fornecido pelo usuario.
7. Ao propor teste, declarar hipotese, variavel unica, metrica e criterio de decisao.
8. Manter vocabulario do glossario (secao 11) para permitir auditoria.
