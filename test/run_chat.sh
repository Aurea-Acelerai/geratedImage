#!/bin/zsh
# Sobe o chat de teste e abre o navegador. A chave é pedida sem eco e fica só nesta execução.
#   ./run_chat.sh            # usa OPENAI_API_KEY se já estiver definida; senão pergunta
#   ./run_chat.sh --mock     # sem API, imagens falsas
cd "${0:A:h}" || exit 1
if [[ "$*" != *--mock* && -z "$OPENAI_API_KEY" ]]; then
  read -s "OPENAI_API_KEY?Chave da OpenAI (Enter para pular: só o briefing, via Claude): "; echo
  [[ -n "$OPENAI_API_KEY" ]] && export OPENAI_API_KEY || unset OPENAI_API_KEY
fi
(sleep 1.5; open "http://127.0.0.1:8766" 2>/dev/null) &
exec python3 chat_server.py "$@"
