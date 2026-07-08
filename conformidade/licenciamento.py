"""Checagem 3 — licenciamento dos ativos (objetiva).

Antes de um vídeo ir ao ar, todo ativo que ele usou precisa ter uma **origem
licenciada** — música, imagens de banco (Pexels é licenciado), voz, e qualquer outro
ativo. Para o Sem Guru o risco é baixo hoje (visuais por IA ou stock licenciado), mas a
regra precisa existir para o dia em que música ou um ativo de origem duvidosa entrar — e
é essencial se o esqueleto for reusado para o canal de histórias (gameplay em loop é
protegido).

Objetiva: cada provedor de ativo usado (lido do `custos` do sidecar — a fonte fina, que
preserva a mistura por cena) precisa estar no mapa `regras["licencas"]` com `True`. Um
provedor ausente do mapa ou marcado `False` **bloqueia**.
"""


def _ativos_do_sidecar(sidecar: dict) -> list[dict]:
    """Lista dos ativos usados: `[{estagio, provedor}]`, sem repetição por (estágio,
    provedor). Usa `custos` (por cena) unido a `provedores` (um por estágio)."""
    vistos: set = set()
    ativos: list[dict] = []
    fontes = list(sidecar.get("custos") or [])
    fontes += [{"estagio": e, "provedor": p} for e, p in (sidecar.get("provedores") or {}).items()]
    for item in fontes:
        estagio, prov = item.get("estagio"), item.get("provedor")
        if not prov:
            continue
        chave = (estagio, prov)
        if chave in vistos:
            continue
        vistos.add(chave)
        ativos.append({"estagio": estagio, "provedor": prov})
    return ativos


def verificar_licenciamento(sidecar: dict | None, regras: dict) -> dict:
    """Verifica que cada ativo usado tem origem licenciada.

    Args:
        sidecar: o `sidecar.json` do run (usa `custos`/`provedores`), ou None.
        regras: o conteúdo de regras vigente (usa `regras["licencas"]`).

    Returns:
        `{"ok": bool, "sem_licenca": [{"estagio", "provedor"}]}`.
    """
    if not sidecar:
        return {"ok": True, "sem_licenca": []}

    licencas = regras.get("licencas", {})
    sem_licenca = [
        ativo for ativo in _ativos_do_sidecar(sidecar)
        if licencas.get(ativo["provedor"]) is not True
    ]
    return {"ok": not sem_licenca, "sem_licenca": sem_licenca}
