"""Provedor de visuais: **camada de fundo** por foto do Pexels.

`planejar` faz a chamada Groq de cena (frase → emoção + termo de busca) e já resolve
o índice de fundo por termo repetido (para variar a foto quando a mesma busca aparece
de novo). A emoção fica no dado da cena para a camada de personagem (aplicada pelo
pipeline) usá-la — o provedor em si só produz o **fundo**. `renderizar` baixa a foto no
Pexels e recorta para o canvas; se o Pexels falhar, cai num gradiente de placeholder —
o run não quebra. A composição do personagem é uma camada separada, ligada/desligada
independente da fonte do fundo.
"""

from pathlib import Path

from geracao import pexels
from geracao.compositor import compor_fundo
from geracao.custo import CUSTO_GROQ_CHAMADA, CUSTO_PEXELS, CUSTO_PLACEHOLDER
from geracao.generate_scene import _normalizar
from geracao.generate_script import _chamar_api, _parsear_prompts
from geracao.provedores.base import PAPEL_VISUAIS, registrar


def _orientacao(config) -> str:
    return (
        "portrait"
        if config.get("imagens.altura") > config.get("imagens.largura")
        else "landscape"
    )


@registrar(PAPEL_VISUAIS, "pexels")
class VisuaisPexels:
    def planejar(self, frases, config, assets_dir, variacao=None, ledger=None):
        system = (
            (Path(assets_dir) / "system_prompt_cena.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        numeradas = "\n".join(f"{i}. {frase}" for i, frase in frases)
        resposta = _chamar_api(system, numeradas, config)
        cenas_raw = _parsear_prompts(resposta)

        if ledger is not None:
            ledger.registrar(
                "plano_visual", "groq", CUSTO_GROQ_CHAMADA, modelo=config.get("groq.modelo")
            )

        dados = []
        usados: dict[str, int] = {}  # varia o fundo quando o mesmo termo se repete
        for i, _ in enumerate(frases):
            raw = cenas_raw[i] if i < len(cenas_raw) and isinstance(cenas_raw[i], dict) else {}
            emocao, busca, icone = _normalizar(raw)
            i_fundo = usados.get(busca, 0)
            usados[busca] = i_fundo + 1
            # O conceito de ícone rega junto a mesma chamada de cena — a camada de
            # ícones (aplicada pelo pipeline) o consome; None quando nenhum ícone serve.
            dados.append({"emocao": emocao, "busca": busca, "i_fundo": i_fundo, "icone": icone})
        return dados

    def renderizar(self, indice, dado, config, assets_dir, variacao=None, ledger=None):
        fundo_bytes = pexels.buscar_imagem(
            dado["busca"], orientacao=_orientacao(config), indice=dado.get("i_fundo", 0)
        )
        quadro = compor_fundo(fundo_bytes, config, indice=indice)

        if ledger is not None:
            provedor = "pexels" if fundo_bytes else "placeholder"
            custo = CUSTO_PEXELS if fundo_bytes else CUSTO_PLACEHOLDER
            ledger.registrar("visuais", provedor, custo, busca=dado["busca"])
        return quadro  # PIL.Image (só o fundo; o personagem é camada separada)
