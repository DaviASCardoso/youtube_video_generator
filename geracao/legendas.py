"""Legendas opcionais da montagem (default off).

Duas saídas, ambas derivadas das frases + durações de cada cena:
- um arquivo **.srt** inspecionável (sempre barato, escrito quando as legendas
  estão ligadas);
- o **burn-in** opcional do texto sobre cada clipe via moviepy `TextClip`.

A camada de legenda expõe as mesmas alavancas de estilo do texto da thumbnail
(fonte, cor, posição e contorno): o contorno vira `stroke_width`/`stroke_color`
do `TextClip` (o equivalente ao `stroke` do PIL em `publicacao/thumbnail.py`). Com
os defaults (contorno 0, fonte vazia) o resultado é idêntico ao de antes.

O burn-in é best-effort: qualquer falha (ex.: sem ImageMagick/fonte) devolve os
clipes originais — legenda nunca derruba a montagem. Com `legendas.ativo: false`
(default), nada disto roda e a montagem fica idêntica à de antes.
"""

from pathlib import Path

try:  # símbolos no nível do módulo para permitir monkeypatch nos testes
    from moviepy import CompositeVideoClip, TextClip
except Exception:  # noqa: BLE001 (moviepy pode faltar/variar de versão)
    CompositeVideoClip = None
    TextClip = None

_POSICOES = {
    "inferior": ("center", "bottom"),
    "superior": ("center", "top"),
    "centro": ("center", "center"),
}


def _timestamp(segundos: float) -> str:
    """Formata segundos como o timestamp de SRT: HH:MM:SS,mmm."""
    ms = int(round(max(0.0, segundos) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def montar_srt(itens: list[tuple[str, float]]) -> str:
    """Constrói o texto SRT a partir de (frase, duração) por cena (função pura)."""
    blocos, t = [], 0.0
    for i, (texto, dur) in enumerate(itens, start=1):
        inicio, fim = t, t + float(dur)
        blocos.append(f"{i}\n{_timestamp(inicio)} --> {_timestamp(fim)}\n{str(texto).strip()}")
        t = fim
    return "\n\n".join(blocos) + "\n"


def escrever_srt(caminho: str | Path, itens: list[tuple[str, float]]) -> Path:
    p = Path(caminho)
    p.write_text(montar_srt(itens), encoding="utf-8")
    return p


def sobrepor_legendas(clipes: list, itens: list[tuple[str, float]], cfg: dict) -> list:
    """Queima o texto de cada cena sobre o clipe correspondente (best-effort).

    Devolve os clipes originais se o moviepy TextClip não estiver disponível ou se
    a composição falhar — a legenda é um extra, não pode quebrar o vídeo.
    """
    if TextClip is None or CompositeVideoClip is None:
        return clipes

    posicao = _POSICOES.get(cfg.get("posicao", "inferior"), ("center", "bottom"))
    fonte = cfg.get("fonte") or None  # vazio = fonte padrão do moviepy
    contorno = max(0, int(cfg.get("contorno_largura", 0)))  # 0 = sem contorno (idêntico a hoje)
    novos = []
    for clipe, (texto, _) in zip(clipes, itens):
        try:
            legenda = (
                TextClip(
                    text=str(texto).strip(),
                    font=fonte,
                    font_size=cfg.get("tamanho", 48),
                    color=cfg.get("cor", "#FFFFFF"),
                    stroke_color=cfg.get("contorno_cor", "#000000"),
                    stroke_width=contorno,
                )
                .with_duration(clipe.duration)
                .with_position(posicao)
            )
            novos.append(CompositeVideoClip([clipe, legenda]))
        except Exception:  # noqa: BLE001 (degrada para o clipe sem legenda)
            novos.append(clipe)
    return novos
