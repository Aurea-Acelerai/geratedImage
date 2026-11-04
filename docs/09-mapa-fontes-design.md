# 09. Mapa das fontes de design (estudo de 04/11/2026)

Estudo das duas fontes do Kelvin e do que ficou no sistema. Fontes (cópias em `docs/fontes/`, não editar):
- **F1** `01-design-nivel-apple-roadmap.md`: roadmap de design "nível Apple" (sem a seção 9, de referências).
- **F2** `02-design-visual-direcao-arte.md`: skill de direção de arte e UI, escrita como contrato para agente.

## 1. Resumo

- **F1 explica o porquê** (modelo mental, 12 camadas, percepção) e **F2 diz como validar** (12 invariantes, 12 gates binários, catálogo de 14 estilos, compilador de prompt). Já havíamos destilado F1 em `docs/08` e nas skills; F2 trouxe o que faltava: **estilos, gates e especificação de peça**.
- Entrou agora: `prompts/estilos.json` e a skill `design-estilos` (gerados da própria F2), `test/qa_gates.py` (os 12 gates sobre uma especificação), a regra "título ≥ 2,5x o corpo", a escala de espaçamento 4/8/12/16/24/32/48/64 e o compilador de prompt (nomear o mecanismo, remover ruído).
- **Critic:** o juiz de base é o modelo da OpenAI com instrução enxuta; o nosso mundo entra como **pacotes por caso de uso** (seção 8). Imagem livre deixou de ser julgada por critérios de marketing.
- Achei **9 conflitos ou erros** entre as fontes e o que já tínhamos (seção 5). Seis ficaram resolvidos; três dependem de decisão de vocês (seção 9).

## 2. Natureza de cada fonte

| | F1 | F2 |
|---|---|---|
| Público | designer humano em formação | agente de IA |
| Forma | roadmap, tabelas, carreira | contrato: regras verificáveis, gates, dados |
| Força | por que a peça "parece cara", prioridades, rituais | validação binária, estilos com mecanismo, formato de saída |
| Fraqueza | metade é carreira (portfólio, 12 meses) | parte vale só para UI/marketing e parte inventa precisão sem fonte |
| No sistema | `docs/08` + skills `design-*` | `design-estilos`, `estilos.json`, `qa_gates.py`, rubrica v4 |

## 3. O que verifiquei nas fontes (e o que não consegui)

| Afirmação | Resultado |
|---|---|
| JSON de estilos da F2 | carrega; 14 estilos; mesmas 10 chaves em todos; tabela (4), regras (4.1) e JSON têm os mesmos slugs. |
| "Regra dos 20% de texto não existe desde set/2020" (F1 e F2) | **confirmada** em várias fontes. Nuance: anúncios com muito texto podem ter menos alcance, então a regra de densidade (T6, gate 11) continua justificada. |
| Safe zone 9:16 = 14% topo, 35% base, 6% laterais (F1 e F2, "invariante" 7) | **não confirmada**: as páginas oficiais da Meta que consegui ler não publicam percentuais, só indicam um verificador de Reels. Stories parece ter base menor (~20%, fonte secundária). Tratamos como **piso conservador a confirmar**. |
| Tabela de tracking SF Pro (F1) e linha de tracking (F2 3.1) | **não confirmada** na documentação da Apple; fontes de terceiros usam outra unidade (em, não pt). A F2 ainda **erra** a linha ("−0,31 a 17pt; −0,43 a 17pt+": na F1, −0,31 é 16pt e −0,43 é 17pt). Usamos só a **direção** (título grande: negativo; texto pequeno: positivo). |
| Mínimos "corpo ≥ 16 px, headline ≥ 32 px" (F1 e F2) | valem para CSS em tela, **não** para canvas: 1080 px aparecem com ~390 pt (fator 0,36). Já corrigido em T5 (`checks.type_min_canvas`). |
| Liquid Glass (WWDC25) como "camada funcional" e WCAG 1.4.3/1.4.6 | citados; **não reverifiquei** o Liquid Glass. WCAG 4,5:1 e 3:1 são padrão. |
| Hook rate 20–25% baseline, 30%+ bom, 100 conversões por variante | vêm de fontes "não avaliadas": **hipóteses**, nunca critério de aprovação. Hoje ninguém mede desempenho. |

## 4. Matriz de cobertura da F2

| F2 | O que pede | Onde está agora | Estado |
|---|---|---|---|
| 0.1 (1) | 4 entradas antes de desenhar | `design-estrategia` (E1, E4), formato (F), marca (modo marca) | coberto, **só em peça de marketing** |
| 0.1 (2) | ponto focal declarado | E3, H2; gate 1 | coberto |
| 0.1 (3) | escolher 1 estilo do catálogo | `design-estilos` | **opt-in** (decisão pendente D2) |
| 0.1 (4) a (6) | especificação, racional, gates | `design-estilos` (modo especificação) + `qa_gates.py` | novo |
| 0.2 | nunca: inventar métrica, "bonito" como justificativa, aprovar sem teste, mexer em 2 variáveis | veto `dado_inventado`, E5, F6, gates 4 e 5 | coberto |
| 1 | pipeline de 5 passos; "não pule do 2 para o 4" | `design-estrategia` (Ordem de decisão), `design-estilos` | novo |
| 2 | 12 invariantes | seção 5 abaixo | coberto, 1 reforçada, 1 nova |
| 3 | constantes técnicas | `docs/08`, `checks.py`, skills | coberto; 3 divergências (seção 5) |
| 4 e 5 | 14 estilos e JSON | `estilos.json` + skill (gerados por `gen_estilos.py`) | novo |
| 6 | compilador de prompt, anti-padrões, regra de finalização | prompt do designer (regra 12), `design-estilos` | novo; "sem texto" condicional (C7) |
| 7 | modelos de saída | `qa_gates.py` (esquema da especificação), skill | novo |
| 8 | 12 gates binários | `qa_gates.py` (+ 1 gate da regra 11) | novo; ver seção 7 |
| 9 | rubrica 0–5 | **não adotada como nota principal** (ver D4) | ver abaixo |
| 10 | anti-padrões | "Revisão (critic)" de `design-estilos` e "Falha típica" das skills | coberto |
| 11 | glossário | vocabulário adotado nos docs e skills | coberto |
| 13 | instruções de aprendizagem (8) | prompts e skills; #3 limitado a peça de marketing | coberto com escopo |

**Rubrica 0–5 (F2 §9):** a nota 5 exige "evidência: peça + racional + métrica + consistência em 20+ peças". Um critic que olha **uma** imagem não consegue dar 5. Mantemos o critic em 0–10 com pacotes e deixamos a escala 0–5 como **meta de série** para o curador. Conversão, quando preciso: nota 0–10 = 2 × nota 0–5.

## 5. As 12 invariantes e os conflitos

| # | Invariante (F2 §2) | Onde vive | Observação |
|---|---|---|---|
| 1 | um ponto focal | E3, H2 | igual |
| 2 | 3 níveis, título ≥ **2,5x** o corpo | H1 (atualizado), gate 2, rubrica `hierarchy` | **F2 mais restritiva que nós (1,5x): adotada** |
| 3 | contraste 4,5:1 e 3:1 | C1, `checks.contrast_ok`, gate 3 | igual |
| 4 | máx. 2 famílias | T1, gate 8 | igual |
| 5 | ≤ 7 palavras/linha, 3 linhas | T6, gate 11 | igual |
| 6 | um CTA, verbo + benefício | E, F4, gate 7 | igual |
| 7 | safe zone 14/35/6 | F2, gate 6 | **não confirmada** (C4) |
| 8 | contraste no pior caso | C1, gate 4 | exige pixels (seção 7) |
| 9 | transparência com scrim e fallback | `design-estilos`, gate 10 | nova no código |
| 10 | uma fonte de luz | K1, gate 9 | só visão |
| 11 | escala de espaçamento 4/8/12/16/24/32/48/64 | `design-serie-marca` (atualizada), gate 13 | **nossa escala (múltiplos de 8) estava incompleta** |
| 12 | teste 120 px + celular | F6, gate 5 | heurística + visão |

### Conflitos e erros

| ID | Conflito ou erro | Decisão | Estado |
|---|---|---|---|
| C1 | F2: título ≥ 2,5x o corpo; nós: ≥ 1,5x entre níveis | adotar 2,5x título/corpo e manter 1,5x título/apoio | aplicado |
| C2 | F1 e F2: mínimos 16/32 px (CSS) | mínimos relativos à tela (T5) | aplicado |
| C3 | F2 erra a linha de tracking | manter a tabela da F1; tratar tudo como direção | aplicado |
| C4 | F2 trata safe zone como invariante; a Meta não publica números | piso conservador marcado "a confirmar" | aplicado; **D3** |
| C5 | F2: transição padrão ease-in-out; F1: entradas ease-out | tabela da F2 para UI; regra de entrada/saída da F1 para hero | registrado (vídeo, futuro) |
| C6 | F2: coletar 4 entradas e perguntar oferta e formato; nós: o pedido manda e só perguntamos o assunto | a regra da F2 vale **só em peça de marketing** | aplicado |
| C7 | F2 6.4: texto em imagem de IA "é sempre provisório"; "sem texto renderizado" no template | peça de marketing: texto exato por código (a compor; `compose_text_overlay` ainda não existe); imagem livre: texto nativo permitido, critic confere letra por letra | aplicado; **D1** |
| C8 | F2: escolher sempre 1 estilo; nós: não impor estilo em imagem livre | catálogo opt-in (pedido nomeia o estilo, ou UI) | aplicado; **D2** |
| C9 | catálogo é de UI; só parte é "gerável" por modelo de imagem | classificação imagem / híbrido / código por estilo (proposta nossa, a validar) | aplicado |

Classificação de geração (proposta): **imagem** = dark_cyberpunk, skeuomorphism, aurora, isometric, claymorphism; **híbrido** = glassmorphism, retro_pixel; **código** = minimal_flat, neo_brutalism, material3, typographic, brutalism, bento, neumorphism.

## 6. Como a fonte 2 foi encaixada no pipeline

```
pedido → [triagem: modo, tipo de peça] → skills por pedido (+ design-estilos se pede estilo/UI)
       → designer escreve o briefing (compilador: mecanismo, sistema, proporção numérica, sem ruído)
       → imagem (API da OpenAI) → checagens por código → critic (OpenAI + pacotes) → até 2 correções
       → (futuro) composição por código emite a especificação → qa_gates → veredito
```

## 7. Os 12 gates: quem consegue provar o quê

| Gate | Método | Estado |
|---|---|---|
| 1 Ponto focal | declarado (código) + domínio visual (critic) | parcial |
| 2 Hierarquia | **código** (níveis e razões) | pronto |
| 3 Contraste do texto | **código** (WCAG, tamanho relativo à tela) | pronto |
| 4 Contraste no pior caso | código se a especificação trouxer os extremos do fundo; senão precisa dos pixels | parcial. Próximo: decodificar o PNG (stdlib) e medir a região do texto |
| 5 120 px | heurística de tamanho + critic | parcial |
| 6 Safe zone | **código** em 9:16 (valores a confirmar); outras proporções sem regra | parcial |
| 7 CTA | código (genérico, quantidade, contraste) + critic (benefício) | parcial |
| 8 Tipografia | **código** (famílias, escala modular) | pronto |
| 9 Luz | só visão ou humano | critic |
| 10 Fallback de transparência | **código** sobre a especificação | pronto |
| 11 Densidade | **código** | pronto |
| 12 Marca | código (paleta, âncoras, master) + critic (`brand_fit`) | parcial |
| 13 Espaçamento (regra 11) | **código** | pronto |

`qa_gates.py` nunca aprova por omissão: campo ausente vira `NAO_VERIFICAVEL` ou `FALHA` (autoteste cobre). Veredito pela regra da fonte: uma falha = REVISAR; duas na mesma dimensão = REFAZER; tudo verificável passou mas falta visão = PENDENTE_REVISAO_VISUAL.

## 8. O critic: modelo da OpenAI + pacotes

- **Não existe um "critic da OpenAI" como produto ou endpoint.** O que existe é o modelo de visão deles. Usá-lo como juiz é o que já fazemos (`CRITIC_MODEL`, hoje o mesmo modelo de texto). O que mudou é **quanto da nossa instrução** vai junto.
- **Base neutra (sempre):** fidelidade ao pedido, estilo, composição, craft, cor, defeitos, formato, vinculação e contagem. Vetos: marca d'água, pessoa real sem referência, formato errado (por código).
- **Pacotes só no caso de uso** (`prompts/rubric.json` v4; v3 em `rubric.v3.json`):

| Pacote | Entra quando | Acrescenta |
|---|---|---|
| marketing | anúncio, banner, post de divulgação, flyer, campanha | hierarquia, legibilidade a 120 px, clareza da mensagem; vetos: safe zone, CTA vago, dado inventado |
| brand | modo com marca do cliente | `brand_fit`; veto: logo inventado |
| text | texto entre aspas ou peça com texto | texto exato; veto: texto indevido |
| edit | edição da imagem anterior ou série | invariantes |
| estilos | pedido nomeia estilo do catálogo ou é UI | `style_mechanism` |

- O critic recebe só os critérios ativos; vetos de pacotes inativos são ignorados (veto desconhecido continua reprovando). As checagens das skills aplicadas (seção "Revisão") seguem indo junto.
- **Pendente de calibração:** concordância do critic com avaliação humana por pacote (ver `test/calibration/README.md`). Sem isso, a nota é um sinal, não uma verdade.

## 9. Decisões que dependem de vocês

| ID | Decisão | Opções | Minha recomendação |
|---|---|---|---|
| D1 | Texto dentro da imagem | (a) sempre por código; (b) nativo do modelo quando o usuário pede e o critic confere; (c) por código só em peça de marketing | (c): é o que está aplicado. Reavaliar quando o `compose_text_overlay` existir |
| D2 | Estilo do catálogo em peça de marketing | (a) sempre escolher um (F2); (b) só quando pedido/UI | (b) enquanto a imagem repetida for um risco. Testar (a) com A/B |
| D3 | Safe zone | baixar o verificador de Reels da Meta e transformar nos números oficiais | fazer; hoje é piso conservador |
| D4 | Escala de nota | manter 0–10 com pacotes; 0–5 só para série | manter |
| D5 | O que "usar o critic deles" significa | (a) o modelo da OpenAI como juiz com nossos pacotes (feito); (b) outro mecanismo | se for (b), me diga qual |

## 10. Como treinar e validar agentes com isso (ordem)

1. **Agora, com a chave:** rodar o chat, comparar "com a aplicação" contra "GPT puro" na mesma régua, e `DESIGN_SKILLS=off` contra ligado.
2. **Gold set por gate:** cada gate tem casos que devem PASSAR e FALHAR (os de `qa_gates.py --self-test` são o começo). Para os gates de visão, imagens boas e ruins do CEO, com o motivo.
3. **Teste de estilos:** gerar um prompt por estilo a partir de `estilos.json` (`prompt_en`) e medir com o pacote `estilos`; isso valida a classificação imagem/híbrido/código.
4. **Composição por código** (`compose_text_overlay`, `composite_with_mask`): passa a emitir a especificação e rodar `qa_gates` antes do critic.
5. **Contraste no pior caso com pixels:** decodificar PNG (stdlib) e medir a região do texto.
6. **Memória de aprovadas e reprovadas com motivo**, e o **curador** que propõe mudanças (aprovação do CEO, portão no eval set).
7. Perfis de agentes: triagem (código), designer (briefing), diretor de estilo (`design-estilos`), compositor (código), critic em camadas (OpenAI + pacotes), curador (futuro).
