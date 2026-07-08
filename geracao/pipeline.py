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

import re
import time
from pathlib import Path

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image

from config.sistema import sistema
from config.tipos import TipoVideo
from geracao import gates, legendas, sidecar
from geracao.checkpoint import deve_reaproveitar
from geracao.compositor import _fundo_placeholder, validar_personagens
from geracao.configuracao import mesclar_geracao
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


_RE_CENA = re.compile(r"^\[(?P<emocao>.*?)\]\s*\((?P<busca>.*)\)$")


def _escrever_cenas(caminho: Path, dados: list) -> None:
    caminho.write_text(
        "\n".join(f"[{d['emocao']}] ({d['busca']})" for d in dados), encoding="utf-8"
    )


def _ler_cenas(caminho: Path) -> list[dict]:
    dados, usados = [], {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        m = _RE_CENA.match(linha.strip())
        emocao = m.group("emocao") if m else "neutro"
        busca = (m.group("busca") if m else "abstract background") or "abstract background"
        i_fundo = usados.get(busca, 0)
        usados[busca] = i_fundo + 1
        dados.append({"emocao": emocao, "busca": busca, "i_fundo": i_fundo})
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


def _estagio_visuais(frases, prov, dados, tipo, pasta_imagens, cfg_ger, politica, rel, nome_visual, var, led, reaproveitar):
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
    for pasta in (base, pasta_audio, pasta_imagens):
        pasta.mkdir(parents=True, exist_ok=True)

    cfg_ger = mesclar_geracao(tipo.config.get_all().get("geracao"))
    politica = resiliencia.de_tipo(tipo)
    rel = relatorio if relatorio is not None else {}  # observabilidade do motor
    led = ledger if ledger is not None else Ledger()
    var = Variacao(cfg_ger["variacao"])
    reaproveitar = cfg_ger["checkpoint"]["reaproveitar"]

    modo = _modo_imagens(tipo)
    nome_visual = cfg_ger["visuais"]["provedor"]
    if nome_visual == "auto":
        nome_visual = provedores.provedor_visuais_para_modo(modo)
    if nome_visual == "pexels":
        validar_personagens(tipo.assets_dir)  # fail-fast antes de gastar

    # Estágios explícitos, cada um checkpointado + com gate de saída. Entre eles,
    # checa o cancelamento cooperativo (fronteira de estágio).
    _checar_cancelamento(cancelado)
    frases = _estagio_roteiro(tema, tipo, base, cfg_ger, politica, rel, var, led, reaproveitar)
    _checar_cancelamento(cancelado)
    prov_visual, dados = _estagio_plano_visual(
        frases, tipo, base, cfg_ger, politica, rel, nome_visual, var, led, reaproveitar
    )
    _checar_cancelamento(cancelado)
    _estagio_visuais(
        frases, prov_visual, dados, tipo, pasta_imagens, cfg_ger, politica, rel, nome_visual, var, led, reaproveitar
    )
    _checar_cancelamento(cancelado)
    _estagio_narracao(frases, tipo, pasta_audio, cfg_ger, politica, rel, led, reaproveitar)
    _checar_cancelamento(cancelado)
    caminho_video, duracao = _estagio_montagem(frases, base, pasta_audio, pasta_imagens, cfg_ger)

    modo_visual = "personagem" if nome_visual == "pexels" else "ia"
    sidecar.escrever(base, sidecar.montar(tema, frases, duracao, led, modo_visual=modo_visual))
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
