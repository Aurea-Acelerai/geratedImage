#!/bin/sh
# Roda os testes automáticos, em portas livres e com dados temporários (nunca toca em clients/ nem chat_out/).
#   ./run_tests.sh
# Cada e2e sobe o próprio servidor e o encerra no fim. Para na primeira falha. É o mesmo comando que o CI roda.
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-python3}"
for t in test_provider.py test_runner.py test_obsidian_sync.py test_store.py e2e_brand.py e2e_convs.py e2e_chat.py e2e_preflight.py e2e_vercel.py; do
  echo "== $t"
  "$PY" "$t" || { echo "FALHOU: $t"; exit 1; }
done
echo "TODOS OS TESTES PASSARAM"
