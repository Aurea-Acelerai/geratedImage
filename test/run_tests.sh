#!/bin/zsh
# Roda os testes automáticos do chat, em portas livres e com dados temporários (nunca toca em clients/ nem chat_out/).
#   ./run_tests.sh
# Cada e2e sobe o próprio servidor e o encerra no fim. Para na primeira falha.
cd "${0:A:h}" || exit 1
for t in e2e_brand.py e2e_convs.py e2e_projects.py e2e_chat.py; do
  echo "== $t"
  python3 "$t" || { echo "FALHOU: $t"; exit 1; }
done
echo "TODOS OS TESTES PASSARAM"
