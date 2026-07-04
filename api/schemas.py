from pydantic import BaseModel, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

from config.constantes import FEEDS_TRENDS, FREQUENCIAS, MODOS_IMAGEM, VISIBILIDADES
from descoberta.configuracao import (
    ESTRATEGIAS_DEDUP,
    MODOS_REVIEW,
    POLITICAS_RETENCAO,
    REDDIT_PERIODOS,
)
from geracao.compositor import POSICOES
from geracao.generate_image import ASPECT_RATIOS

_HORARIO_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


class SistemaExecucao(BaseModel):
    max_simultaneo: int = Field(ge=1)


class SistemaSaida(BaseModel):
    pasta_base: str = Field(min_length=1)


class SistemaVideo(BaseModel):
    fps: int = Field(ge=1, le=120)
    codec: str = Field(min_length=1)
    audio_codec: str = Field(min_length=1)


class SistemaConfig(BaseModel):
    execucao: SistemaExecucao
    saida: SistemaSaida
    video: SistemaVideo


class GroqConfig(BaseModel):
    modelo: str = Field(min_length=1)
    temperatura: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1, le=32768)


class TogetherConfig(BaseModel):
    modelo: str = Field(min_length=1)
    steps: int = Field(ge=1, le=50)
    aspect_ratio: str

    @field_validator("aspect_ratio")
    @classmethod
    def _validar_aspect_ratio(cls, v):
        if v not in ASPECT_RATIOS:
            raise ValueError(f"aspect_ratio deve ser um de: {', '.join(ASPECT_RATIOS)}")
        return v


class PersonagemConfig(BaseModel):
    posicao: str
    altura_percentual: int = Field(ge=10, le=100)
    margem_lateral: int = Field(ge=0, le=1000)
    margem_vertical: int = Field(ge=0, le=1000)

    @field_validator("posicao")
    @classmethod
    def _validar_posicao(cls, v):
        if v not in POSICOES:
            raise ValueError(f"posicao deve ser uma de: {', '.join(POSICOES)}")
        return v


class ImagensConfig(BaseModel):
    modo: str
    largura: int = Field(ge=480, le=3840)
    altura: int = Field(ge=480, le=3840)
    personagem: PersonagemConfig

    @field_validator("modo")
    @classmethod
    def _validar_modo(cls, v):
        if v not in MODOS_IMAGEM:
            raise ValueError(f"modo deve ser um de: {', '.join(MODOS_IMAGEM)}")
        return v


class TtsConfig(BaseModel):
    idioma: str
    voz: str = Field(min_length=1)
    velocidade: float = Field(ge=0.25, le=4.0)
    pitch: float = Field(ge=-20.0, le=20.0)

    @field_validator("idioma")
    @classmethod
    def _validar_idioma(cls, v):
        if not _LOCALE_RE.match(v):
            raise ValueError("idioma deve seguir o formato 'xx-YY' (ex: pt-BR)")
        return v


class PipelineConfig(BaseModel):
    min_chars_por_periodo: int = Field(ge=1)


class AgendamentoConfig(BaseModel):
    frequencia: str
    horario: str
    fuso_horario: str

    @field_validator("frequencia")
    @classmethod
    def _validar_frequencia(cls, v):
        if v not in FREQUENCIAS:
            raise ValueError(f"frequencia deve ser uma de: {', '.join(FREQUENCIAS)}")
        return v

    @field_validator("horario")
    @classmethod
    def _validar_horario(cls, v):
        if not _HORARIO_RE.match(v):
            raise ValueError("horario deve seguir o formato HH:MM (24h)")
        return v

    @field_validator("fuso_horario")
    @classmethod
    def _validar_fuso(cls, v):
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError:
            raise ValueError(f"fuso_horario inválido: '{v}'")
        return v


class YoutubeConfig(BaseModel):
    categoria_id: str = Field(pattern=r"^\d+$")
    visibilidade: str
    tags: list[str] = Field(default_factory=list)
    publicar: bool = False
    descricao_base: str = ""

    @field_validator("visibilidade")
    @classmethod
    def _validar_visibilidade(cls, v):
        if v not in VISIBILIDADES:
            raise ValueError(f"visibilidade deve ser uma de: {', '.join(VISIBILIDADES)}")
        return v


class FonteTrendsMcpConfig(BaseModel):
    ativo: bool
    feed: str
    limite: int = Field(ge=1, le=200)

    @field_validator("feed")
    @classmethod
    def _validar_feed(cls, v):
        if v not in FEEDS_TRENDS:
            raise ValueError(f"feed deve ser um de: {', '.join(FEEDS_TRENDS)}")
        return v


class FonteYoutubeConfig(BaseModel):
    ativo: bool
    limite: int = Field(ge=1, le=50)
    consultas: list[str] = Field(default_factory=list)
    canais_nicho: list[str] = Field(default_factory=list)
    regiao: str = Field(pattern=r"^[A-Z]{2}$")


class FonteGoogleTrendsConfig(BaseModel):
    ativo: bool
    limite: int = Field(ge=1, le=100)
    geo: str = Field(pattern=r"^[A-Z]{2}$")


class FonteRedditConfig(BaseModel):
    ativo: bool
    subreddits: list[str] = Field(default_factory=list)
    limite: int = Field(ge=1, le=100)
    periodo: str

    @field_validator("periodo")
    @classmethod
    def _validar_periodo(cls, v):
        if v not in REDDIT_PERIODOS:
            raise ValueError(f"periodo deve ser um de: {', '.join(REDDIT_PERIODOS)}")
        return v


class FonteWikipediaConfig(BaseModel):
    ativo: bool
    limite: int = Field(ge=1, le=100)


class FontePoolConfig(BaseModel):
    ativo: bool


class FontesConfig(BaseModel):
    trends_mcp: FonteTrendsMcpConfig
    youtube: FonteYoutubeConfig
    google_trends: FonteGoogleTrendsConfig
    reddit: FonteRedditConfig
    wikipedia: FonteWikipediaConfig
    manual: FontePoolConfig
    evergreen: FontePoolConfig


class FitConfig(BaseModel):
    score_minimo: int = Field(ge=0, le=100)


class DedupConfig(BaseModel):
    dias: int = Field(ge=1, le=365)
    estrategia: str
    limiar: float = Field(ge=0.0, le=1.0)

    @field_validator("estrategia")
    @classmethod
    def _validar_estrategia(cls, v):
        if v not in ESTRATEGIAS_DEDUP:
            raise ValueError(f"estrategia deve ser uma de: {', '.join(ESTRATEGIAS_DEDUP)}")
        return v


class SelecaoConfig(BaseModel):
    peso_sinal: float = Field(ge=0.0, le=1.0)
    peso_fit: float = Field(ge=0.0, le=1.0)
    peso_frescor: float = Field(ge=0.0, le=1.0)
    meia_vida_horas: float = Field(gt=0.0, le=8760.0)


class DescobertaConfig(BaseModel):
    antecedencia_horas: int = Field(ge=0, le=168)
    fontes: FontesConfig
    fit: FitConfig
    dedup: DedupConfig
    selecao: SelecaoConfig
    evergreen_ratio: float = Field(ge=0.0, le=1.0)
    modo_revisao: str
    retencao: str
    orcamento_avaliacao: int = Field(ge=1, le=20)

    @field_validator("modo_revisao")
    @classmethod
    def _validar_modo_revisao(cls, v):
        if v not in MODOS_REVIEW:
            raise ValueError(f"modo_revisao deve ser um de: {', '.join(MODOS_REVIEW)}")
        return v

    @field_validator("retencao")
    @classmethod
    def _validar_retencao(cls, v):
        if v not in POLITICAS_RETENCAO:
            raise ValueError(f"retencao deve ser uma de: {', '.join(POLITICAS_RETENCAO)}")
        return v


class TipoConfig(BaseModel):
    nome: str = Field(min_length=1)
    ativo: bool
    groq: GroqConfig
    together: TogetherConfig
    imagens: ImagensConfig
    tts: TtsConfig
    pipeline: PipelineConfig
    agendamento: AgendamentoConfig
    youtube: YoutubeConfig
    descoberta: DescobertaConfig


class CriarTipoForm(BaseModel):
    nome: str = Field(min_length=1)


class RenomearTipoForm(BaseModel):
    novo_nome: str = Field(min_length=1)


class DuplicarTipoForm(BaseModel):
    novo_nome: str = Field(min_length=1)


class TemaForm(BaseModel):
    tema: str = Field(min_length=1)
    prioridade: int = Field(ge=0, le=100)
    fonte: str = Field(default="manual", min_length=1)


class AlterarPrioridadeForm(BaseModel):
    nova_prioridade: int = Field(ge=0, le=100)


class AssetTextoForm(BaseModel):
    conteudo: str = Field(min_length=1)


class DispararExecucaoForm(BaseModel):
    tipo_id: str = Field(min_length=1)
    tema: str | None = None
