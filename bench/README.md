# Benchmark do harness de imagens

Coleção versionada de casos gerais (fotografia, ilustração, edição, personagens, produtos, interfaces, banners, flyers, posts, diagramas) e a ferramenta `test/bench.py` para executar, checar, comparar às cegas e relatar. Só stdlib; sem rede e sem custo por padrão.

Arquivos:

| Arquivo | O que é |
|---|---|
| `dev.json` | casos de **desenvolvimento**: podem ser rodados e usados para ajustar prompts, regras e modelo |
| `final.json` | casos de **avaliação final**: existem para detectar sobreajuste; travados por hash |
| `LOCK.json` | `final_sha256`, data, regra e `history` (cada mudança do final, com razão e data) |
| `refs/` | referências reais **fornecidas por você** (não versionadas; ver abaixo) |
| `final_runs.jsonl` | auditoria: uma linha por uso do conjunto final (criado na primeira execução) |

## Uso

```bash
python3 test/bench.py validate                      # esquema, ids, splits, 14 categorias, quase duplicatas dev x final, lock
python3 test/bench.py run --split dev --generate fake            # pipeline local, sem rede, sem custo
python3 test/bench.py run --split dev --generate fake --only dev-foto-01 dev-texto-01
python3 test/bench.py check --run RUN               # checagens automáticas aplicáveis -> RUN/checks.json
python3 test/bench.py report --run RUN --out relatorio.md
python3 test/bench.py blind-pack --a RUN_A --b RUN_B --seed 7     # pacote cego + key.json
python3 test/bench.py blind-score --ratings ratings.csv --key key.json
python3 test/bench.py report --run RUN_A --ratings ratings.csv --key key.json
```

Os runs ficam em `test/bench_out/<run_id>/` (`images/`, `results.json`, `checks.json`). Essa pasta deve ser ignorada pelo git. Cada caso registra status (`done`, `skipped`, `failed`, `budget_exhausted`), latência, tentativas, chamadas pagas, `request_id`s, avisos, data, modelo, tamanho pedido e real, e a versão do benchmark (sha256 de dev e final).

### Gerar com a API real (gasta dinheiro)

```bash
OPENAI_API_KEY=... python3 test/bench.py run --split dev --generate openai --max-calls 5 --i-approve-paid-calls
```

Recusado sem `--max-calls` >= 1, sem `--i-approve-paid-calls` ou sem `OPENAI_API_KEY`. Usa `provider.OpenAIImages` com um `Budget` de N chamadas pagas (cada tentativa HTTP, inclusive repetição segura, conta). Quando o orçamento acaba, o que sobrou fica `budget_exhausted` no `results.json`. Só rode com orçamento aprovado.

### A regra dev x final

- O conjunto **final não pode ser usado para ajustar prompts, regras ou modelo.** Se um resultado do final levar a uma mudança, o final deixa de medir sobreajuste.
- `run --split final` exige `--confirm-final`, imprime o aviso e acrescenta uma linha (data, run_id, gerador, nº de casos) em `final_runs.jsonl`: dá para auditar quantas vezes o final foi consultado.
- `final.json` só muda de propósito: depois de editar, `python3 test/bench.py lock --reason "por que mudou"` regrava o hash e acrescenta razão e data em `history`. Sem isso, `validate` (e portanto `run`) falha.
- O `validate` recusa um brief do final quase igual a um do dev (similaridade de palavras >= 0,5).

## Formato de um caso

`id` (estável, `dev-foto-01`), `split`, `category` (uma das 14 obrigatórias), `brief` (o que o usuário escreveria), `references` (`id`, `role` em identidade/estilo/logo/base/produto/dados, `description`, `user_supplied`), `required_criteria` (`id`, `text`, `check` em `human`/`auto:size`/`auto:ocr`/`auto:preservation`), `preservation` (o que não pode mudar; obrigatório nas edições), `text_literals` (textos exatos para OCR), `expected_size` (`1024x1024`, `1536x1024`, `1024x1536` ou `auto`), `eval_method`, e opcionais `difficulty`, `notes`, `known_failure_mode` (obrigatório em "caso de falha esperada"). Campos desconhecidos são erro.

Categorias: fotografia, ilustração, cena complexa, texto em português, produto, personagem recorrente, edição local, troca de fundo, preservação de identidade, múltiplas referências, peça de marketing, diagrama com dados fornecidos pelo usuário, pedido ambíguo, caso de falha esperada. Em "pedido ambíguo" o critério correto é pedir esclarecimento ou assumir **e avisar**, nunca um default silencioso.

## Como fornecer referências reais

Nenhuma imagem está no repositório. Para um caso com referência `user_supplied: true`, coloque o arquivo em:

```
bench/refs/<id do caso>/<id da referência>.png      (ou .jpg, .jpeg, .webp)
```

Exemplo: `bench/refs/dev-edicao-01/sala-base.png`. Use só imagens suas ou de pessoas que autorizaram o uso (casos de identidade e troca de fundo). Se faltar qualquer referência de um caso, o caso é **pulado com o motivo** (`skipped`) e nunca "passa". Referências com `user_supplied: false` (por exemplo, dados escritos no próprio pedido) não precisam de arquivo.

## Checagens automáticas (`check`)

| Critério | Resultado |
|---|---|
| `human` | `pending_human` (nunca aprovado automaticamente) |
| `auto:size` | `pass` ou `fail`, lendo o tamanho real do PNG; JPEG/WebP ficam `not_verified` |
| `auto:ocr` | `ocr_match`, `ocr_mismatch` ou `not_verified` (OCR indisponível). O OCR (`test/ocr.py`) é auxiliar: texto pequeno, fontes decorativas, baixo contraste, texto curvo e outros idiomas não são verificáveis; preços, datas e números vão para revisão humana |
| `auto:preservation` | `not_implemented` |
| caso sem imagem | `not_run` |

## Comparação cega

`blind-pack` embaralha a ordem (metade dos casos com os braços trocados, sorteio pela `--seed`), remove metadados auxiliares dos PNGs e grava:

- `avaliador/`: `<caso>_X.png`, `<caso>_Y.png`, `ratings_template.csv`, `INSTRUCOES.txt` (**só isto** vai ao avaliador);
- `key.json`: seed e mapeamento X/Y -> braço (**nunca** entregar; a seed permite recalcular o sorteio).

O avaliador preenche `preferred` (X, Y ou empate) e `fidelity_x`/`fidelity_y` (1 a 5). `blind-score` agrega por braço, mostrando n e empates, e recusa linhas inválidas em vez de ignorá-las.

### Baseline externo (ChatGPT ou outro)

Comparar com o ChatGPT exige imagens **obtidas legitimamente** (geradas manualmente por você, na sua conta, dentro dos termos do serviço) e ordem aleatória. **Este benchmark não automatiza o acesso à interface do ChatGPT e não deve ser usado para isso.** Para usar um baseline: monte uma pasta de run com `images/<id do caso>.png` e um `results.json` mínimo (`run_id`, `generate: "external"`, `source` descrevendo como as imagens foram obtidas, e `cases: [{id, status: "done", image: "images/<id>.png"}]`), e passe `--baseline-arm` e `--baseline-source` ao `blind-pack`. Não há comando de importação.

O `report` só omite a frase **"paridade ainda não demonstrada"** quando existe um braço `external` declarado como baseline, o outro braço não é `fake`, e há avaliação cega com preferências. Mesmo assim ele não afirma paridade nem superioridade.

## O que NÃO está implementado

- **O harness completo não está no caminho do `run --generate openai`:** o prompt é o brief literal enviado ao adapter de imagens (`generate` ou `edit`). Runner, briefing, critic e resolução de contexto não participam, e casos de "pedido ambíguo" (cuja resposta correta é uma pergunta) só podem ser avaliados num harness conversacional.
- Preservação fora de uma máscara (`auto:preservation`) e qualquer verificação automática de identidade, estilo, anatomia, contagem ou dados de gráficos.
- OCR depende do executável `tesseract` (não instalado por padrão): sem ele, `auto:ocr` fica `not_verified`.
- Importação de baseline externo, avaliadores múltiplos, concordância entre avaliadores, teste estatístico e intervalo de confiança.
- Preço em dinheiro: o custo é contado em chamadas pagas (os modelos 2.5 cobram por tokens e não há tabela por imagem); `usage` fica no `results.json` quando a API o devolve.
- Remoção de metadados de JPEG e WebP no pacote cego (só PNG); formatos diferentes entre os braços podem revelar a origem pela extensão, e `blind-pack` avisa em `key.json`.
- Nada foi medido com a API real. O gerador `fake` só valida o pipeline e não mede qualidade. **Paridade com o ChatGPT: ainda não demonstrada.**
