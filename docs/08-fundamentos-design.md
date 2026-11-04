# 08. Fundamentos de design para os agentes (v0.1)

Fonte: documento "Design Nível Apple — Roadmap Completo" (material do Kelvin, nov/2026), **filtrado** para o que um agente de geração de imagem usa. Roadmap de carreira, portfólio, tendências e as 90 referências ficaram de fora; a fonte original continua com o autor.

As seções 1 a 6 (entre os marcadores `agent:start` e `agent:end`) são **injetadas no system prompt do designer em toda geração**, via `test/checks.py` (`design_fundamentals()`); se os marcadores sumirem, o designer não roda. Editar essas seções muda o comportamento do agente e exige aprovação do CEO (seção 9).

**Aprofundamento:** cada regra é detalhada (por quê, como aplicar no briefing, como verificar, falha típica) nas skills `skills/design-*`, que o roteador (`test/skills_router.py`) carrega conforme o pedido (texto na peça, canal, série, vídeo). Este documento é o índice e o núcleo sempre ativo; as skills são o aprofundamento.

Cada regra tem um ID (`H1`, `F2`...) para o designer, o critic e o curador citarem. Cada uma diz **onde é aplicada**:

- **CÓDIGO**: checagem determinística, não depende de prompt (`test/checks.py`, ainda por fazer).
- **RUBRICA**: o critic avalia (`prompts/rubric.json`, v3).
- **PLAYBOOK**: princípio que o designer usa ao escrever o briefing.
- **ESTRATÉGIA**: decidido antes de gerar.

## 0. Princípio
"Clareza agressiva": nada na peça é acidental e a hierarquia funciona em 1,5 s, no mudo, num celular. Mede-se por **resultado** (a peça resolve o problema?), não por "ficou bonito". [PLAYBOOK]

<!-- agent:start -->
## 1. Estratégia (antes de gerar) [ESTRATÉGIA]
- **E1.** Escrever a oferta em **uma frase** antes do briefing de imagem. Sem oferta clara numa peça de marketing, **gerar a arte sem texto e avisar** (a oferta entra por código depois); nunca inventar número, preço ou prazo.
- **E2.** Hook em **até 7 palavras**; nunca abrir com logo.
- **E3.** **Um ponto focal**, declarado antes de desenhar. **Uma ideia por peça**; detalhe vai para a landing page.
- **E4.** Escolher o **ângulo** (dor, desejo, prova, comparação, urgência, educação) antes do tratamento (foto, tipografia dominante, colagem, 3D). Trocar cor não é variar conceito.
- **E5.** Conjunto de peças: variar o ângulo antes do tratamento; 15–20 ativos *conceitualmente* distintos por campanha, não recortes da mesma ideia.

## 2. Hierarquia e composição
- **H1.** Mínimo de 3 níveis de leitura, com salto real de escala ou peso; em peça com texto, título >= 2,5x o corpo. [RUBRICA: `hierarchy`]
- **H2.** Um único ponto focal; o olho vai a ele primeiro. [RUBRICA: `hierarchy`]
- **H3.** Zonas: topo = logo ou proposta de valor; meio = mensagem e visual; base = CTA. [PLAYBOOK]
- **H4.** Espaço negativo é função, não sobra: reservar onde o texto entra. [RUBRICA: `composition`]
- **H5.** Peso visual equilibrado; sem elementos competindo pelo mesmo peso. [RUBRICA: `composition`]
- **H6.** Prägnanz: se a peça precisa ser decifrada, perdeu. [RUBRICA: `hierarchy`]

### Gestalt aplicada (PLAYBOOK)
| Princípio | Uso |
|---|---|
| Proximidade | Separar oferta de CTA por distância, sem caixas |
| Similaridade | Ritmo e família visual (selos, ícones, chips) |
| Fechamento | Autoriza minimalismo e recorte ousado |
| Região comum | Card de preço, bloco de prova |
| Figura-fundo | Separar sujeito do fundo, decisivo em fundo fotográfico |
| Continuidade | Direção do olhar do modelo até a oferta |

## 3. Cor, contraste e craft
- **C1.** Contraste de texto **>= 4,5:1** (normal) e **>= 3:1** (grande: >= 18pt ou >= 14pt negrito). AA é o piso, não a meta. [CÓDIGO + RUBRICA: `legibility_size`]
- **C2.** Saturação é orçamento: poucas cores fortes, cada uma com papel. [PLAYBOOK]
- **K1.** Uma única fonte de luz coerente em todos os elementos. [RUBRICA: `craft`]
- **K2.** Sombras com opacidade e raio proporcionais à escala do objeto. [RUBRICA: `craft`]
- **K3.** Grão ou textura sutil unifica camadas e tira o aspecto plástico; blend modes unificam colagem. [PLAYBOOK + RUBRICA: `craft`]
- **K4.** Alinhamento óptico, não só matemático. [PLAYBOOK]
- **K5.** Vocabulário curto repetido com precisão: restrição, não variedade. [PLAYBOOK]

## 4. Tipografia
**Importante:** texto exato sai por código (decisão do HANDOFF), não do modelo de imagem. As regras abaixo são **parâmetros do `compose_text_overlay`**, não instruções para o gerador. [CÓDIGO]
- **T1.** Máximo de **2 famílias**; variar peso, não família.
- **T2.** Entrelinha: display 1,05–1,15; corpo 1,4–1,6.
- **T3.** Tracking: título grande mais negativo, texto pequeno mais positivo (SF Pro: 12pt = 0; 13 = -0,08; 14 = -0,15; 16 = -0,31; 17 = -0,43).
- **T4.** Nunca justificar texto curto.
- **T5.** Tamanho mínimo medido **na tela do celular**, não no canvas: um canvas de 1080 px aparece com ~390 pt (fator ~0,36). Mínimos de partida no canvas de 1080: legal >= 33 px, apoio >= 46 px, título >= 80 px (`checks.type_min_canvas`; heurística derivada, a validar). Os mínimos CSS (corpo >= 16 px, headline >= 32 px) valem só para telas de design.
- **T6.** Densidade: no máximo 7 palavras por linha e 3 linhas em anúncio.
- **T7.** Teste dos 3 níveis sem cor: a hierarquia sobrevive em preto e branco.

## 5. Formato e canal
- **F1.** Formato padrão em social é **9:16**; 1:1 e 16:9 recortam mal no celular. **Adaptar por formato é redesenhar a hierarquia**, não redimensionar. [RUBRICA: `format`]
- **F2.** Safe zone 9:16: **~14% topo, ~35% base, ~6% laterais**. Texto, logo e CTA ficam dentro. [CÓDIGO + RUBRICA: veto `safe_zone_violada`]
  - *A confirmar (verificado em 04/11/2026):* as páginas oficiais da Meta que consegui ler confirmam que a zona de segurança do Reels existe e oferecem um verificador para baixar, mas **não publicam os percentuais**. Os 14/35/6% vêm do documento-fonte e de fontes secundárias; o código os usa como piso conservador. Conferir no verificador oficial antes de tratar como regra da plataforma. Para outras proporções, levantar os valores antes de usar.
- **F3.** A "regra dos 20% de texto" **não existe mais** (Meta removeu em set/2020). Não reprovar por isso.
- **F4.** CTA: um só, alto contraste, em área terminal, alvo de toque >= 44 px, verbo + benefício. [RUBRICA: `message_clarity`, veto `cta_vago`]
- **F5.** Projetar para consumo **no mudo**: o que importa vai escrito na tela.
- **F6.** Teste final: reduzir a ~120 px de largura (e visão de celular, brilho 50%). [CÓDIGO + RUBRICA: `legibility_size`]
- **F7.** Impressão (flyer): sangria 3 mm, zona segura +3 mm, CMYK, 300 dpi no tamanho final, fontes embutidas ou em curvas; A5 148x210 mm vira documento 154x216 mm. [CÓDIGO]
- **F8.** Nomenclatura `campanha_formato_conceito_versao`; sempre master editável + export. [CÓDIGO]

## 6. Erros previsíveis (checklist negativo)
Layout sobrecarregado; hierarquia fraca; texto ilegível no tamanho renderizado; CTA que se mistura ao fundo ou é vago; contraste insuficiente; redimensionamento mecânico; imagem genérica de banco; marca inconsistente na campanha; animação decorativa; promessa que a landing não cumpre; **texto gerado dentro da imagem por IA sem revisão**.
<!-- agent:end -->

## 7. Movimento (vídeo)
Fora do escopo da geração de **imagem estática**, mas registrado porque "todos os formatos" são foco. Entra com o agente de vídeo. [FUTURO]
- Durações: feedback 80–150 ms; estado pequeno 150–250 ms; transição padrão 220–400 ms; estrutural 350–650 ms; narrativo 700–1200 ms.
- ease-out para entradas, ease-in para saídas (70–80% da entrada), ease-in-out para reposicionar, linear só em loops. Stagger de 40–80 ms, sequência total <= 600–800 ms.
- Estrutura: hook (0–1,5 s) → problema → diferencial → prova → oferta → CTA, com re-hook por volta de 7 s.

## 8. Desempenho: o que ainda não temos
**Hoje ninguém mede** CTR, hook rate ou CPL das peças. Consequências:
- Os benchmarks do documento (hook rate 20–25% baseline, 30%+ bom; ~100 conversões por variante; 95% de confiança) ficam como **hipótese**. Nenhum é usado para aprovar ou reprovar peça.
- O sistema aprende por enquanto só de **decisão humana + motivo** (seção 9). Quando houver métrica, ela entra como segundo sinal, nunca substitui o primeiro sem aprovação.
- Diagnósticos de bolso para quando houver dados: CTR alto + conversão baixa = a peça promete o que a página não entrega; CTR baixo + conversão alta = problema de hook ou primeira impressão.

## 9. Aprendizado e governança
O agente **não treina modelo**. Aprende por memória curada com portão de qualidade:
1. **Registro:** cada peça guarda briefing, nota por critério, decisão humana (aprovada ou reprovada) e **motivo**. As reprovadas com motivo são o material mais valioso.
2. **Curador:** periodicamente lê o registro e **propõe** (nunca aplica): item de rubrica, regra por cliente, entrada de playbook ou perfil novo.
3. **Portão automático:** toda proposta roda no `test/eval_set.json` e só segue se não piorar a média da rubrica vigente (referência atual, rubrica v2: B = 8,91; **medir de novo na v3**, a escala mudou).
4. **Aprovação:** **o CEO aprova** toda proposta antes de entrar. Sem aprovação, nada muda em `prompts/` nem em `rubric.json`.
5. Mudança na rubrica incrementa `version` e mantém a anterior (`rubric.v2.json`) para comparar resultados.

## 10. Escala de maturidade (para o critic e o curador)
Scorecard 0–2 por item do documento-fonte (oferta em uma frase, 3 níveis de hierarquia, teste de 120 px, CTA com benefício, adaptação por formato, contraste medido, grid e espaçamento definidos, tokens e componentes, hook rate/CTR conhecidos, decisões justificadas em uma frase, cadência de teste, racional escrito). Serve como lista de perguntas do curador ao revisar um lote; não é critério de aprovação de peça.

## Pendências deste documento
- Conferir os percentuais de safe zone no verificador oficial da Meta e levantar os de outros canais (F2).
- Validar com dados reais os mínimos de tipografia por tela (T5) e os tamanhos por canal da skill `design-formato-canal`.
- Medir se as skills melhoram a nota: rodar o teste com e sem (`DESIGN_SKILLS=off`).
- `test/checks.py`: contraste WCAG, safe zone por formato, miniatura de 120 px, mínimos de tipografia.
- Parâmetros de tipografia e grid por cliente no `compose_text_overlay`.
- Medir a rubrica v3 no eval set e recalibrar o critic com exemplos do CEO (`test/calibration/README.md`).
