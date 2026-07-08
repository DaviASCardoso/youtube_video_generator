from pathlib import Path
import queue as queue_mod

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from api.auth import auth_ativo
from api.templating import templates
from operacoes import saude
from operacoes import scheduler as scheduler_mod
from config.tipos import carregar_tipo, listar_tipos
from config import caminhos
from operacoes.execucoes import historico, transmissor, ExecucaoEmAndamentoError

router = APIRouter(prefix="/execucoes", tags=["execucoes"])


def _em_andamento() -> list[dict]:
    return [e for e in historico.listar() if e["status"] == "executando"]


def _contexto_index(erro: str | None = None, msg: str | None = None) -> dict:
    return {
        "tipos": listar_tipos(),
        "em_andamento": _em_andamento(),
        "recentes": historico.listar()[:10],
        "saude": saude.coletar(),
        "auth_ativo": auth_ativo(),
        "erro": erro,
        "msg": msg,
    }


@router.get("", response_class=HTMLResponse)
def pagina_inicio(request: Request):
    return templates.TemplateResponse(
        "execucoes_index.html", {"request": request, **_contexto_index()}
    )


@router.post("/descobrir", response_class=HTMLResponse)
def descobrir(request: Request, tipo_id: str = Form(...)):
    """Descoberta-only: decide o tema agora (sem gerar), no executor dos jobs."""
    tipo = carregar_tipo(tipo_id)
    scheduler_mod.descobrir_agora(tipo)
    return templates.TemplateResponse(
        "execucoes_index.html",
        {"request": request, **_contexto_index(msg=f"Descoberta disparada para {tipo.nome}. Veja a aba Descoberta do tipo.")},
    )


@router.post("/{execucao_id}/cancelar")
def cancelar(execucao_id: str):
    """Cancelamento cooperativo (efetiva na próxima fronteira de estágio)."""
    scheduler_mod.cancelar(execucao_id)
    return RedirectResponse(url=f"/execucoes/{execucao_id}", status_code=303)


@router.post("/{execucao_id}/reexecutar")
def reexecutar(request: Request, execucao_id: str):
    """Re-enfileira um run parado (dead-letter/adiado/erro) reaproveitando a pasta —
    o checkpoint retoma de onde parou. Redireciona para o novo run."""
    try:
        nova = scheduler_mod.reexecutar_agora(execucao_id)
    except (ValueError, KeyError, ExecucaoEmAndamentoError) as e:
        return templates.TemplateResponse(
            "execucoes_index.html",
            {"request": request, **_contexto_index(erro=str(e))},
            status_code=409,
        )
    return RedirectResponse(url=f"/execucoes/{nova['id']}", status_code=303)


@router.post("", response_class=HTMLResponse)
def disparar(request: Request, tipo_id: str = Form(...), tema: str = Form("")):
    tipo = carregar_tipo(tipo_id)
    tema_informado = tema.strip() or None

    try:
        execucao = scheduler_mod.disparar_agora(tipo, tema_informado)
    except (ExecucaoEmAndamentoError, ValueError) as e:
        return templates.TemplateResponse(
            "execucoes_index.html",
            {"request": request, **_contexto_index(erro=str(e))},
            status_code=409,
        )

    return RedirectResponse(url=f"/execucoes/{execucao['id']}", status_code=303)


def _url_video(execucao: dict) -> str | None:
    # historico.concluir() guarda o caminho do próprio video_final.mp4 (não a pasta).
    if execucao["status"] != "concluido" or not execucao.get("output_path"):
        return None

    pasta_base = caminhos.raiz("saida").resolve()
    caminho_video = Path(execucao["output_path"]).resolve()
    try:
        relativo = caminho_video.relative_to(pasta_base)
    except ValueError:
        return None
    return f"/saida/{relativo.as_posix()}"


def _auditoria_conformidade(execucao: dict) -> list[dict]:
    """Registros da trilha de auditoria da Conformidade ligados a este run (mais
    recentes primeiro). Vazio quando o pilar nunca rodou para o tipo."""
    from conformidade.auditoria import auditoria_de

    try:
        tipo = carregar_tipo(execucao["tipo_id"])
    except Exception:  # noqa: BLE001 (tipo renomeado/excluído)
        return []
    return auditoria_de(tipo).de_execucao(execucao["id"])


@router.get("/historico", response_class=HTMLResponse)
def pagina_historico(request: Request, tipo_id: str | None = None):
    # rota estática registrada antes de "/{execucao_id}" para não ser capturada por ela.
    return templates.TemplateResponse(
        "execucoes_historico.html",
        {
            "request": request,
            "registros": historico.listar(tipo_id),
            "tipos": listar_tipos(),
            "tipo_id": tipo_id,
        },
    )


@router.get("/{execucao_id}", response_class=HTMLResponse)
def pagina_detalhe(execucao_id: str, request: Request):
    try:
        execucao = historico.obter(execucao_id)
    except KeyError:
        return HTMLResponse("Execução não encontrada.", status_code=404)

    log_inicial = ""
    if execucao.get("log_path") and Path(execucao["log_path"]).exists():
        log_inicial = Path(execucao["log_path"]).read_text(encoding="utf-8")

    return templates.TemplateResponse(
        "execucoes_detalhe.html",
        {
            "request": request,
            "execucao": execucao,
            "log_inicial": log_inicial,
            "url_video": _url_video(execucao),
            "auditoria_conformidade": _auditoria_conformidade(execucao),
        },
    )


@router.get("/{execucao_id}/stream")
def stream_log(execucao_id: str):
    try:
        historico.obter(execucao_id)
    except KeyError:
        return HTMLResponse("Execução não encontrada.", status_code=404)

    fila = transmissor.assinar(execucao_id)
    linhas_replay = transmissor.linhas_ate_agora(execucao_id)

    def gerar():
        try:
            for linha in linhas_replay:
                yield f"data: {linha}\n\n"
            while True:
                try:
                    linha = fila.get(timeout=5)
                except queue_mod.Empty:
                    # sentinela pode ter sido perdida (ex: processo reiniciado);
                    # confere o status no histórico para não bloquear pra sempre.
                    if historico.obter(execucao_id)["status"] != "executando":
                        break
                    continue
                if linha is None:
                    break
                yield f"data: {linha}\n\n"
        finally:
            transmissor.desassinar(execucao_id, fila)
        yield "event: fim\ndata: \n\n"

    return StreamingResponse(gerar(), media_type="text/event-stream")
