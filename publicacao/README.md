# Pilar Publicação

Leva o **artefato final até a(s) plataforma(s)**: a partir do `video_final.mp4` + do
`sidecar.json` da Geração, produz metadados e thumbnail, define visibilidade/disclosure,
sobe no horário certo e registra onde o vídeo foi parar.

A spec de referência é `PILAR_3_PUBLICACAO.md` (raiz), sob dois princípios:
**eficiência** (upload é caro em *cota*, não em dólar — nunca subir duas vezes; nunca
refazer metadados/thumbnail que já existem e validam) e **configurabilidade** (todo
destino/template/toggle/default é editável na aba **Publicação** do painel).

## Fluxo

```
vídeo + sidecar → metadados (Groq) → thumbnail (fundo FLUX/Pexels + texto Groq)
  → [disclosure / visibilidade / gate de revisão] → por destino ativo (imediato/agendado)
  → published-record (ids, urls, cota)
```

`publicador.publicar(tipo, pasta_run, execucao_id, ledger)` orquestra tudo. Em modo
`revisar`, prepara metadados/thumbnail e **aguarda aprovação** (o run fica
`aguardando_publicacao`); o botão **Aprovar & publicar** dispara
`publicador.publicar_aprovado` (idempotente). Sem destino ativo, não publica — o
comportamento default de hoje.

## Módulos

- `configuracao.py` — `PUBLICACAO_PADRAO`, enums e `mesclar_publicacao` (+ migração do
  bloco `youtube` legado: `publicar` → `destinos.youtube.ativo`).
- `metadados.py` — Groq (via `_chamar_api`) transforma tema/roteiro em `{titulo,
  descricao, tags}` otimizados; checkpoint em `publicacao.json`.
- `thumbnail.py` — Groq gera texto + prompt/termo; fundo por FLUX **ou** Pexels; texto
  composto com PIL (`ImageDraw` + stroke); ligável por tipo; checkpoint `thumbnail.png`.
- `registro.py` — o `publicacao.json` da pasta do run (metadados + texto da thumb).
- `quota.py` — cota diária de upload por credencial (`execucoes/quota_publicacao.json`).
- `publicador.py` — orquestrador (gate de revisão, cota, credencial, idempotência,
  degradação por destino).
- `destinos/base.py` — contrato de destino plugável (registro `nome → destino`).
- `destinos/youtube.py` — YouTube atrás do contrato (metadados otimizados, `publishAt`,
  thumbnail, verificação de credencial).
- `youtube.py` — cliente OAuth por tipo de baixo nível (auth, `videos.insert`,
  `thumbnails.set`, `checar_credencial`); costura para novos destinos.

Novos destinos (TikTok/Reels/Kwai) entram implementando o contrato em `destinos/`, sem
recablear o pilar. Nenhuma credencial nova é configurada aqui — reusa YouTube/Groq/
FLUX/Pexels já presentes.

## Credenciais e CLI

Credenciais **por tipo** (isolam a cota, um projeto Cloud por canal):
`tipos/<id>/youtube_client_secret.json` e `tipos/<id>/youtube_token.json` (gitignored).

- `python -m publicacao.youtube auth --tipo <id>` — consentimento OAuth único.
- `python -m publicacao.youtube publicar <video> --tipo <id>` — upload manual (legado).

**Gotcha:** apps OAuth em "Testing" expiram o refresh token em ~7 dias — a Publicação
surfaca o token expirado/prestes a expirar (`checar_credencial`) em vez de falhar calada.
