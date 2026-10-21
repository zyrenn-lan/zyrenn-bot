import discord
import aiohttp
from discord.ext import commands
from discord import app_commands

import yt_dlp

import os
import re
import asyncio
import subprocess
import time
import urllib.parse
import urllib.request
import json
import random
import html
import shutil
import mimetypes


# =========================================================
# CONFIGURAÇÃO
# =========================================================

DOWNLOADS_DIR = "downloads"

# Caminho que você já estava usando
FFMPEG_PATH = (
    r"C:\Users\User\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-9.0.2-full_build\bin"
)

# Tenta achar o FFmpeg pelo PATH primeiro
FFMPEG_EXE = shutil.which("ffmpeg")

if not FFMPEG_EXE:
    possivel_ffmpeg = os.path.join(FFMPEG_PATH, "ffmpeg.exe")

    if os.path.isfile(possivel_ffmpeg):
        FFMPEG_EXE = possivel_ffmpeg

if FFMPEG_EXE:
    FFMPEG_PATH_REAL = os.path.dirname(FFMPEG_EXE)
else:
    FFMPEG_PATH_REAL = FFMPEG_PATH


os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Discord permite arquivos maiores dependendo do servidor,
# mas usamos 19 MB para ficar mais seguro.
LIMITE_DISCORD = 19 * 1024 * 1024

# Zyrenn Videos: integração SOMENTE para comandos de vídeo.
ZYRENN_VIDEOS_URL = os.getenv(
    "ZYRENN_VIDEOS_URL",
    "https://zyrenn-videos--daviikkjz.replit.app"
).rstrip("/")
ZYRENN_VIDEOS_TOKEN = os.getenv("ZYRENN_VIDEOS_TOKEN")
LIMITE_ZYRENN_VIDEOS = 24 * 1024 * 1024


async def enviar_video_para_zyrenn(arquivo):
    if not ZYRENN_VIDEOS_TOKEN:
        raise RuntimeError("ZYRENN_VIDEOS_TOKEN não está configurado no .env.")
    if not arquivo or not os.path.isfile(arquivo):
        raise FileNotFoundError("Arquivo de vídeo não encontrado.")
    if os.path.getsize(arquivo) > LIMITE_ZYRENN_VIDEOS:
        raise ValueError("O vídeo ultrapassa o limite de 24 MB do Zyrenn Videos.")

    timeout = aiohttp.ClientTimeout(total=300, connect=30, sock_read=120)
    headers = {"Authorization": f"Bearer {ZYRENN_VIDEOS_TOKEN}"}
    with open(arquivo, "rb") as fp:
        form = aiohttp.FormData()
        form.add_field(
            "file", fp,
            filename=os.path.basename(arquivo),
            content_type=(
                mimetypes.guess_type(arquivo)[0]
                or "application/octet-stream"
            )
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{ZYRENN_VIDEOS_URL}/upload",
                headers=headers,
                data=form
            ) as response:
                body = await response.text()
                if response.status >= 400:
                    raise RuntimeError(f"Servidor Zyrenn Videos ({response.status}): {body[:400]}")
                dados = json.loads(body)

    link = dados.get("url")
    if not link:
        raise RuntimeError("O servidor não retornou o link do vídeo.")
    # A página /share/ é a que gera o player no Discord (só aceita MP4).
    # Para outros formatos usamos a rota pública /videos/.
    if os.path.splitext(arquivo)[1].lower() != ".mp4":
        if "/share/" in link:
            link = link.replace("/share/", "/videos/", 1)
    return link


# =========================================================
# REGEX
# =========================================================

URL_REGEX = re.compile(
    r"https?://[^\s<>]+",
    re.IGNORECASE
)


# Aceita:
# https://open.spotify.com/track/...
# https://open.spotify.com/intl-pt/track/...
# https://spotify.com/track/...
# https://spotify.link/...
SPOTIFY_REGEX = re.compile(
    r"https?://(?:(?:open\.)?spotify\.com|spotify\.link)/[^\s<>]+",
    re.IGNORECASE
)


YOUTUBE_REGEX = re.compile(
    r"https?://(?:www\.)?"
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)"
    r"[A-Za-z0-9_-]+",
    re.IGNORECASE
)


TIKTOK_REGEX = re.compile(
    r"https?://(?:www\.)?"
    r"(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/[^\s<>]+",
    re.IGNORECASE
)


INSTAGRAM_REGEX = re.compile(
    r"https?://(?:www\.)?"
    r"instagram\.com/(?:reel|reels|p|tv)/[^\s<>]+",
    re.IGNORECASE
)


# =========================================================
# MEMÓRIA DOS ÚLTIMOS VÍDEOS
# =========================================================

ULTIMOS_VIDEOS = {}


# =========================================================
# UTILITÁRIOS
# =========================================================

def limpar_nome_arquivo(nome):
    """
    Remove caracteres que não podem existir em nomes de arquivos
    no Windows.
    """

    if not nome:
        nome = "audio"

    nome = html.unescape(str(nome))

    nome = re.sub(r'[<>:"/\\|?*]', '', nome)

    nome = nome.replace("\n", " ")
    nome = nome.replace("\r", " ")

    nome = re.sub(r"\s+", " ", nome)

    nome = nome.strip(" .")

    if not nome:
        nome = "audio"

    # Limite para evitar caminho grande demais
    return nome[:180]


def remover_query(url):
    """
    Remove ?query e #fragment da URL.
    """

    if not url:
        return url

    try:
        partes = urllib.parse.urlsplit(url)

        return urllib.parse.urlunsplit(
            (
                partes.scheme,
                partes.netloc,
                partes.path,
                "",
                ""
            )
        )

    except Exception:
        return url


def extrair_url(texto):
    """
    Pega a primeira URL encontrada em um texto.
    """

    if not texto:
        return None

    encontrado = URL_REGEX.search(texto)

    if not encontrado:
        return None

    return encontrado.group(0).rstrip(").,>]}\"'")


def eh_spotify(url):
    if not url:
        return False

    return bool(SPOTIFY_REGEX.search(url))


def eh_youtube(url):
    if not url:
        return False

    return bool(YOUTUBE_REGEX.search(url))


def eh_tiktok(url):
    if not url:
        return False

    return bool(TIKTOK_REGEX.search(url))


def eh_instagram(url):
    if not url:
        return False

    return bool(INSTAGRAM_REGEX.search(url))


# =========================================================
# SPOTIFY
# =========================================================

def expandir_spotify_link(url):
    """
    Converte links do tipo:

    https://spotify.link/xxxxx

    para a URL real do Spotify.
    """

    if not url:
        return url

    try:
        url = remover_query(url)

        if "spotify.link" not in url.lower():
            return url

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/154.0 Safari/537.36"
                )
            }
        )

        with urllib.request.urlopen(req, timeout=5) as resposta:
            final_url = resposta.geturl()

        return final_url

    except Exception as e:
        print(f"[Spotify] Não foi possível expandir link: {e}")
        return url


def extrair_spotify_track_id(url):
    """
    Extrai o ID da música do Spotify.
    """

    if not url:
        return None

    url = expandir_spotify_link(url)

    padroes = [
        r"spotify\.com/(?:intl-[a-z]{2}/)?track/([A-Za-z0-9]+)",
        r"spotify:track:([A-Za-z0-9]+)"
    ]

    for padrao in padroes:

        resultado = re.search(
            padrao,
            url,
            re.IGNORECASE
        )

        if resultado:
            return resultado.group(1)

    return None


def requisicao_url(url):
    """
    Faz GET em uma URL e retorna o HTML.
    """

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/154.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
        }
    )

    with urllib.request.urlopen(req, timeout=8) as resposta:

        charset = resposta.headers.get_content_charset()

        if not charset:
            charset = "utf-8"

        conteudo = resposta.read()

        return conteudo.decode(
            charset,
            errors="ignore"
        )


def valor_json(html_texto, chaves):
    """
    Tenta encontrar valores em estruturas JSON/HTML.

    Exemplo:

    "artistName":"NOME"
    "trackTitle":"MUSICA"
    """

    for chave in chaves:

        padroes = [
            rf'"{re.escape(chave)}"\s*:\s*"([^"]+)"',
            rf"'{re.escape(chave)}'\s*:\s*'([^']+)'",
        ]

        for padrao in padroes:

            resultado = re.search(
                padrao,
                html_texto,
                re.IGNORECASE
            )

            if resultado:

                valor = resultado.group(1)

                valor = bytes(
                    valor,
                    "utf-8"
                ).decode(
                    "unicode_escape",
                    errors="ignore"
                )

                return html.unescape(valor)

    return None


def limpar_texto_spotify(texto):
    if not texto:
        return None

    texto = html.unescape(texto)

    texto = texto.replace("\\u0026", "&")
    texto = texto.replace("\\/", "/")
    texto = texto.replace('\\"', '"')

    texto = re.sub(
        r"\s+",
        " ",
        texto
    ).strip()

    return texto


def extrair_info_do_embed_spotify(track_id):
    """
    Tenta pegar as informações da página embed do Spotify.

    Não baixa nada do Spotify.
    Apenas pega metadados.
    """

    url = (
        f"https://open.spotify.com/embed/track/{track_id}"
    )

    try:

        pagina = requisicao_url(url)

        pagina = limpar_texto_spotify(pagina)

        titulo = None
        artistas = []

        # =====================================================
        # TÍTULO
        # =====================================================

        chaves_titulo = [
            "trackTitle",
            "track_name",
            "trackName",
            "title",
            "name"
        ]

        for chave in chaves_titulo:

            encontrado = valor_json(
                pagina,
                [chave]
            )

            if encontrado:

                if encontrado.lower() not in [
                    "spotify",
                    "spotify embed"
                ]:

                    titulo = encontrado
                    break

        # =====================================================
        # ARTISTA
        # =====================================================

        chaves_artista = [
            "artistName",
            "artist",
            "artist_name"
        ]

        for chave in chaves_artista:

            encontrado = valor_json(
                pagina,
                [chave]
            )

            if encontrado:

                if encontrado.lower() != "spotify":

                    artistas.append(
                        encontrado
                    )

                    break

        # =====================================================
        # TENTA ARRAY DE ARTISTAS
        # =====================================================

        padroes_artistas = [
            r'"artists"\s*:\s*\[(.*?)\]',
            r'"artist"\s*:\s*\[(.*?)\]'
        ]

        for padrao in padroes_artistas:

            resultado = re.search(
                padrao,
                pagina,
                re.IGNORECASE | re.DOTALL
            )

            if not resultado:
                continue

            bloco = resultado.group(1)

            encontrados = re.findall(
                r'"name"\s*:\s*"([^"]+)"',
                bloco
            )

            for artista in encontrados:

                artista = limpar_texto_spotify(
                    artista
                )

                if not artista:
                    continue

                if artista.lower() == "spotify":
                    continue

                if artista not in artistas:

                    artistas.append(
                        artista
                    )

        # =====================================================
        # META OG:TITLE
        # =====================================================

        if not titulo:

            og = re.search(
                r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                pagina,
                re.IGNORECASE
            )

            if og:

                titulo = limpar_texto_spotify(
                    og.group(1)
                )

        # =====================================================
        # TITLE HTML
        # =====================================================

        if not titulo:

            title_tag = re.search(
                r"<title[^>]*>(.*?)</title>",
                pagina,
                re.IGNORECASE | re.DOTALL
            )

            if title_tag:

                titulo = limpar_texto_spotify(
                    title_tag.group(1)
                )

                if titulo:

                    titulo = re.sub(
                        r"\s*\|\s*Spotify.*$",
                        "",
                        titulo,
                        flags=re.IGNORECASE
                    ).strip()

        # =====================================================
        # LIMPEZA
        # =====================================================

        if titulo:

            titulo = titulo.strip()

            if titulo.lower() == "spotify":
                titulo = None

        artistas_limpos = []

        for artista in artistas:

            artista = limpar_texto_spotify(
                artista
            )

            if not artista:
                continue

            if artista.lower() == "spotify":
                continue

            if artista not in artistas_limpos:

                artistas_limpos.append(
                    artista
                )

        artistas = artistas_limpos

        if titulo or artistas:

            return {
                "titulo": titulo,
                "artistas": artistas,
                "track_id": track_id
            }

    except Exception as e:

        print(
            f"[Spotify] Erro ao ler embed: {e}"
        )

    return None


def obter_info_spotify(url):
    chave = (url or "").strip()
    em_cache = _cache_get(_CACHE_SPOTIFY, chave, 86400)
    if em_cache is not None:
        return em_cache
    info = _obter_info_spotify(url)
    if info:
        _cache_set(_CACHE_SPOTIFY, chave, info)
    return info


def _obter_info_spotify(url):
    """
    Obtém título + artistas de uma música do Spotify.

    Primeiro tenta o embed.
    Depois tenta o oEmbed.
    """

    try:

        url_original = url

        # -----------------------------------------------------
        # Expande spotify.link
        # -----------------------------------------------------

        url = expandir_spotify_link(
            url
        )

        print(
            f"[Spotify] URL real: {url}"
        )

        # -----------------------------------------------------
        # ID
        # -----------------------------------------------------

        track_id = extrair_spotify_track_id(
            url
        )

        if not track_id:

            print(
                "[Spotify] Não consegui encontrar o ID da música."
            )

            return None

        print(
            f"[Spotify] Track ID: {track_id}"
        )

        # -----------------------------------------------------
        # PRIMEIRO: EMBED
        # -----------------------------------------------------

        info = extrair_info_do_embed_spotify(
            track_id
        )

        if info:

            titulo = info.get(
                "titulo"
            )

            artistas = info.get(
                "artistas",
                []
            )

            if titulo:

                print(
                    f"[Spotify] Título: {titulo}"
                )

                print(
                    f"[Spotify] Artistas: "
                    f"{', '.join(artistas) if artistas else 'não identificado'}"
                )

                return {
                    "titulo": titulo,
                    "artistas": artistas,
                    "track_id": track_id
                }

        # -----------------------------------------------------
        # SEGUNDO: OEMBED
        # -----------------------------------------------------

        oembed_url = (
            "https://open.spotify.com/oembed?"
            + urllib.parse.urlencode(
                {
                    "url": url
                }
            )
        )

        print(
            f"[Spotify] Tentando oEmbed..."
        )

        resposta = urllib.request.urlopen(
            urllib.request.Request(
                oembed_url,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            ),
            timeout=6
        )

        dados = json.loads(
            resposta.read().decode(
                "utf-8",
                errors="ignore"
            )
        )

        titulo = dados.get(
            "title"
        )

        titulo = limpar_texto_spotify(
            titulo
        )

        if titulo and titulo.lower() == "spotify":
            titulo = None

        if titulo:

            print(
                f"[Spotify] Título pelo oEmbed: {titulo}"
            )

            return {
                "titulo": titulo,
                "artistas": [],
                "track_id": track_id
            }

        print(
            "[Spotify] Não consegui identificar a música."
        )

        print(
            f"[Spotify] Link recebido: {url_original}"
        )

    except Exception as e:

        print(
            f"[Spotify] Erro geral: {e}"
        )

    return None


# =========================================================
# YOUTUBE
# =========================================================

# Opções comuns do yt-dlp para downloads mais rápidos
YDL_RAPIDO = {
    "concurrent_fragment_downloads": 8,
    "retries": 3,
    "fragment_retries": 3,
    "socket_timeout": 10,
    "noprogress": True,
    "http_chunk_size": 10485760,
    "check_formats": False,
    "extractor_retries": 1,
    "no_color": True,
}

# Caches em memória (evitam repetir buscas iguais)
_CACHE_PESQUISA = {}
_CACHE_SPOTIFY = {}
_CACHE_STREAM = {}
_TTL_PESQUISA = 600
_TTL_STREAM = 3600


def _cache_get(cache, chave, ttl):
    item = cache.get(chave)
    if item and (time.time() - item[0]) < ttl:
        return item[1]
    cache.pop(chave, None)
    return None


def _cache_set(cache, chave, valor):
    if len(cache) > 200:
        cache.clear()
    cache[chave] = (time.time(), valor)


async def pesquisar_youtube(pesquisa, quantidade=20):

    chave_cache = (pesquisa.lower().strip(), quantidade)
    em_cache = _cache_get(_CACHE_PESQUISA, chave_cache, _TTL_PESQUISA)
    if em_cache is not None:
        return em_cache

    def buscar():

        try:

            opcoes = {
                "quiet": True,
                "skip_download": True,
                "extract_flat": True,
                "noplaylist": True,
                "socket_timeout": 10,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(opcoes) as ydl:

                dados = ydl.extract_info(
                    f"ytsearch{quantidade}:{pesquisa}",
                    download=False
                )

                resultados = []

                for item in dados.get(
                    "entries",
                    []
                ):

                    if not item:
                        continue

                    video_id = item.get(
                        "id"
                    )

                    if not video_id:
                        continue

                    resultados.append(
                        {
                            "title": item.get(
                                "title",
                                "Sem título"
                            ),
                            "url": (
                                f"https://www.youtube.com/watch?v={video_id}"
                            ),
                           "thumbnail": (
    item.get("thumbnail")
    or next(
        (
            thumb.get("url")
            for thumb in reversed(item.get("thumbnails") or [])
            if thumb.get("url")
        ),
        None
    )
    or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
),
                        }
                    )

                return resultados

        except Exception as e:

            print(
                f"[YouTube] Erro na pesquisa: {e}"
            )

            return []

    resultado_busca = await asyncio.to_thread(
        buscar
    )

    if resultado_busca:
        _cache_set(_CACHE_PESQUISA, chave_cache, resultado_busca)

    return resultado_busca


async def pesquisar_musica_youtube(
    titulo,
    artistas
):
    """
    Procura a música do Spotify no YouTube.

    Dá prioridade para resultados que:
    - tenham o nome da música
    - tenham o artista
    - não sejam remix/slowed/etc.
    """

    artista_texto = ", ".join(
        artistas
    ) if artistas else ""

    pesquisa_base = (
        f"{titulo} {artista_texto}"
    ).strip()

    pesquisas = [
        f"{pesquisa_base} official audio",
        pesquisa_base
    ]

    todos = []

    for pesquisa in pesquisas:

        resultados = await pesquisar_youtube(
            pesquisa,
            5
        )

        todos.extend(
            resultados
        )

        if resultados:
            break

    if not todos:

        return None

    titulo_normalizado = (
        titulo.lower()
        .replace("-", " ")
    )

    palavras_titulo = [
        p for p in re.findall(
            r"[a-zA-ZÀ-ÿ0-9]+",
            titulo_normalizado
        )
        if len(p) > 2
    ]

    palavras_artistas = []

    for artista in artistas:

        palavras_artistas.extend(
            [
                p.lower()
                for p in re.findall(
                    r"[a-zA-ZÀ-ÿ0-9]+",
                    artista
                )
                if len(p) > 2
            ]
        )

    proibidos = [
        "sped up",
        "slowed",
        "reverb",
        "8d",
        "nightcore",
        "cover",
        "karaoke",
        "instrumental",
        "live",
        "remix",
        "edit",
        "version"
    ]

    def pontuar(item):

        titulo_video = item.get(
            "title",
            ""
        ).lower()

        pontos = 0

        # ---------------------------------------------
        # Nome da música
        # ---------------------------------------------

        for palavra in palavras_titulo:

            if palavra in titulo_video:

                pontos += 8

        # ---------------------------------------------
        # Artistas
        # ---------------------------------------------

        for palavra in palavras_artistas:

            if palavra in titulo_video:

                pontos += 10

        # ---------------------------------------------
        # Official
        # ---------------------------------------------

        if "official audio" in titulo_video:
            pontos += 20

        elif "official" in titulo_video:
            pontos += 10

        # ---------------------------------------------
        # Penalizações
        # ---------------------------------------------

        for palavra in proibidos:

            if palavra in titulo_video:

                pontos -= 25

        return pontos

    melhor = max(
        todos,
        key=pontuar
    )

    print(
        f"[Spotify] Encontrado no YouTube: "
        f"{melhor.get('title')}"
    )

    print(
        f"[Spotify] URL: "
        f"{melhor.get('url')}"
    )

    return melhor


# =========================================================
# DOWNLOAD DE VÍDEO
# =========================================================

async def baixar_video(url):

    nome_base = limpar_nome_arquivo(
        f"video_{random.randint(1000, 9999)}"
    )

    caminho_base = os.path.join(
        DOWNLOADS_DIR,
        nome_base
    )

    opcoes = {
        "format": "bv*+ba/b",
        "outtmpl": caminho_base + ".%(ext)s",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        **YDL_RAPIDO,
    }

    if FFMPEG_PATH_REAL:
        opcoes["ffmpeg_location"] = (
            FFMPEG_PATH_REAL
        )

    def baixar():

        with yt_dlp.YoutubeDL(
            opcoes
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            arquivo = ydl.prepare_filename(
                info
            )

            mp4 = os.path.splitext(
                arquivo
            )[0] + ".mp4"

            if os.path.isfile(mp4):

                return mp4

            if os.path.isfile(arquivo):

                return arquivo

            # Procura o arquivo criado
            for nome in os.listdir(
                DOWNLOADS_DIR
            ):

                if nome.startswith(
                    nome_base
                ):

                    caminho = os.path.join(
                        DOWNLOADS_DIR,
                        nome
                    )

                    if os.path.isfile(
                        caminho
                    ):

                        return caminho

            return None

    try:

        return await asyncio.to_thread(
            baixar
        )

    except Exception as e:

        print(
            f"[Download] Erro vídeo: {e}"
        )

        return None


# =========================================================
# COMPRESSÃO DE VÍDEO
# =========================================================

async def comprimir_video(
    arquivo,
    crf=28
):

    if not FFMPEG_EXE:
        return arquivo

    nome, extensao = os.path.splitext(
        arquivo
    )

    saida = (
        nome
        + "_compressed"
        + ".mp4"
    )

    comando = [
        FFMPEG_EXE,
        "-y",
        "-i",
        arquivo,

        "-vf",
        "scale='min(1280,iw)':-2",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-threads",
        "0",

        "-crf",
        str(crf),

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-movflags",
        "+faststart",

        saida
    ]

    try:

        processo = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await processo.communicate()

        if processo.returncode != 0:

            print(
                "[FFmpeg] Erro:",
                stderr.decode(
                    errors="ignore"
                )
            )

            return arquivo

        if os.path.isfile(saida):

            if os.path.getsize(
                saida
            ) < os.path.getsize(
                arquivo
            ):

                try:
                    os.remove(
                        arquivo
                    )
                except:
                    pass

                return saida

            try:
                os.remove(
                    saida
                )
            except:
                pass

    except Exception as e:

        print(
            f"[FFmpeg] Erro compressão: {e}"
        )

    return arquivo


# =========================================================
# DOWNLOAD DE ÁUDIO
# =========================================================

async def baixar_audio(
    url,
    nome_final=None,
    titulo=None,
    artistas=None
):

    if not nome_final:

        nome_final = limpar_nome_arquivo(
            f"audio_{random.randint(1000, 9999)}"
        )

    nome_final = limpar_nome_arquivo(
        nome_final
    )

    caminho_saida = os.path.join(
        DOWNLOADS_DIR,
        nome_final + ".mp3"
    )

    # -----------------------------------------------------
    # Se já existe, remove
    # -----------------------------------------------------

    if os.path.exists(
        caminho_saida
    ):

        try:
            os.remove(
                caminho_saida
            )
        except:
            pass

    arquivo_temp = os.path.join(
        DOWNLOADS_DIR,
        f"temp_{random.randint(100000,999999)}"
    )

    opcoes = {
        "format": "bestaudio/best",
        "outtmpl": arquivo_temp + ".%(ext)s",

        "noplaylist": True,

        "quiet": True,
        "no_warnings": True,
        **YDL_RAPIDO,

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    if FFMPEG_PATH_REAL:

        opcoes[
            "ffmpeg_location"
        ] = FFMPEG_PATH_REAL

    def baixar():

        with yt_dlp.YoutubeDL(
            opcoes
        ) as ydl:

            ydl.download(
                [url]
            )

        possiveis = []

        for nome in os.listdir(
            DOWNLOADS_DIR
        ):

            if nome.startswith(
                os.path.basename(
                    arquivo_temp
                )
            ) and nome.lower().endswith(
                ".mp3"
            ):

                possiveis.append(
                    os.path.join(
                        DOWNLOADS_DIR,
                        nome
                    )
                )

        if not possiveis:

            return None

        arquivo = max(
            possiveis,
            key=os.path.getmtime
        )

        # -------------------------------------------------
        # Renomeia
        # -------------------------------------------------

        os.replace(
            arquivo,
            caminho_saida
        )

        return caminho_saida

    try:

        resultado = await asyncio.to_thread(
            baixar
        )

        if not resultado:
            return None

        # -------------------------------------------------
        # METADADOS DO MP3
        # -------------------------------------------------

        if titulo and artistas:

            await adicionar_metadados_mp3(
                resultado,
                titulo,
                artistas
            )

        return resultado

    except Exception as e:

        print(
            f"[Download] Erro áudio: {e}"
        )

        return None


# =========================================================
# METADADOS DO MP3
# =========================================================

async def adicionar_metadados_mp3(
    arquivo,
    titulo,
    artistas
):

    if not FFMPEG_EXE:
        return

    if not os.path.isfile(
        arquivo
    ):
        return

    arquivo_temp = (
        arquivo
        + ".metadata.mp3"
    )

    artista_texto = ", ".join(
        artistas
    )

    comando = [
        FFMPEG_EXE,
        "-y",

        "-i",
        arquivo,

        "-map",
        "0:a:0",

        "-c:a",
        "copy",

        "-metadata",
        f"title={titulo}",

        "-metadata",
        f"artist={artista_texto}",

        "-metadata",
        "album=Spotify",

        arquivo_temp
    ]

    try:

        processo = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await processo.communicate()

        if processo.returncode != 0:

            print(
                "[MP3] Erro ao adicionar metadados:"
            )

            print(
                stderr.decode(
                    errors="ignore"
                )
            )

            if os.path.exists(
                arquivo_temp
            ):

                try:
                    os.remove(
                        arquivo_temp
                    )
                except:
                    pass

            return

        if os.path.isfile(
            arquivo_temp
        ):

            os.replace(
                arquivo_temp,
                arquivo
            )

            print(
                "[MP3] Metadados adicionados!"
            )

    except Exception as e:

        print(
            f"[MP3] Erro metadados: {e}"
        )


# =========================================================
# SPOTIFY → YOUTUBE → MP3
# =========================================================

async def spotify_para_audio(
    url
):

    print(
        "======================================"
    )

    print(
        "[Spotify] Iniciando..."
    )

    info = await asyncio.to_thread(
        obter_info_spotify,
        url
    )

    if not info:

        print(
            "[Spotify] Não consegui pegar "
            "as informações da música."
        )

        return None

    titulo = info.get(
        "titulo"
    )

    artistas = info.get(
        "artistas",
        []
    )

    if not titulo:

        print(
            "[Spotify] Música sem título."
        )

        return None

    # -----------------------------------------------------
    # Se não encontrou artista, tenta usar o título inteiro
    # para o YouTube.
    # -----------------------------------------------------

    print(
        f"[Spotify] Título: {titulo}"
    )

    print(
        "[Spotify] Artistas:",
        ", ".join(
            artistas
        ) if artistas else "não identificado"
    )

    # -----------------------------------------------------
    # Pesquisa no YouTube
    # -----------------------------------------------------

    print(
        "[YouTube] Procurando música..."
    )

    resultado = await pesquisar_musica_youtube(
        titulo,
        artistas
    )

    if not resultado:

        print(
            "[YouTube] Não encontrei a música."
        )

        return None

    youtube_url = resultado.get(
        "url"
    )

    if not youtube_url:

        return None

    # -----------------------------------------------------
    # Nome do arquivo
    # -----------------------------------------------------

    if artistas:

        artista_texto = ", ".join(
            artistas
        )

    else:

        artista_texto = "Artista desconhecido"

    nome_arquivo = limpar_nome_arquivo(
        f"{artista_texto} - {titulo}"
    )

    print(
        f"[Spotify] Arquivo final: "
        f"{nome_arquivo}.mp3"
    )

    # -----------------------------------------------------
    # Baixa pelo YouTube
    # -----------------------------------------------------

    arquivo = await baixar_audio(
        youtube_url,
        nome_final=nome_arquivo,
        titulo=titulo,
        artistas=artistas
    )

    if not arquivo:

        print(
            "[Spotify] Falha ao baixar áudio."
        )

        return None

    print(
        f"[Spotify] Áudio pronto: {arquivo}"
    )

    print(
        "======================================"
    )

    return arquivo


# =========================================================
# PROCURAR LINK NO CONTEXTO
# =========================================================

async def procurar_link_contexto(
    message,
    ultimo_video=None
):
    """Encontra links no texto, em respostas e nos embeds recentes."""

    def link_suportado(url):
        if not url:
            return None

        url = extrair_url(url) or url.strip()

        if (
            eh_youtube(url)
            or eh_tiktok(url)
            or eh_instagram(url)
            or eh_spotify(url)
        ):
            return url

        return None

    def procurar_link_mensagem(msg):
        candidatos = []

        # URLs escritas na mensagem
        candidatos.extend(
            URL_REGEX.findall(msg.content or "")
        )

        # URLs guardadas nos embeds, inclusive no título clicável
        for embed in msg.embeds:
            if embed.url:
                candidatos.append(embed.url)

            if embed.author and embed.author.url:
                candidatos.append(embed.author.url)

            if embed.title:
                candidatos.extend(URL_REGEX.findall(embed.title))

            if embed.description:
                candidatos.extend(
                    URL_REGEX.findall(embed.description)
                )

            for campo in embed.fields:
                candidatos.extend(
                    URL_REGEX.findall(campo.value or "")
                )

        for candidato in candidatos:
            url = link_suportado(candidato)

            if url:
                return url

        return None

    # 1. Se respondeu a uma mensagem, verifica essa mensagem primeiro
    if message.reference and message.reference.message_id:
        try:
            mensagem_referenciada = (
                await message.channel.fetch_message(
                    message.reference.message_id
                )
            )

            link = procurar_link_mensagem(
                mensagem_referenciada
            )

            if link:
                return link

        except (discord.NotFound, discord.HTTPException) as erro:
            print(
                f"[Contexto] Erro ao ler resposta: {erro}"
            )

    # 2. Verifica a própria mensagem do comando
    link = procurar_link_mensagem(message)

    if link:
        return link

    # 3. Verifica o último vídeo guardado, se existir
    link = link_suportado(ultimo_video)

    if link:
        return link

    # 4. Procura nos resultados e nas mensagens recentes do canal
    try:
        async for msg in message.channel.history(
            limit=25,
            before=message
        ):
            link = procurar_link_mensagem(msg)

            if link:
                return link

    except discord.HTTPException as erro:
        print(
            f"[Contexto] Erro ao consultar histórico: {erro}"
        )

    return None

# =========================================================
# VIEW DO YOUTUBE
# =========================================================

class YouTubeSearchView(
    discord.ui.View
):

    def __init__(
        self,
        resultados,
        autor_id
    ):

        super().__init__(
            timeout=120
        )

        self.resultados = resultados
        self.autor_id = autor_id
        self.indice = 0

    def gerar_embed(self):

        item = self.resultados[
            self.indice
        ]

        embed = discord.Embed(
            title=item.get(
                "title",
                "YouTube"
            ),
            url=item.get(
                "url"
            ),
            color=discord.Color.from_str(
                "#6A00FF"
            )
        )

        thumbnail = item.get("thumbnail")
        if not thumbnail and item.get("id"):
            thumbnail = (
                f"https://i.ytimg.com/vi/"
                f"{item['id']}/hqdefault.jpg"
            )

        if thumbnail:
            embed.set_image(
                url=thumbnail
            )

        embed.set_footer(
            text=(
                f"Resultado "
                f"{self.indice + 1}/"
                f"{len(self.resultados)}"
            )
        )

        return embed

    @discord.ui.button(
        label="‹",
        style=discord.ButtonStyle.secondary
    )
    async def anterior(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if interaction.user.id != self.autor_id:

            await interaction.response.send_message(
                "❌ Esse painel não é seu.",
                ephemeral=True
            )

            return

        self.indice -= 1

        if self.indice < 0:

            self.indice = (
                len(self.resultados) - 1
            )

        await interaction.response.edit_message(
            embed=self.gerar_embed(),
            view=self
        )

    @discord.ui.button(
        label="›",
        style=discord.ButtonStyle.secondary
    )
    async def proximo(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if interaction.user.id != self.autor_id:

            await interaction.response.send_message(
                "❌ Esse painel não é seu.",
                ephemeral=True
            )

            return

        self.indice += 1

        if self.indice >= len(
            self.resultados
        ):

            self.indice = 0

        await interaction.response.edit_message(
            embed=self.gerar_embed(),
            view=self
        )


# =========================================================
# COG
# =========================================================

class Media(commands.Cog):

    def __init__(
        self,
        bot
    ):
        self.bot = bot

        # Sistema de música por servidor
        self.music_queues = {}
        self.music_tasks = {}
        self.music_current = {}
        self.music_votes = {}

    async def procurar_anexo_video(self, ctx):
        # Primeiro verifica se o comando tem anexo
        if ctx.message.attachments:
            return ctx.message.attachments[0]

        # Procura nas últimas 10 mensagens do canal
        async for mensagem in ctx.channel.history(
            limit=10,
            before=ctx.message
        ):
            if mensagem.attachments:
                for anexo in mensagem.attachments:
                    nome = anexo.filename.lower()
                    tipo = anexo.content_type or ""

                    if (
                        nome.endswith((".mp4", ".mov", ".webm", ".m4v",
                                       ".mp3", ".wav", ".ogg", ".m4a", ".flac"))
                        or tipo.startswith(("video/", "audio/"))
                    ):
                        return anexo

        return None


    async def _detectar_track_confiavel(self, arquivo_local):
        """Analisa cinco trechos e exige concordância entre resultados."""

        import unicodedata
        from collections import Counter
        from shazamio import Shazam

        if not FFMPEG_EXE or not os.path.isfile(arquivo_local):
            return None

        ffprobe = shutil.which("ffprobe")

        if not ffprobe:
            ffprobe = os.path.join(
                FFMPEG_PATH_REAL,
                "ffprobe.exe"
            )

        if not os.path.isfile(ffprobe):
            print("[Shazam] FFprobe não encontrado.")
            return None

        processo = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            arquivo_local,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await processo.communicate()

        if processo.returncode != 0:
            print(
                "[Shazam] Erro ao ler duração:",
                stderr.decode(errors="ignore")[-300:]
            )
            return None

        try:
            duracao = float(stdout.decode().strip())
        except (ValueError, TypeError):
            return None

        if duracao < 5:
            print("[Shazam] Áudio curto demais para analisar.")
            return None

        # Sempre cinco posições de análise.
        # Para vídeos curtos, alguns trechos podem se sobrepor.
        quantidade_trechos = 5
        tamanho_trecho = min(8.0, max(5.0, duracao / 5.0))
        inicio_maximo = max(0.0, duracao - tamanho_trecho)

        inicios = [
            round(
                inicio_maximo * indice / (quantidade_trechos - 1),
                3
            )
            for indice in range(quantidade_trechos)
        ]

        shazam = Shazam()
        resultados = []
        temporarios = []

        try:
            for indice, inicio in enumerate(inicios):
                trecho = os.path.join(
                    DOWNLOADS_DIR,
                    (
                        f"shazam_trecho_"
                        f"{random.randint(100000, 999999)}_"
                        f"{indice}.mp3"
                    )
                )

                temporarios.append(trecho)

                print(
                    f"[Shazam] Analisando trecho "
                    f"{indice + 1}/5, início: {inicio}s"
                )

                comando = [
                    FFMPEG_EXE,
                    "-y",
                    "-ss", str(inicio),
                    "-i", arquivo_local,
                    "-t", str(tamanho_trecho),
                    "-vn",
                    "-af", "bass=g=-12:f=100:w=0.7",
                    "-ac", "1",
                    "-ar", "44100",
                    "-b:a", "192k",
                    trecho
                ]

                processo = await asyncio.create_subprocess_exec(
                    *comando,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                _, stderr = await processo.communicate()

                if (
                    processo.returncode != 0
                    or not os.path.isfile(trecho)
                    or os.path.getsize(trecho) == 0
                ):
                    print(
                        f"[Shazam] Falha ao extrair trecho "
                        f"{indice + 1}/5: "
                        f"{stderr.decode(errors='ignore')[-300:]}"
                    )
                    continue

                try:
                    resposta = await shazam.recognize(trecho)
                    track = resposta.get("track") if resposta else None

                    if (
                        track
                        and track.get("title")
                        and track.get("subtitle")
                    ):
                        resultados.append(track)

                        print(
                            f"[Shazam] Resultado {indice + 1}/5: "
                            f"{track['title']} - {track['subtitle']}"
                        )
                    else:
                        print(
                            f"[Shazam] Trecho {indice + 1}/5: "
                            "nenhum resultado."
                        )

                except Exception as erro:
                    print(
                        f"[Shazam] Erro no trecho "
                        f"{indice + 1}/5: {erro}"
                    )

            # Uma única identificação não é suficiente.
            if len(resultados) < 2:
                print(
                    "[Shazam] Não houve resultados suficientes "
                    "para confirmar a música."
                )
                return None

            def normalizar(texto):
                texto = unicodedata.normalize(
                    "NFKD",
                    str(texto).lower()
                )

                return "".join(
                    caractere
                    for caractere in texto
                    if not unicodedata.combining(caractere)
                ).strip()

            def chave(track):
                identificador = track.get("key")

                if identificador is not None:
                    return ("id", str(identificador))

                return (
                    "texto",
                    normalizar(track.get("title", "")),
                    normalizar(track.get("subtitle", ""))
                )

            contagem = Counter(
                chave(track)
                for track in resultados
            )

            melhor_chave, quantidade = contagem.most_common(1)[0]

                       # Exige 3 identificações iguais entre os 5 trechos.
            # Se não houver confirmação suficiente, não arrisca.
            if quantidade < 3:
                print(
                    f"[Shazam] Resultado recusado: "
                    f"{quantidade} confirmações. "
                    "São necessárias pelo menos 3."
                )
                return None
                print(
                    "[Shazam] Resultado inconclusivo: "
                    f"{quantidade} de {len(resultados)} "
                    "identificações concordaram."
                )
                return None

            for track in reversed(resultados):
                if chave(track) == melhor_chave:
                    print(
                        f"[Shazam] Música confirmada: "
                        f"{track['title']} - {track['subtitle']} "
                        f"({quantidade} confirmações)"
                    )
                    return track

            return None

        finally:
            for temporario in temporarios:
                try:
                    if os.path.exists(temporario):
                        os.remove(temporario)
                except OSError:
                    pass
                
    # =====================================================
    # /youtube
    # =====================================================

    youtube = app_commands.Group(
        name="youtube",
        description="Ferramentas do YouTube"
    )

    @youtube.command(
        name="pesquisa",
        description="Pesquisa vídeos no YouTube"
    )
    @app_commands.describe(
        pesquisa="O que você quer pesquisar"
    )
    async def youtube_pesquisa(
        self,
        interaction: discord.Interaction,
        pesquisa: str
    ):

        await interaction.response.defer()

        resultados = await pesquisar_youtube(
            pesquisa
        )

        if not resultados:

            await interaction.followup.send(
                "❌ Não encontrei resultados."
            )

            return

        view = YouTubeSearchView(
            resultados,
            interaction.user.id
        )

        await interaction.followup.send(
            embed=view.gerar_embed(),
            view=view
        )

    # =====================================================
    # /extrair audio
    # =====================================================

    extrair = app_commands.Group(
        name="extrair",
        description="Extrair mídia"
    )

    @extrair.command(
        name="audio",
        description="Extrai o áudio de um link"
    )
    @app_commands.describe(
        link="Link do YouTube, TikTok, Instagram ou Spotify"
    )
    async def extrair_audio_slash(
        self,
        interaction: discord.Interaction,
        link: str = None
    ):

        await interaction.response.defer()

        if not link:

            await interaction.followup.send(
                "❌ Coloque o link da música/vídeo."
            )

            return

        await self.enviar_audio(
            interaction,
            link
        )

    # =====================================================
    # /download
    # =====================================================

    @app_commands.command(
        name="download",
        description="Baixa um vídeo"
    )
    @app_commands.describe(
        link="Link do vídeo"
    )
    async def download_slash(
        self,
        interaction: discord.Interaction,
        link: str
    ):

        await interaction.response.defer()

        if not (
            eh_youtube(link)
            or eh_tiktok(link)
            or eh_instagram(link)
        ):

            await interaction.followup.send(
                "❌ Esse link não parece ser um vídeo válido."
            )

            return

        arquivo = await baixar_video(
            link
        )

        if not arquivo:

            await interaction.followup.send(
                "❌ Não consegui baixar o vídeo."
            )

            return

        tamanho = os.path.getsize(
            arquivo
        )

        # =================================================
        # COMPRIME SE PASSAR DO LIMITE
        # =================================================

        if tamanho > LIMITE_DISCORD:

            await interaction.followup.send(
                "⏳ O vídeo ficou grande, vou tentar comprimir..."
            )

            arquivo = await comprimir_video(
                arquivo,
                28
            )

            tamanho = os.path.getsize(
                arquivo
            )

        if tamanho > LIMITE_DISCORD:

            arquivo = await comprimir_video(
                arquivo,
                31
            )

            tamanho = os.path.getsize(
                arquivo
            )

        if tamanho > LIMITE_DISCORD:

            try:
                os.remove(
                    arquivo
                )
            except:
                pass

            await interaction.followup.send(
                "❌ O vídeo continua maior que o limite do Discord."
            )

            return

        try:
            link_publico = await enviar_video_para_zyrenn(arquivo)
            await interaction.followup.send(
                content=f"🎬 **Vídeo baixado!**\n[Assistir em zyrenn.gg]({link_publico})"
            )
        except Exception as e:
            print(f"[Zyrenn Videos] Erro enviando vídeo: {e}")
            await interaction.followup.send(
                f"❌ Não consegui hospedar o vídeo: {str(e)[:300]}"
            )
        finally:
            try:
                if os.path.exists(arquivo):
                    os.remove(arquivo)
            except OSError:
                pass

    # =====================================================
    # PREFIXO -DL
    # =====================================================

    @commands.command(
        name="dl",
        aliases=[
            "download"
        ]
    )
    async def dl_prefix(
        self,
        ctx,
        link: str = None
    ):

        if not link:

            link = await procurar_link_contexto(
                ctx.message
            )

        if not link:

            await ctx.send(
                "❌ Manda um link ou responde uma mensagem que tenha um link."
            )

            return

        if not (
            eh_youtube(link)
            or eh_tiktok(link)
            or eh_instagram(link)
        ):

            await ctx.send(
                "❌ Esse link não parece ser um vídeo."
            )

            return

        msg = await ctx.send(
            "⏳ Baixando vídeo..."
        )

        arquivo = await baixar_video(
            link
        )

        if not arquivo:

            await msg.edit(
                content="❌ Não consegui baixar o vídeo."
            )

            return

        tamanho = os.path.getsize(
            arquivo
        )

        if tamanho > LIMITE_DISCORD:

            await msg.edit(
                content=(
                    "⏳ O vídeo ficou grande, "
                    "comprimindo..."
                )
            )

            arquivo = await comprimir_video(
                arquivo,
                28
            )

            tamanho = os.path.getsize(
                arquivo
            )

        if tamanho > LIMITE_DISCORD:

            arquivo = await comprimir_video(
                arquivo,
                31
            )

            tamanho = os.path.getsize(
                arquivo
            )

        if tamanho > LIMITE_DISCORD:

            try:
                os.remove(
                    arquivo
                )
            except:
                pass

            await msg.edit(
                content=(
                    "❌ O vídeo continua maior "
                    "que o limite do Discord."
                )
            )

            return

        try:

            await msg.delete()

        except:
            pass

        try:
            link_publico = await enviar_video_para_zyrenn(arquivo)
            await ctx.send(
                content=f"🎬 **Vídeo baixado!**\n[Assistir em zyrenn.gg]({link_publico})"
            )
        except Exception as e:
            print(f"[Zyrenn Videos] Erro enviando vídeo: {e}")
            await ctx.send(
                f"❌ Não consegui hospedar o vídeo: {str(e)[:300]}"
            )
        finally:
            try:
                if os.path.exists(arquivo):
                    os.remove(arquivo)
            except OSError:
                pass

    # =====================================================
    # PREFIXO -EXTRAIR AUDIO
    # =====================================================

    @commands.command(
        name="extrair",
        aliases=[
            "extract"
        ]
    )
    async def extrair_prefix(
        self,
        ctx,
        tipo: str = None,
        link: str = None
    ):

        # -------------------------------------------------
        # Aceita:
        #
        # -extrair audio LINK
        # -extract audio LINK
        # -------------------------------------------------

        if not tipo:

            await ctx.send(
                "❌ Use: `-extrair audio LINK`"
            )

            return

        if tipo.lower() not in [
            "audio",
            "áudio"
        ]:

            await ctx.send(
                "❌ Use: `-extrair audio LINK`"
            )

            return

        if not link:

            link = await procurar_link_contexto(
                ctx.message,
                ULTIMOS_VIDEOS.get(
                    ctx.channel.id
                )
            )

        if not link:

            await ctx.send(
                "❌ Manda um link ou responde uma mensagem com um link."
            )

            return

        await self.enviar_audio(
            ctx,
            link
        )

    # =====================================================
    # ENVIAR ÁUDIO
    # =====================================================

    async def enviar_audio(
        self,
        origem,
        url
    ):

        url = extrair_url(
            url
        )

        if not url:

            mensagem = (
                "❌ Não encontrei um link válido."
            )

            if isinstance(
                origem,
                discord.Interaction
            ):

                await origem.followup.send(
                    mensagem
                )

            else:

                await origem.send(
                    mensagem
                )

            return

        # =================================================
        # SPOTIFY
        # =================================================

        if eh_spotify(url):

            if isinstance(
                origem,
                discord.Interaction
            ):

                status = await origem.followup.send(
                    "⏳ Pegando informações do Spotify e procurando no YouTube..."
                )

            else:

                status = await origem.send(
                    "⏳ Pegando informações do Spotify e procurando no YouTube..."
                )

            arquivo = await spotify_para_audio(
                url
            )

            if not arquivo:

                mensagem = (
                    "❌ Não consegui identificar "
                    "ou encontrar essa música."
                )

                try:

                    await status.edit(
                        content=mensagem
                    )

                except:

                    if isinstance(
                        origem,
                        discord.Interaction
                    ):

                        await origem.followup.send(
                            mensagem
                        )

                    else:

                        await origem.send(
                            mensagem
                        )

                return

            try:

                await status.delete()

            except:
                pass

            # ---------------------------------------------
            # Tamanho
            # ---------------------------------------------

            if os.path.getsize(
                arquivo
            ) > LIMITE_DISCORD:

                try:
                    os.remove(
                        arquivo
                    )
                except:
                    pass

                mensagem = (
                    "❌ O MP3 ficou maior que "
                    "o limite permitido."
                )

                if isinstance(
                    origem,
                    discord.Interaction
                ):

                    await origem.followup.send(
                        mensagem
                    )

                else:

                    await origem.send(
                        mensagem
                    )

                return

            try:

                arquivo_discord = discord.File(
                    arquivo,
                    filename=os.path.basename(
                        arquivo
                    )
                )

                if isinstance(
                    origem,
                    discord.Interaction
                ):

                    await origem.followup.send(
                        content="🎵 Áudio extraído!",
                        file=arquivo_discord
                    )

                else:

                    await origem.send(
                        content="🎵 Áudio extraído!",
                        file=arquivo_discord
                    )

            except Exception as e:

                print(
                    f"[Discord] Erro enviando Spotify: {e}"
                )

                mensagem = (
                    "❌ Não consegui enviar o MP3."
                )

                if isinstance(
                    origem,
                    discord.Interaction
                ):

                    await origem.followup.send(
                        mensagem
                    )

                else:

                    await origem.send(
                        mensagem
                    )

            finally:

                try:

                    if os.path.exists(
                        arquivo
                    ):

                        os.remove(
                            arquivo
                        )

                except:
                    pass

            return

        # =================================================
        # YOUTUBE / TIKTOK / INSTAGRAM
        # =================================================

        if not (
            eh_youtube(url)
            or eh_tiktok(url)
            or eh_instagram(url)
        ):

            mensagem = (
                "❌ Esse link não é de "
                "YouTube, TikTok, Instagram ou Spotify."
            )

            if isinstance(
                origem,
                discord.Interaction
            ):

                await origem.followup.send(
                    mensagem
                )

            else:

                await origem.send(
                    mensagem
                )

            return

        if isinstance(
            origem,
            discord.Interaction
        ):

            status = await origem.followup.send(
                "⏳ Extraindo áudio..."
            )

        else:

            status = await origem.send(
                "⏳ Extraindo áudio..."
            )

        arquivo = await baixar_audio(
            url
        )

        if not arquivo:

            try:

                await status.edit(
                    content="❌ Não consegui extrair o áudio."
                )

            except:
                pass

            return

        # =================================================
        # TAMANHO
        # =================================================

        if os.path.getsize(
            arquivo
        ) > LIMITE_DISCORD:

            try:
                os.remove(
                    arquivo
                )
            except:
                pass

            try:

                await status.edit(
                    content=(
                        "❌ O MP3 ficou maior que "
                        "o limite do Discord."
                    )
                )

            except:
                pass

            return

        try:

            await status.delete()

        except:
            pass

        # =================================================
        # ENVIA SEM EMBED
        # =================================================

        try:

            arquivo_discord = discord.File(
                arquivo,
                filename=os.path.basename(
                    arquivo
                )
            )

            if isinstance(
                origem,
                discord.Interaction
            ):

                await origem.followup.send(
                    content="🎵 Áudio extraído!",
                    file=arquivo_discord
                )

            else:

                await origem.send(
                    content="🎵 Áudio extraído!",
                    file=arquivo_discord
                )

        except Exception as e:

            print(
                f"[Discord] Erro enviando áudio: {e}"
            )

            mensagem = (
                "❌ Não consegui enviar o MP3."
            )

            if isinstance(
                origem,
                discord.Interaction
            ):

                await origem.followup.send(
                    mensagem
                )

            else:

                await origem.send(
                    mensagem
                )

        finally:

            try:

                if os.path.exists(
                    arquivo
                ):

                    os.remove(
                        arquivo
                    )

            except:
                pass

    # =====================================================
    # /detectar audio
    # =====================================================

    detectar = app_commands.Group(
        name="detectar",
        description="Ferramentas para detectar músicas"
    )

    @detectar.command(
        name="audio",
        description="Identifica uma música em um áudio ou vídeo"
    )
    @app_commands.describe(
        arquivo="Envie um áudio ou vídeo",
        link="Ou coloque um link de áudio/vídeo"
    )
    async def detectar_audio_slash(
        self,
        interaction: discord.Interaction,
        arquivo: discord.Attachment = None,
        link: str = None
    ):

        await interaction.response.defer()

        arquivo_local = None

        try:

            # =================================================
            # ANEXO
            # =================================================

            if arquivo:

                nome = limpar_nome_arquivo(
                    arquivo.filename
                )

                arquivo_local = os.path.join(
                    DOWNLOADS_DIR,
                    f"shazam_{random.randint(100000, 999999)}_{nome}"
                )

                await arquivo.save(
                    arquivo_local
                )

            # =================================================
            # LINK
            # =================================================

            elif link:

                url = extrair_url(link)

                if not url:

                    await interaction.followup.send(
                        "❌ Não encontrei um link válido."
                    )

                    return

                status = await interaction.followup.send(
                    "⏳ Baixando o áudio..."
                )

                arquivo_local = await baixar_audio(
                    url
                )

                try:
                    await status.delete()
                except:
                    pass

                if not arquivo_local:

                    await interaction.followup.send(
                        "❌ Não consegui baixar o áudio desse link."
                    )

                    return

            else:

                await interaction.followup.send(
                    "❌ Envie um áudio/vídeo ou coloque um link."
                )

                return

            # =================================================
            # CONVERTER VÍDEO/ÁUDIO PARA MP3
            # =================================================

            status = await interaction.followup.send(
                "🔎 Procurando a música..."
            )

            if not FFMPEG_EXE:

                await status.edit(
                    content="❌ FFmpeg não foi encontrado."
                )

                return

            arquivo_shazam = os.path.join(
                DOWNLOADS_DIR,
                f"shazam_audio_{random.randint(100000, 999999)}.mp3"
            )

            comando = [
                FFMPEG_EXE,
                "-y",
                "-i",
                arquivo_local,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "44100",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                arquivo_shazam
            ]

            processo = await asyncio.create_subprocess_exec(
                *comando,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await processo.communicate()

            if processo.returncode != 0:

                print(
                    "[Shazam] Erro FFmpeg:",
                    stderr.decode(errors="ignore")
                )

                await status.edit(
                    content="❌ Não consegui extrair o áudio."
                )

                return

            # =================================================
            # SHAZAM
            # =================================================

            track = await self._detectar_track_confiavel(
    arquivo_local
            )

            if not track:
                embed_erro = discord.Embed(
                    title="🎵 Música não encontrada",
                    description=(
                        "Não consegui identificar a música com confiança.\n\n"
                        "Tente enviar outro trecho do áudio ou vídeo."
                    ),
                    color=discord.Color.from_str("#6A00FF")
                )

                await status.edit(
                    content=None,
                    embed=embed_erro
                )
                return

            # =================================================
            # INFORMAÇÕES
            # =================================================

            titulo = track.get(
                "title",
                "Não encontrado"
            )

            artista = track.get(
                "subtitle",
                "Não encontrado"
            )

            data = track.get(
                "releasedate"
            ) or "Não encontrada"

            capa = (
                track.get(
                    "images",
                    {}
                ).get(
                    "coverarthq"
                )
                or
                track.get(
                    "images",
                    {}
                ).get(
                    "coverart"
                )
            )

            album = "Não encontrado"
            gravadora = "Não encontrada"

            # =================================================
            # METADADOS
            # =================================================

            for section in track.get(
                "sections",
                []
            ):

                for item in section.get(
                    "metadata",
                    []
                ):

                    nome = item.get(
                        "title",
                        ""
                    ).lower()

                    valor = item.get(
                        "text"
                    )

                    if not valor:
                        continue

                    if nome in [
                        "album",
                        "álbum"
                    ]:

                        album = valor

                    elif nome in [
                        "label",
                        "gravadora"
                    ]:

                        gravadora = valor

            # =================================================
            # EMBED
            # =================================================

            embed = discord.Embed(
                title="🎵 Música encontrada!",
                description=(
                    f"**{titulo}**\n"
                    f"por **{artista}**"
                ),
                color=discord.Color.from_str(
                    "#6A00FF"
                )
            )

            embed.add_field(
                name="🎤 Artista",
                value=artista,
                inline=True
            )

            embed.add_field(
                name="💿 Álbum",
                value=album,
                inline=True
            )

            embed.add_field(
                name="📅 Data",
                value=data,
                inline=True
            )

            embed.add_field(
                name="🏷️ Gravadora",
                value=gravadora,
                inline=True
            )

            if capa:

                embed.set_thumbnail(
                    url=capa
                )

            link_shazam = (
                track.get(
                    "share",
                    {}
                ).get(
                    "href"
                )
            )

            if link_shazam:

                embed.url = link_shazam

            embed.set_footer(
                text="Identificado pelo Shazam"
            )

            await status.delete()

            await interaction.followup.send(
                embed=embed
            )

        except Exception as e:

            print(
                f"[Shazam] Erro: {e}"
            )

            try:

                await interaction.followup.send(
                    "❌ Ocorreu um erro ao tentar identificar a música."
                )

            except:
                pass

        finally:

            # =================================================
            # LIMPEZA
            # =================================================

            for arquivo_temp in [
                arquivo_local,
                locals().get("arquivo_shazam")
            ]:

                if arquivo_temp:

                    try:

                        if os.path.exists(
                            arquivo_temp
                        ):

                            os.remove(
                                arquivo_temp
                            )

                    except:
                        pass

    # =====================================================
    # -detectar audio
    # =====================================================

    @commands.group(
        name="detectar",
        invoke_without_command=True
    )
    async def detectar_prefix(
        self,
        ctx,
        *,
        link: str = None
    ):
        await self.detectar_audio_prefix(
            ctx,
            link=link
        )

    @detectar_prefix.command(
        name="audio"
    )
    async def detectar_audio_prefix(
        self,
        ctx,
        *,
        link: str = None
    ):
        arquivo_local = None
        status = None

        try:
            # =============================================
            # ANEXO: ÁUDIO OU VÍDEO
            # =============================================

                        # =============================================
            # PROCURAR ANEXO NA MENSAGEM ATUAL OU ANTERIOR
            # =============================================

            anexo = await self.procurar_anexo_video(ctx)

            if anexo:
                nome = limpar_nome_arquivo(anexo.filename)

                arquivo_local = os.path.join(
                    DOWNLOADS_DIR,
                    f"shazam_{random.randint(100000, 999999)}_{nome}"
                )

                await anexo.save(arquivo_local)

                print(f"[Shazam] Anexo recebido: {anexo.filename}")

            else:
                if not link:
                    link = await procurar_link_contexto(
                        ctx.message,
                        ULTIMOS_VIDEOS.get(ctx.channel.id)
                    )

                if not link:
                    await ctx.send(
                        "❌ Não encontrei áudio, vídeo ou link nas mensagens recentes."
                    )
                    return

                url = extrair_url(link)

                if not url:
                    await ctx.send(
                        "❌ Não encontrei um link válido."
                    )
                    return

                status = await ctx.send("⏳ Baixando o áudio...")

                arquivo_local = await baixar_audio(url)

                try:
                    await status.delete()
                except discord.HTTPException:
                    pass

                status = None

                if not arquivo_local:
                    await ctx.send(
                        "❌ Não consegui baixar o áudio desse link."
                    )
                    return
                
            # =============================================
            # IDENTIFICAR MÚSICA
            # =============================================

            status = await ctx.send(
                "🔎 Procurando a música..."
            )

            track = await self._detectar_track_confiavel(
                arquivo_local
            )

            if not track:
                embed_erro = discord.Embed(
                    title="🎵 Música não encontrada",
                    description=(
                        "Não consegui identificar a música com confiança.\n\n"
                        "Tente enviar outro trecho do áudio ou vídeo."
                    ),
                    color=discord.Color.from_str("#6A00FF")
                )

                if status:
                    await status.edit(
                        content=None,
                        embed=embed_erro
                    )

                    # Impede o finally de apagar o embed
                    status = None
                else:
                    await ctx.send(embed=embed_erro)

                return
        
            # =============================================
            # DADOS DA MÚSICA
            # =============================================

            titulo = track.get("title", "Não encontrado")
            artista = track.get("subtitle", "Não encontrado")
            data = track.get("releasedate") or "Não encontrada"

            imagens = track.get("images", {})
            capa = (
                imagens.get("coverarthq")
                or imagens.get("coverart")
            )

            album = "Não encontrado"
            gravadora = "Não encontrada"

            for section in track.get("sections", []):
                for item in section.get("metadata", []):
                    nome_item = item.get("title", "").lower()
                    valor = item.get("text")

                    if nome_item in ["album", "álbum"] and valor:
                        album = valor

                    elif nome_item in ["label", "gravadora"] and valor:
                        gravadora = valor

            embed = discord.Embed(
                title="🎵 Música encontrada!",
                description=(
                    f"**{titulo}**\n"
                    f"por **{artista}**"
                ),
                color=discord.Color.from_str("#6A00FF")
            )

            embed.add_field(
                name="🎤 Artista",
                value=artista,
                inline=True
            )

            embed.add_field(
                name="💿 Álbum",
                value=album,
                inline=True
            )

            embed.add_field(
                name="📅 Data",
                value=data,
                inline=True
            )

            embed.add_field(
                name="🏷️ Gravadora",
                value=gravadora,
                inline=True
            )

            if capa:
                embed.set_thumbnail(url=capa)

            link_shazam = track.get("share", {}).get("href")

            if link_shazam:
                embed.url = link_shazam

            embed.set_footer(
                text="Identificado pelo Shazam"
            )

            await status.delete()
            status = None

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"[Shazam] Erro prefixo: {e}")

            await ctx.send(
                "❌ Ocorreu um erro ao tentar identificar a música."
            )

        finally:
            if status:
                try:
                    await status.delete()
                except Exception:
                    pass

            if arquivo_local:
                try:
                    if os.path.exists(arquivo_local):
                        os.remove(arquivo_local)
                except OSError:
                    pass


    # =====================================================
    # SISTEMA DE MÚSICA - FILA E REPRODUÇÃO
    # =====================================================

    def _music_resolve_stream(self, video_url):
        em_cache = _cache_get(_CACHE_STREAM, video_url, _TTL_STREAM)
        if em_cache is not None:
            return em_cache
        resultado = self._music_resolve_stream_raw(video_url)
        _cache_set(_CACHE_STREAM, video_url, resultado)
        return resultado

    def _music_resolve_stream_raw(self, video_url):
        """Obtém a URL direta do áudio usando yt-dlp."""

        opcoes = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            **YDL_RAPIDO,
        }

        if FFMPEG_PATH_REAL:
            opcoes["ffmpeg_location"] = FFMPEG_PATH_REAL

        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = ydl.extract_info(
                video_url,
                download=False
            )

        if not info:
            raise RuntimeError("Não consegui abrir o vídeo.")

        if info.get("entries"):
            info = next(
                (
                    item for item in info["entries"]
                    if item
                ),
                None
            )

        if not info:
            raise RuntimeError("Nenhum vídeo encontrado.")

        stream_url = info.get("url")

        if not stream_url:
            formatos = [
                formato
                for formato in info.get("formats", [])
                if formato.get("url")
                and formato.get("acodec") not in (None, "none")
            ]

            formatos.sort(
                key=lambda formato: formato.get("abr") or 0
            )

            if formatos:
                stream_url = formatos[-1]["url"]

        if not stream_url:
            raise RuntimeError("Não encontrei o áudio do vídeo.")

        return stream_url, info.get("title", "Música desconhecida")

    async def _music_get_control_voice(self, ctx):
        """Confere se o usuário está na call em que o bot está."""

        if not ctx.guild:
            await ctx.send(
                "❌ Esse comando só funciona dentro de um servidor."
            )
            return None

        estado = getattr(ctx.author, "voice", None)

        if not estado or not estado.channel:
            await ctx.send(
                "❌ Entre na call primeiro."
            )
            return None

        voice = ctx.guild.voice_client

        if not voice or not voice.is_connected():
            await ctx.send(
                "❌ O bot não está em uma call."
            )
            return None

        if estado.channel != voice.channel:
            await ctx.send(
                "❌ Você precisa estar na mesma call que o bot."
            )
            return None

        return voice

    async def _music_player_loop(self, guild):
        """Toca cada música da fila e espera até ela terminar."""

        guild_id = guild.id

        fila = self.music_queues.setdefault(
            guild_id,
            asyncio.Queue()
        )

        while True:
            musica = await fila.get()

            try:
                voice = guild.voice_client

                if not voice or not voice.is_connected():
                    await musica["canal"].send(
                        "❌ O bot saiu da call. "
                        "Use `-play.m` novamente depois de reconectar."
                    )
                    continue

                self.music_current[guild_id] = musica
                self.music_votes[guild_id] = set()

                # Obtém o áudio do YouTube sem baixar o vídeo inteiro.
                stream_url, titulo_real = await asyncio.to_thread(
                    self._music_resolve_stream,
                    musica["url"]
                )

                voice = guild.voice_client

                if not voice or not voice.is_connected():
                    continue

                fonte = discord.FFmpegOpusAudio(
                    stream_url,
                    executable=FFMPEG_EXE or "ffmpeg",
                    before_options=(
                        "-reconnect 1 "
                        "-reconnect_streamed 1 "
                        "-reconnect_delay_max 5"
                    ),
                    options="-vn"
                )

                loop = asyncio.get_running_loop()
                terminou = loop.create_future()

                def depois_de_tocar(erro):
                    def resolver():
                        if not terminou.done():
                            terminou.set_result(erro)

                    loop.call_soon_threadsafe(resolver)

                voice.play(
                    fonte,
                    after=depois_de_tocar
                )

                try:
                    await musica["canal"].send(
                        f"🎶 **Tocando agora:** {musica['titulo']}\n"
                        f"👤 Pedido por: {musica['autor_nome']}"
                    )
                except discord.HTTPException:
                    pass

                erro = await terminou

                if erro:
                    print(
                        f"[Música] Erro ao reproduzir: {erro}"
                    )

            except Exception as erro:
                print(
                    f"[Música] Erro na fila: {erro}"
                )

                try:
                    await musica["canal"].send(
                        "❌ Não consegui reproduzir essa música. "
                        "Vou tentar a próxima da fila."
                    )
                except discord.HTTPException:
                    pass

            finally:
                if self.music_current.get(guild_id) is musica:
                    self.music_current.pop(guild_id, None)

                self.music_votes.pop(guild_id, None)

                fila.task_done()

    # =====================================================
    # -PLAY.M
    # =====================================================

    @commands.command(name="play.m")
    async def play_m(self, ctx, *, pesquisa: str = None):

        if not ctx.guild:
            return

        if not pesquisa:
            await ctx.send(
                "❌ Use: `-play.m nome da música`"
            )
            return

        estado = getattr(ctx.author, "voice", None)

        if not estado or not estado.channel:
            await ctx.send(
                "❌ Entre na call primeiro."
            )
            return

        await ctx.send(
            "🔎 Procurando a música no YouTube..."
        )

        resultados = await pesquisar_youtube(pesquisa)

        if not resultados:
            await ctx.send(
                "❌ Não encontrei essa música no YouTube."
            )
            return

        item = resultados[0]
        guild_id = ctx.guild.id

        voice = ctx.guild.voice_client

        if voice and not voice.is_connected():
            try:
                await voice.disconnect(force=True)
            except Exception:
                pass

            voice = None

        if voice:
            if voice.channel != estado.channel:
                await ctx.send(
                    "❌ Já estou tocando em outra call."
                )
                return
        else:
            try:
                # O bot entra surdo para não ouvir os membros.
                voice = await estado.channel.connect(
                    self_deaf=True
                )

            except Exception as erro:
                print(f"[Música] Erro ao entrar na call: {erro}")

                await ctx.send(
                    "❌ Não consegui entrar na call. "
                    "Confira minhas permissões de voz."
                )
                return

        fila = self.music_queues.setdefault(
            guild_id,
            asyncio.Queue()
        )

        musica = {
            "url": item["url"],
            "titulo": item.get("title", pesquisa),
            "autor_id": ctx.author.id,
            "autor_nome": ctx.author.display_name,
            "canal": ctx.channel,
        }

        fila.put_nowait(musica)

        tarefa = self.music_tasks.get(guild_id)

        if tarefa is None or tarefa.done():
            self.music_tasks[guild_id] = asyncio.create_task(
                self._music_player_loop(ctx.guild)
            )

        posicao = fila.qsize()

        await ctx.send(
            f"✅ Música adicionada à fila!\n"
            f"🎵 **{musica['titulo']}**\n"
            f"📍 Posição na fila: {posicao}"
        )

    # =====================================================
    # -PAUSE.M
    # =====================================================

    @commands.command(name="pause.m")
    async def pause_m(self, ctx):

        voice = await self._music_get_control_voice(ctx)

        if not voice:
            return

        if voice.is_paused():
            await ctx.send(
                "⏸️ A música já está pausada."
            )
            return

        if not voice.is_playing():
            await ctx.send(
                "❌ Não tem música tocando agora."
            )
            return

        voice.pause()

        await ctx.send(
            "⏸️ Música pausada!"
        )

    # =====================================================
    # -UNPAUSE.M
    # =====================================================

    @commands.command(name="unpause.m")
    async def unpause_m(self, ctx):

        voice = await self._music_get_control_voice(ctx)

        if not voice:
            return

        if not voice.is_paused():
            await ctx.send(
                "❌ A música não está pausada."
            )
            return

        voice.resume()

        await ctx.send(
            "▶️ Música retomada do mesmo ponto!"
        )

    # =====================================================
    # -SKIP.M
    # =====================================================

    @commands.command(name="skip.m")
    async def skip_m(self, ctx):

        voice = await self._music_get_control_voice(ctx)

        if not voice:
            return

        guild_id = ctx.guild.id
        musica = self.music_current.get(guild_id)

        if not musica or not (
            voice.is_playing() or voice.is_paused()
        ):
            await ctx.send(
                "❌ Não tem música tocando para pular."
            )
            return

        # Quem pediu a música pode pular diretamente.
        if ctx.author.id == musica["autor_id"]:
            self.music_votes[guild_id] = set()

            voice.stop()

            await ctx.send(
                "⏭️ O autor pulou a música!"
            )
            return

        # Os votos só contam entre as pessoas da call.
        membros = [
            membro
            for membro in voice.channel.members
            if not membro.bot
        ]

        quantidade_pessoas = len(membros)

        # Exemplo: 5 pessoas na call = 4 votos necessários.
        votos_necessarios = max(
            1,
            quantidade_pessoas - 1
        )

        votos = self.music_votes.setdefault(
            guild_id,
            set()
        )

        if ctx.author.id in votos:
            await ctx.send(
                "🗳️ Você já votou para pular essa música."
            )
            return

        votos.add(ctx.author.id)

        quantidade_votos = len(votos)

        if quantidade_votos >= votos_necessarios:
            self.music_votes[guild_id] = set()

            voice.stop()

            await ctx.send(
                f"⏭️ Música pulada por votação! "
                f"({quantidade_votos}/{votos_necessarios} votos)"
            )

        else:
            await ctx.send(
                f"🗳️ Voto registrado: "
                f"**{quantidade_votos}/{votos_necessarios}**\n"
                f"Faltam **{votos_necessarios - quantidade_votos}** votos."
            )

    # =====================================================
    # -LEAVE.M
    # =====================================================

    @commands.command(name="leave.m")
    async def leave_m(self, ctx):

        if not ctx.guild:
            return

        voice = ctx.guild.voice_client

        if not voice or not voice.is_connected():
            await ctx.send(
                "❌ Não estou em nenhuma call."
            )
            return

        estado = getattr(ctx.author, "voice", None)

        if not estado or estado.channel != voice.channel:
            await ctx.send(
                "❌ Você precisa estar na mesma call que eu."
            )
            return

        guild_id = ctx.guild.id

        # Para a música atual
        if voice.is_playing() or voice.is_paused():
            voice.stop()

        # Encerra a tarefa responsável pela fila
        tarefa = self.music_tasks.get(guild_id)

        if tarefa and not tarefa.done():
            tarefa.cancel()

            try:
                await tarefa
            except asyncio.CancelledError:
                pass
            except Exception as erro:
                print(
                    f"[Música] Erro ao encerrar a fila: {erro}"
                )

        # Limpa as músicas que ainda estavam na fila
        fila = self.music_queues.get(guild_id)

        if fila:
            while not fila.empty():
                try:
                    fila.get_nowait()
                    fila.task_done()
                except asyncio.QueueEmpty:
                    break

        # Limpa o estado do sistema de música
        self.music_queues.pop(guild_id, None)
        self.music_tasks.pop(guild_id, None)
        self.music_current.pop(guild_id, None)
        self.music_votes.pop(guild_id, None)

        # Sai da call
        try:
            await voice.disconnect(force=True)

            await ctx.send(
                "👋 Saí da call e limpei a fila de músicas!"
            )

        except Exception as erro:
            print(
                f"[Música] Erro ao sair da call: {erro}"
            )

            await ctx.send(
                "❌ Não consegui sair da call."
            )

# =========================================================
# SETUP
# =========================================================

async def setup(
    bot
):

    await bot.add_cog(
        Media(bot)
    )

    print(
        "Cog carregado: media.py"
    )