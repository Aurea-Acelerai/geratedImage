---
name: design-formato-canal
description: Formato, canal e especificações: proporção por placement (feed, stories, reels, display, e-mail, impressão), safe zones, teste de 120 px e adaptação por formato (regras F1 a F8). Use quando a peça tem canal, formato ou destino declarado.
always: false
triggers: [story, stories, reels, feed, banner, flyer, panfleto, cartaz, folder, email, e-mail, newsletter, display, google, meta, instagram, facebook, linkedin, tiktok, 9:16, 4:5, 16:9, 1:1, 1.91, a4, a5, impressao, impressão, post, anuncio, anúncio, ads, capa, thumbnail]
order: 50
---

# Formato e canal (F1 a F8)

Cada formato é um problema de design diferente. **Adaptar não é redimensionar**: refaça a hierarquia para o novo quadro. A API de imagem entrega só alguns tamanhos (hoje 1024x1024, 1536x1024, 1024x1536); outras proporções exigem recorte ou extensão por código, e o briefing precisa dizer o destino final.

### Tabela de formatos

| Destino | Proporção e tamanho de trabalho | Nível de confiança |
|---|---|---|
| Stories e Reels (Meta) | **9:16**, 1080x1920 | oficial (Meta recomenda 9:16; 1080x1920 para Stories) |
| Feed Instagram e Facebook | **4:5**, 1080x1350 (alguns guias citam mín. 1440x1800) | consenso de guias; confirmar no Ads Guide |
| Feed, alternativa | **1:1**, 1080x1080 | consenso de guias |
| Carrossel | 1:1 é o mais seguro; 4:5 só se todos os cards forem imagem | fontes divergem |
| Google Display responsivo | **1.91:1** 1200x628; **1:1** 1200x1200; vertical 9:16 900x1600 (guias citam também 4:5) | oficial (página do Google); vertical diverge |
| Logo no Google (RDA) | 1:1 1200x1200 (mín. 128x128); 4:1 1200x300 (mín. 512x128); PNG | consenso de guias |
| Banners display padrão | 300x250, 336x280, 728x90, 160x600, 300x600, 320x50, 320x100, 970x250 | padrão do mercado; confirmar no inventário da plataforma |
| E-mail (cabeçalho) | largura 600 px; arte a 1200 px de largura (retina) | prática de mercado |
| Impressão | tamanho final + 3 mm de sangria por lado; 300 dpi; CMYK | norma gráfica |

### F1 — Formato padrão e adaptação por formato
- **Aplicar:** em social, o padrão de **alcance** é 9:16; o de **feed** é 4:5. 1:1 e 16:9 recortam mal no celular. Para cada formato, redesenhe: o que muda na hierarquia?

| De → para | O que refazer |
|---|---|
| 4:5 → 9:16 | texto sobe para a zona segura; foco sobe; cena ganha altura calma no topo e na base |
| 4:5 → 1:1 | foco ao centro-alto; texto menor em 2 linhas; sem sangrar o assunto |
| 1.91:1 → 4:5 | recompor: assunto vira vertical; título passa de lado para cima |
| qualquer → display 728x90 | só um hook de 3–4 palavras, logo e CTA em linha |

- **Falha típica:** o mesmo master reduzido para todos os placements; texto cortado no 1:1.

### F2 — Safe zones (áreas que a interface cobre)
- **Status honesto:** a Meta **confirma que a zona de segurança existe** e oferece um *verificador de zona de segurança do Reels* (arquivos PPT/PSD/Keynote), mas as páginas oficiais lidas **não publicam os percentuais**. Os valores abaixo vêm do documento-fonte e de fontes secundárias; use como **piso conservador** até conferir no verificador oficial.

| Formato | Topo | Base | Laterais | Origem |
|---|---|---|---|---|
| 9:16 Reels | 14% | **35%** | 6% | documento-fonte; **a confirmar** |
| 9:16 Stories | 14% | ~20% | — | fontes secundárias; **a confirmar** |
| Demais proporções | sem regra no código; trate o perímetro de 6% como margem mínima | | | — |

- **Aplicar:** texto, logo e CTA dentro da área segura; o assunto principal também. Fundo e cena podem sangrar nas zonas. O código (`checks.safe_zone_ok`) usa a regra mais conservadora (9:16: 14/35/6).
- **Falha típica:** CTA na base de um Reels, coberto pela legenda e pelos botões.

### F3 — Sem regra dos 20% de texto
Removida pela Meta em set/2020. Não reprove por percentual; reprove por **densidade ilegível** (T6).

### F4 — CTA
Um só, verbo + benefício, alto contraste, em área terminal e dentro da safe zone (T, seção CTA). O alvo ≥ 44 pt vale só para botões reais.

### F5 — Projetar para o mudo
Tudo que importa está escrito na tela. Em vídeo, legendas e texto na tela; em imagem, a mensagem não depende de som nem de legenda do post.

### F6 — Teste final
Reduza a ~120 px de largura (e simule celular com brilho a 50%): foco e texto principal ainda se leem? Simule também as sobreposições da interface: nome da conta no topo, legenda e botões na base.

### F7 — Impressão (flyer, cartaz)
- Sangria **3 mm** por lado; zona segura **3 mm** para dentro do corte; texto e logos nunca na faixa de sangria. Fundo estende até a sangria.
- 300 dpi no tamanho final colocado; cor em **CMYK** (prova quando a cor da marca é crítica); PDF com fontes embutidas ou em curvas e transparências achatadas.
- A5 148x210 mm → documento 154x216 mm (≈ 1819x2551 px a 300 dpi). A4 210x297 mm → 216x303 mm (≈ 2551x3579 px).
- O modelo de imagem não entrega esse tamanho nem CMYK: a arte vai para ampliação e conversão por código; o texto fica vetorial. **Fora da geração atual**; o briefing deve apenas declarar o destino e manter a arte sem elementos críticos nas bordas.

### F8 — Nomenclatura e masters
`campanha_formato_conceito_versao` (ex.: `verao26_4x5_desconto20_v2`). Sempre master editável + exportação + ativos aprovados com data. Peças reprovadas ficam arquivadas **com o motivo**.

## Revisão (critic)
- A proporção e a resolução batem com o destino declarado? Se o canal não foi declarado, avalie só proporção e resolução e **não aplique** o veto de safe zone.
- Texto, logo ou CTA dentro da área coberta pela interface do canal (9:16: topo 14%, base 35%, lados 6%)? Veto `safe_zone_violada` (somente com canal declarado).
- A peça é uma adaptação (hierarquia refeita) ou um redimensionamento mecânico?
- Foco e texto principal legíveis a 120 px?
