"""Forma normalizada de um candidato a tema + a decisão final da Descoberta.

Qualquer fonte, seja qual for, devolve `Candidato`s — assim fit/dedup/seleção
nunca precisam saber de qual fonte veio. Cada candidato carrega sua origem e a
força bruta do sinal (rank/interesse normalizado 0..1), porque a seleção depende
disso. `fit_score`/`justificativa`/`tema` só são preenchidos após a avaliação de
fit; em modo "reter" eles persistem no buffer sem serem reavaliados.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


def agora() -> datetime:
    """Instante atual em UTC (usado como carimbo de frescor dos candidatos)."""
    return datetime.now(timezone.utc)


def forca_por_posicao(posicao: int, total: int) -> float:
    """Converte a posição num ranking (0 = topo) numa força de sinal 0..1.

    O 1º item vale ~1.0 e o último ~1/total. Fontes que só sabem ordenar (sem
    um número de interesse) usam isto para expressar força de sinal.
    """
    if total <= 0:
        return 0.0
    return max(0.0, 1.0 - posicao / total)


@dataclass
class Candidato:
    texto: str
    fonte: str
    forca_sinal: float
    observado_em: datetime
    categoria: str = "trending"
    fit_score: float | None = None
    justificativa: str | None = None
    tema: str | None = None

    def para_dict(self) -> dict:
        return {
            "texto": self.texto,
            "fonte": self.fonte,
            "forca_sinal": self.forca_sinal,
            "observado_em": self.observado_em.isoformat(),
            "categoria": self.categoria,
            "fit_score": self.fit_score,
            "justificativa": self.justificativa,
            "tema": self.tema,
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "Candidato":
        return cls(
            texto=dados["texto"],
            fonte=dados["fonte"],
            forca_sinal=dados["forca_sinal"],
            observado_em=datetime.fromisoformat(dados["observado_em"]),
            categoria=dados.get("categoria", "trending"),
            fit_score=dados.get("fit_score"),
            justificativa=dados.get("justificativa"),
            tema=dados.get("tema"),
        )


@dataclass
class Decisao:
    """O único tema decidido por tipo que a Descoberta entrega à produção.

    Contrato de hand-off (forma estável): downstream lê isto em vez de drenar
    uma fila. `estado` é "pronto" (segue direto para produção) ou "pendente"
    (gate de revisão ligado, aguardando aprovação).
    """

    tema: str
    fonte: str
    categoria: str
    fit_score: float
    justificativa: str
    prioridade: float
    estado: str = "pronto"

    def para_dict(self) -> dict:
        return {
            "tema": self.tema,
            "fonte": self.fonte,
            "categoria": self.categoria,
            "fit_score": self.fit_score,
            "justificativa": self.justificativa,
            "prioridade": self.prioridade,
            "estado": self.estado,
        }

    @classmethod
    def de_dict(cls, dados: dict) -> "Decisao":
        return cls(
            tema=dados["tema"],
            fonte=dados["fonte"],
            categoria=dados["categoria"],
            fit_score=dados["fit_score"],
            justificativa=dados["justificativa"],
            prioridade=dados["prioridade"],
            estado=dados.get("estado", "pronto"),
        )
