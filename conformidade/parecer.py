"""Formas de hand-off da Conformidade — o veredito estável que ela emite.

A Conformidade não produz conteúdo: ela **veta** e **marca**. Estas dataclasses são o
contrato pelo qual ela entrega esses julgamentos:

- `Veredito` — a avaliação de um **tema** na borda da Descoberta (`liberado`/`bloqueado`/
  `flag`), antes de a produção gastar qualquer coisa.
- `Parecer` — a avaliação de uma **publicação** (bloqueio objetivo por disclosure/licença,
  flags advisory, e a decisão de disclosure que a Publicação aplica).
- `Checagem` — o resultado de uma checagem individual, para a trilha de auditoria.
"""

from dataclasses import dataclass, field

# Resultado de um tema (Descoberta).
LIBERADO = "liberado"
BLOQUEADO = "bloqueado"
FLAG = "flag"

# Resultado de uma checagem individual.
PASSOU = "passou"


@dataclass
class Checagem:
    """O desfecho de uma checagem individual (para a auditoria)."""

    nome: str  # disclosure | licenciamento | marca | autenticidade | factual
    resultado: str  # passou | bloqueado | flag
    detalhe: str = ""

    def para_dict(self) -> dict:
        return {"nome": self.nome, "resultado": self.resultado, "detalhe": self.detalhe}


@dataclass
class Veredito:
    """Veredito sobre um tema na borda da Descoberta."""

    resultado: str = LIBERADO  # liberado | bloqueado | flag
    motivo: str = ""

    @property
    def bloqueado(self) -> bool:
        return self.resultado == BLOQUEADO

    @property
    def sinalizado(self) -> bool:
        return self.resultado == FLAG

    def para_dict(self) -> dict:
        return {"resultado": self.resultado, "motivo": self.motivo}


@dataclass
class Parecer:
    """Parecer sobre uma publicação: bloqueios objetivos, flags advisory e disclosure."""

    bloqueado: bool = False
    motivos_bloqueio: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    disclosure_requer: bool = False
    disclosure_base: str = ""
    checagens: list[Checagem] = field(default_factory=list)

    def para_dict(self) -> dict:
        return {
            "bloqueado": self.bloqueado,
            "motivos_bloqueio": list(self.motivos_bloqueio),
            "flags": list(self.flags),
            "disclosure": {"requer": self.disclosure_requer, "base": self.disclosure_base},
            "checagens": [c.para_dict() for c in self.checagens],
        }
