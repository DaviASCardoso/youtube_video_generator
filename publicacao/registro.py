"""Registro local da Publicação na pasta do run (`publicacao.json`).

Ao lado do `video_final.mp4`/`sidecar.json`, a Publicação grava um `publicacao.json`
com os artefatos que ela produziu e que não devem ser refeitos: os **metadados
escolhidos** (título/descrição/tags) e o **texto da thumbnail**. É o checkpoint que
garante a eficiência da spec — nunca regenerar metadados/thumbnail que já existem e
validam. Mesmo padrão do `geracao/sidecar.py`, mas com escrita incremental (merge por
chave) porque metadados e thumbnail são preenchidos em passos distintos.

Não confundir com o *published-record* (ids/urls por plataforma), que vive no
`HistoricoExecucoes` — este arquivo é só o material local pré-upload.
"""

import json
from pathlib import Path

NOME_ARQUIVO = "publicacao.json"


def ler(pasta: str | Path) -> dict:
    """Lê o publicacao.json da pasta do run ({} se ausente/ilegível)."""
    caminho = Path(pasta) / NOME_ARQUIVO
    if not caminho.exists():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return dados if isinstance(dados, dict) else {}


def gravar(pasta: str | Path, **campos) -> dict:
    """Faz merge de `campos` no publicacao.json (preservando as outras chaves) e grava."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    dados = ler(pasta)
    dados.update(campos)
    (pasta / NOME_ARQUIVO).write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dados
