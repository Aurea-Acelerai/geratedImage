#!/bin/zsh
# Sobe o chat de teste e abre o navegador.
#   ./run_chat.sh            # encerra um chat antigo, pega a chave (Keychain ou digitada) e abre o navegador
#   ./run_chat.sh --mock     # sem API, imagens falsas
# A chave nunca vai para arquivo do repositório. Opcionalmente fica no Keychain do Mac (item "geratedimage-openai").
cd "${0:A:h}" || exit 1
PORT=8766
SERVICE="geratedimage-openai"

# libera a porta se um chat antigo ainda estiver rodando (só mata se for o chat_server.py)
pid=$(lsof -tiTCP:$PORT -sTCP:LISTEN 2>/dev/null | head -1)
if [[ -n "$pid" ]] && ps -p "$pid" -o command= | grep -q "chat_server.py"; then
  echo "Encerrando o chat antigo (pid $pid)..."; kill "$pid"; sleep 1
fi

if [[ "$*" != *--mock* && -z "$OPENAI_API_KEY" ]]; then
  k=$(security find-generic-password -a "$USER" -s "$SERVICE" -w 2>/dev/null)
  if [[ -n "$k" ]]; then
    export OPENAI_API_KEY="$k"; echo "Chave lida do Keychain do Mac."
  else
    read -s "OPENAI_API_KEY?Chave da OpenAI (Enter para pular: só o briefing, via Claude): "; echo
    if [[ -n "$OPENAI_API_KEY" ]]; then
      export OPENAI_API_KEY
      read "ans?Guardar no Keychain do Mac para não digitar de novo? [s/N] "
      if [[ "$ans" == [sS]* ]]; then
        echo "O Keychain vai pedir a chave mais uma vez (assim ela não aparece na lista de processos)."
        security add-generic-password -a "$USER" -s "$SERVICE" -U -w && echo "Guardada. Para apagar: security delete-generic-password -s $SERVICE"
      fi
    else
      unset OPENAI_API_KEY
    fi
  fi
fi

(sleep 1.5; open "http://127.0.0.1:$PORT" 2>/dev/null) &
exec python3 chat_server.py --port $PORT "$@"
