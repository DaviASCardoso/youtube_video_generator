"""Checagem 1 — julgamento de disclosure de mídia sintética (objetiva).

A Publicação *seta* o flag de disclosure; a Conformidade *decide quando ele se aplica*.
Um vídeo com narração por IA e visuais por IA ou stock realista quase certamente precisa
do rótulo de conteúdo alterado/sintético do YouTube (obrigatório desde jan/2026). Esta
checagem é **objetiva**: ela é a dona da regra (dadas as características deste conteúdo, o
disclosure é exigido?) e o bloqueio de uma publicação que o omitiria é do orquestrador.

Determinística e sem LLM: lê os provedores de ativo do sidecar e a regra versionada
(`regras["disclosure"]`). Regra: exige disclosure se a narração veio de um provedor
sintético **e** o visual veio de um provedor sintético/realista.
"""


def _provedores_por_estagio(sidecar: dict) -> dict:
    """Reúne o conjunto de provedores usados por estágio, a partir do sidecar.

    Usa `provedores` (um provedor por estágio, last-write-wins) unido a `custos` (a lista
    completa por cena — a fonte fina, que preserva flux/pexels/placeholder misturados)."""
    resultado: dict[str, set] = {}
    for estagio, prov in (sidecar.get("provedores") or {}).items():
        if prov:
            resultado.setdefault(estagio, set()).add(prov)
    for item in sidecar.get("custos") or []:
        estagio, prov = item.get("estagio"), item.get("provedor")
        if estagio and prov:
            resultado.setdefault(estagio, set()).add(prov)
    return resultado


def avaliar_disclosure(sidecar: dict | None, regras: dict) -> dict:
    """Decide se o disclosure de mídia sintética é exigido para este vídeo.

    Args:
        sidecar: o `sidecar.json` do run (tema/roteiro/provedores/custos), ou None.
        regras: o conteúdo de regras vigente (`RegrasConformidade.atual()`).

    Returns:
        `{"requer": bool, "base": str}` — se o disclosure se aplica e a justificativa.
    """
    if not sidecar:
        return {"requer": False, "base": "sidecar ausente — impossível determinar"}

    cfg = regras.get("disclosure", {})
    narr_sint = set(cfg.get("narracao_sintetica", []))
    vis_sint = set(cfg.get("visual_sintetico_ou_realista", []))

    provs = _provedores_por_estagio(sidecar)
    narr_usados = provs.get("narracao", set()) & narr_sint
    vis_usados = provs.get("visuais", set()) & vis_sint

    if narr_usados and vis_usados:
        base = (
            f"narração sintética ({', '.join(sorted(narr_usados))}) "
            f"+ visual sintético/realista ({', '.join(sorted(vis_usados))})"
        )
        return {"requer": True, "base": base}

    faltou = []
    if not narr_usados:
        faltou.append("sem narração sintética")
    if not vis_usados:
        faltou.append("sem visual sintético/realista")
    return {"requer": False, "base": "; ".join(faltou)}
