"""Bloco de guia aprendida por prompt: store versionado + injetor compartilhado.

Cada prompt relevante (fit da Descoberta, roteiro e visual da Geração, metadados e
thumbnail da Publicação) ganha um bloco de diretrizes aprendidas **separado do
prompt-base escrito por humano**, versionado e inspecionável. O Feedback escreve
esse bloco (via tradução por LLM); o prompt-base nunca é sobrescrito.

Armazenamento: um JSON por bloco em `tipos/<id>/guia/<nome>.json` (gitignored,
runtime — mesmo padrão dos `descoberta_*.json`). Injeção: `compor(assets_dir, nome,
base)` é chamado no ponto em que cada prompt é lido e **anexa** as linhas ativas do
bloco sob um delimitador. Bloco ausente/vazio ⇒ devolve o base intacto (parity: o
prompt fica idêntico ao de hoje até o Feedback aprender algo).

Cada linha é vetoável (o humano remove uma diretriz específica no Controle sem apagar
o bloco) e fixável (protege da reescrita/decaimento). O render é **defensivo**: um
JSON corrompido degrada para "sem bloco", nunca quebra a leitura do prompt.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# Nomes de bloco conhecidos (um por prompt injetado). São os slugs dos arquivos em
# tipos/<id>/guia/<nome>.json.
NOMES = ("fit", "roteiro", "visual", "metadados", "thumbnail")

# Delimitador que separa o prompt-base do bloco aprendido (visível para o humano).
DELIMITADOR = "--- Diretrizes aprendidas (geridas pelo Feedback) ---"

_VAZIO = {"versao": 0, "atualizado_em": None, "linhas": []}


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def linha(texto: str, confianca: float = 0.0, fonte: str = "", fixado: bool = False) -> dict:
    """Monta uma linha de diretriz normalizada."""
    return {
        "texto": str(texto).strip(),
        "confianca": float(confianca),
        "fonte": str(fonte),
        "fixado": bool(fixado),
        "vetado": False,
        "atualizado_em": _agora(),
    }


def _ordenar(linhas: list[dict]) -> list[dict]:
    """Fixadas primeiro, depois por confiança decrescente."""
    return sorted(
        linhas,
        key=lambda l: (not l.get("fixado", False), -float(l.get("confianca", 0.0))),
    )


class BlocoGuia:
    """Um bloco de guia aprendida (um prompt), num JSON protegido por lock."""

    def __init__(self, caminho: Path):
        self._caminho = Path(caminho)
        self._lock = threading.Lock()

    # --- leitura -------------------------------------------------------------

    def ler(self) -> dict:
        """Lê o bloco. Defensivo: arquivo ausente/corrompido ⇒ bloco vazio."""
        with self._lock:
            return self._carregar()

    def _carregar(self) -> dict:
        if not self._caminho.exists():
            return json.loads(json.dumps(_VAZIO))
        try:
            dados = json.loads(self._caminho.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(_VAZIO))
        if not isinstance(dados, dict) or not isinstance(dados.get("linhas"), list):
            return json.loads(json.dumps(_VAZIO))
        return dados

    def linhas_ativas(self) -> list[dict]:
        """Linhas não-vetadas, ordenadas (fixadas primeiro, depois confiança)."""
        dados = self.ler()
        ativas = [l for l in dados["linhas"] if isinstance(l, dict) and not l.get("vetado") and l.get("texto")]
        return _ordenar(ativas)

    def render(self) -> str:
        """O texto do bloco a anexar ao prompt (vazio se nada ativo)."""
        ativas = self.linhas_ativas()
        if not ativas:
            return ""
        return "\n".join(f"- {l['texto']}" for l in ativas)

    # --- escrita -------------------------------------------------------------

    def _salvar(self, dados: dict) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def substituir(self, linhas: list[dict]) -> dict:
        """Reescreve as linhas do bloco por inteiro, subindo a versão.

        As linhas vetadas/fixadas existentes que casarem por texto têm seus flags
        preservados — o humano não perde um veto quando o LLM reescreve o bloco.
        """
        with self._lock:
            dados = self._carregar()
            flags = {
                l["texto"]: (l.get("fixado", False), l.get("vetado", False))
                for l in dados["linhas"]
                if isinstance(l, dict) and l.get("texto")
            }
            novas = []
            for l in linhas:
                l = dict(l)
                fix, vet = flags.get(l.get("texto"), (l.get("fixado", False), False))
                l["fixado"] = fix
                l["vetado"] = vet
                l.setdefault("atualizado_em", _agora())
                novas.append(l)
            dados = {
                "versao": dados.get("versao", 0) + 1,
                "atualizado_em": _agora(),
                "linhas": novas,
            }
            self._salvar(dados)
            return dados

    def _mutar_indice(self, indice: int, campo: str, valor: bool) -> dict | None:
        with self._lock:
            dados = self._carregar()
            if not (0 <= indice < len(dados["linhas"])):
                return None
            dados["linhas"][indice][campo] = valor
            dados["linhas"][indice]["atualizado_em"] = _agora()
            dados["atualizado_em"] = _agora()
            self._salvar(dados)
            return dados

    def vetar(self, indice: int, vetado: bool = True) -> dict | None:
        """Marca/desmarca uma linha como vetada (some do prompt, fica no arquivo)."""
        return self._mutar_indice(indice, "vetado", vetado)

    def fixar(self, indice: int, fixado: bool = True) -> dict | None:
        """Fixa/desafixa uma linha (protege da reescrita e do decaimento)."""
        return self._mutar_indice(indice, "fixado", fixado)

    def limpar(self) -> None:
        """Esvazia o bloco (mantém a versão para histórico)."""
        with self._lock:
            dados = self._carregar()
            dados = {
                "versao": dados.get("versao", 0) + 1,
                "atualizado_em": _agora(),
                "linhas": [],
            }
            self._salvar(dados)


def _dir_guia(assets_dir) -> Path:
    """A pasta guia/ é irmã de assets/ dentro de tipos/<id>/."""
    return Path(assets_dir).parent / "guia"


def bloco_de(assets_dir, nome: str) -> BlocoGuia:
    """O bloco de guia de um prompt (`nome`) para um tipo (via seu assets_dir)."""
    return BlocoGuia(_dir_guia(assets_dir) / f"{nome}.json")


def compor(assets_dir, nome: str, base: str) -> str:
    """Injeta o bloco de guia `nome` no prompt-base, sob o delimitador.

    Bloco ausente/vazio ⇒ devolve `base` intacto (o prompt fica idêntico ao de hoje).
    Nunca levanta: qualquer falha de leitura degrada para o base.
    """
    try:
        extra = bloco_de(assets_dir, nome).render()
    except Exception:  # noqa: BLE001 — o hot path do prompt nunca pode quebrar
        return base
    if not extra:
        return base
    if base:
        return f"{base}\n\n{DELIMITADOR}\n{extra}"
    return f"{DELIMITADOR}\n{extra}"
