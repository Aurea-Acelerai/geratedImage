#!/bin/bash
B=${1:-localhost:8792}
for p in / /brand/logo-acelerai-white.png /brand/logo-acelerai-white-sm.png /brand/favicon.png /brand/brand.css /brand/../chat_server.py /brand/%2e%2e/chat_server.py /brand/..%2fchat_server.py /brand/%2e%2e%2fchat_server.py "/brand/%00.png" /brand/chat_server.py /brand/x.py /brand/ /brand /brand/..%5cchat_server.py "/brand/....//chat_server.py" /brand//etc/passwd "/brand/%252e%252e/chat_server.py" "/brand/..;/chat_server.py"; do
 printf "%s -> " "$p"; curl -s --path-as-is -o /dev/null -w "%{http_code} %{content_type} %{size_download}\n" "$B$p"; done
