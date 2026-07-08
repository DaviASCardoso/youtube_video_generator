"""Orquestrador da Conformidade — a consciência que veta e marca.

Duas entradas, uma para cada borda que o pilar cruza:

- `avaliar_tema(tipo, tema) -> Veredito` — brand safety na borda da **Descoberta**, antes
  de a produção gastar.
- `avaliar_publicacao(tipo, pasta_run, cfg_pub, execucao_id) -> Parecer` — disclosure +
  licenciamento (objetivas, bloqueiam) + autenticidade + factual (subjetivas, advisory) na
  borda da **Publicação**.

Ambas escrevem a trilha de auditoria e **são no-op quando `conformidade.ativo` é falso**
(o pilar nasce inerte ⇒ o comportamento default é idêntico ao de hoje). O rigor global
(`estrategia`) modula o modo efetivo de cada checagem; **objetivas bloqueiam, subjetivas
avisam** — um veto de máquina sobre julgamento faria desligarem o pilar.
"""

from pathlib import Path

from conformidade import autenticidade as aut
from conformidade import disclosure as disc
from conformidade import factual as fac
from conformidade import licenciamento as lic
from conformidade import marca as mrc
from conformidade.auditoria import auditoria_de
from conformidade.configuracao import mesclar_conformidade
from conformidade.parecer import BLOQUEADO, FLAG, LIBERADO, PASSOU, Checagem, Parecer, Veredito
from conformidade.regras import regras_de
from geracao import sidecar as sidecar_mod
from geracao.configuracao import mesclar_geracao

_ORDEM = ("advisory", "equilibrada", "bloquear")


def _cfg(tipo) -> dict:
    return mesclar_conformidade(tipo.config.get_all().get("conformidade"))


def modo_efetivo(nome_check: str, cfg: dict) -> str:
    """Modo efetivo de uma checagem, com o rigor global aplicado: `estrita` sobe um
    nível (mais rigor), `permissiva` desce um, `equilibrada` mantém."""
    modo = cfg["checagens"][nome_check].get("modo", "advisory")
    i = _ORDEM.index(modo) if modo in _ORDEM else 0
    estrategia = cfg.get("estrategia", "equilibrada")
    if estrategia == "estrita":
        i = min(i + 1, 2)
    elif estrategia == "permissiva":
        i = max(i - 1, 0)
    return _ORDEM[i]


def _forca_variacao(cfg_ger: dict) -> float:
    """Força média da variação da Geração (os knobs numéricos, exceto a semente)."""
    variacao = cfg_ger.get("variacao", {}) or {}
    knobs = [
        v for k, v in variacao.items()
        if k != "semente" and isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    return sum(knobs) / len(knobs) if knobs else 0.0


def _persona(tipo) -> str:
    caminho = Path(tipo.assets_dir) / "system_prompt_script.txt"
    if caminho.exists():
        return caminho.read_text(encoding="utf-8")
    return ""


def _roteiros_recentes(tipo, n: int, pasta_atual) -> list[str]:
    """Roteiros dos vídeos recentes do tipo (dos sidecars), excluindo o run atual."""
    from operacoes.execucoes import historico, pasta_da_execucao

    atual = Path(pasta_atual).resolve() if pasta_atual else None
    roteiros: list[str] = []
    for reg in historico.listar(tipo.id):
        pasta = pasta_da_execucao(reg)
        if pasta is None:
            continue
        if atual is not None and Path(pasta).resolve() == atual:
            continue
        dados = sidecar_mod.ler(pasta)
        if dados and dados.get("roteiro"):
            roteiros.append(dados["roteiro"])
        if len(roteiros) >= n:
            break
    return roteiros


# --- Borda da Descoberta: veto de tema --------------------------------------


def avaliar_tema(tipo, tema: str, auditar: bool = True) -> Veredito:
    """Brand safety de um tema na borda da Descoberta. Inerte (liberado) quando o pilar
    está desligado. Registra a auditoria (a menos que `auditar=False`, p/ o dry-run)."""
    cfg = _cfg(tipo)
    if not cfg.get("ativo"):
        return Veredito(LIBERADO)

    regras_store = regras_de(tipo)
    regras = regras_store.atual()
    modo = modo_efetivo("marca", cfg)
    veredito = mrc.avaliar_tema(tema, modo, regras, tipo.config)

    if auditar:
        auditoria_de(tipo).registrar({
            "etapa": "descoberta",
            "execucao_id": None,
            "tema": tema,
            "resultado": veredito.resultado,
            "checagens": [Checagem("marca", veredito.resultado, veredito.motivo).para_dict()],
            "regras_versao": regras_store.versao(),
        })
    return veredito


# --- Borda da Publicação: disclosure + licença + autenticidade + factual ----


def avaliar_publicacao(tipo, pasta_run, cfg_pub: dict, execucao_id: str | None = None) -> Parecer:
    """Avaliação de conformidade de uma publicação. Aplica o disclosure decidido em
    `cfg_pub` (quando exigido e já ligado), bloqueia nas objetivas e sinaliza nas
    subjetivas. Inerte (parecer vazio) quando o pilar está desligado. Registra a auditoria.
    """
    parecer = Parecer()
    cfg = _cfg(tipo)
    if not cfg.get("ativo"):
        return parecer

    regras_store = regras_de(tipo)
    regras = regras_store.atual()
    sidecar = sidecar_mod.ler(pasta_run)

    # 1. Disclosure (objetiva). Compliance decide; Publicação carrega o flag.
    d = disc.avaliar_disclosure(sidecar, regras)
    parecer.disclosure_requer = d["requer"]
    parecer.disclosure_base = d["base"]
    flag_ligado = bool(cfg_pub.get("visibilidade", {}).get("disclosure_sintetico"))
    if d["requer"] and not flag_ligado:
        # omissão de um disclosure exigido
        if modo_efetivo("disclosure", cfg) in ("bloquear", "equilibrada"):
            parecer.bloqueado = True
            parecer.motivos_bloqueio.append("disclosure exigido mas desativado")
            parecer.checagens.append(Checagem("disclosure", BLOQUEADO, d["base"]))
        else:
            parecer.flags.append("disclosure exigido mas desativado (advisory)")
            parecer.checagens.append(Checagem("disclosure", FLAG, d["base"]))
    else:
        parecer.checagens.append(Checagem("disclosure", PASSOU, d["base"]))

    # 2. Licenciamento (objetiva).
    l = lic.verificar_licenciamento(sidecar, regras)
    if not l["ok"]:
        detalhe = ", ".join(f"{a['estagio']}:{a['provedor']}" for a in l["sem_licenca"])
        if modo_efetivo("licenciamento", cfg) in ("bloquear", "equilibrada"):
            parecer.bloqueado = True
            parecer.motivos_bloqueio.append(f"ativo(s) sem licença: {detalhe}")
            parecer.checagens.append(Checagem("licenciamento", BLOQUEADO, detalhe))
        else:
            parecer.flags.append(f"ativo(s) sem licença: {detalhe} (advisory)")
            parecer.checagens.append(Checagem("licenciamento", FLAG, detalhe))
    else:
        parecer.checagens.append(Checagem("licenciamento", PASSOU))

    # 3. Autenticidade (subjetiva, advisory).
    cfg_aut = cfg["checagens"]["autenticidade"]
    a = aut.verificar_autenticidade(
        (sidecar or {}).get("roteiro", ""),
        _roteiros_recentes(tipo, int(cfg_aut.get("n_recentes", 5)), pasta_run),
        _forca_variacao(mesclar_geracao(tipo.config.get_all().get("geracao"))),
        _persona(tipo),
        cfg_aut,
        tipo.config,
    )
    if a["flag"]:
        detalhe = "; ".join(a["motivos"])
        if modo_efetivo("autenticidade", cfg) == "bloquear":
            parecer.bloqueado = True
            parecer.motivos_bloqueio.append(f"autenticidade: {detalhe}")
            parecer.checagens.append(Checagem("autenticidade", BLOQUEADO, detalhe))
        else:
            parecer.flags.append(f"autenticidade: {detalhe}")
            parecer.checagens.append(Checagem("autenticidade", FLAG, detalhe))
    else:
        parecer.checagens.append(Checagem("autenticidade", PASSOU))

    # 4. Factual (opcional, advisory) — só quando ligada.
    if cfg["checagens"]["factual"].get("ativo"):
        f = fac.verificar_factual((sidecar or {}).get("roteiro", ""), tipo.config)
        if f["flag"]:
            detalhe = "; ".join(f["alegacoes"])
            if modo_efetivo("factual", cfg) == "bloquear":
                parecer.bloqueado = True
                parecer.motivos_bloqueio.append(f"factual: {detalhe}")
                parecer.checagens.append(Checagem("factual", BLOQUEADO, detalhe))
            else:
                parecer.flags.append(f"factual: {detalhe}")
                parecer.checagens.append(Checagem("factual", FLAG, detalhe))
        else:
            parecer.checagens.append(Checagem("factual", PASSOU))

    resultado = BLOQUEADO if parecer.bloqueado else (FLAG if parecer.flags else LIBERADO)
    auditoria_de(tipo).registrar({
        "etapa": "publicacao",
        "execucao_id": execucao_id,
        "tema": (sidecar or {}).get("tema", ""),
        "resultado": resultado,
        "checagens": [c.para_dict() for c in parecer.checagens],
        "disclosure": {"requer": parecer.disclosure_requer, "base": parecer.disclosure_base},
        "regras_versao": regras_store.versao(),
    })
    return parecer
