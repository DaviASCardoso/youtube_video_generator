"""Provedor de visuais: FLUX.2-dev (Together) — **camada de fundo** por IA.

`planejar` faz a segunda chamada Groq (frases → prompts de imagem) e reporta o
custo dessa chamada; `renderizar` chama o FLUX por prompt (aplicando a variação de
estilo ao texto do prompt) e reporta o custo da imagem. Produz só o **fundo**: a
camada de personagem (com emoção por cena, planejada à parte) é composta pelo
pipeline sobre este fundo — por isso o `dado` da cena pode chegar como o prompt puro
ou como um dict `{"prompt", "emocao"}` quando o personagem está ligado.
"""

from pathlib import Path

from geracao.custo import CUSTO_FLUX_IMAGEM, CUSTO_GROQ_CHAMADA
from geracao.generate_image import gerar_imagem
from geracao.generate_script import _chamar_api, _parsear_prompts
from geracao.provedores.base import PAPEL_VISUAIS, registrar


@registrar(PAPEL_VISUAIS, "flux")
class VisuaisFlux:
    def planejar(self, frases, config, assets_dir, variacao=None, ledger=None):
        system = (
            (Path(assets_dir) / "system_prompt_prompt.txt")
            .read_text(encoding="utf-8")
            .strip()
        )
        numeradas = "\n".join(f"{i}. {frase}" for i, frase in frases)
        resposta = _chamar_api(system, numeradas, config)
        prompts = _parsear_prompts(resposta)

        if ledger is not None:
            ledger.registrar(
                "plano_visual", "groq", CUSTO_GROQ_CHAMADA, modelo=config.get("groq.modelo")
            )
        return list(prompts)  # 1:1 com as frases

    def renderizar(self, indice, dado, config, assets_dir, variacao=None, ledger=None):
        prompt = dado["prompt"] if isinstance(dado, dict) else dado
        if variacao is not None:
            prompt = variacao.aplicar_ao_estilo(prompt)

        referencia = Path(assets_dir) / "imagem_referencia.png"
        ref_arg = str(referencia) if referencia.exists() else None
        imagem = gerar_imagem(prompt, config, assets_dir, referencia=ref_arg)

        if ledger is not None:
            ledger.registrar(
                "visuais", "flux", CUSTO_FLUX_IMAGEM, modelo=config.get("together.modelo")
            )
        return imagem  # bytes
