"""Sinais de saúde/custo/cota — leitura pura do que Operações e os pilares gravam.

O Controle usa isto para o dashboard "está tudo OK e quanto custa" e o job periódico
usa para alertar (disco baixo, credencial expirando). Aqui **só se lê e formata** o que
já existe; nada é computado ou forçado (isso é de Operações/pilares). Imports pesados
(Google, scheduler) são tardios, dentro das funções, para não criar ciclo e para os
testes mockarem com facilidade.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config import caminhos

# Limiares default (só para marcar "atenção"; não forçam nada).
DISCO_BAIXO_PCT = 10.0

# Batida do scheduler: o job de saúde a grava; o dashboard a lê para detectar um
# scheduler travado (running=True, mas sem disparar jobs). Estagnado após ~13h — pouco
# mais de duas passadas do job de saúde (6h), então uma batida perdida não alarma.
_HEARTBEAT_PATH = caminhos.raiz("execucoes") / "heartbeat.json"
HEARTBEAT_LIMITE_SEG = 13 * 3600


def scheduler_rodando() -> bool:
    """True se o BackgroundScheduler está de pé (import tardio evita ciclo)."""
    try:
        from operacoes import scheduler as sched_mod

        return bool(sched_mod.scheduler.running)
    except Exception:
        return False


def registrar_heartbeat(agora: datetime | None = None, caminho: Path | None = None) -> None:
    """Grava a batida do scheduler (chamada pelo job periódico de saúde)."""
    agora = agora or datetime.now(timezone.utc)
    caminho = caminho or _HEARTBEAT_PATH
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps({"quando": agora.isoformat()}), encoding="utf-8")


def heartbeat(agora: datetime | None = None, caminho: Path | None = None) -> dict:
    """Última batida do scheduler + se está estagnada (job de saúde não roda há muito).

    Devolve `{quando, idade_seg, estagnado}`. Sem batida ainda (start recente), quando é
    None e estagnado é False — não alarma antes da primeira passada."""
    agora = agora or datetime.now(timezone.utc)
    caminho = caminho or _HEARTBEAT_PATH
    try:
        quando = datetime.fromisoformat(json.loads(caminho.read_text(encoding="utf-8"))["quando"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return {"quando": None, "idade_seg": None, "estagnado": False}
    idade = (agora - quando).total_seconds()
    return {"quando": quando.isoformat(), "idade_seg": round(idade, 1), "estagnado": idade > HEARTBEAT_LIMITE_SEG}


def _pasta_existente(caminho: Path) -> Path:
    """Sobe até um ancestral que exista (a pasta de saída pode ainda não ter sido criada)."""
    caminho = Path(caminho)
    for p in [caminho, *caminho.parents]:
        if p.exists():
            return p
    return Path(".")


def disco(pasta: str | None = None, limite_pct: float = DISCO_BAIXO_PCT) -> dict:
    """Uso de disco da pasta de saída. Marca `baixo` quando o livre cai do limite."""
    if pasta is None:
        pasta = str(caminhos.raiz("saida"))
    alvo = _pasta_existente(Path(pasta))
    uso = shutil.disk_usage(alvo)
    livre_pct = (uso.free / uso.total * 100) if uso.total else 0.0
    gb = 1024 ** 3
    return {
        "caminho": str(alvo),
        "total_gb": round(uso.total / gb, 1),
        "livre_gb": round(uso.free / gb, 1),
        "livre_pct": round(livre_pct, 1),
        "baixo": livre_pct < limite_pct,
    }


def caminhos_saude() -> list[dict]:
    """Estado de cada raiz de armazenamento configurada (existe? gravável?).

    Uma raiz que aponta para um mount (NAS) ausente ou somente-leitura aparece como
    `ok: False` — o dashboard mostra o sinal antes de um run falhar gravando nela."""
    return caminhos.verificar_raizes()


def _tipos(tipos=None):
    if tipos is not None:
        return tipos
    from config.tipos import listar_tipos

    return listar_tipos()


def _youtube_ativo(tipo) -> bool:
    from publicacao.configuracao import mesclar_publicacao

    cfg = mesclar_publicacao(tipo.config.get_all().get("publicacao"))
    return bool(cfg["destinos"].get("youtube", {}).get("ativo"))


def credenciais(tipos=None) -> list[dict]:
    """Status da credencial de cada tipo que publica no YouTube (o único destino real
    hoje). Só checa quem tem o destino ativo; degrada por tipo em caso de erro."""
    from publicacao import youtube

    resultado = []
    for tipo in _tipos(tipos):
        if not _youtube_ativo(tipo):
            continue
        try:
            cred = youtube.checar_credencial(tipo)
        except Exception as e:  # noqa: BLE001
            cred = {"status": "erro", "detalhe": str(e)}
        resultado.append(
            {"tipo_id": tipo.id, "tipo_nome": tipo.nome, "destino": "youtube", **cred}
        )
    return resultado


def gasto_hoje() -> float:
    """Gasto acumulado (USD) hoje, global — o GastoDiario é por dia, não por tipo."""
    from geracao.custo import gasto_diario

    return round(gasto_diario.gasto_hoje(), 6)


def orcamento_do_tipo(tipo) -> float:
    """Teto de gasto diário (USD) configurado para o tipo (0 = sem limite)."""
    from geracao.configuracao import mesclar_geracao

    cfg = mesclar_geracao(tipo.config.get_all().get("geracao"))
    return float(cfg["orcamento"]["por_dia_usd"])


def cota_do_tipo(tipo) -> dict:
    """Uploads feitos hoje pela credencial do tipo vs. o cap configurado."""
    from publicacao.configuracao import mesclar_publicacao
    from publicacao.quota import quota_diaria

    cfg = mesclar_publicacao(tipo.config.get_all().get("publicacao"))
    cap = cfg["quota"]["cap_diario"]
    credencial = f"youtube:{tipo.id}"
    return {
        "tipo_id": tipo.id,
        "tipo_nome": tipo.nome,
        "uploads": quota_diaria.uploads_hoje(credencial),
        "cap": cap,
    }


def ultimo_publish(tipo) -> dict | None:
    """Última publicação bem-sucedida do tipo (dos records do histórico), ou None."""
    from operacoes.execucoes import historico

    for reg in historico.listar(tipo.id):  # mais recentes primeiro
        for item in reg.get("publicacao", []):
            if item.get("status") in ("publicado", "agendado") and item.get("url"):
                return {
                    "url": item["url"],
                    "destino": item.get("destino"),
                    "quando": reg.get("finalizado_em") or reg.get("iniciado_em"),
                }
    return None


def coletar(tipos=None) -> dict:
    """Reúne todos os sinais para o dashboard, numa passada só."""
    from operacoes import notificacoes

    tipos = _tipos(tipos)
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "scheduler_rodando": scheduler_rodando(),
        "heartbeat": heartbeat(),
        "disco": disco(),
        "caminhos": caminhos_saude(),
        "credenciais": credenciais(tipos),
        "gasto_hoje": gasto_hoje(),
        "orcamentos": [
            {"tipo_id": t.id, "tipo_nome": t.nome, "teto_dia": orcamento_do_tipo(t)} for t in tipos
        ],
        "cotas": [cota_do_tipo(t) for t in tipos],
        "publicacoes": [{"tipo_id": t.id, "tipo_nome": t.nome, "ultimo": ultimo_publish(t)} for t in tipos],
        "ntfy_configurado": notificacoes.configurado(),
    }


def verificar_e_alertar(tipos=None) -> list[str]:
    """Roda os checks que valem um push (disco baixo, credencial expirando/expirada/
    ausente) e emite. Devolve as categorias emitidas (para teste/observabilidade).

    O `scheduler_parado` NÃO é checado aqui de propósito: se este job rodou, o
    scheduler está de pé — esse sinal fica só no dashboard (lido a cada request)."""
    from operacoes import notificacoes

    emitidas = []
    d = disco()
    if d["baixo"]:
        notificacoes.emitir(
            "disco_baixo",
            "Espaço em disco baixo",
            f"{d['caminho']}: {d['livre_gb']} GB livres ({d['livre_pct']}%).",
        )
        emitidas.append("disco_baixo")

    for c in caminhos_saude():
        if not c["ok"]:
            notificacoes.emitir(
                "disco_baixo",
                f"Caminho de armazenamento indisponível — {c['nome']}",
                f"{c['caminho']}: ausente ou não gravável (verifique o mount/permissões).",
            )
            emitidas.append("caminho_indisponivel")

    for c in credenciais(tipos):
        if c["status"] in ("expirando", "expirado", "ausente", "erro"):
            notificacoes.emitir(
                "credencial",
                f"Credencial {c['status']} — {c['tipo_nome']}",
                f"Destino {c['destino']}: {c.get('detalhe', '')}",
            )
            emitidas.append("credencial")
    return emitidas
