---
name: design-estrategia
description: Estratégia de peças de marketing: oferta em uma frase, hook, ponto focal único, ângulo e lógica de conjunto (regras E1 a E5). Use quando o pedido é anúncio, banner, post de divulgação, flyer ou campanha; não vale para imagem livre (arte, foto, ilustração).
always: false
triggers: [anuncio, anúncio, ads, banner, promo, promoção, promocao, oferta, desconto, campanha, post, flyer, panfleto, cartaz, cta, venda, lancamento, lançamento, black friday, story, stories, reels, capa, thumbnail, folder, email, e-mail, divulgacao, divulgação]
order: 10
---

# Estratégia antes da imagem (E1 a E5)

**Escopo:** esta skill vale para **peças de marketing**. Em imagem livre (arte, foto, ilustração, retrato, cena), não invente oferta, hook nem CTA. Os exemplos abaixo ilustram forma, não conteúdo.

Uma peça bonita sem hipótese é só output. Antes de escrever o briefing, registre **quatro linhas**: oferta, hook, ponto focal, ângulo. Se não der para preencher a oferta com o pedido e o contexto do cliente, **pergunte ao usuário** (uma pergunta curta); nunca invente número, preço, prazo ou condição (veto `dado_inventado`).

### E1 — Oferta em uma frase
- **Por quê:** é o que o espectador entende em 1,5 s. Se a oferta não cabe numa frase, a peça vai tentar dizer duas coisas e dirá nenhuma.
- **Aplicar:** `[quem] recebe [benefício concreto] [condição/prazo]`. Ex.: "Mulheres que querem pele protegida levam 20% off em protetor solar até domingo". Teste: apague a imagem; a frase ainda faz sentido? Se o pedido é só institucional (sem oferta), a frase vira a **proposta de valor** ("moda praia que acompanha o seu dia").
- **Verificar:** a oferta aparece no briefing como uma linha; todo número vem do contexto do cliente ou do pedido.
- **Falha típica:** "Confira nossas novidades" (não é oferta); desconto inventado para "dar força" à peça.

### E2 — Hook de até 7 palavras
- **Por quê:** o gargalo de toda peça é o início. Nunca abra com logo.
- **Aplicar:** escolha um tipo e escreva o hook final: *interrupção de padrão* ("Seu protetor não protege?"), *número específico* ("−20% só até domingo"), *pergunta direta*, *antes/depois*, *demonstração em uso*, *prova social* ("+10 mil clientes"). Em peça estática o hook é o **título** (texto composto por código, nunca pelo modelo de imagem); a imagem deve **reforçar** o hook, não competir.
- **Verificar:** contar palavras (≤ 7); o hook não repete o nome da marca como abertura; é específico (um número, um objeto, uma situação).
- **Falha típica:** hook genérico ("Descubra a diferença"); hook longo que vira parágrafo; hook que a imagem contradiz.

### E3 — Um ponto focal e uma ideia por peça
- **Por quê:** dois focos dividem o olhar e a leitura cai pela metade. Detalhes (condições, especificações) pertencem à landing page.
- **Aplicar:** declare o ponto focal como um substantivo concreto ("a modelo de costas olhando o mar", "o frasco em primeiro plano"). Tudo mais é subordinado. Duas ideias fortes = **duas peças**.
- **Verificar:** o briefing nomeia um único ponto focal; o `Subject` do briefing coincide com ele.
- **Falha típica:** modelo + produto + selo + frase + ícones disputando o mesmo peso.

### E4 — Ângulo antes do tratamento
- **Por quê:** o ângulo (por que a pessoa deveria agir) decide mais que o estilo visual. Trocar cor ou fonte não é testar conceito.
- **Aplicar:** escolha um e deixe-o guiar cena, hook e prova:

| Ângulo | Quando | Consequência visual |
|---|---|---|
| Dor | público consciente do problema | mostrar o problema ou o alívio dele |
| Desejo | público aspiracional | cena de resultado, emoção, luz favorável |
| Prova | público cético | depoimento, número, uso real |
| Comparação | mercado saturado | lado a lado, antes/depois |
| Urgência | oferta com prazo real | prazo legível, contraste forte |
| Educação | produto novo ou complexo | demonstração clara, passo a passo |

  Consciência do público: frio (não conhece) → dor ou desejo; morno (conhece) → prova ou comparação; quente (já considerou) → urgência e oferta.
- **Verificar:** o briefing declara o ângulo e a cena é coerente com ele.
- **Falha típica:** ângulo de urgência sem prazo real (promessa que a landing não cumpre).

### E5 — Conjunto: variar ângulo, não cor
- **Por quê:** campanhas que rodam 15–20 ativos *conceitualmente distintos* dão ao algoritmo o que otimizar; 20 recortes da mesma ideia não.
- **Aplicar:** ao receber "faça variações/opções", varie **ângulo** (E4) primeiro, depois hook e tratamento (foto, tipografia dominante, colagem, 3D). Cada variação declara uma hipótese: "se mostrarmos [X], então [métrica] melhora porque [razão]". Hoje **não há métrica** de desempenho; registre a hipótese para quando houver.
- **Verificar:** variações diferem em ângulo ou hook, não só em paleta; uma variável por vez quando o objetivo é testar.
- **Falha típica:** "três opções" que são a mesma cena com fundos de cores diferentes.

## Revisão (critic)
- A peça comunica **uma** ideia? Se for preciso decifrar, `message_clarity` e `hierarchy` caem.
- Existe número, preço, prazo ou fato exibido que não veio do contexto? Veto `dado_inventado`.
- O hook (se visível) é específico, curto e não abre com logo?
- Em conjunto: as peças diferem em ângulo ou só em estilo? Só estilo = nota baixa em `message_clarity`.
