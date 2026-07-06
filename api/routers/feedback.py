from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from api import formulario
from api.schemas import FeedbackConfig
from api.templating import templates
from config.tipos import TipoVideo, carregar_tipo, listar_tipos
from feedback import aplicacao, atribuicao, guia
from feedback.armazenamento import aplicados_de, findings_de, propostas_de
from feedback.configuracao import FEEDBACK_PADRAO, UI_HINTS, mesclar_feedback

router = APIRouter(prefix="/tipos/{id}/feedback", tags=["feedback"])


def _formatar_erros(erro: ValidationError) -> str:
    partes = []
    for e in erro.errors():
        caminho = ".".join(str(p) for p in e["loc"])
        partes.append(f"{caminho}: {e['msg']}")
    return "; ".join(partes)


def _campos(atual: dict) -> list:
    return formulario.arvore(FEEDBACK_PADRAO, atual, UI_HINTS)


def contexto_feedback(tipo: TipoVideo) -> dict:
    """Contexto da aba Feedback (config schema-driven), usado na página de edição."""
    atual = mesclar_feedback(tipo.config.get_all().get("feedback"))
    return {"tipo": tipo, "campos_feedback": _campos(atual)}


def _render(tipo_id, request, atual, erro=None, sucesso=False, status_code=200):
    tipo = carregar_tipo(tipo_id)
    ctx = {
        "request": request,
        "tipo": tipo,
        "campos_feedback": _campos(atual),
        "erro": erro,
        "sucesso": sucesso,
    }
    return templates.TemplateResponse("_tipos_feedback_tab.html", ctx, status_code=status_code)


@router.post("", response_class=HTMLResponse)
async def salvar(id: str, request: Request):
    form = dict(await request.form())
    dados = formulario.reagrupar(form, FEEDBACK_PADRAO, UI_HINTS)

    try:
        validado = FeedbackConfig(**dados)
    except ValidationError as e:
        return _render(id, request, dados, erro=_formatar_erros(e), status_code=422)

    tipo = carregar_tipo(id)
    completo = tipo.config.get_all()
    completo["feedback"] = validado.model_dump()
    tipo.config.salvar(completo)

    return _render(id, request, validado.model_dump(), sucesso=True)


# --- Página standalone /feedback (o que o Feedback computou/aprendeu) --------

painel = APIRouter(prefix="/feedback", tags=["feedback"])

# Cada bloco de guia → o arquivo de prompt-base que ele complementa e onde é injetado.
_ARQUIVO_BASE = {
    "fit": "system_prompt_tendencia.txt",
    "roteiro": "system_prompt_script.txt",
    "visual": "system_prompt_prompt.txt",
    "metadados": "system_prompt_metadados.txt",
    "thumbnail": "system_prompt_thumbnail.txt",
}
_INJETADO_EM = {
    "fit": "Descoberta — critério de fit",
    "roteiro": "Geração — roteiro",
    "visual": "Geração — plano visual (imagem/cena)",
    "metadados": "Publicação — metadados",
    "thumbnail": "Publicação — thumbnail",
}


def _sparkline(curva, largura=120, altura=32) -> str:
    """Polyline points de uma curva de retenção (SVG self-contained, sem libs)."""
    if not curva:
        return ""
    ys = [p[1] for p in curva if len(p) >= 2]
    if not ys:
        return ""
    ymax = max(ys) or 1
    n = len(curva)
    pts = []
    for i, p in enumerate(curva):
        x, y = p[0], p[1]
        px = (x if 0 <= x <= 1 else i / max(1, n - 1)) * largura
        py = altura - (y / ymax) * altura
        pts.append(f"{px:.1f},{py:.1f}")
    return " ".join(pts)


def _blocos_guia(tipo) -> list[dict]:
    blocos = []
    for nome in guia.NOMES:
        dados = guia.bloco_de(tipo.assets_dir, nome).ler()
        linhas = [{"indice": i, **l} for i, l in enumerate(dados.get("linhas", []))]
        arq = tipo.assets_dir / _ARQUIVO_BASE[nome]
        base = arq.read_text(encoding="utf-8").strip() if arq.exists() else ""
        blocos.append({
            "nome": nome,
            "injetado_em": _INJETADO_EM[nome],
            "base": base,
            "linhas": linhas,
            "versao": dados.get("versao"),
        })
    return blocos


def _performance(tipo) -> list[dict]:
    itens = []
    for v in atribuicao.atribuir(tipo):
        itens.append({
            "video_id": v["video_id"],
            "tema": v["tema"],
            "marco": v["marco"],
            "metricas": v["metricas"],
            "inputs": v["inputs"],
            "curva_svg": _sparkline(v.get("curva")),
        })
    return itens


def _contexto_painel(tipo, request):
    return {
        "request": request,
        "tipos": listar_tipos(),
        "tipo": tipo,
        "propostas": propostas_de(tipo).pendentes() if tipo else [],
        "findings": findings_de(tipo).itens() if tipo else [],
        "performance": _performance(tipo) if tipo else [],
        "aplicados": aplicados_de(tipo).listar()[:20] if tipo else [],
        "blocos": _blocos_guia(tipo) if tipo else [],
    }


@painel.get("", response_class=HTMLResponse)
def pagina(request: Request, tipo: str | None = None):
    tipos = listar_tipos()
    alvo = None
    if tipos:
        alvo = carregar_tipo(tipo) if tipo else tipos[0]
    return templates.TemplateResponse("feedback_painel.html", _contexto_painel(alvo, request))


def _voltar(id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/feedback?tipo={id}", status_code=303)


@painel.post("/{id}/propostas/{proposta_id}/aprovar")
def aprovar_proposta(id: str, proposta_id: str):
    aplicacao.aprovar(carregar_tipo(id), proposta_id)
    return _voltar(id)


@painel.post("/{id}/propostas/{proposta_id}/rejeitar")
def rejeitar_proposta(id: str, proposta_id: str):
    aplicacao.rejeitar(carregar_tipo(id), proposta_id)
    return _voltar(id)


@painel.post("/{id}/guia/{bloco}/{indice}/{acao}")
def acao_linha(id: str, bloco: str, indice: int, acao: str):
    b = guia.bloco_de(carregar_tipo(id).assets_dir, bloco)
    if acao == "vetar":
        b.vetar(indice, True)
    elif acao == "desvetar":
        b.vetar(indice, False)
    elif acao == "fixar":
        b.fixar(indice, True)
    elif acao == "desfixar":
        b.fixar(indice, False)
    return _voltar(id)


@painel.post("/{id}/guia/{bloco}/limpar")
def limpar_bloco(id: str, bloco: str):
    guia.bloco_de(carregar_tipo(id).assets_dir, bloco).limpar()
    return _voltar(id)


@painel.post("/{id}/aplicados/{indice}/reverter")
def reverter_aplicado(id: str, indice: int):
    tipo = carregar_tipo(id)
    aplicados = aplicados_de(tipo).listar()
    if 0 <= indice < len(aplicados):
        aplicacao.reverter(tipo, aplicados[indice])
    return _voltar(id)
