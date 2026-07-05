"""Provedor de roteiro: Groq (llama-3.3-70b).

Embrulha a primeira chamada de `generate_script` (texto do roteiro + separação em
períodos), aplica a variação de abertura/estrutura ao system prompt e reporta o
custo de uma chamada Groq.
"""

from pathlib import Path

from geracao.custo import CUSTO_GROQ_CHAMADA
from geracao.generate_script import _chamar_api, _separar_periodos
from geracao.provedores.base import PAPEL_ROTEIRO, registrar


@registrar(PAPEL_ROTEIRO, "groq")
class RoteiroGroq:
    def gerar(self, tema, config, assets_dir, variacao=None, ledger=None):
        system = (
            (Path(assets_dir) / "system_prompt_script.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        if variacao is not None:
            system = variacao.aplicar_ao_roteiro(system)

        texto = _chamar_api(system, f"Gere um roteiro sobre {tema}", config)
        frases = _separar_periodos(texto, config.get("pipeline.min_chars_por_periodo"))

        if ledger is not None:
            ledger.registrar(
                "roteiro", "groq", CUSTO_GROQ_CHAMADA, modelo=config.get("groq.modelo")
            )
        return [(i + 1, frase) for i, frase in enumerate(frases)]
