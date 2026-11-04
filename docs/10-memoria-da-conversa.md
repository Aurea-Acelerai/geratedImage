# 10. Memória da conversa e referências de identidade (04/11/2026)

Sintomas relatados no teste real do chat: (1) pediu uma imagem "com o Rodrigo Faro" e saiu "outra coisa nada a ver"; (2) a IA "esquece" o que foi dito. A conclusão do usuário foi "se uso a API da OpenAI, isso não deveria acontecer". Este documento registra o que foi verificado, o que mudou e o que ainda depende de teste com a API real.

## 1. A API da OpenAI não tem memória; a memória é nossa

A API de imagens e a de chat são **sem estado**: cada chamada só conhece o que enviamos nela. O ChatGPT lembra porque o app em volta guarda a conversa, anexa os arquivos e decide, a cada mensagem, se é uma edição da imagem anterior ou um pedido novo. No nosso chat, esse "app em volta" é o `test/chat_server.py`, e ele tinha lacunas.

## 2. O que foi verificado (evidência)

| # | Achado | Evidência |
|---|---|---|
| 1 | A foto do Rodrigo foi cadastrada como **logo**. O briefing dizia ao modelo "LOGO oficial: deve aparecer idêntico, nunca redesenhado". | `test/clients/71/assets.json` (`kind: logo`, `rodrigo.webp`); o tipo padrão do seletor era `logo` |
| 2 | Os anexos eram **limpos depois de cada resposta**. Na mensagem seguinte a foto não ia mais. | `chat/index.html` (`S.selected.clear()` em `finish` e `loadClient`) |
| 3 | O designer só via, de cada imagem gerada, o texto `[imagem gerada]`: **sem o briefing, sem o que foi mostrado**. Histórico de 6 turnos e 400 caracteres cada. | `chat_server.py` `build_user` (versão anterior) |
| 4 | Edição só acontecia se o usuário clicasse em "Editar esta imagem" e o alvo era limpo depois. Uma frase como "agora com camisa azul" gerava imagem do zero. | `chat/index.html` (`S.editOf = null`) |
| 5 | Edições com foto de pessoa, logo ou produto **sem `input_fidelity`**: por padrão a edição pode recriar o rosto. | nenhuma ocorrência de `input_fidelity` no código anterior |
| 6 | O critic **não comparava a identidade** com a referência: um sósia ou uma modelo genérica passava. As imagens geradas (viajante no aeroporto, selfie com logo da CVC desenhado pelo modelo, mala na praia) não têm a pessoa da foto. | `test/chat_out/71/*.png`, foto em `test/clients/71/assets/` |
| 7 | **Linha do tempo das imagens** (horários dos arquivos): as 4 primeiras (12:46 a 12:54) são **anteriores** ao upload da foto (12:57); a das 12:58 tem uma pessoa em cena de sofá com pipoca (a referência foi usada nessa rodada); a das **13:00 é uma mala na praia, sem pessoa**, logo depois, sem a foto. Isso encaixa com o achado 2: a foto foi usada na primeira mensagem e **sumiu na seguinte**. Não avaliei semelhança facial entre a referência e as imagens; essa conferência é do usuário. | `test/chat_out/71/` (timestamps e imagens), `assets.json` (criado 12:57) |
| 8 | **O designer não é o culpado.** Reproduzi o pedido com o designer real (Claude como redator): sem foto, ele **pergunta pela foto**; com a foto (como logo ou como pessoa), o briefing mantém o Rodrigo e a referência. | execução de 04/11/2026, três configurações |

**Confirmação independente:** um agente de depuração, sem receber as minhas conclusões, chegou às mesmas quatro causas (anexo apagado, foto marcada como logo, edição sem `input_fidelity`, histórico sem o que foi gerado), com a mesma linha do tempo.

**Não consegui verificar:** (a) o texto exato dos pedidos do usuário (o `localStorage` do navegador não devolveu a conversa; por isso o chat agora grava as conversas em disco); (b) o comportamento da API de imagens da OpenAI com o nome e o rosto de uma pessoa real. Sem a chave, isso só se confirma rodando.

## 3. O que mudou

| Problema | Correção |
|---|---|
| Foto de pessoa tratada como logo | Tipo padrão agora é `referencia`; cada imagem da biblioteca tem um **seletor de tipo** (`/api/asset/kind`); `pessoa` tem papel próprio: "identidade a preservar, nunca trocar por sósia". |
| Anexos esquecidos | Imagens escolhidas ficam **fixadas na conversa** (persistem ao recarregar) até você remover; "Nova conversa" limpa. |
| Designer sem saber o que foi gerado | **Memória em disco** (`test/conversations/<cliente>/<conversa>.json`): cada turno guarda pedido, pedido resolvido, intenção, briefing final, imagem e nota, e as perguntas do designer. O designer recebe esse resumo. |
| "Agora com camisa azul" virava imagem do zero | **Resolvedor de contexto** (`prompts/memory.system.md`) antes do designer: devolve `intent` (nova, edição, variação) e um pedido **autossuficiente** que preserva pessoa, produto, marca e restrições. Edição e variação usam a **última imagem como entrada 1**. |
| Resposta a uma pergunta do designer perdia o pedido | A pergunta fica na memória marcada como pendente; a resposta é unida ao pedido original. |
| Rosto, logo ou produto recriados | `input_fidelity=high` nas edições com pessoa/logo/produto (se o modelo recusar o parâmetro, repete sem ele e **avisa** na mensagem). |
| Sósia aprovado | Pacote **`identity`** no critic (`identity_match`, veto `identidade_divergente`) quando há pessoa, logo ou produto de referência. |
| Opacidade | Painel **Memória da conversa** na barra lateral e linha "Como a IA entendeu (com a memória)" em cada resposta. |

## 4. Como funciona

```
mensagem + imagens fixadas + id da conversa
  → carrega a conversa (disco) → resolvedor: intent + pedido autossuficiente (+ última imagem se edição/variação)
  → designer escreve o briefing com a memória, o pedido resolvido e a intenção
  → imagem (edição com input_fidelity=high se há identidade) → checagens → critic (base + pacotes, inclui identity)
  → grava o turno na conversa
```

O resolvedor foi testado com um LLM real (Claude como substituto do GPT, que precisa da sua chave) em quatro situações:
- "agora com camisa azul e sem a mala" → `edit`, mantém Rodrigo Faro e a campanha;
- resposta "30% de desconto…" a uma pergunta pendente → `new`, junta com o pedido original;
- "um gato astronauta…" → `new`, **não herda** o Rodrigo;
- "faz outra versão dele, mais perto do rosto" → `variation`, mantém o conceito.

## 5. Revisão independente (três agentes)

Três agentes leram o trabalho sem receber as minhas conclusões:

| Agente | Resultado |
|---|---|
| Depurador (causa-raiz) | Chegou às mesmas quatro causas: anexo apagado, foto marcada como logo, edição sem `input_fidelity`, histórico sem o que foi gerado. |
| Verificador de integração | Rotas e campos da interface e do servidor batem e não há travessia de caminho. Achou **problemas reais, todos corrigidos e testados**: (1) duas tarefas da mesma conversa se sobrescreviam (agora trava e relê do disco); (2) "editar" sem imagem anterior no disco seguia como edição (agora vira pedido novo com aviso); (3) anexo apagado da biblioteca era ignorado em silêncio (agora erro 409 claro); (4) memória truncada em 300 caracteres e resposta a pergunta de edição perdia a imagem-alvo (limites maiores e a intenção original é mantida); (5) editar uma imagem antiga confundia o resolvedor (agora ele recebe o turno escolhido); (6) resultado podia cair na conversa errada se você trocasse de conversa durante a geração (agora o botão e o seletor ficam desativados enquanto gera); (7) a recusa de `input_fidelity` repetia chamada e aviso a cada tentativa (agora lembra a recusa); (8) JSON de conversa corrompido, SVG de teste antigo e nome de arquivo com quebra de linha. |
| Teste no navegador (mock) | 7 de 7 fluxos passaram: tipo da imagem, anexos fixos, recarregar, edição por contexto, nova conversa, console limpo e visual. |

## 6. Limites

- **Rosto de pessoa real:** mesmo com `input_fidelity=high`, a API pode recusar ou alterar o rosto. Se acontecer, a mensagem sai **reprovada com `identidade_divergente`** e um aviso, em vez de "parecer ok". Cabe uma decisão do CEO sobre direitos de imagem e sobre outro fluxo para pessoas reais (foto real + composição por código).
- **Logo da CVC:** na imagem de teste, o modelo **desenhou** o logo da CVC por conta própria. Logo e texto exato continuam devendo ser compostos por código (`compose_text_overlay` ainda não existe); com o logo anexado como tipo `logo` e o pacote `identity`, o critic passa a reprovar o logo redesenhado.
- O resolvedor é um modelo: pode errar a intenção. O botão "Editar esta imagem" continua mandando mais que ele, e o painel de memória mostra o que ele entendeu.
- Os dados ficam em `test/conversations/` (fora do git). **Não apague** essa pasta nem `test/clients/` e `test/chat_out/`.

## 7. Como testar com a chave

1. Envie a foto da pessoa, mude o tipo para **pessoa** e deixe-a fixada.
2. Peça: "retrato desta pessoa em um escritório". Confira a nota, `identidade_divergente` e os avisos.
3. Sem anexar nada de novo, peça: "agora com camisa azul". Deve aparecer "Memória: entendi como edição da imagem anterior" e a imagem deve mudar só a camisa.
4. Peça algo sem relação ("um gato astronauta"): não deve herdar a pessoa.
5. `cd test && python3 e2e_chat.py` prova a fiação sem custo (pasta temporária, sem tocar nos seus dados).
