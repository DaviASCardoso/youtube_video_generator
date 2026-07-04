# Pilar Publicação

Leva o **artefato final até a plataforma**: metadados, upload, visibilidade e distribuição.

Módulos:
- `youtube.py` — publicação no YouTube (OAuth por tipo, `videos.insert`, metadados a partir do tema/roteiro).

Runners:
- `python -m publicacao.youtube auth --tipo <id>` — consentimento OAuth único.
- `python -m publicacao.youtube publicar <video> --tipo <id>` — upload manual.

Credenciais **por tipo** (isolam a cota, um projeto Cloud por canal): `tipos/<id>/youtube_client_secret.json` e `tipos/<id>/youtube_token.json` (ambos gitignored).
