# Referência de UX/UI: padrões do ChatGPT para o chat do designer

Estudo feito em 04/11/2026 sobre a página pública do ChatGPT (sem login), por medição de estilos computados em 1440x900, mais os dois prints que o Kelvin enviou (resultado de imagem e estado "Pensando"). Serve de **referência de padrão de interação**; não copiar marca, logo, ícones nem textos. Valores são do site público em português e podem mudar. Aplicar sempre por tokens do nosso design system (`chat/brand/tokens.css`), mantendo o tema escuro da Aceleraí.

## 1. Medidas observadas (fato, medido)

| Elemento | Valor |
| --- | --- |
| Fonte do corpo | pilha do sistema (`-apple-system`, `ui-sans-serif`, `system-ui`), 16px / 24px |
| Barra lateral | 260px de largura, mesmo fundo da página (sem cartão), sem borda pesada |
| Item da barra lateral | altura 36px, raio 10px, fonte 14px / 20px, padding 8px 10px, fundo transparente (hover sutil) |
| Cabeçalho | botão recolher 44x44 redondo; ações da conta como pílulas de 44px de altura, fonte 14px / peso 600 |
| Título da tela inicial | centrado, 24px / 28px, peso 400 ("Por onde começamos?") |
| Campo de mensagem | `form` de 768px de largura máxima, 52px de altura inicial, raio 28px, borda 1px de 10% de opacidade, sombra suave de 2px/8px, padding 7px 10px |
| Texto digitado | 17px / 24px, sem borda, fundo transparente |
| Sugestão | pílula de 44px, raio 999px, borda 1px de 20%, fonte 14px / peso 600 |
| Botão enviar | círculo de 32px com ícone; o "+" de anexar à esquerda; microfone à direita |
| Tema escuro | página `#000`, campo `#212121` com borda branca a 15% e brilho interno de 1px, placeholder `#CDCDCD` |
| Rodapé | texto legal de 12px, centrado, discreto |

## 2. Padrões de interação (do uso e dos prints do Kelvin)

1. **Resultado de imagem sem metadados.** Só a imagem com cantos arredondados (~16px); botão-pílula "Editar" sobreposto no canto inferior esquerdo e botão circular de baixar/compartilhar no canto inferior direito. Abaixo, uma linha de ícones: copiar, curtir, não curtir, compartilhar, regenerar, mais (⋯). Nenhuma nota, tempo, modelo ou regra aparece.
2. **Estado de processamento "Pensando".** Linha cinza e discreta com chevron ("Pensando ⌄"). Expandida, lista passos curtos e humanos ("Criando o banner"). Ao terminar vira "Pensou por N s". Sem nomes de modelo, regras ou números.
3. **Campo de mensagem é o centro da tela.** Controles de modelo e opções moram DENTRO ou junto do campo, como pílulas pequenas; configurações finas ficam em menu.
4. **Barra lateral limpa.** Ações no topo (novo chat, buscar), lista de conversas agrupada por data, rodapé com conta. Recolher vira trilho de ícones.
5. **Tela inicial vazia** com uma pergunta curta centrada e poucas sugestões em pílula, sem blocos explicativos.

## 3. Como aplicar no nosso chat (proposta)

- Largura máxima da coluna de conversa e do campo: ~768px, centralizados e alinhados entre si.
- Campo com raio 28px; pílulas de controle de 32px de altura dentro dele; enviar circular de 32px em `--color-action-primary`.
- Tela inicial: uma pergunta curta ("O que vamos criar?") e 3-4 sugestões em pílula; remover o parágrafo explicativo.
- Detalhes técnicos (nota, critic, skills, briefing, modelos) fora da vista; só em ⋯ → "Ver detalhes técnicos".

## 4. Limites do estudo

- Só a página pública: não vi o estado logado (lista de chats, mensagens do assistente, menu de modelos), então esses padrões vêm dos prints enviados e do conhecimento geral do produto, não de medição.
- Valores de tema escuro foram medidos na tela inicial apenas.
- Estilos do site usam classes atômicas e variáveis privadas; não há tokens públicos para extrair.
