"""Publicação de vídeos no YouTube (YouTube Data API v3).

Etapa final do pipeline: sobe o video_final.mp4 para o canal do tipo. Cada tipo
tem seu próprio projeto Google Cloud (para isolar a cota de upload — ~6/dia por
projeto), então as credenciais são por tipo:

  tipos/<id>/youtube_client_secret.json  (app OAuth Desktop; cai na raiz
                                          client_secret_youtube.json se ausente)
  tipos/<id>/youtube_token.json          (refresh token, criado no 1º
                                          consentimento; gitignored)

Consentimento único:  python -m publicacao.youtube auth --tipo <id>
Teste manual:         python -m publicacao.youtube publicar <video> --tipo <id> [--tema ...]

Gotcha: em modo "Testing" do OAuth o refresh token expira em 7 dias (causa
clássica de automação que "para sozinha"). Ponha o app em "In production" no
console para tokens duráveis; se expirar, rode 'auth' de novo.
"""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config.tipos import TipoVideo, carregar_tipo

# Escopos: upload (a função) + readonly (para a verificação não-destrutiva
# channels.list mine=true, que confirma qual canal foi autenticado).
ESCOPOS = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

_RAIZ = Path(__file__).parent.parent
_CLIENT_SECRET_RAIZ = _RAIZ / "client_secret_youtube.json"

TITULO_MAX = 100   # limite do YouTube para o título
DESCRICAO_MAX = 5000  # limite do YouTube para a descrição


def _caminho_client_secret(tipo: TipoVideo) -> Path:
    """App OAuth do tipo; cai na raiz se o tipo não tiver o seu próprio."""
    por_tipo = tipo.caminho / "youtube_client_secret.json"
    return por_tipo if por_tipo.exists() else _CLIENT_SECRET_RAIZ


def _caminho_token(tipo: TipoVideo) -> Path:
    return tipo.caminho / "youtube_token.json"


def autenticar(tipo: TipoVideo, permitir_consentimento: bool = False) -> Credentials:
    """Devolve credenciais OAuth válidas para o canal do tipo.

    Carrega o token salvo; renova se expirado. Se não houver token válido e
    `permitir_consentimento` for True, abre o navegador para o consentimento
    único e grava o token. Caso contrário, levanta RuntimeError orientando a
    rodar o comando 'auth'.
    """
    token_path = _caminho_token(tipo)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), ESCOPOS)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as e:
            if not permitir_consentimento:
                raise RuntimeError(
                    f"O token do YouTube de '{tipo.id}' expirou e não deu para "
                    f"renovar ({e}). Rode: python -m publicacao.youtube auth --tipo {tipo.id}"
                ) from e

    if not permitir_consentimento:
        raise RuntimeError(
            f"Sem credencial válida do YouTube para '{tipo.id}'. "
            f"Rode: python -m publicacao.youtube auth --tipo {tipo.id}"
        )

    client_secret = _caminho_client_secret(tipo)
    if not client_secret.exists():
        raise FileNotFoundError(
            f"client secret do YouTube não encontrado em {client_secret} "
            f"(nem na raiz {_CLIENT_SECRET_RAIZ})."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), ESCOPOS)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _servico(tipo: TipoVideo, permitir_consentimento: bool = False):
    creds = autenticar(tipo, permitir_consentimento)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def canal_autenticado(tipo: TipoVideo) -> dict:
    """Retorna {id, titulo} do canal autenticado (channels.list mine=true).

    Verificação não-destrutiva: confirma que a cadeia OAuth funciona e mostra
    qual canal foi autorizado (pega o erro comum de autenticar a conta errada).
    """
    servico = _servico(tipo)
    resposta = servico.channels().list(part="snippet", mine=True).execute()
    itens = resposta.get("items", [])
    if not itens:
        raise RuntimeError("Nenhum canal associado à conta autenticada.")
    item = itens[0]
    return {"id": item["id"], "titulo": item["snippet"]["title"]}


def _montar_metadados(tema: str, roteiro: str, config) -> dict:
    """Monta o corpo de videos.insert a partir do tema/roteiro e do config do tipo.

    Título = tema (cortado no limite do YouTube). Descrição = roteiro +
    descrição-base do config + rodapé com #Shorts e as tags como hashtags.
    """
    titulo = tema.strip()[:TITULO_MAX]

    tags = config.get("youtube.tags")
    base = config.get("youtube.descricao_base")

    partes = []
    if roteiro.strip():
        partes.append(roteiro.strip())
    if base and base.strip():
        partes.append(base.strip())

    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags)
    partes.append("#Shorts" + (f" {hashtags}" if hashtags else ""))

    descricao = "\n\n".join(partes)[:DESCRICAO_MAX]

    return {
        "snippet": {
            "title": titulo,
            "description": descricao,
            "tags": tags,
            "categoryId": config.get("youtube.categoria_id"),
        },
        "status": {
            "privacyStatus": config.get("youtube.visibilidade"),
            "selfDeclaredMadeForKids": False,
        },
    }


def publicar_video(video_path, tema: str, tipo: TipoVideo, roteiro: str = "") -> str:
    """Sobe um vídeo já gerado para o canal do tipo e devolve a URL pública.

    Args:
        video_path: Caminho do video_final.mp4.
        tema: Tema do vídeo (vira o título).
        tipo: Tipo de vídeo (config + credenciais).
        roteiro: Texto do roteiro (entra na descrição). Opcional.

    Returns:
        URL curta do vídeo (https://youtu.be/<id>).
    """
    servico = _servico(tipo)
    corpo = _montar_metadados(tema, roteiro, tipo.config)

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    requisicao = servico.videos().insert(part="snippet,status", body=corpo, media_body=media)

    resposta = None
    while resposta is None:
        status, resposta = requisicao.next_chunk()
        if status:
            print(f"    [youtube] upload {int(status.progress() * 100)}%")

    url = f"https://youtu.be/{resposta['id']}"
    print(f"    [youtube] publicado: {url}")
    return url


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Publicação no YouTube")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_auth = sub.add_parser("auth", help="consentimento OAuth (abre o navegador)")
    p_auth.add_argument("--tipo", required=True)

    p_pub = sub.add_parser("publicar", help="publica um vídeo já gerado")
    p_pub.add_argument("video")
    p_pub.add_argument("--tipo", required=True)
    p_pub.add_argument("--tema", default="Vídeo de teste")

    args = parser.parse_args()
    tipo = carregar_tipo(args.tipo)

    if args.cmd == "auth":
        autenticar(tipo, permitir_consentimento=True)
        canal = canal_autenticado(tipo)
        print(f"Consentimento salvo. Autenticado como: {canal['titulo']} ({canal['id']})")
    elif args.cmd == "publicar":
        print(publicar_video(args.video, args.tema, tipo))
