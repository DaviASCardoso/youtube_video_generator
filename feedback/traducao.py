"""Tradução de findings textuais em guia de prompt (Groq reconcilia e reescreve).

Para um finding textual (hook, título), o Groq — já usado no projeto — recebe as
diretrizes atuais do bloco + o novo achado e **reescreve o bloco inteiro**: resolve
contradições, mantém só as `top_k` mais úteis/confiáveis e fica sob o teto de tamanho.
Não anexa linhas soltas. O LLM só **traduz**; o roteamento é determinístico (`roteador`).

Degrada em vez de quebrar: qualquer falha (sem chave, parse ruim) devolve `None` e o
bloco atual (último bom) fica de pé. Se a reescrita for idêntica ao bloco atual, também
devolve `None` — nada a propor (traduz só quando muda algo).
"""

from feedback import guia
from feedback.roteador import ROTAS

_SYSTEM = (
    "Você mantém um bloco curto de DIRETRIZES APRENDIDAS que será injetado no prompt "
    "de um canal de vídeos, separado do prompt-base escrito por humano. Recebe as "
    "diretrizes atuais e um novo achado de performance (o que funcionou melhor). "
    "Reescreva o bloco inteiro: resolva contradições, una redundâncias, mantenha só as "
    "mais úteis e de maior confiança, cada uma curta e acionável, em português do "
    "Brasil. NÃO invente além do achado e das diretrizes atuais. Devolva um ARRAY JSON "
    "de strings (uma diretriz por item), sem comentários."
)


def _user_prompt(atuais: list[str], finding: dict, top_k: int) -> str:
    linhas = "\n".join(f"- {t}" for t in atuais) or "(nenhuma ainda)"
    exemplos = "\n".join(f"- {e}" for e in finding.get("exemplos", [])) or "(sem exemplos)"
    piores = "\n".join(f"- {e}" for e in finding.get("piores", []))
    partes = [
        f"DIRETRIZES ATUAIS:\n{linhas}",
        f"\nNOVO ACHADO — dimensão '{finding.get('dimensao')}', "
        f"efeito {finding.get('efeito')} em {finding.get('metrica')} "
        f"(n={finding.get('n')}, confiança={finding.get('confianca')}).",
        f"\nEXEMPLOS QUE PERFORMARAM MELHOR:\n{exemplos}",
    ]
    if piores:
        partes.append(f"\nEXEMPLOS QUE PERFORMARAM PIOR (evite o padrão):\n{piores}")
    partes.append(f"\nDevolva no máximo {top_k} diretrizes, da mais para a menos importante.")
    return "\n".join(partes)


def _sob_cap(linhas: list[str], cap: int) -> list[str]:
    if cap <= 0:
        return linhas
    out, total = [], 0
    for l in linhas:
        total += len(l) + 3  # "- " + \n
        if total > cap and out:
            break
        out.append(l)
    return out


def traduzir(tipo, bloco_nome: str, finding: dict, cfg: dict) -> list[str] | None:
    """Reescreve as linhas do bloco a partir do finding. `None` se falhou ou não mudou."""
    from geracao.generate_script import _chamar_api, _parsear_prompts

    bloco = guia.bloco_de(tipo.assets_dir, bloco_nome)
    atuais = [l["texto"] for l in bloco.linhas_ativas()]
    guia_cfg = cfg.get("guia", {})
    top_k = int(guia_cfg.get("top_k", 8))
    cap = int(guia_cfg.get("tamanho_max_chars", 800))

    user = _user_prompt(atuais, finding, top_k)
    try:
        resposta = _chamar_api(_SYSTEM, user, tipo.config)
        brutas = _parsear_prompts(resposta)
    except Exception:  # noqa: BLE001 — deixa o último bloco bom de pé
        return None
    if not isinstance(brutas, list):
        return None

    linhas = [str(l).strip() for l in brutas if str(l).strip()][:top_k]
    linhas = _sob_cap(linhas, cap)
    if not linhas or linhas == atuais:
        return None
    return linhas


def propor_guia(tipo, finding: dict, cfg: dict) -> dict | None:
    """Proposta de atualização de bloco de guia para um finding textual, ou None."""
    rota = ROTAS.get(finding["dimensao"])
    if not rota or rota["classe"] != "guia":
        return None

    linhas = traduzir(tipo, rota["bloco"], finding, cfg)
    if linhas is None:
        return None

    atuais = [l["texto"] for l in guia.bloco_de(tipo.assets_dir, rota["bloco"]).linhas_ativas()]
    return {
        "tipo": "guia",
        "pilar": rota["pilar"],
        "alvo": f"guia:{rota['bloco']}",
        "bloco": rota["bloco"],
        "dimensao": finding["dimensao"],
        "linhas_atuais": atuais,
        "linhas_novas": linhas,
        "confianca": finding.get("confianca"),
        "descricao": f"Atualizar a guia de '{rota['bloco']}' a partir de {finding['dimensao']}.",
        "chave": f"guia:{rota['bloco']}",
        "finding": {
            "dimensao": finding["dimensao"], "efeito": finding.get("efeito"),
            "n": finding.get("n"), "confianca": finding.get("confianca"),
            "metrica": finding.get("metrica"),
        },
    }
