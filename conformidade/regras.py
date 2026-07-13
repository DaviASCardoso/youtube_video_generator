"""Conjunto de regras da Conformidade — versionado por tipo, com changelog.

A requisição da Conformidade **muda de fora**: a plataforma endurece uma política e a
saída segura de ontem fica insegura hoje. Por isso o *conteúdo* das regras (a regra de
disclosure, as listas de brand safety, o mapa de licenças) não fica espalhado pela
lógica — vive num único lugar **versionado**, por tipo, para que apertar o canal a uma
política nova seja **uma edição** e não uma caçada.

Guarda um `regras.json` por tipo em `tipos/<id>/conformidade/regras.json` (JSON + lock,
mesmo padrão de `feedback/guia.py`), com uma `versao` monotônica e um `changelog` (cada
publicação registra versão + quando + nota). Ausente/corrompido ⇒ cai nos defaults
(`REGRAS_PADRAO`), então um tipo sem regras ainda checa com um conjunto sensato.
"""

import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# --- Defaults do conteúdo de regras -----------------------------------------

REGRAS_PADRAO = {
    "disclosure": {
        # Narração por estes provedores conta como voz sintética.
        "narracao_sintetica": ["google", "elevenlabs"],
        # Visual por estes provedores conta como sintético OU realista (stock realista) —
        # o que, somado à narração sintética, exige o disclosure do YouTube.
        "visual_sintetico_ou_realista": ["flux", "pexels"],
    },
    "marca": {
        # Temas inequivocamente inapropriados → bloqueiam (clear-cut).
        "bloqueio": [
            "suicídio", "automutilação", "estupro", "pornografia", "pedofilia",
            "atentado", "massacre", "genocídio", "tortura", "decapitação",
        ],
        # Temas sensíveis → sinalizam para revisão (limítrofe).
        "sensivel": [
            "morte", "assassinato", "tragédia", "acidente fatal", "doença terminal",
            "guerra", "aborto", "overdose", "vício",
        ],
    },
    # Origem de cada provedor de ativo: licenciada (True) ou não (ausente/False = sem licença).
    "licencas": {
        "flux": True,        # imagem gerada por IA (original)
        "pexels": True,      # stock licenciado (Pexels License)
        "google": True,      # narração TTS licenciada
        "groq": True,        # roteiro gerado (original)
        "placeholder": True, # gradiente local
        "iconify": True,     # ícones do Iconify; set padrão mdi = Apache-2.0, sem atribuição
    },
}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _estado_inicial() -> dict:
    """Estado 'ainda não publicado': versão 0, regras default, changelog vazio."""
    return {
        "versao": 0,
        "atualizado_em": None,
        "regras": copy.deepcopy(REGRAS_PADRAO),
        "changelog": [],
    }


class RegrasConformidade:
    """Conjunto de regras versionado de um tipo (JSON protegido por lock)."""

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)
        self._lock = threading.Lock()

    # --- leitura -------------------------------------------------------------

    def estado(self) -> dict:
        """O registro completo: `{versao, atualizado_em, regras, changelog}`.
        Ausente/corrompido ⇒ estado inicial (versão 0, regras default)."""
        with self._lock:
            return self._carregar()

    def _carregar(self) -> dict:
        if not self._caminho.exists():
            return _estado_inicial()
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return _estado_inicial()
        if not isinstance(dados, dict) or not isinstance(dados.get("regras"), dict):
            return _estado_inicial()
        dados.setdefault("versao", 0)
        dados.setdefault("atualizado_em", None)
        dados.setdefault("changelog", [])
        return dados

    def atual(self) -> dict:
        """Apenas o conteúdo de regras vigente (o que as checagens consultam)."""
        return self.estado()["regras"]

    def versao(self) -> int:
        return int(self.estado().get("versao", 0))

    def changelog(self) -> list[dict]:
        """O histórico de mudanças, mais recentes primeiro."""
        return list(reversed(self.estado().get("changelog", [])))

    # --- escrita -------------------------------------------------------------

    def _salvar(self, dados: dict) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def publicar(self, regras: dict, nota: str = "") -> dict:
        """Publica uma nova versão do conjunto de regras (substitui o conteúdo por
        inteiro, sobe a versão e registra a nota no changelog). Devolve o novo estado."""
        with self._lock:
            estado = self._carregar()
            nova_versao = int(estado.get("versao", 0)) + 1
            quando = _agora()
            changelog = list(estado.get("changelog", []))
            changelog.append({"versao": nova_versao, "quando": quando, "nota": nota or ""})
            novo = {
                "versao": nova_versao,
                "atualizado_em": quando,
                "regras": copy.deepcopy(regras),
                "changelog": changelog,
            }
            self._salvar(novo)
            return novo


def _dir_conformidade(tipo) -> Path:
    """A pasta conformidade/ dentro de tipos/<id>/."""
    return Path(tipo.caminho) / "conformidade"


def regras_de(tipo) -> RegrasConformidade:
    """O conjunto de regras versionado de um tipo."""
    return RegrasConformidade(_dir_conformidade(tipo) / "regras.json")
