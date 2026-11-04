# 11. Harness no estilo do ChatGPT: o que os vazados ensinam e as regras rígidas (04/11/2026)

Pedido: o chat não pode se perder na própria conversa, o usuário não pode ter que reanexar imagens a cada mensagem, deve dar para buscar logos na web, e a imagem pedida "com o Rodrigo Faro" não pode virar outra coisa. Base: os prompts vazados já mapeados em `docs/01` e `docs/02`.

## 1. O que os vazados mostram (verificado em `docs/01`, `docs/02`)

| Mecanismo do ChatGPT | Detalhe | Consequência para o nosso harness |
|---|---|---|
| `image_gen.text2im` com **`referenced_image_ids`** | Toda imagem da conversa (anexada ou gerada) tem um id; o orquestrador escolhe quais usar em cada chamada | Referências são **da conversa**, não da mensagem |
| Orquestrador com a conversa **inteira** + memória + anexos | O prompt final é escrito por um modelo que vê tudo | O designer recebe a **transcrição inteira**, não um resumo |
| "Gerar direto, exceto quando a imagem inclui o próprio usuário: pede uma foto de referência" | Regra de pessoa específica | Pessoa nomeada exige referência; sem ela, perguntar |
| Edição só com **alvo real** na conversa | Sem alvo, pede o upload | Edição sem imagem anterior vira pedido novo, com aviso |
| `image_group`: **busca de imagens na web** | É busca, não geração | Painel "Buscar na web" |
| Modo agente: "não retratar entidades reais (logos, marcos)" com imagegen | Logo e marca vêm de arquivo oficial | Logo real: biblioteca ou web, nunca gerado do zero |
| Argumentos da ferramenta nunca aparecem ao usuário | Regra em caixa alta | Já aplicada |
| Política: recusa educada | Depiction Protocol não copiado (decisão do HANDOFF) | Mantemos julgamento próprio e **falha às claras** |

O que os vazados **não** mostram é o raciocínio interno do modelo. Não dá para copiá-lo; dá para copiar o harness.

## 2. Regras públicas verificadas hoje (com grau de confiança)

| Regra | Fonte | Confiança |
|---|---|---|
| A OpenAI passou a permitir imagens de figuras públicas adultas (mar/2025), com salvaguardas, opt-out e regras extras para figuras políticas | cobertura jornalística (TechCrunch, CBC) | média: não achei página oficial de 2026; aplicação relatada como **inconsistente** |
| `input_fidelity="high"` na edição serve para rostos e logos; **só a primeira imagem enviada** ganha riqueza extra de textura | cookbook da OpenAI | alta; suporte varia por modelo (não vale para `gpt-image-1-mini`) |
| Primeiras versões do parâmetro davam "Unknown parameter" | fórum da OpenAI | média; o nosso fallback sem o parâmetro cobre |

**Não pesquisei** as regras de Anthropic, Google e Meta. Fica pendente se o CEO quiser o comparativo.

## 3. Por que "peço o Rodrigo Faro e vem outra coisa" (e o que mudou)

| Causa (verificada em `docs/10` e no teste de hoje) | Correção |
|---|---|
| A foto valia só para a mensagem em que foi anexada | Arquivos da **conversa**, gravados no servidor: ficam até você soltar |
| A foto vinha marcada como logo | Tipo editável por imagem; padrão `referencia`; `pessoa` = identidade a preservar |
| O usuário precisava citar/anexar a foto toda hora | **Apelido**: citar "Rodrigo" anexa a foto sozinho (e o progresso avisa) |
| O designer pedia uma foto que já estava na biblioteca | Ele diz qual arquivo; botão "📌 Usar e continuar" |
| Sem foto na biblioteca | Botão "🔎 Buscar «…» na web" (Wikimedia Commons, com licença e autor) |
| Um sósia passava como aprovado | Pacote `identity` no critic; **falha explícita** ("Não consegui manter a identidade…") |
| A API pode recusar ou alterar o rosto de uma pessoa real | Aviso claro e dica de reescrita; nunca entrega outra pessoa como se fosse |

## 4. As regras rígidas (no prompt do designer, seção 0, e no código)

| # | Regra | Onde |
|---|---|---|
| R1 | Contexto inteiro: tudo o que foi dito, anexado e gerado continua valendo | transcrição completa em `memory_text`; teste e2e |
| R2 | Referências são da conversa (anexadas ou citadas pelo nome) até o usuário remover | `conv["files"]`, `resolve_files`, `alias_matches` |
| R3 | Pessoa específica exige referência; nunca trocar por sósia sem dizer | prompt, pacote `identity`, `falha_identidade` |
| R4 | Entidades reais (logo, marca, marco) não se inventam: arquivo ou busca | prompt, `search` na pergunta, painel da web |
| R5 | Edição só com alvo real | `run_chat` (vira pedido novo com aviso) |
| R6 | Falhar às claras: dizer o que não deu e por quê | avisos, `falha_identidade`, dica de bloqueio da OpenAI |
| R7 | Gerar direto; perguntar só o necessário | prompt |
| R8 | Nunca expor argumentos da ferramenta | prompt |
| R9 | Só o navegador local usa o chat (Host e Origin) | `_local_only`; teste e2e |
| R10 | A chave nunca vai para o chat, o registro ou o repositório | campo no navegador, Keychain, teste e2e |
| R11 | Downloads da web: https, fora da rede interna, até 15 MB, só PNG/JPEG/WEBP conferidos pelo conteúdo | `fetch_image`, `_check_url` |

## 5. Busca na web: limites

- Fonte: **Wikimedia Commons** (aberta, sem chave). Boa para logos antigos e fotos livres; **não é um logo oficial vigente de uma marca**. Para "CVC" ela devolve também o logo da CVC Capital Partners, que é outra empresa: o usuário escolhe, vê título, licença e autor.
- Direito de uso é responsabilidade de quem publica; a tela diz isso. Para peça de cliente, o ideal é o **logo oficial enviado pelo cliente**.
- Outras fontes (Brave, Bing) exigem chave; ficam como extensão.

## 6. O que ainda não é "estilo ChatGPT" (próximo passo)

Hoje o fluxo é em etapas fixas (resolvedor → designer → imagem → critic) e a **busca na web é decidida pelo usuário** (o designer só sugere). O ChatGPT usa um **laço de ferramentas**: o modelo vê a conversa e chama `image_gen`, busca e Python por conta própria, na ordem que julgar. Dá para chegar lá com function calling da OpenAI, com os mesmos testes. Troca: mais flexível, menos previsível. Recomendação: manter as etapas fixas até a primeira rodada de testes reais com a chave e migrar depois, se a qualidade pedir.
