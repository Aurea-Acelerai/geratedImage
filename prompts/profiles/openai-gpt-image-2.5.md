Perfil da ferramenta de imagem: OpenAI gpt-image-2.5 (valores da documentação de nov/2026; confirme na conta antes de usar).

- Modelo: `gpt-image-2.5-flare` para rascunho e exploração; `gpt-image-2.5-sunburst` para final, edição precisa e identidade.
- Qualidade: `low` para rascunho; `medium` ou `high` para final; `xhigh` ou `max` só quando um requisito não atendido justificar o custo.
- Tamanhos: 1:1 = 1024x1024; retrato e story = 1024x1536; banner = 1536x1024. Tamanho livre: lados múltiplos de 16, razão máxima 3:1. Acima de 2560x1440 é experimental.
- Transparência: `background=transparent` com saída PNG ou WebP. Confira o canal alfa.
- Identificação do cliente: envie `safety_identifier` com o hash do cliente.
- Latência: até 2 minutos por imagem; trabalhe de forma assíncrona.
- Erros sem nova tentativa: `image_generation_user_error` (por exemplo `moderation_blocked`). Só repita depois de alterar o prompt ou as imagens.
- Erros com nova tentativa: limite de taxa e 5xx, com backoff.
