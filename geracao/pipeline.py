"""Pipeline de geração em estágios, checkpointado e dirigido por config.

`gerar_video` executa estágios explícitos — roteiro → plano visual → visuais →
narração → montagem — e cada um:

- **reaproveita** o artefato se ele já existe e valida (checkpoint/resumabilidade);
- passa por um **gate** de qualidade antes de o próximo estágio gastar;
- roda atrás de um **contrato de provedor** (selecionado por `geracao.*.provedor`);
- **registra o custo** num `Ledger` e respeita o **orçamento** (degradar/parar);
- **degrada em vez de quebrar** (retry+backoff, provedor de fallback, placeholder).

Ao final, escreve o `video_final.mp4` **e** um `sidecar.json` (tema/roteiro/duração/
provedores/custos) que a Publicação consome. Sob a config default, os provedores
chamam exatamente as funções de sempre, na mesma ordem — a saída fica equivalente à
de hoje (a variação atua só no texto do prompt).
"""

import io
import re
import time
from pathlib import Path

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image

from config.sistema import sistema
from config.tipos import TipoVideo
from geracao import gates, generate_scene, iconify, legendas, sidecar
from geracao.checkpoint import deve_reaproveitar
from geracao.compositor import (
    EMOCAO_PADRAO,
    _fundo_placeholder,
    sobrepor_icone,
    sobrepor_personagem,
    validar_personagens,
)
from geracao.configuracao import mesclar_geracao, resolver_fundo, resolver_personagem
from geracao.custo import (
    CUSTO_FLUX_IMAGEM,
    CUSTO_PEXELS,
    Ledger,
    checar_orcamento,
    gasto_diario,
)
from geracao.generate_image import ASPECT_RATIOS
from geracao.generate_voice import gerar_narracao  # noqa: F401 (mantido p/ compat de testes)
from geracao.provedores import base as provedores
from geracao.variacao import Variacao
from operacoes import resiliencia

# Backoff entre tentativas (segundos, base do crescimento exponencial). Os provedores
# mockados dos testes acertam na 1ª tentativa, então o sleep nunca é exercido lá.
# Mantidos por compat; o retry/backoff de fato agora vem do motor (resiliencia.executar).
ESPERA_BACKOFF = 2.0
TENTATIVAS = 3

# Provedor externo por trás de cada papel — chave do circuit breaker (agrega falhas
# por serviço real, não por nome de config). Visuais mapeia por modo (flux/pexels).
_PROVEDOR_CIRCUITO = {"roteiro": "groq", "narracao": "google"}

_CUSTO_PREVISTO_VISUAL = {"flux": CUSTO_FLUX_IMAGEM, "pexels": CUSTO_PEXELS, "placeholder": 0.0}


class OrcamentoExcedido(Exception):
    """Um estágio pago estouraria o orçamento configurado (ação 'parar')."""


class ExecucaoCancelada(Exception):
    """Cancelamento cooperativo pedido pelo painel, checado entre estágios."""


def _checar_cancelamento(cancelado) -> None:
    """Aborta (entre estágios) se o painel pediu cancelamento. Best-effort: efetiva
    na próxima fronteira de estágio — não há como matar uma etapa longa em curso."""
    if cancelado is not None and cancelado():
        raise ExecucaoCancelada("execução cancelada pelo usuário")


def _modo_imagens(tipo: TipoVideo) -> str:
    """Modo de geração das cenas: "ia" (Together) ou "personagem" (Pexels + PNG).

    Tipos antigos, sem a seção imagens no config.json, caem no modo "ia" —
    o comportamento original.
    """
    try:
        return tipo.config.get("imagens.modo")
    except KeyError:
        return "ia"


def _tentar(fn, tentativas: int = TENTATIVAS):
    """Executa `fn` com retry + backoff exponencial; re-levanta o último erro."""
    ultimo = None
    for i in range(tentativas):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 (resiliência deliberada por estágio)
            ultimo = e
            if i < tentativas - 1 and ESPERA_BACKOFF:
                time.sleep(ESPERA_BACKOFF * (2**i))
    raise ultimo


# --- estágio: roteiro -----------------------------------------------------


def _ler_roteiro(caminho: Path) -> list[tuple[int, str]]:
    linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [(i + 1, l) for i, l in enumerate(linhas)]


def _escrever_roteiro(caminho: Path, frases: list) -> None:
    caminho.write_text("\n".join(str(f[1]) for f in frases), encoding="utf-8")


def _estagio_roteiro(tema, tipo, base, cfg_ger, politica, rel, var, led, reaproveitar):
    caminho = base / "roteiro.txt"
    if deve_reaproveitar(caminho, reaproveitar):
        print(f"Reaproveitando roteiro de {caminho}")
        frases = _ler_roteiro(caminho)
    else:
        print("Gerando roteiro...")
        prov = provedores.obter(provedores.PAPEL_ROTEIRO, cfg_ger["roteiro"]["provedor"])
        frases = resiliencia.executar(
            lambda: prov.gerar(tema, tipo.config, tipo.assets_dir, variacao=var, ledger=led),
            estagio="roteiro",
            provedor=_PROVEDOR_CIRCUITO["roteiro"],
            politica=politica,
            contexto={"tema": tema, "tipo": tipo.id},
            relatorio=rel,
        )
        _escrever_roteiro(caminho, frases)
        print(f"Roteiro salvo em: {caminho}")
    gates.validar_roteiro(frases, cfg_ger)
    return frases


# --- estágio: plano visual ------------------------------------------------


def _escrever_prompts(caminho: Path, dados: list) -> None:
    caminho.write_text("\n".join(str(p) for p in dados), encoding="utf-8")


def _ler_prompts(caminho: Path) -> list[str]:
    return [l for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]


# O conceito de ícone (camada de ícones) fica num sufixo opcional `<icone>`, para o
# checkpoint sobreviver a um resume sem perder o ícone e sem quebrar cenas.txt antigos.
_RE_CENA = re.compile(r"^\[(?P<emocao>.*?)\]\s*\((?P<busca>.*?)\)(?:\s*<(?P<icone>.*?)>)?$")


def _escrever_cenas(caminho: Path, dados: list) -> None:
    linhas = []
    for d in dados:
        linha = f"[{d['emocao']}] ({d['busca']})"
        if d.get("icone"):
            linha += f" <{d['icone']}>"
        linhas.append(linha)
    caminho.write_text("\n".join(linhas), encoding="utf-8")


def _ler_cenas(caminho: Path) -> list[dict]:
    dados, usados = [], {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        m = _RE_CENA.match(linha.strip())
        emocao = m.group("emocao") if m else "neutro"
        busca = (m.group("busca") if m else "abstract background") or "abstract background"
        icone = (m.group("icone") or None) if m else None
        i_fundo = usados.get(busca, 0)
        usados[busca] = i_fundo + 1
        dados.append({"emocao": emocao, "busca": busca, "i_fundo": i_fundo, "icone": icone})
    return dados


def _estagio_plano_visual(frases, tipo, base, cfg_ger, politica, rel, nome_visual, var, led, reaproveitar):
    prov = provedores.obter(provedores.PAPEL_VISUAIS, nome_visual)
    if nome_visual == "pexels":
        caminho = base / "cenas.txt"
        ler, escrever = _ler_cenas, _escrever_cenas
    else:
        caminho = base / "prompts.txt"
        ler, escrever = _ler_prompts, _escrever_prompts

    if deve_reaproveitar(caminho, reaproveitar):
        print(f"Reaproveitando plano visual de {caminho}")
        dados = ler(caminho)
    else:
        print("Planejando visuais...")
        # O plano visual (emoção/prompt por frase) roda no Groq — mesmo circuito do roteiro.
        dados = resiliencia.executar(
            lambda: prov.planejar(frases, tipo.config, tipo.assets_dir, variacao=var, ledger=led),
            estagio="plano_visual",
            provedor="groq",
            politica=politica,
            contexto={"tipo": tipo.id},
            relatorio=rel,
        )
        escrever(caminho, dados)
        print(f"Plano visual salvo em: {caminho}")

    gates.validar_plano_visual(frases, dados)
    return prov, dados


# --- estágio: plano da camada de personagem (emoção por cena) -------------


def _estagio_plano_personagem(frases, dados, tipo, base, politica, rel, nome_visual, personagem_ativo, led, reaproveitar):
    """Planeja a emoção do personagem por cena, como camada independente do fundo.

    Fundo Pexels já decide a emoção junto da busca (mesma chamada) — nada a fazer.
    Fundo por IA: a emoção é planejada aqui, à parte (checkpoint próprio `emocoes.txt`),
    e mesclada no `dado` de cada cena (`prompt` -> `{"prompt", "emocao"}`), para que
    um fundo por IA também tenha um personagem que muda de expressão."""
    if not personagem_ativo or nome_visual == "pexels":
        return dados  # sem personagem, ou o fundo Pexels já planejou a emoção

    caminho = base / "emocoes.txt"
    emocoes = None
    if deve_reaproveitar(caminho, reaproveitar):
        lidas = [l.strip() for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(lidas) == len(frases):  # só reaproveita se casa 1:1 com as cenas
            print(f"Reaproveitando emoções do personagem de {caminho}")
            emocoes = lidas
    if emocoes is None:
        print("Planejando emoções do personagem...")
        emocoes = resiliencia.executar(
            lambda: generate_scene.planejar_emocoes(frases, tipo.config, tipo.assets_dir, ledger=led),
            estagio="plano_personagem",
            provedor="groq",
            politica=politica,
            contexto={"tipo": tipo.id},
            relatorio=rel,
        )
        caminho.write_text("\n".join(emocoes), encoding="utf-8")
        print(f"Emoções do personagem salvas em: {caminho}")

    return [{"prompt": p, "emocao": e} for p, e in zip(dados, emocoes)]


# --- estágio: plano da camada de ícones (conceito por cena) ---------------


def _mesclar_icone(dado, conceito: str | None):
    """Anexa o conceito de ícone ao dado da cena, seja ele o prompt puro (fundo por IA
    sem personagem) ou já um dict (fundo por IA com personagem)."""
    if isinstance(dado, dict):
        novo = dict(dado)
        novo["icone"] = conceito
        return novo
    return {"prompt": dado, "icone": conceito}


def _ler_icones(caminho: Path) -> list[str | None]:
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    return [(l.strip() or None) if l.strip().lower() != "null" else None for l in linhas]


def _escrever_icones(caminho: Path, conceitos: list) -> None:
    caminho.write_text("\n".join(c or "null" for c in conceitos), encoding="utf-8")


def _estagio_plano_icone(frases, dados, tipo, base, politica, rel, nome_visual, icone_ativo, led, reaproveitar):
    """Planeja o conceito de ícone por cena, como camada independente do fundo e do
    personagem.

    Fundo Pexels já decide o ícone junto da emoção/busca (mesma chamada) — nada a fazer.
    Fundo por IA: o conceito é planejado aqui, à parte (checkpoint próprio `icones.txt`),
    e mesclado no `dado` de cada cena, para que um fundo por IA também mostre um ícone."""
    if not icone_ativo or nome_visual == "pexels":
        return dados  # desligado, ou o fundo Pexels já planejou o ícone

    caminho = base / "icones.txt"
    conceitos = None
    if deve_reaproveitar(caminho, reaproveitar):
        lidas = _ler_icones(caminho)
        if len(lidas) == len(frases):  # só reaproveita se casa 1:1 com as cenas
            print(f"Reaproveitando conceitos de ícone de {caminho}")
            conceitos = lidas
    if conceitos is None:
        print("Planejando ícones das cenas...")
        conceitos = resiliencia.executar(
            lambda: generate_scene.planejar_icones(frases, tipo.config, tipo.assets_dir, ledger=led),
            estagio="plano_icone",
            provedor="groq",
            politica=politica,
            contexto={"tipo": tipo.id},
            relatorio=rel,
        )
        _escrever_icones(caminho, conceitos)
        print(f"Conceitos de ícone salvos em: {caminho}")

    return [_mesclar_icone(d, c) for d, c in zip(dados, conceitos)]


# --- estágio: visuais (render por cena) -----------------------------------


def _tamanho_canvas(tipo, nome_visual) -> tuple[int, int]:
    if nome_visual == "pexels":
        return tipo.config.get("imagens.largura"), tipo.config.get("imagens.altura")
    return ASPECT_RATIOS[tipo.config.get("together.aspect_ratio")]


def _placeholder(indice, tipo, nome_visual) -> Image.Image:
    largura, altura = _tamanho_canvas(tipo, nome_visual)
    return _fundo_placeholder(indice, largura, altura)


def _salvar_imagem(caminho: Path, imagem) -> None:
    if isinstance(imagem, (bytes, bytearray)):
        caminho.write_bytes(imagem)
    else:  # PIL.Image
        imagem.save(caminho)


def _para_pil(imagem) -> Image.Image:
    """Normaliza a saída do provedor (bytes do FLUX ou PIL do fundo) em PIL, para a
    camada de personagem poder compor sobre qualquer fonte de fundo."""
    if isinstance(imagem, (bytes, bytearray)):
        return Image.open(io.BytesIO(imagem)).convert("RGB")
    return imagem


def _aplicar_personagem(imagem, dado, tipo) -> Image.Image:
    """Sobrepõe a camada de personagem sobre o fundo já renderizado. A emoção vem do
    plano da cena quando existe (fundo Pexels); com fundo por IA, cai em neutro."""
    emocao = dado.get("emocao", EMOCAO_PADRAO) if isinstance(dado, dict) else EMOCAO_PADRAO
    return sobrepor_personagem(_para_pil(imagem), emocao, tipo.config, tipo.assets_dir)


def _aplicar_icone(imagem, indice, dado, pasta_icones, cfg_ger, led):
    """Camada de ícones: quando a cena tem um conceito, busca o ícone no Iconify (dentro
    do set configurado), grava em `icons/icone_N.png` (checkpoint do run — nunca refaz o
    que já está no disco desta run) e o compõe sobre o quadro. Sem conceito ou com falha
    de busca/rasterização, o quadro sai sem ícone (degrada em vez de quebrar)."""
    conceito = dado.get("icone") if isinstance(dado, dict) else None
    if not conceito:
        return imagem  # esta cena não pede ícone

    cfg_icones = cfg_ger["icones"]
    destino = pasta_icones / f"icone_{indice}.png"
    if not destino.exists():  # nunca refaz um ícone já baixado nesta run
        caminho = iconify.buscar_icone(
            conceito,
            prefixo=cfg_icones["conjunto"],
            cor=cfg_icones["cor"],
            destino=destino,
        )
        if caminho is None:
            print(f"  cena {indice}: sem ícone para '{conceito}' — seguindo sem ícone")
            return imagem

    if led is not None:
        led.registrar("icones", "iconify", 0.0, conceito=conceito, conjunto=cfg_icones["conjunto"])
    return sobrepor_icone(_para_pil(imagem), destino, cfg_icones)


def _render_resiliente(prov, indice, dado, tipo, cfg_ger, nome_visual, previsto, politica, rel, var, led, degradar):
    def _placeholder_failover(_politica=None):
        led.registrar("visuais", "placeholder", 0.0)
        return _placeholder(indice, tipo, nome_visual)

    if degradar:
        print(f"  cena {indice}: orçamento apertado — usando placeholder")
        return _placeholder_failover()

    def _cabe_no_orcamento():
        return checar_orcamento(
            led.total(), previsto, gasto_diario.gasto_hoje(), cfg_ger["orcamento"]
        ) != "parar"

    try:
        # O motor casa a resposta à classe do erro: transitório retenta (backoff+jitter,
        # sem furar o orçamento) e, esgotado, faz failover para o placeholder do pilar.
        return resiliencia.executar(
            lambda: prov.renderizar(
                indice, dado, tipo.config, tipo.assets_dir, variacao=var, ledger=led
            ),
            estagio="visuais",
            provedor=nome_visual,
            politica=politica,
            custo_ok=_cabe_no_orcamento,
            alternativa=_placeholder_failover,
            contexto={"cena": indice, "tipo": tipo.id},
            relatorio=rel,
        )
    except (resiliencia.ResilienciaEsgotada, resiliencia.HaltDestino, resiliencia.Deferir) as e:
        # Erro classificado (permanente/auth/quota) numa cena isolada → política de
        # falha parcial: por padrão degrada para placeholder; "falhar" derruba o run.
        if politica.falha_parcial == "falhar":
            raise
        print(f"  cena {indice}: visual falhou ({e}) — caindo para placeholder")
        return _placeholder_failover()


def _estagio_visuais(frases, prov, dados, tipo, pasta_imagens, pasta_icones, cfg_ger, politica, rel, nome_visual, personagem_ativo, icone_ativo, var, led, reaproveitar):
    previsto = _CUSTO_PREVISTO_VISUAL.get(nome_visual, 0.0)
    print("\nGerando visuais...")
    for (indice, _), dado in zip(frases, dados):
        caminho = pasta_imagens / f"imagem_{indice}.png"
        if deve_reaproveitar(caminho, reaproveitar):
            print(f"  cena {indice}: reaproveitada")
            continue
        decisao = checar_orcamento(
            led.total(), previsto, gasto_diario.gasto_hoje(), cfg_ger["orcamento"]
        )
        if decisao == "parar":
            raise OrcamentoExcedido(
                f"cena {indice}: orçamento excedido (ação 'parar')"
            )
        imagem = _render_resiliente(
            prov, indice, dado, tipo, cfg_ger, nome_visual, previsto, politica, rel, var, led,
            degradar=(decisao == "degradar"),
        )
        # Camadas sobrepostas, independentes da fonte do fundo (foto ou IA):
        # personagem primeiro, ícone por cima de tudo.
        if personagem_ativo:
            imagem = _aplicar_personagem(imagem, dado, tipo)
        if icone_ativo:
            imagem = _aplicar_icone(imagem, indice, dado, pasta_icones, cfg_ger, led)
        _salvar_imagem(caminho, imagem)
        print(f"  cena {indice}/{len(frases)} pronta")

    caminhos = [pasta_imagens / f"imagem_{i}.png" for i, _ in frases]
    gates.validar_visuais(caminhos, esperado=len(frases))


# --- estágio: narração ----------------------------------------------------


def _narrar_resiliente(prov, texto, caminho, tipo, cfg_ger, politica, rel, led):
    voz_sec = cfg_ger["narracao"].get("voz_secundaria") or None

    def _voz_secundaria(_politica=None):
        print(f"  narração falhou — tentando voz secundária '{voz_sec}'")
        return resiliencia.executar(
            lambda: prov.narrar(texto, caminho, tipo.config, voz=voz_sec, ledger=led),
            estagio="narracao",
            provedor="google",
            politica=politica,
            contexto={"voz": voz_sec, "tipo": tipo.id},
            relatorio=rel,
        )

    return resiliencia.executar(
        lambda: prov.narrar(texto, caminho, tipo.config, ledger=led),
        estagio="narracao",
        provedor="google",
        politica=politica,
        alternativa=(_voz_secundaria if voz_sec else None),
        contexto={"tipo": tipo.id},
        relatorio=rel,
    )


def _estagio_narracao(frases, tipo, pasta_audio, cfg_ger, politica, rel, led, reaproveitar):
    prov = provedores.obter(provedores.PAPEL_NARRACAO, cfg_ger["narracao"]["provedor"])
    print("\nGerando narrações...")
    for indice, frase in frases:
        caminho = pasta_audio / f"frase_{indice}.mp3"
        if deve_reaproveitar(
            caminho, reaproveitar, validar=lambda p: p.stat().st_size >= 512
        ):
            print(f"  narração {indice}: reaproveitada")
            continue
        _narrar_resiliente(prov, frase, caminho, tipo, cfg_ger, politica, rel, led)
        gates.validar_narracao(caminho)
        print(f"  narração {indice}/{len(frases)} gerada")


# --- estágio: montagem ----------------------------------------------------


def _estagio_montagem(frases, base, pasta_audio, pasta_imagens, cfg_ger) -> tuple[Path, float]:
    print("\nMontando o vídeo final...")
    clipes, itens, duracao_total = [], [], 0.0
    for indice, frase in frases:
        audio = AudioFileClip(str(pasta_audio / f"frase_{indice}.mp3"))
        clipe = (
            ImageClip(str(pasta_imagens / f"imagem_{indice}.png"))
            .with_duration(audio.duration)
            .with_audio(audio)
        )
        clipes.append(clipe)
        itens.append((frase, audio.duration))
        duracao_total += audio.duration
        print(f"  cena {indice} montada ({audio.duration:.2f}s)")

    if cfg_ger["legendas"]["ativo"]:
        legendas.escrever_srt(base / "legendas.srt", itens)
        clipes = legendas.sobrepor_legendas(clipes, itens, cfg_ger["legendas"])
        print("  legendas aplicadas")

    video_final = concatenate_videoclips(clipes, method="compose")
    caminho_video = base / "video_final.mp4"
    video_final.write_videofile(
        str(caminho_video),
        fps=sistema.get("video.fps"),
        codec=sistema.get("video.codec"),
        audio_codec=sistema.get("video.audio_codec"),
    )
    return caminho_video, duracao_total


# --- orquestração ---------------------------------------------------------


def gerar_video(
    tema: str,
    tipo: TipoVideo,
    output_path: str | Path,
    ledger: Ledger | None = None,
    cancelado=None,
    relatorio: dict | None = None,
) -> Path:
    """Executa o pipeline em estágios, checkpointado, e grava vídeo + sidecar.

    Args:
        tema: Tema do vídeo a ser gerado.
        tipo: Tipo de vídeo (configuração, prompts e assets) a usar na geração.
        output_path: Pasta do run (artefatos intermediários, vídeo e sidecar).
        ledger: Ledger de custo opcional (o histórico injeta o seu; senão cria um).
        cancelado: Callable opcional que devolve True quando o painel pediu para
            cancelar; checado entre estágios (levanta ExecucaoCancelada). None = sem
            cancelamento (comportamento de sempre).

    Returns:
        Path do vídeo final gerado.
    """
    base = Path(output_path)
    pasta_audio = base / "audio"
    pasta_imagens = base / "images"
    pasta_icones = base / "icons"
    for pasta in (base, pasta_audio, pasta_imagens, pasta_icones):
        pasta.mkdir(parents=True, exist_ok=True)

    cfg_ger = mesclar_geracao(tipo.config.get_all().get("geracao"))
    politica = resiliencia.de_tipo(tipo)
    rel = relatorio if relatorio is not None else {}  # observabilidade do motor
    led = ledger if ledger is not None else Ledger()
    var = Variacao(cfg_ger["variacao"])
    reaproveitar = cfg_ger["checkpoint"]["reaproveitar"]

    # Três camadas independentes. "auto" migra dos dois modos empacotados (legado
    # imagens.modo); qualquer combinação fundo × personagem é possível.
    modo = _modo_imagens(tipo)
    fundo = resolver_fundo(cfg_ger["visuais"], modo)
    personagem_ativo = resolver_personagem(cfg_ger["visuais"], modo)
    icone_ativo = cfg_ger["icones"]["ativo"]

    nome_visual = cfg_ger["visuais"]["provedor"]
    if nome_visual == "auto":
        nome_visual = provedores.provedor_visuais_para_fundo(fundo)
    if personagem_ativo:
        validar_personagens(tipo.assets_dir)  # fail-fast antes de gastar

    # Estágios explícitos, cada um checkpointado + com gate de saída. Entre eles,
    # checa o cancelamento cooperativo (fronteira de estágio).
    _checar_cancelamento(cancelado)
    frases = _estagio_roteiro(tema, tipo, base, cfg_ger, politica, rel, var, led, reaproveitar)
    _checar_cancelamento(cancelado)
    prov_visual, dados = _estagio_plano_visual(
        frases, tipo, base, cfg_ger, politica, rel, nome_visual, var, led, reaproveitar
    )
    dados = _estagio_plano_personagem(
        frases, dados, tipo, base, politica, rel, nome_visual, personagem_ativo, led, reaproveitar
    )
    dados = _estagio_plano_icone(
        frases, dados, tipo, base, politica, rel, nome_visual, icone_ativo, led, reaproveitar
    )
    _checar_cancelamento(cancelado)
    _estagio_visuais(
        frases, prov_visual, dados, tipo, pasta_imagens, pasta_icones, cfg_ger, politica, rel, nome_visual, personagem_ativo, icone_ativo, var, led, reaproveitar
    )
    _checar_cancelamento(cancelado)
    _estagio_narracao(frases, tipo, pasta_audio, cfg_ger, politica, rel, led, reaproveitar)
    _checar_cancelamento(cancelado)
    caminho_video, duracao = _estagio_montagem(frases, base, pasta_audio, pasta_imagens, cfg_ger)

    # A dimensão modo_visual do Feedback agora é a fonte do fundo (camada de background):
    # a seleção do provedor e o aprendizado giram esse knob real, não o modo aposentado.
    modo_visual = "pexels" if nome_visual == "pexels" else "ia"
    conceitos_icone = (
        [d.get("icone") if isinstance(d, dict) else None for d in dados]
        if icone_ativo else None
    )
    sidecar.escrever(
        base,
        sidecar.montar(tema, frases, duracao, led, modo_visual=modo_visual, icones=conceitos_icone),
    )
    gasto_diario.registrar(led.total())

    print(f"\nVídeo gerado com sucesso: {caminho_video}")
    return caminho_video


if __name__ == "__main__":
    from config.tipos import carregar_tipo

    gerar_video(
        tema="dicas de produtividade para estudantes",
        tipo=carregar_tipo("cetico_pratico"),
        output_path="output/teste",
    )
