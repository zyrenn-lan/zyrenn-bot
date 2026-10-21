import asyncio
import io
import os
import threading
import unicodedata
from datetime import datetime, timezone, timedelta
from functools import lru_cache

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont


# =========================================================
# CONFIGURAÇÃO
# =========================================================

LOG_CHANNEL_ID = 1561580334104055910

# Horário de Brasília (UTC-3), sem depender do tzdata do Windows.
FUSO = timezone(timedelta(hours=-3))

# Avisa o criador.py que este arquivo já desenha o cartão de sugestão.
SUPORTA_SUGESTAO = True

# ---------------------------------------------------------
# FONTES
# ---------------------------------------------------------
# As imagens usam a fonte Lato. Baixe em fonts.google.com/specimen/Lato e
# coloque estes dois arquivos na pasta "fonts" (ao lado deste logs.py):
#     fonts/Lato-Regular.ttf
#     fonts/Lato-Bold.ttf
#
# Nomes com símbolos/estilos especiais (𝓓𝓪𝓿𝔂, ᴅᴇᴠ, ★, ┃, ▪ ...) funcionam
# por "fallback": cada caractere que a Lato não tem é procurado nas outras
# fontes. Qualquer .ttf/.otf que você colocar na pasta "fonts" entra
# automaticamente como reserva (ex.: NotoSansSymbols2-Regular.ttf,
# NotoSansMath-Regular.ttf, NotoSansSymbols-Regular.ttf, Unifont).
# Caracteres que nenhuma fonte tiver (emojis, por exemplo) são omitidos em
# vez de aparecerem como quadradinhos.
PASTA_FONTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

FONTES_SISTEMA = [
    "DejaVuSans.ttf", "NotoSans-Regular.ttf", "NotoSansSymbols-Regular.ttf",
    "NotoSansSymbols2-Regular.ttf", "NotoSansMath-Regular.ttf",
    "FreeSans.ttf", "LiberationSans-Regular.ttf", "Unifont.ttf",
    "NotoSansCJK-Regular.ttc", "arial.ttf", "seguisym.ttf", "segoeui.ttf",
    "msyh.ttc", "malgun.ttf",
]
FONTES_SISTEMA_BOLD = [
    "DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf", "NotoSansSymbols-Regular.ttf",
    "NotoSansSymbols2-Regular.ttf", "NotoSansMath-Regular.ttf",
    "FreeSansBold.ttf", "LiberationSans-Bold.ttf", "Unifont.ttf",
    "NotoSansCJK-Bold.ttc", "arialbd.ttf", "seguisym.ttf", "segoeuib.ttf",
    "msyhbd.ttc", "malgunbd.ttf",
]

# ---------------------------------------------------------
# CORES (RGB) — medidas a partir das imagens de referência
# ---------------------------------------------------------
COR_FUNDO = (49, 51, 56)

COR_VERMELHO = (250, 64, 68)
COR_FUNDO_VERMELHO = (68, 52, 57)
COR_VERDE = (35, 168, 90)
COR_FUNDO_VERDE = (48, 62, 59)

COR_NOME = (255, 255, 255)
COR_MENSAGEM = (225, 229, 232)
COR_MUTED = (181, 186, 193)
COR_ROTULO = (190, 195, 202)

COR_CARTAO = (17, 18, 20)
COR_BANNER = (88, 101, 242)
COR_SEPARADOR = (35, 36, 38)
COR_CHIP = (36, 37, 39)
COR_CHIP_TEXTO = (242, 243, 245)
COR_CARGO_PADRAO = (181, 186, 193)

MAX_LINHAS_BLOCO = 10
MAX_CARGOS_IMAGEM = 24

# O Pillow/FreeType não é seguro para várias threads ao mesmo tempo.
_LOCK_RENDER = threading.Lock()


# =========================================================
# FONTES COM FALLBACK POR CARACTERE
# =========================================================

def _cadeia_fontes(bold):
    """Lista de fontes em ordem de prioridade."""
    preferidas = ["Lato-Bold.ttf", "bold.ttf"] if bold else ["Lato-Regular.ttf", "regular.ttf"]
    cadeia = [os.path.join(PASTA_FONTES, nome) for nome in preferidas]

    if os.path.isdir(PASTA_FONTES):
        for arquivo in sorted(os.listdir(PASTA_FONTES)):
            if arquivo.lower().endswith((".ttf", ".otf", ".ttc")) and arquivo not in preferidas:
                cadeia.append(os.path.join(PASTA_FONTES, arquivo))

    cadeia += FONTES_SISTEMA_BOLD if bold else FONTES_SISTEMA
    return cadeia


def limpar_texto(texto):
    """Normaliza e remove caracteres invisíveis/de controle."""
    texto = unicodedata.normalize("NFC", str(texto))
    saida = []

    for ch in texto:
        if ch == "\n":
            saida.append(ch)
            continue
        if ch == "\t":
            saida.append(" ")
            continue
        if unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn", "Mn", "Me"):
            continue
        saida.append(ch)

    return "".join(saida)


class Fonte:
    """Várias fontes do mesmo tamanho: cada letra usa a primeira que a tiver."""

    def __init__(self, bold, tamanho):
        self.tamanho = tamanho
        self.fontes = []

        for caminho in _cadeia_fontes(bold):
            try:
                self.fontes.append(ImageFont.truetype(caminho, tamanho))
            except OSError:
                continue

        if not self.fontes:
            try:
                self.fontes = [ImageFont.load_default(size=tamanho)]
            except TypeError:
                self.fontes = [ImageFont.load_default()]

        self._notdef = {}
        self._glifos = {}
        self._resolvidos = {}

    # ---------- descoberta de glifos ----------

    def _assinatura(self, fonte, ch):
        lado = self.tamanho * 2 + 8
        img = Image.new("L", (lado, lado), 0)
        ImageDraw.Draw(img).text((4, 4), ch, font=fonte, fill=255)
        return img.tobytes()

    def _tem_glifo(self, indice, ch):
        chave = (indice, ch)
        if chave in self._glifos:
            return self._glifos[chave]

        fonte = self.fontes[indice]

        if ch.isspace():
            resultado = True
        else:
            if indice not in self._notdef:
                self._notdef[indice] = self._assinatura(fonte, "\uffff")
            assinatura = self._assinatura(fonte, ch)
            resultado = assinatura != self._notdef[indice] and any(assinatura)

        self._glifos[chave] = resultado
        return resultado

    def _buscar(self, ch):
        for indice, fonte in enumerate(self.fontes):
            if self._tem_glifo(indice, ch):
                return [(fonte, ch)]
        return None

    def _resolver(self, ch):
        if ch in self._resolvidos:
            return self._resolvidos[ch]

        resultado = self._buscar(ch)

        # Letras "decoradas" (𝓓, ａ, ᴬ...) viram a letra comum equivalente.
        if resultado is None:
            normal = unicodedata.normalize("NFKC", ch)
            if normal != ch:
                resultado = []
                for c in normal:
                    achado = self._buscar(c)
                    if achado:
                        resultado.extend(achado)
                resultado = resultado or None

        self._resolvidos[ch] = resultado
        return resultado

    def _trechos(self, texto):
        trechos = []
        for ch in limpar_texto(texto):
            if ch == "\n":
                continue
            resolvido = self._resolver(ch)
            if not resolvido:
                continue
            for fonte, c in resolvido:
                if trechos and trechos[-1][0] is fonte:
                    trechos[-1][1] += c
                else:
                    trechos.append([fonte, c])
        return trechos

    # ---------- medir e desenhar ----------

    def largura(self, texto, espaco=0.0):
        total = 0.0
        quantidade = 0
        for fonte, trecho in self._trechos(texto):
            if espaco:
                total += sum(fonte.getlength(c) for c in trecho)
            else:
                total += fonte.getlength(trecho)
            quantidade += len(trecho)
        if espaco and quantidade:
            total += espaco * (quantidade - 1)
        return total

    def desenhar(self, draw, x, y, texto, cor, espaco=0.0):
        """Desenha com a linha de base em y. Retorna o x final."""
        for fonte, trecho in self._trechos(texto):
            if espaco:
                for c in trecho:
                    _escrever(draw, x, y, c, fonte, cor)
                    x += fonte.getlength(c) + espaco
            else:
                _escrever(draw, x, y, trecho, fonte, cor)
                x += fonte.getlength(trecho)
        return x


def _escrever(draw, x, y, texto, fonte, cor):
    try:
        draw.text((x, y), texto, font=fonte, fill=cor, anchor="ls")
    except (TypeError, ValueError):
        draw.text((x, y - getattr(fonte, "size", 12)), texto, font=fonte, fill=cor)


@lru_cache(maxsize=64)
def obter_fonte(bold, tamanho):
    return Fonte(bold, tamanho)


# =========================================================
# FUNÇÕES DE DESENHO
# =========================================================

def quebrar_texto(texto, fonte, largura_max, max_linhas=MAX_LINHAS_BLOCO):
    """Quebra o texto por largura em pixels (respeita \\n e palavras longas)."""
    linhas = []

    for paragrafo in limpar_texto(texto).split("\n"):
        if not paragrafo.strip():
            linhas.append("")
            continue

        atual = ""
        for palavra in paragrafo.split(" "):
            teste = f"{atual} {palavra}" if atual else palavra

            if fonte.largura(teste) <= largura_max:
                atual = teste
                continue

            if atual:
                linhas.append(atual)
                atual = ""

            while fonte.largura(palavra) > largura_max and len(palavra) > 1:
                corte = len(palavra)
                while corte > 1 and fonte.largura(palavra[:corte]) > largura_max:
                    corte -= 1
                linhas.append(palavra[:corte])
                palavra = palavra[corte:]

            atual = palavra

        linhas.append(atual)

    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] = linhas[-1].rstrip() + " …"

    return linhas


def ajustar_texto(texto, fonte, largura_max):
    """Corta o texto com '…' para caber em uma linha."""
    texto = limpar_texto(texto).replace("\n", " ").strip()

    if fonte.largura(texto) <= largura_max:
        return texto

    while texto and fonte.largura(texto + "…") > largura_max:
        texto = texto[:-1]

    return texto.rstrip() + "…"


def circulo(diametro, cor):
    """Círculo liso (com suavização) como imagem RGBA."""
    escala = 4
    grande = Image.new("L", (diametro * escala, diametro * escala), 0)
    ImageDraw.Draw(grande).ellipse(
        (0, 0, diametro * escala - 1, diametro * escala - 1), fill=255
    )
    mascara = grande.resize((diametro, diametro), Image.LANCZOS)

    imagem = Image.new("RGBA", (diametro, diametro), cor + (255,))
    imagem.putalpha(mascara)
    return imagem


def avatar_redondo(avatar_bytes, diametro):
    """Avatar circular. Se falhar, devolve um círculo azul do Discord."""
    try:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((diametro, diametro), Image.LANCZOS)

        escala = 4
        grande = Image.new("L", (diametro * escala, diametro * escala), 0)
        ImageDraw.Draw(grande).ellipse(
            (0, 0, diametro * escala - 1, diametro * escala - 1), fill=255
        )
        avatar.putalpha(grande.resize((diametro, diametro), Image.LANCZOS))
        return avatar
    except Exception:
        return circulo(diametro, COR_BANNER)


def mascara_arredondada(tamanho, caixa, raio):
    escala = 4
    grande = Image.new("L", (tamanho[0] * escala, tamanho[1] * escala), 0)
    x0, y0, x1, y1 = caixa
    ImageDraw.Draw(grande).rounded_rectangle(
        (x0 * escala, y0 * escala, x1 * escala - 1, y1 * escala - 1),
        radius=raio * escala, fill=255
    )
    return grande.resize(tamanho, Image.LANCZOS)


def retangulo_arredondado(imagem, caixa, raio, cor):
    """Retângulo arredondado suavizado."""
    x0, y0, x1, y1 = caixa
    mascara = mascara_arredondada(imagem.size, (x0, y0, x1, y1), raio)
    camada = Image.new("RGBA", imagem.size, cor + (255,))
    imagem.paste(camada, (0, 0), mascara)


# =========================================================
# IMAGEM: MENSAGEM APAGADA / EDITADA
# =========================================================

def renderizar_cartao(
    avatar_bytes, nome, canal, tipo, texto_antes, texto_depois,
    horario_antes, horario_depois, anexos
):
    with _LOCK_RENDER:
        return _renderizar_cartao(
            avatar_bytes, nome, canal, tipo, texto_antes, texto_depois,
            horario_antes, horario_depois, anexos
        )


def _renderizar_cartao(
    avatar_bytes, nome, canal, tipo, texto_antes, texto_depois,
    horario_antes, horario_depois, anexos
):
    LARGURA = 880
    X_AVATAR = 32
    TAM_AVATAR = 80
    X_TEXTO = 145
    X_DIREITA = 848
    LARGURA_TEXTO = X_DIREITA - X_TEXTO
    ALTURA_LINHA = 46

    f_rotulo = obter_fonte(True, 22)
    f_canal = obter_fonte(False, 24)
    f_nome = obter_fonte(True, 32)
    f_hora = obter_fonte(False, 24)
    f_texto = obter_fonte(False, 34)
    f_editado = obter_fonte(False, 22)

    limite_linhas = 18 if tipo == "sugestao" else MAX_LINHAS_BLOCO

    def preparar(texto, vazio, editado=False, qtd_anexos=0):
        texto = (texto or "").strip()
        if texto:
            entradas = [
                (linha, COR_MENSAGEM, False)
                for linha in quebrar_texto(
                    texto, f_texto, LARGURA_TEXTO, limite_linhas
                )
            ]
        else:
            entradas = [(vazio, COR_MUTED, False)]

        if editado:
            ultima, cor, _ = entradas[-1]
            largura = f_texto.largura(ultima) + f_editado.largura(" (editado)")
            if largura > LARGURA_TEXTO:
                entradas.append(("", COR_MUTED, True))
            else:
                entradas[-1] = (ultima, cor, True)

        if qtd_anexos:
            entradas.append((f"+ {qtd_anexos} anexo(s)", COR_MUTED, False))

        return entradas

    def altura_linha(entradas):
        return 90 + (max(len(entradas), 1) - 1) * ALTURA_LINHA + 30

    avatar = avatar_redondo(avatar_bytes, TAM_AVATAR)

    # ---------- monta as linhas ----------
    if tipo == "editada":
        linhas_a = preparar(texto_antes, "(mensagem sem texto)")
        linhas_b = preparar(texto_depois, "(mensagem sem texto)", editado=True)
        altura_a = altura_linha(linhas_a)
        altura_b = altura_linha(linhas_b)
        altura_total = 72 + altura_a + 60 + altura_b + 12
    else:
        linhas_a = preparar(texto_antes, "(mensagem sem texto)", qtd_anexos=anexos)
        linhas_b = None
        altura_a = altura_linha(linhas_a)
        altura_total = 72 + altura_a + 12

    imagem = Image.new("RGBA", (LARGURA, altura_total), COR_FUNDO + (255,))
    draw = ImageDraw.Draw(imagem)

    def cabecalho(y_base, texto, cor, com_canal=False):
        f_rotulo.desenhar(draw, 32, y_base, texto, cor, espaco=1.0)
        if com_canal:
            texto_canal = ajustar_texto(f"# {canal}", f_canal, 380)
            largura = f_canal.largura(texto_canal)
            f_canal.desenhar(
                draw, X_DIREITA - largura, y_base, texto_canal, COR_MUTED
            )

    def linha(y_topo, cor_fundo, cor_barra, entradas, horario, editado):
        altura = altura_linha(entradas)

        draw.rectangle((0, y_topo, LARGURA, y_topo + altura - 1), fill=cor_fundo)
        draw.rectangle((0, y_topo, 3, y_topo + altura - 1), fill=cor_barra)

        imagem.paste(avatar, (X_AVATAR, y_topo + 16), avatar)

        largura_hora = f_hora.largura(horario)
        texto_nome = ajustar_texto(
            nome, f_nome, X_DIREITA - X_TEXTO - largura_hora - 16
        )
        x_fim = f_nome.desenhar(draw, X_TEXTO, y_topo + 45, texto_nome, COR_NOME)
        f_hora.desenhar(draw, x_fim + 16, y_topo + 45, horario, COR_MUTED)

        y_base = y_topo + 90
        for texto, cor, sufixo in entradas:
            x_fim = f_texto.desenhar(draw, X_TEXTO, y_base, texto, cor)
            if sufixo:
                prefixo = " " if texto else ""
                f_editado.desenhar(
                    draw, x_fim, y_base, prefixo + "(editado)", COR_MUTED
                )
            y_base += ALTURA_LINHA

    # ---------- desenha ----------
    if tipo == "editada":
        cabecalho(52, "ANTES", COR_VERMELHO, com_canal=True)
        linha(72, COR_FUNDO_VERMELHO, COR_VERMELHO, linhas_a, horario_antes, False)

        y2 = 72 + altura_a
        cabecalho(y2 + 40, "DEPOIS", COR_VERDE)
        linha(y2 + 60, COR_FUNDO_VERDE, COR_VERDE, linhas_b, horario_depois, True)
    elif tipo == "sugestao":
        cabecalho(52, "NOVA SUGESTÃO", clarear(COR_BANNER_AZUL), com_canal=True)
        linha(
            72, misturar(COR_BANNER_AZUL, COR_FUNDO, 0.09), COR_BANNER_AZUL,
            linhas_a, horario_antes, False
        )
    else:
        cabecalho(52, "MENSAGEM APAGADA", COR_VERMELHO, com_canal=True)
        linha(72, COR_FUNDO_VERMELHO, COR_VERMELHO, linhas_a, horario_antes, False)

    saida = io.BytesIO()
    imagem.convert("RGB").save(saida, format="PNG")
    saida.seek(0)
    return saida


# =========================================================
# IMAGEM: CARTÃO DE PERFIL (cargos, banimento, expulsão, saída)
# =========================================================

COR_BANNER_AZUL = (88, 101, 242)
COR_BANNER_VERMELHO = (242, 63, 67)
COR_BANNER_LARANJA = (250, 166, 26)

COR_BOX = (43, 45, 49)
COR_BORDA_BOX = (31, 32, 35)
COR_DESCRICAO = (155, 163, 172)


def misturar(cor, base, fator):
    return tuple(int(cor[i] * fator + base[i] * (1 - fator)) for i in range(3))


def clarear(cor):
    return tuple(min(255, int(c * 1.06) + 3) for c in cor)


def renderizar_cartao_perfil(
    avatar_bytes, nome, handle, user_id, pilula, cor_banner, secoes
):
    with _LOCK_RENDER:
        return _renderizar_cartao_perfil(
            avatar_bytes, nome, handle, user_id, pilula, cor_banner, secoes
        )


def _renderizar_cartao_perfil(
    avatar_bytes, nome, handle, user_id, pilula, cor_banner, secoes
):
    """
    Cartão com banner colorido, avatar, nome e seções.
    Cada seção é uma tupla:
      ("chips", rotulo, [(nome_cargo, (r, g, b)), ...])
      ("ator",  rotulo, nome_ou_None, avatar_bytes)
      ("texto", rotulo, texto)
    """
    LARGURA = 880
    X0, X1 = 32, 848            # bordas do cartão
    Y0 = 36
    X_CONTEUDO = 64
    X_FIM = 816

    f_pilula = obter_fonte(True, 22)
    f_nome = obter_fonte(True, 42)
    f_handle = obter_fonte(False, 26)
    f_rotulo = obter_fonte(True, 21)
    f_chip = obter_fonte(False, 24)
    f_ator = obter_fonte(True, 28)
    f_texto = obter_fonte(False, 30)

    def posicionar_chips(cargos, y_inicial):
        lista = list(cargos[:MAX_CARGOS_IMAGEM])
        extras = len(cargos) - len(lista)

        chips = []
        for nome_cargo, cor_cargo in lista:
            texto = ajustar_texto(nome_cargo, f_chip, 420)
            largura = int(14 + 22 + 8 + f_chip.largura(texto) + 16)
            chips.append((texto, tuple(cor_cargo), largura))

        if extras > 0:
            texto = f"+{extras}"
            largura = int(14 + 22 + 8 + f_chip.largura(texto) + 16)
            chips.append((texto, COR_CARGO_PADRAO, largura))

        itens = []
        x, y = X_CONTEUDO, y_inicial
        for texto, cor_cargo, largura in chips:
            if x + largura > X_FIM and x > X_CONTEUDO:
                x = X_CONTEUDO
                y += 54
            itens.append((texto, cor_cargo, largura, x, y))
            x += largura + 10

        fim = (itens[-1][4] + 44) if itens else y_inicial
        return itens, fim

    # ---------- plano de layout ----------
    plano = []
    y_rotulo = 362
    fim_cartao = 327 + 40

    for secao in secoes:
        tipo, rotulo = secao[0], secao[1]
        item = {"tipo": tipo, "rotulo": rotulo, "y": y_rotulo}

        if tipo == "chips":
            itens, fim = posicionar_chips(secao[2], y_rotulo + 16)
            item["itens"] = itens
            proximo, fim_cartao = fim + 28, fim + 38

        elif tipo == "ator":
            item["nome"], item["avatar"] = secao[2], secao[3]
            fim = y_rotulo + 22 + 40
            proximo, fim_cartao = fim + 30, fim + 38

        else:  # texto
            linhas = quebrar_texto(
                secao[2] or "-", f_texto, X_FIM - X_CONTEUDO, max_linhas=4
            )
            item["linhas"] = linhas
            ultima = y_rotulo + 42 + (len(linhas) - 1) * 42
            proximo, fim_cartao = ultima + 42, ultima + 52

        plano.append(item)
        y_rotulo = proximo

    altura_total = fim_cartao + 24

    # ---------- fundo e cartão ----------
    imagem = Image.new("RGBA", (LARGURA, altura_total), COR_FUNDO + (255,))

    camada = Image.new("RGBA", imagem.size, COR_CARTAO + (255,))
    ImageDraw.Draw(camada).rectangle((X0, Y0, X1, Y0 + 103), fill=cor_banner + (255,))
    mascara = mascara_arredondada(imagem.size, (X0, Y0, X1, fim_cartao), 16)
    imagem.paste(camada, (0, 0), mascara)

    draw = ImageDraw.Draw(imagem)

    # ---------- avatar grande com anel ----------
    anel = circulo(144, COR_CARTAO)
    imagem.paste(anel, (60, 69), anel)
    avatar = avatar_redondo(avatar_bytes, 134)
    imagem.paste(avatar, (65, 74), avatar)

    # ---------- pílula ----------
    largura_pilula = int(f_pilula.largura(pilula, espaco=1.0)) + 32
    x_pilula = X_FIM - largura_pilula
    retangulo_arredondado(
        imagem, (x_pilula, 160, X_FIM, 200), 20,
        misturar(cor_banner, COR_CARTAO, 0.28)
    )
    f_pilula.desenhar(
        draw, x_pilula + 16, 188, pilula, clarear(cor_banner), espaco=1.0
    )

    # ---------- nome e identificação ----------
    largura_max = X_FIM - X_CONTEUDO
    f_nome.desenhar(
        draw, X_CONTEUDO, 263,
        ajustar_texto(nome, f_nome, largura_max), COR_NOME
    )
    f_handle.desenhar(
        draw, X_CONTEUDO, 300,
        ajustar_texto(f"{handle}  ·  ID {user_id}", f_handle, largura_max),
        COR_MUTED
    )

    draw.rectangle((X_CONTEUDO, 326, X_FIM - 1, 327), fill=COR_SEPARADOR)

    # ---------- seções ----------
    for item in plano:
        f_rotulo.desenhar(
            draw, X_CONTEUDO, item["y"], item["rotulo"], COR_ROTULO, espaco=1.0
        )

        if item["tipo"] == "chips":
            for texto, cor_cargo, largura, cx, cy in item["itens"]:
                retangulo_arredondado(
                    imagem, (cx, cy, cx + largura, cy + 44), 10, COR_CHIP
                )
                bolinha = circulo(22, cor_cargo)
                imagem.paste(bolinha, (cx + 14, cy + 11), bolinha)
                f_chip.desenhar(draw, cx + 44, cy + 31, texto, COR_CHIP_TEXTO)

        elif item["tipo"] == "ator":
            y_av = item["y"] + 22
            if item["nome"]:
                avatar_ator = avatar_redondo(item["avatar"], 40)
                imagem.paste(avatar_ator, (X_CONTEUDO, y_av), avatar_ator)
                f_ator.desenhar(
                    draw, X_CONTEUDO + 52, y_av + 30,
                    ajustar_texto(item["nome"], f_ator, X_FIM - X_CONTEUDO - 52),
                    COR_NOME
                )
            else:
                f_ator.desenhar(
                    draw, X_CONTEUDO, y_av + 30, "Não identificado", COR_MUTED
                )

        else:
            y_texto = item["y"] + 42
            for linha in item["linhas"]:
                f_texto.desenhar(draw, X_CONTEUDO, y_texto, linha, COR_MENSAGEM)
                y_texto += 42

    saida = io.BytesIO()
    imagem.convert("RGB").save(saida, format="PNG")
    saida.seek(0)
    return saida


def renderizar_cartao_cargos(
    avatar_bytes, nome, handle, user_id, titulo, cargos,
    ator_nome, ator_avatar_bytes
):
    return renderizar_cartao_perfil(
        avatar_bytes, nome, handle, user_id, "CARGOS", COR_BANNER_AZUL,
        [
            ("chips", titulo, cargos),
            ("ator", "ALTERADO POR", ator_nome, ator_avatar_bytes),
        ]
    )


def renderizar_cartao_moderacao(
    avatar_bytes, nome, handle, user_id, titulo,
    ator_nome, ator_avatar_bytes, motivo
):
    """titulo: 'BANIDO' ou 'EXPULSO'."""
    return renderizar_cartao_perfil(
        avatar_bytes, nome, handle, user_id, titulo, COR_BANNER_VERMELHO,
        [
            ("ator", "MODERADOR", ator_nome, ator_avatar_bytes),
            ("texto", "MOTIVO", motivo or "Sem motivo informado"),
        ]
    )


def renderizar_cartao_saida(
    avatar_bytes, nome, handle, user_id, entrou_texto, cargos
):
    secoes = [("texto", "ENTROU NO SERVIDOR", entrou_texto)]
    if cargos:
        secoes.append(("chips", "CARGOS", cargos))

    return renderizar_cartao_perfil(
        avatar_bytes, nome, handle, user_id, "SAIU", COR_BANNER_LARANJA, secoes
    )


# =========================================================
# IMAGEM: CARGO EXCLUÍDO
# =========================================================

def renderizar_cartao_cargo_excluido(nome_cargo, cor):
    with _LOCK_RENDER:
        return _renderizar_cartao_cargo_excluido(nome_cargo, cor)


def _renderizar_cartao_cargo_excluido(nome_cargo, cor):
    LARGURA, ALTURA = 768, 185

    f_rotulo = obter_fonte(True, 21)
    f_nome = obter_fonte(True, 31)
    f_cor = obter_fonte(False, 24)

    imagem = Image.new("RGBA", (LARGURA, ALTURA), COR_FUNDO + (255,))

    # Caixa com borda de 2px
    retangulo_arredondado(imagem, (28, 73, 740, 171), 16, COR_BORDA_BOX)
    retangulo_arredondado(imagem, (30, 75, 738, 169), 14, COR_BOX)

    draw = ImageDraw.Draw(imagem)

    # Título e barra lateral
    f_rotulo.desenhar(
        draw, 28, 46, "CARGO EXCLUÍDO", COR_VERMELHO, espaco=1.5
    )
    draw.rectangle((0, 73, 5, 170), fill=COR_VERMELHO)

    # Bolinha na cor do cargo
    bolinha = circulo(40, tuple(cor))
    imagem.paste(bolinha, (60, 102), bolinha)

    # Nome riscado
    texto_nome = ajustar_texto(nome_cargo, f_nome, 740 - 126 - 24)
    x_fim = f_nome.desenhar(draw, 126, 120, texto_nome, COR_NOME)
    draw.rectangle((126, 109, int(x_fim) + 1, 110), fill=COR_NOME)

    # Cor em hexadecimal
    hexa = "#{:02x}{:02x}{:02x}".format(*cor)
    f_cor.desenhar(draw, 126, 152, f"cor {hexa}", COR_DESCRICAO)

    saida = io.BytesIO()
    imagem.convert("RGB").save(saida, format="PNG")
    saida.seek(0)
    return saida


# =========================================================
# COG
# =========================================================

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._online_log_enviado = False

    # =====================================================
    # FUNÇÕES AUXILIARES
    # =====================================================

    def obter_canal_logs(self):
        return self.bot.get_channel(LOG_CHANNEL_ID)

    def horario_atual(self):
        return datetime.now(FUSO)

    def formatar_horario(self, momento=None):
        """'Hoje às 23:11', 'Ontem às 23:11' ou '14/10/2026 às 23:11'."""
        if momento is None:
            momento = datetime.now(timezone.utc)

        momento = momento.astimezone(FUSO)
        hoje = self.horario_atual().date()

        if momento.date() == hoje:
            return f"Hoje às {momento:%H:%M}"
        if momento.date() == hoje - timedelta(days=1):
            return f"Ontem às {momento:%H:%M}"
        return f"{momento:%d/%m/%Y} às {momento:%H:%M}"

    async def enviar_log(self, embed, arquivo=None):
        canal = self.obter_canal_logs()

        if canal is None:
            return

        try:
            if arquivo is not None:
                await canal.send(embed=embed, file=arquivo)
            else:
                await canal.send(embed=embed)
        except discord.Forbidden:
            print("❌ Sem permissão para enviar logs.")
        except discord.HTTPException as erro:
            print(f"❌ Erro ao enviar log: {erro}")

    def criar_embed(self, titulo, cor=discord.Color.blurple(), descricao=None):
        return discord.Embed(
            title=titulo,
            description=descricao,
            color=cor,
            timestamp=discord.utils.utcnow()
        )

    def definir_autor(self, embed, membro):
        embed.set_author(
            name=f"{membro.display_name} ({membro})",
            icon_url=membro.display_avatar.url
        )

    def rodape_ids(self, embed, membro, mensagem=None):
        texto = f"ID do usuário: {membro.id}"
        if mensagem is not None:
            texto += f" • ID da mensagem: {mensagem.id}"
        embed.set_footer(text=texto)

    async def buscar_audit(self, guild, acao, alvo_id, janela=15):
        """Procura no audit log quem executou uma ação recente."""
        try:
            await asyncio.sleep(1)  # o Discord demora um instante para registrar
            async for entrada in guild.audit_logs(limit=6, action=acao):
                if entrada.target and entrada.target.id == alvo_id:
                    idade = (
                        datetime.now(timezone.utc) - entrada.created_at
                    ).total_seconds()
                    if 0 <= idade <= janela:
                        return entrada
        except (discord.Forbidden, discord.HTTPException):
            pass
        return None

    async def baixar_avatar(self, usuario, tamanho):
        try:
            return await usuario.display_avatar.replace(
                size=tamanho, static_format="png"
            ).read()
        except Exception:
            return b""

    def citar(self, texto, limite=900):
        """Formata um texto como citação do Discord, com limite de tamanho."""
        texto = texto or "*Sem texto*"
        if len(texto) > limite:
            texto = texto[:limite].rstrip() + " …"
        return "\n".join(f"> {linha}" if linha else ">" for linha in texto.split("\n"))

    def descricao_deletada(self, mensagem):
        partes = [
            f"{mensagem.author.mention} teve uma mensagem **deletada** em "
            f"{mensagem.channel.mention}.",
            f"**Conteúdo da mensagem:**\n{self.citar(mensagem.content, 1500)}",
        ]

        if mensagem.attachments:
            partes.append(
                f"**Anexos:** {len(mensagem.attachments)} arquivo(s) foram "
                f"removidos junto com a mensagem."
            )

        if mensagem.reference and mensagem.reference.message_id:
            partes.append(
                f"**Respondia a:** [outra mensagem]"
                f"(https://discord.com/channels/{mensagem.guild.id}/"
                f"{mensagem.channel.id}/{mensagem.reference.message_id})"
            )

        partes.append(
            f"**Enviada em:** {discord.utils.format_dt(mensagem.created_at, 'F')} "
            f"({discord.utils.format_dt(mensagem.created_at, 'R')})"
        )
        return "\n\n".join(partes)

    def descricao_editada(self, antes, depois):
        return "\n\n".join([
            f"{antes.author.mention} **editou** uma mensagem em "
            f"{antes.channel.mention}. [Ir para a mensagem]({depois.jump_url})",
            f"**Antes:**\n{self.citar(antes.content, 1200)}",
            f"**Depois:**\n{self.citar(depois.content, 1200)}",
            f"**Enviada em:** {discord.utils.format_dt(antes.created_at, 'F')} "
            f"({discord.utils.format_dt(antes.created_at, 'R')})",
        ])

    # =====================================================
    # IMAGENS
    # =====================================================

    async def criar_imagem_mensagem(
        self, autor, canal, tipo, texto_antes, horario_antes,
        texto_depois=None, horario_depois=None, anexos=0
    ):
        """Imagem da mensagem apagada/editada como discord.File."""
        avatar_bytes = await self.baixar_avatar(autor, 128)

        dados = await asyncio.to_thread(
            renderizar_cartao,
            avatar_bytes,
            autor.display_name,
            canal,
            tipo,
            texto_antes,
            texto_depois,
            horario_antes,
            horario_depois,
            anexos,
        )

        return discord.File(dados, filename="mensagem.png")

    async def criar_imagem_cargos(self, membro, cargos, adicionado, ator):
        """Imagem de cargos adicionados/removidos como discord.File."""
        avatar_bytes = await self.baixar_avatar(membro, 256)
        ator_avatar = await self.baixar_avatar(ator, 64) if ator else b""

        lista = []
        for cargo in cargos:
            cor = cargo.color
            lista.append((
                cargo.name,
                (cor.r, cor.g, cor.b) if cor.value else COR_CARGO_PADRAO
            ))

        dados = await asyncio.to_thread(
            renderizar_cartao_cargos,
            avatar_bytes,
            membro.display_name,
            f"@{membro.name}",
            membro.id,
            "ADICIONADOS" if adicionado else "REMOVIDOS",
            lista,
            ator.display_name if ator else None,
            ator_avatar,
        )

        return discord.File(dados, filename="cargos.png")

    async def criar_imagem_moderacao(self, usuario, titulo, ator, motivo):
        """Imagem de banimento/expulsão como discord.File."""
        avatar_bytes = await self.baixar_avatar(usuario, 256)
        ator_avatar = await self.baixar_avatar(ator, 64) if ator else b""

        dados = await asyncio.to_thread(
            renderizar_cartao_moderacao,
            avatar_bytes,
            usuario.display_name,
            f"@{usuario.name}",
            usuario.id,
            titulo,
            ator.display_name if ator else None,
            ator_avatar,
            motivo,
        )

        return discord.File(dados, filename="moderacao.png")

    async def criar_imagem_saida(self, membro):
        """Imagem de saída de membro como discord.File."""
        avatar_bytes = await self.baixar_avatar(membro, 256)

        entrou_texto = "Não encontrado"
        if membro.joined_at:
            entrou = membro.joined_at.astimezone(FUSO)
            dias = (datetime.now(timezone.utc) - membro.joined_at).days
            tempo = f"há {dias} dia(s)" if dias >= 1 else "há menos de 1 dia"
            entrou_texto = f"{entrou:%d/%m/%Y} às {entrou:%H:%M}  ·  {tempo}"

        cargos = []
        for cargo in membro.roles:
            if cargo.is_default():
                continue
            cor = cargo.color
            cargos.append((
                cargo.name,
                (cor.r, cor.g, cor.b) if cor.value else COR_CARGO_PADRAO
            ))

        dados = await asyncio.to_thread(
            renderizar_cartao_saida,
            avatar_bytes,
            membro.display_name,
            f"@{membro.name}",
            membro.id,
            entrou_texto,
            cargos,
        )

        return discord.File(dados, filename="saida.png")

    async def criar_imagem_cargo_excluido(self, cargo):
        """Imagem de cargo excluído como discord.File."""
        cor = cargo.color
        dados = await asyncio.to_thread(
            renderizar_cartao_cargo_excluido,
            cargo.name,
            (cor.r, cor.g, cor.b),
        )
        return discord.File(dados, filename="cargo_excluido.png")

 
    # =====================================================
    # BOT ONLINE
    # =====================================================

    @commands.Cog.listener()
    async def on_ready(self):
        # on_ready pode disparar várias vezes (reconexões): envia só uma.
        if self._online_log_enviado:
            return
        self._online_log_enviado = True

        def contar_comandos(comandos):
            total = 0

            for comando in comandos:
                if isinstance(comando, discord.app_commands.Group):
                    total += contar_comandos(comando.commands)
                else:
                    total += 1

            return total

        comandos = contar_comandos(self.bot.tree.get_commands())
        servidores = len(self.bot.guilds)

        embed = self.criar_embed(
            "✅ Bot online",
            discord.Color.green(),
            f"**{self.bot.user}** está online e pronto para ajudar."
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(
            name="📋 Comandos",
            value=f"`{comandos}`",
            inline=True
        )
        embed.add_field(
            name="🌐 Servidores",
            value=f"`{servidores}`",
            inline=True
        )
        embed.add_field(
            name="📦 Versão",
            value="`v5.0 — Python/Discord.py`",
            inline=True
        )
        embed.set_footer(text=f"ID: {self.bot.user.id}")

        await self.enviar_log(embed)

    # =====================================================
    # MENSAGEM DELETADA
    # =====================================================

    @commands.Cog.listener()
    async def on_message_delete(self, mensagem):
        if mensagem.author.bot or mensagem.guild is None:
            return

        embed = self.criar_embed(
            "🗑️ Mensagem deletada",
            discord.Color.red(),
            self.descricao_deletada(mensagem)[:4000]
        )
        self.definir_autor(embed, mensagem.author)

        embed.add_field(
            name="👤 Autor", value=mensagem.author.mention, inline=True
        )
        embed.add_field(
            name="📍 Canal", value=mensagem.channel.mention, inline=True
        )
        embed.add_field(
            name="🕒 Quando",
            value=discord.utils.format_dt(discord.utils.utcnow(), "R"),
            inline=True
        )

        if mensagem.attachments:
            nomes = "\n".join(f"• `{a.filename}`" for a in mensagem.attachments[:5])
            embed.add_field(name="📎 Anexos", value=nomes, inline=False)

        self.rodape_ids(embed, mensagem.author, mensagem)

        arquivo = None
        try:
            arquivo = await self.criar_imagem_mensagem(
                mensagem.author,
                getattr(mensagem.channel, "name", "desconhecido"),
                "deletada",
                mensagem.content,
                self.formatar_horario(mensagem.created_at),
                anexos=len(mensagem.attachments),
            )
            embed.set_image(url="attachment://mensagem.png")
        except Exception as erro:
            print(f"❌ Erro ao gerar imagem do log: {erro}")

        await self.enviar_log(embed, arquivo)

    # =====================================================
    # MENSAGEM EDITADA
    # =====================================================

    @commands.Cog.listener()
    async def on_message_edit(self, antes, depois):
        if antes.author.bot or antes.guild is None:
            return

        # Ignora alterações que não mudaram o texto (ex.: embed carregando).
        if antes.content == depois.content:
            return

        embed = self.criar_embed(
            "✏️ Mensagem editada",
            discord.Color.orange(),
            self.descricao_editada(antes, depois)[:4000]
        )
        self.definir_autor(embed, antes.author)

        embed.add_field(name="👤 Autor", value=antes.author.mention, inline=True)
        embed.add_field(name="📍 Canal", value=antes.channel.mention, inline=True)
        embed.add_field(
            name="🔗 Mensagem",
            value=f"[Ir para a mensagem]({depois.jump_url})",
            inline=True
        )

        self.rodape_ids(embed, antes.author, antes)

        arquivo = None
        try:
            arquivo = await self.criar_imagem_mensagem(
                antes.author,
                getattr(antes.channel, "name", "desconhecido"),
                "editada",
                antes.content,
                self.formatar_horario(antes.created_at),
                texto_depois=depois.content,
                horario_depois=self.formatar_horario(depois.edited_at),
            )
            embed.set_image(url="attachment://mensagem.png")
        except Exception as erro:
            print(f"❌ Erro ao gerar imagem do log: {erro}")

        await self.enviar_log(embed, arquivo)

    # =====================================================
    # MEMBRO BANIDO
    # =====================================================

    @commands.Cog.listener()
    async def on_member_ban(self, guild, usuario):
        entrada = await self.buscar_audit(
            guild, discord.AuditLogAction.ban, usuario.id
        )
        ator = entrada.user if entrada else None
        motivo = entrada.reason if entrada and entrada.reason else None
        agora = discord.utils.utcnow()

        descricao = "\n\n".join([
            f"{usuario.mention} foi **banido** do servidor.",
            f"**Usuário:** {usuario.mention} (`{usuario.id}`)\n"
            f"**Moderador:** {ator.mention if ator else 'Não identificado'}",
            f"**Motivo:**\n{self.citar(motivo or 'Sem motivo informado', 900)}",
            f"**Quando:** {discord.utils.format_dt(agora, 'F')} "
            f"({discord.utils.format_dt(agora, 'R')})",
        ])

        embed = self.criar_embed("🔨 Membro banido", discord.Color.red(), descricao)
        embed.set_author(name=str(usuario), icon_url=usuario.display_avatar.url)
        embed.set_thumbnail(url=usuario.display_avatar.url)

        embed.add_field(
            name="👤 Usuário",
            value=f"{usuario.mention}\n`{usuario.id}`",
            inline=True
        )
        embed.add_field(
            name="🛡️ Moderador",
            value=ator.mention if ator else "Não identificado",
            inline=True
        )
        embed.set_footer(text=f"Servidor: {guild.name}")

        arquivo = None
        try:
            arquivo = await self.criar_imagem_moderacao(
                usuario, "BANIDO", ator, motivo
            )
            embed.set_image(url="attachment://moderacao.png")
        except Exception as erro:
            print(f"❌ Erro ao gerar imagem de banimento: {erro}")

        await self.enviar_log(embed, arquivo)

    # =====================================================
    # MEMBRO SAIU OU FOI EXPULSO
    # =====================================================

    @commands.Cog.listener()
    async def on_member_remove(self, membro):
        if membro.bot:
            return

        entrada = await self.buscar_audit(
            membro.guild, discord.AuditLogAction.kick, membro.id, janela=10
        )

        # Banimento também dispara este evento: já é registrado em on_member_ban.
        if entrada is None:
            banimento = await self.buscar_audit(
                membro.guild, discord.AuditLogAction.ban, membro.id, janela=10
            )
            if banimento is not None:
                return

        agora = discord.utils.utcnow()
        entrou = (
            f"{discord.utils.format_dt(membro.joined_at, 'F')} "
            f"({discord.utils.format_dt(membro.joined_at, 'R')})"
            if membro.joined_at else "Não encontrado"
        )

        if entrada:
            ator = entrada.user
            motivo = entrada.reason or None

            descricao = "\n\n".join([
                f"{membro.mention} foi **expulso** do servidor.",
                f"**Usuário:** {membro.mention} (`{membro.id}`)\n"
                f"**Moderador:** {ator.mention}",
                f"**Motivo:**\n{self.citar(motivo or 'Sem motivo informado', 900)}",
                f"**Entrou em:** {entrou}",
                f"**Quando:** {discord.utils.format_dt(agora, 'F')} "
                f"({discord.utils.format_dt(agora, 'R')})",
            ])

            embed = self.criar_embed(
                "👢 Membro expulso", discord.Color.red(), descricao
            )
            embed.add_field(name="🛡️ Moderador", value=ator.mention, inline=True)
            nome_imagem = "moderacao.png"
        else:
            ator = None
            motivo = None

            descricao = "\n\n".join([
                f"{membro.mention} **saiu** do servidor.",
                f"**Usuário:** {membro.mention} (`{membro.id}`)",
                f"**Entrou em:** {entrou}",
                f"**Saiu em:** {discord.utils.format_dt(agora, 'F')} "
                f"({discord.utils.format_dt(agora, 'R')})",
            ])

            embed = self.criar_embed(
                "👋 Membro saiu", discord.Color.orange(), descricao
            )
            nome_imagem = "saida.png"

        embed.set_author(name=str(membro), icon_url=membro.display_avatar.url)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(
            name="👤 Usuário",
            value=f"{membro.mention}\n`{membro.id}`",
            inline=True
        )
        embed.set_footer(text=f"Membros agora: {membro.guild.member_count}")

        arquivo = None
        try:
            if entrada:
                arquivo = await self.criar_imagem_moderacao(
                    membro, "EXPULSO", ator, motivo
                )
            else:
                arquivo = await self.criar_imagem_saida(membro)
            embed.set_image(url=f"attachment://{nome_imagem}")
        except Exception as erro:
            print(f"❌ Erro ao gerar imagem de saída/expulsão: {erro}")

        await self.enviar_log(embed, arquivo)

    # =====================================================
    # CARGO EXCLUÍDO
    # =====================================================

    @commands.Cog.listener()
    async def on_guild_role_delete(self, cargo):
        entrada = await self.buscar_audit(
            cargo.guild, discord.AuditLogAction.role_delete, cargo.id
        )
        ator = entrada.user if entrada else None
        agora = discord.utils.utcnow()

        descricao = "\n\n".join([
            f"O cargo **{cargo.name}** foi **excluído** do servidor.",
            f"**Cargo:** `{cargo.name}` (`{cargo.id}`)\n"
            f"**Cor:** `{str(cargo.color)}`\n"
            f"**Criado em:** {discord.utils.format_dt(cargo.created_at, 'F')}",
            f"**Excluído por:** {ator.mention if ator else 'Não identificado'}\n"
            f"**Quando:** {discord.utils.format_dt(agora, 'F')} "
            f"({discord.utils.format_dt(agora, 'R')})",
        ])

        embed = self.criar_embed("🗑️ Cargo excluído", discord.Color.red(), descricao)
        embed.add_field(name="🏷️ Cargo", value=f"`{cargo.name}`", inline=True)
        embed.add_field(name="🎨 Cor", value=f"`{str(cargo.color)}`", inline=True)
        embed.add_field(
            name="🛡️ Responsável",
            value=ator.mention if ator else "Não identificado",
            inline=True
        )
        embed.set_footer(text=f"ID do cargo: {cargo.id}")

        arquivo = None
        try:
            arquivo = await self.criar_imagem_cargo_excluido(cargo)
            embed.set_image(url="attachment://cargo_excluido.png")
        except Exception as erro:
            print(f"❌ Erro ao gerar imagem de cargo excluído: {erro}")

        await self.enviar_log(embed, arquivo)

    # =====================================================
    # CARGOS (ADICIONADOS / REMOVIDOS)
    # =====================================================

    async def log_cargos(self, membro, cargos, adicionado, entrada):
        ator = entrada.user if entrada else None
        plural = len(cargos) > 1

        if adicionado:
            titulo = "➕ Cargos adicionados" if plural else "➕ Cargo adicionado"
            cor = discord.Color.green()
            verbo = "recebeu"
        else:
            titulo = "➖ Cargos removidos" if plural else "➖ Cargo removido"
            cor = discord.Color.red()
            verbo = "perdeu"

        lista = "\n".join(f"• {c.mention} (`{c.id}`)" for c in cargos)

        descricao = (
            f"{membro.mention} **{verbo}** "
            f"{'os cargos abaixo' if plural else 'o cargo abaixo'}.\n\n"
            f"**{'Cargos' if plural else 'Cargo'}:**\n{lista}\n\n"
            f"**Membro:** {membro.mention} (`{membro.id}`)\n"
            f"**Alterado por:** {ator.mention if ator else 'Não identificado'}\n"
            f"**Quando:** {discord.utils.format_dt(discord.utils.utcnow(), 'F')} "
            f"({discord.utils.format_dt(discord.utils.utcnow(), 'R')})"
        )

        embed = self.criar_embed(titulo, cor, descricao[:4000])
        self.definir_autor(embed, membro)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(
            name="👥 Total de cargos",
            value=f"`{len(membro.roles) - 1}`",
            inline=True
        )
        embed.add_field(
            name="🛡️ Responsável",
            value=ator.mention if ator else "Não identificado",
            inline=True
        )
        embed.set_footer(text=f"ID do usuário: {membro.id}")

        arquivo = None
        try:
            arquivo = await self.criar_imagem_cargos(membro, cargos, adicionado, ator)
            embed.set_image(url="attachment://cargos.png")
        except Exception as erro:
            print(f"❌ Erro ao gerar imagem de cargos: {erro}")

        await self.enviar_log(embed, arquivo)

    # =====================================================
    # ALTERAÇÃO DE CARGOS E TIMEOUT
    # =====================================================

    @commands.Cog.listener()
    async def on_member_update(self, antes, depois):
        if antes.roles != depois.roles:
            ids_antes = {cargo.id for cargo in antes.roles}
            ids_depois = {cargo.id for cargo in depois.roles}

            adicionados = [
                c for c in depois.roles
                if c.id not in ids_antes and not c.is_default()
            ]
            removidos = [
                c for c in antes.roles
                if c.id not in ids_depois and not c.is_default()
            ]

            if adicionados or removidos:
                entrada = await self.buscar_audit(
                    depois.guild, discord.AuditLogAction.member_role_update,
                    depois.id
                )

                if adicionados:
                    await self.log_cargos(depois, adicionados, True, entrada)

                if removidos:
                    await self.log_cargos(depois, removidos, False, entrada)

        # Registra timeout (castigo temporário do Discord).
        if antes.timed_out_until != depois.timed_out_until:
            embed = self.criar_embed("🔇 Timeout alterado", discord.Color.orange())
            self.definir_autor(embed, depois)
            embed.set_thumbnail(url=depois.display_avatar.url)
            embed.add_field(name="👤 Usuário", value=depois.mention, inline=True)

            if depois.timed_out_until:
                embed.add_field(
                    name="⏳ Até",
                    value=discord.utils.format_dt(depois.timed_out_until, "F"),
                    inline=True
                )
            else:
                embed.add_field(
                    name="✅ Situação", value="Timeout removido", inline=True
                )

            self.rodape_ids(embed, depois)
            await self.enviar_log(embed)

    # =====================================================
    # ALTERAÇÃO DE CANAL
    # =====================================================

    @commands.Cog.listener()
    async def on_guild_channel_update(self, antes, depois):
        campos = []

        if antes.name != depois.name:
            campos.append(("🔤 Nome", f"`{antes.name}` ➜ `{depois.name}`"))

        if hasattr(antes, "topic") and antes.topic != depois.topic:
            campos.append((
                "💬 Tópico",
                f"{antes.topic or 'Nenhum'}\n➜\n{depois.topic or 'Nenhum'}"
            ))

        if antes.category != depois.category:
            cat_antes = antes.category.name if antes.category else "Nenhuma"
            cat_depois = depois.category.name if depois.category else "Nenhuma"
            campos.append(("📁 Categoria", f"`{cat_antes}` ➜ `{cat_depois}`"))

        if not campos:
            return

        embed = self.criar_embed("📝 Canal alterado", discord.Color.blurple())
        embed.add_field(name="📍 Canal", value=depois.mention, inline=False)

        for nome, valor in campos:
            embed.add_field(name=nome, value=valor[:1024], inline=False)

        embed.set_footer(text=f"ID do canal: {depois.id}")

        await self.enviar_log(embed)


# =========================================================
# CARREGAR COG
# =========================================================

async def setup(bot):
    await bot.add_cog(Logs(bot))
