# Calibração do critic

O critic é um modelo e pode ser leniente. Antes de confiar na nota dele, compare com quem decide de verdade: o CEO e o time de design.

## O que juntar
De 20 a 40 peças reais, com mistura de **boas e ruins** (inclua as que o CEO apontou como "ruim" e as que ele achou melhores no chat). Quanto mais perto dos casos de produção, melhor.

## Formato do `labels.csv` (nesta pasta, imagens ao lado)
```
imagem,pedido,briefing,nota_humana_0_10,aprovaria_para_cliente_sim_nao,comentario
exemplo01.png,"post de promoção de verão","<prompt usado>",8,sim,
exemplo02.png,"post de promoção de verão","<prompt usado>",3,nao,"cores lavadas, texto errado"
```
`briefing` pode ficar vazio se não for conhecido; o critic avalia contra o pedido e a marca.

## Rodar
```bash
python ../critic.py --calibrate labels.csv --dry-run   # confere o arquivo, sem custo
python ../critic.py --calibrate labels.csv             # roda o critic (OPENAI_API_KEY ou adaptador próprio)
```
A saída traz a correlação com a nota humana e, para cada limiar de 5 a 9,5, quantas peças ruins o critic aprovaria (**falsa aprovação**, o erro caro) e quantas boas ele reprovaria. Escolha o menor limiar sem falsa aprovação e coloque em `prompts/rubric.json` (`pass_score`).

Se a correlação ficar baixa, ajuste `prompts/critic.system.md` (âncoras, escala, exemplos) e rode de novo. Não use as mesmas peças para ajustar e para validar: separe uma parte só para validar.
