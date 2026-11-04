"""Função da Vercel: o mesmo servidor do chat (test/chat_server.py) como `class handler(BaseHTTPRequestHandler)`.

A documentação da Vercel (Python > api directory) aceita três nomes no nível do módulo: `app` (ASGI/WSGI), `application`
(WSGI) ou `handler` (subclasse de BaseHTTPRequestHandler). Usamos `handler`, então não há framework nem dependência extra.

Em produção/preview a Vercel define VERCEL=1: isso liga JOBS_INLINE (o pipeline roda dentro da requisição), desliga /api/setkey e
troca o guarda "só 127.0.0.1" pela checagem de mesma origem. O estado vai para o Vercel Blob (BLOB_READ_WRITE_TOKEN); a chave da
OpenAI vem de OPENAI_API_KEY. Ver docs/12-memoria-na-vercel.md e HANDOFF.md.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "test"))  # chat_server.py e módulos irmãos (checks, critic, store, ...)

from chat_server import H  # noqa: E402


class handler(H):
    """Nome exigido pelo runtime Python da Vercel. Toda a lógica (rotas, guardas, jobs) está em H."""
