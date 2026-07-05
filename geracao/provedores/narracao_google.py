"""Provedor de narração: Google Cloud TTS.

Embrulha `generate_voice.gerar_narracao`, reporta o custo estimado por caractere e
aceita uma `voz` de override — é a costura que o runner usa no fallback para a voz
secundária (`geracao.narracao.voz_secundaria`) quando a voz principal falha.

Costura para o futuro: um `NarracaoElevenLabs` registrado sob (narracao,
"elevenlabs") entra sem tocar no pipeline — só precisa da mesma interface `narrar`.
"""

from pathlib import Path

from geracao.custo import custo_tts
from geracao.generate_voice import gerar_narracao
from geracao.provedores.base import PAPEL_NARRACAO, registrar


@registrar(PAPEL_NARRACAO, "google")
class NarracaoGoogle:
    def narrar(self, texto, caminho_saida, config, voz=None, ledger=None):
        saida = gerar_narracao(texto, caminho_saida, config, voz=voz)
        if ledger is not None:
            ledger.registrar("narracao", "google", custo_tts(texto), voz=voz or config.get("tts.voz"))
        return Path(saida)
