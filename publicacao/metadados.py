"""Metadados otimizados por Groq — o tema não é o título.

Passo sempre ligado que transforma o **tema + roteiro** (do sidecar) em título,
descrição e tags voltados para clique e busca, em vez do tema cru no campo de título.
O motor é o **Groq** já usado no roteiro (reusa `_chamar_api` e as credenciais do
projeto — nenhum provedor novo). O que é configurável é o **tom**, os **templates** e
a **estratégia de tags** (bloco `publicacao.metadados`); a persona/base vive num prompt
editável (`system_prompt_metadados.txt`).

Degrada em vez de quebrar: se o modelo devolver algo inesperado, cai no tema/roteiro
crus, para a publicação seguir. O resultado é checkpointado em `publicacao.json`
(`registro.py`) — nunca regenerado se já existe e valida.
"""

import json
import re
from pathlib import Path

from geracao.custo import CUSTO_GROQ_CHAMADA
from geracao.generate_script import _chamar_api
from publicacao import registro
from publicacao.configuracao import mesclar_publicacao

TITULO_MAX = 100  # limite do YouTube para o título

_PROMPT_PADRAO = (
    "Você é um especialista em SEO e crescimento de canais. A partir do tema e do "
    "roteiro de um vídeo, gere metadados que maximizem clique e descoberta. Responda "
    "APENAS com um objeto JSON com as chaves \"titulo\" (string), \"descricao\" (string) "
    "e \"tags\" (array de strings), sem texto fora do JSON."
)

_ESTRATEGIA_TAGS = {
    "mistas": "Misture tags de nicho específicas e termos amplos de maior volume.",
    "nicho": "Prefira tags de nicho específicas e long-tail, de intenção clara.",
    "amplas": "Prefira tags amplas de alto volume de busca.",
}


def _parsear(resposta: str) -> dict:
    resposta = re.sub(r"```(?:json)?\s*", "", resposta).strip().rstrip("`").strip()
    dados = json.loads(resposta)
    return dados if isinstance(dados, dict) else {}


def _system_prompt(assets_dir: Path) -> str:
    caminho = Path(assets_dir) / "system_prompt_metadados.txt"
    if caminho.exists():
        texto = caminho.read_text(encoding="utf-8").strip()
        if texto:
            return texto
    return _PROMPT_PADRAO


def _user_prompt(tema: str, roteiro: str, cfg_meta: dict) -> str:
    partes = [f"TEMA: {tema}", f"ROTEIRO:\n{roteiro}"]
    if cfg_meta.get("tom"):
        partes.append(f"TOM: {cfg_meta['tom']}")
    partes.append(_ESTRATEGIA_TAGS.get(cfg_meta.get("estrategia_tags", "mistas"), ""))
    partes.append(f"Gere no máximo {cfg_meta.get('max_tags', 15)} tags.")
    if cfg_meta.get("template_titulo"):
        partes.append(f"MOLDE DE TÍTULO (siga o formato): {cfg_meta['template_titulo']}")
    if cfg_meta.get("template_descricao"):
        partes.append(f"MOLDE DE DESCRIÇÃO (siga o formato): {cfg_meta['template_descricao']}")
    return "\n\n".join(p for p in partes if p)


def _normalizar(bruto: dict, tema: str, roteiro: str, max_tags: int) -> dict:
    """Sanitiza a resposta do modelo, com fallback para o tema/roteiro crus."""
    titulo = str(bruto.get("titulo") or "").strip() or tema.strip()
    descricao = str(bruto.get("descricao") or "").strip() or roteiro.strip()

    tags_brutas = bruto.get("tags") or []
    if not isinstance(tags_brutas, list):
        tags_brutas = []
    tags, vistos = [], set()
    for t in tags_brutas:
        t = str(t).strip()
        chave = t.lower()
        if t and chave not in vistos:
            vistos.add(chave)
            tags.append(t)
    if max_tags > 0:
        tags = tags[:max_tags]

    return {"titulo": titulo[:TITULO_MAX], "descricao": descricao, "tags": tags}


def gerar_metadados(sidecar: dict, config, assets_dir, ledger=None) -> dict:
    """Gera metadados otimizados a partir do sidecar (tema/roteiro).

    Returns:
        {"titulo", "descricao", "tags"} — sempre válido (degrada para o tema/roteiro
        crus se a chamada ou o parse falharem).
    """
    cfg_meta = mesclar_publicacao(config.get_all().get("publicacao"))["metadados"]
    tema = str(sidecar.get("tema") or "").strip()
    roteiro = str(sidecar.get("roteiro") or "").strip()

    system = _system_prompt(Path(assets_dir))
    user = _user_prompt(tema, roteiro, cfg_meta)

    try:
        resposta = _chamar_api(system, user, config)
        bruto = _parsear(resposta)
    except Exception as e:  # noqa: BLE001 (degrada para o tema cru)
        print(f"    [metadados] falha na geração ({e}) — usando tema/roteiro crus")
        bruto = {}

    if ledger is not None:
        ledger.registrar("metadados", "groq", CUSTO_GROQ_CHAMADA, modelo=config.get("groq.modelo"))

    return _normalizar(bruto, tema, roteiro, cfg_meta.get("max_tags", 15))


def obter_metadados(pasta, config, assets_dir, ledger=None, reaproveitar=True) -> dict:
    """Metadados com checkpoint: reaproveita `publicacao.json` se já tiver metadados
    válidos; senão lê o sidecar do run, gera e persiste. Nunca refaz o que existe."""
    from geracao import sidecar as sidecar_mod

    if reaproveitar:
        existente = registro.ler(pasta).get("metadados")
        if isinstance(existente, dict) and existente.get("titulo"):
            return existente

    sidecar = sidecar_mod.ler(pasta) or {}
    metadados = gerar_metadados(sidecar, config, assets_dir, ledger=ledger)
    registro.gravar(pasta, metadados=metadados)
    return metadados
