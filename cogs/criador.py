import asyncio
import importlib
import re
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

# A imagem da sugestão usa o mesmo renderizador dos logs (cogs/logs.py).
# Só é usada se o logs.py for a versão nova (que tem SUPORTA_SUGESTAO).
# Com um logs.py antigo, a imagem sairia com o título errado
# ("MENSAGEM APAGADA"), então nesse caso a sugestão vai só com o embed.
renderizar_cartao = None
LOGS_DESATUALIZADO = False

for _nome_modulo in ("cogs.logs", "logs"):
    try:
        _modulo = importlib.import_module(_nome_modulo)
    except ImportError:
        continue

    if getattr(_modulo, "SUPORTA_SUGESTAO", False):
        renderizar_cartao = _modulo.renderizar_cartao
        LOGS_DESATUALIZADO = False
        break

    if hasattr(_modulo, "renderizar_cartao"):
        LOGS_DESATUALIZADO = True


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

# Canal das sugestões. Se ficar 0, a sugestão é enviada no canal
# onde o comando /sugestao foi usado.
CANAL_SUGESTOES_ID = 1561049289533292676

# Horário de Brasília (UTC-3).
FUSO = timezone(timedelta(hours=-3))

# Convite do Leooxxz Bot (aparece na descrição padrão do embed).
LINK_LEOOXXZ_BOT = (
    "https://discord.com/oauth2/authorize?client_id=1482754340832805014"
    "&permissions=8&integration_type=0&scope=bot+applications.commands"
)

# Descrição que já vem preenchida no editor de embed.
# O texto "Leooxxz Bot" é um link para o convite do Leooxxz Bot.
# Quem estiver criando o embed pode editar ou apagar pelo botão "Descrição".
DESCRICAO_PADRAO = (
    "Gosta de bots como este? Leve mais praticidade, organização e "
    "segurança para a sua comunidade.\n\n"
    "Adicione o **[Leooxxz Bot](" + LINK_LEOOXXZ_BOT + ")** ao seu servidor "
    "e deixe tudo mais completo, do jeito que a sua equipe e os seus "
    "membros merecem.\n\n"
    "➡️ **[Clique aqui para adicionar o Leooxxz Bot](" + LINK_LEOOXXZ_BOT + ")**"
)

COR_PADRAO = 0x6A00FF
TEMPO_EDITOR = 840          # segundos (14 min, antes do token expirar)
MAX_CAMPOS = 25


# ==========================================================
# VARIÁVEIS  {author.name}, {server.name} ...
# ==========================================================

AJUDA_VARIAVEIS = (
    "**Variáveis disponíveis**\n"
    "Funcionam no título, descrição, autor, rodapé, campos e nos links "
    "de imagem.\n\n"
    "**Autor (quem criou o embed)**\n"
    "`{author.name}` nome de exibição\n"
    "`{author.username}` nome de usuário\n"
    "`{author.mention}` menção\n"
    "`{author.id}` ID\n"
    "`{author.avatar}` link do avatar\n\n"
    "**Servidor**\n"
    "`{server.name}` `{server.id}` `{server.icon}` "
    "`{server.members}` `{server.owner}`\n\n"
    "**Canal de destino**\n"
    "`{channel.name}` `{channel.mention}` `{channel.id}`\n\n"
    "**Bot**\n"
    "`{bot.name}` `{bot.avatar}` `{bot.mention}` `{bot.id}` "
    "`{bot.invite}`\n\n"
    "**Data e hora**\n"
    "`{date}` dia/mês/ano  •  `{time}` hora:minuto"
)

_PADRAO_VARIAVEL = re.compile(r"\{([a-zA-Z_]+(?:\.[a-zA-Z_]+)?)\}")


def montar_variaveis(usuario, guild, canal, bot_user):
    agora = datetime.now(FUSO)

    return {
        "author.name": usuario.display_name,
        "author.username": usuario.name,
        "author.mention": usuario.mention,
        "author.id": str(usuario.id),
        "author.avatar": usuario.display_avatar.url,
        "server.name": guild.name,
        "server.id": str(guild.id),
        "server.icon": guild.icon.url if guild.icon else "",
        "server.members": str(guild.member_count or 0),
        "server.owner": f"<@{guild.owner_id}>",
        "channel.name": getattr(canal, "name", ""),
        "channel.mention": getattr(canal, "mention", ""),
        "channel.id": str(getattr(canal, "id", "")),
        "bot.name": bot_user.name,
        "bot.avatar": bot_user.display_avatar.url,
        "bot.mention": bot_user.mention,
        "bot.id": str(bot_user.id),
        "bot.invite": discord.utils.oauth_url(
            bot_user.id, scopes=("bot", "applications.commands")
        ),
        "date": agora.strftime("%d/%m/%Y"),
        "time": agora.strftime("%H:%M"),
    }


def aplicar_variaveis(texto, variaveis):
    """Troca {chave} pelo valor. Chaves desconhecidas ficam como estão."""
    return _PADRAO_VARIAVEL.sub(
        lambda m: variaveis.get(m.group(1), m.group(0)), texto or ""
    )


def url_valida(texto):
    return bool(texto) and texto.startswith(("http://", "https://"))


def valor_imagem_ok(texto):
    """Aceita link http(s) ou uma única variável, como {author.avatar}."""
    return url_valida(texto) or bool(_PADRAO_VARIAVEL.fullmatch(texto))


def validar_embed(embed):
    dados = embed.to_dict()

    if not (set(dados) - {"type", "color", "timestamp"}):
        return "O embed está vazio. Adicione um título, descrição ou imagem."

    if len(embed) > 6000:
        return "O embed passa de 6000 caracteres no total. Reduza os textos."

    return None


# ==========================================================
# ESTADO DO EMBED EM CRIAÇÃO
# ==========================================================

class EstadoEmbed:
    def __init__(self):
        self.titulo = ""
        self.titulo_url = ""
        self.descricao = DESCRICAO_PADRAO
        self.cor = COR_PADRAO
        self.autor_nome = ""
        self.autor_avatar = ""
        self.rodape_texto = ""
        self.rodape_icone = ""
        self.imagem = ""
        self.miniatura = ""
        self.campos = []          # (nome, valor, lado_a_lado)
        self.timestamp = True

    def construir(self, v):
        embed = discord.Embed(color=discord.Color(self.cor))

        titulo = aplicar_variaveis(self.titulo, v)[:256]
        if titulo:
            embed.title = titulo
            url = aplicar_variaveis(self.titulo_url, v)
            if url_valida(url):
                embed.url = url

        descricao = aplicar_variaveis(self.descricao, v)[:4096]
        if descricao:
            embed.description = descricao

        autor_nome = aplicar_variaveis(self.autor_nome, v)[:256]
        autor_avatar = aplicar_variaveis(self.autor_avatar, v)
        if not url_valida(autor_avatar):
            autor_avatar = ""
        if autor_nome or autor_avatar:
            embed.set_author(
                name=autor_nome or "\u200b",
                icon_url=autor_avatar or None
            )

        rodape_texto = aplicar_variaveis(self.rodape_texto, v)[:2048]
        rodape_icone = aplicar_variaveis(self.rodape_icone, v)
        if not url_valida(rodape_icone):
            rodape_icone = ""
        if rodape_texto or rodape_icone:
            embed.set_footer(
                text=rodape_texto or "\u200b",
                icon_url=rodape_icone or None
            )

        imagem = aplicar_variaveis(self.imagem, v)
        if url_valida(imagem):
            embed.set_image(url=imagem)

        miniatura = aplicar_variaveis(self.miniatura, v)
        if url_valida(miniatura):
            embed.set_thumbnail(url=miniatura)

        for nome, valor, lado_a_lado in self.campos:
            embed.add_field(
                name=aplicar_variaveis(nome, v)[:256] or "\u200b",
                value=aplicar_variaveis(valor, v)[:1024] or "\u200b",
                inline=lado_a_lado
            )

        if self.timestamp:
            embed.timestamp = discord.utils.utcnow()

        return embed


# ==========================================================
# MODAIS (janelinhas de preenchimento)
# ==========================================================

class ModalEditor(discord.ui.Modal):
    def __init__(self, editor, titulo):
        super().__init__(title=titulo, timeout=600)
        self.editor = editor


class ModalAutor(ModalEditor):
    def __init__(self, editor):
        super().__init__(editor, "Autor do embed")
        e = editor.estado

        self.nome = discord.ui.TextInput(
            label="Nome do autor (opcional)",
            placeholder="Ex.: {author.name}",
            default=e.autor_nome or None,
            required=False,
            max_length=256,
        )
        self.avatar = discord.ui.TextInput(
            label="Avatar do autor (opcional)",
            placeholder="Link da imagem ou {author.avatar}",
            default=e.autor_avatar or None,
            required=False,
            max_length=500,
        )
        self.add_item(self.nome)
        self.add_item(self.avatar)

    async def on_submit(self, interaction):
        avatar = self.avatar.value.strip()

        if avatar and not valor_imagem_ok(avatar):
            await interaction.response.send_message(
                "❌ Avatar inválido. Use um link que comece com "
                "http:// ou https://, ou uma variável como `{author.avatar}`.",
                ephemeral=True
            )
            return

        e = self.editor.estado
        e.autor_nome = self.nome.value.strip()
        e.autor_avatar = avatar
        await self.editor.atualizar(interaction)


class ModalTitulo(ModalEditor):
    def __init__(self, editor):
        super().__init__(editor, "Título do embed")
        e = editor.estado

        self.titulo = discord.ui.TextInput(
            label="Título",
            placeholder="Deixe vazio para remover o título",
            default=e.titulo or None,
            required=False,
            max_length=256,
        )
        self.url = discord.ui.TextInput(
            label="Link do título (opcional)",
            placeholder="https://...",
            default=e.titulo_url or None,
            required=False,
            max_length=500,
        )
        self.add_item(self.titulo)
        self.add_item(self.url)

    async def on_submit(self, interaction):
        url = self.url.value.strip()

        if url and not (url_valida(url) or _PADRAO_VARIAVEL.fullmatch(url)):
            await interaction.response.send_message(
                "❌ Link inválido. Ele precisa começar com http:// ou https://.",
                ephemeral=True
            )
            return

        e = self.editor.estado
        e.titulo = self.titulo.value.strip()
        e.titulo_url = url
        await self.editor.atualizar(interaction)


class ModalDescricao(ModalEditor):
    def __init__(self, editor):
        super().__init__(editor, "Descrição do embed")

        self.descricao = discord.ui.TextInput(
            label="Descrição",
            style=discord.TextStyle.paragraph,
            placeholder="Apague todo o texto para remover a descrição.",
            default=editor.estado.descricao or None,
            required=False,
            max_length=4000,
        )
        self.add_item(self.descricao)

    async def on_submit(self, interaction):
        self.editor.estado.descricao = self.descricao.value.strip()
        await self.editor.atualizar(interaction)


class ModalCor(ModalEditor):
    def __init__(self, editor):
        super().__init__(editor, "Cor do embed")

        self.cor = discord.ui.TextInput(
            label="Cor em hexadecimal",
            placeholder="Ex.: #6A00FF",
            default=f"#{editor.estado.cor:06X}",
            required=True,
            min_length=6,
            max_length=7,
        )
        self.add_item(self.cor)

    async def on_submit(self, interaction):
        cor_hex = self.cor.value.strip().removeprefix("#")

        if len(cor_hex) != 6 or any(
            c not in "0123456789abcdefABCDEF" for c in cor_hex
        ):
            await interaction.response.send_message(
                "❌ Cor inválida! Use um formato como #6A00FF.",
                ephemeral=True
            )
            return

        self.editor.estado.cor = int(cor_hex, 16)
        await self.editor.atualizar(interaction)


class ModalRodape(ModalEditor):
    def __init__(self, editor):
        super().__init__(editor, "Rodapé do embed")
        e = editor.estado

        self.texto = discord.ui.TextInput(
            label="Texto do rodapé",
            placeholder="Ex.: {server.name}",
            default=e.rodape_texto or None,
            required=False,
            max_length=2048,
        )
        self.icone = discord.ui.TextInput(
            label="Ícone do rodapé (opcional)",
            placeholder="Link da imagem ou {server.icon}",
            default=e.rodape_icone or None,
            required=False,
            max_length=500,
        )
        self.add_item(self.texto)
        self.add_item(self.icone)

    async def on_submit(self, interaction):
        icone = self.icone.value.strip()

        if icone and not valor_imagem_ok(icone):
            await interaction.response.send_message(
                "❌ Ícone inválido. Use um link http(s) ou uma variável.",
                ephemeral=True
            )
            return

        e = self.editor.estado
        e.rodape_texto = self.texto.value.strip()
        e.rodape_icone = icone
        await self.editor.atualizar(interaction)


class ModalImagem(ModalEditor):
    """Serve para a imagem grande e para a miniatura."""

    def __init__(self, editor, tipo):
        titulo = "Imagem do embed" if tipo == "imagem" else "Miniatura do embed"
        super().__init__(editor, titulo)
        self.tipo = tipo

        atual = editor.estado.imagem if tipo == "imagem" else editor.estado.miniatura

        self.link = discord.ui.TextInput(
            label="Link da imagem",
            placeholder="https://...  (vazio remove a imagem)",
            default=atual or None,
            required=False,
            max_length=500,
        )
        self.add_item(self.link)

    async def on_submit(self, interaction):
        link = self.link.value.strip()

        if link and not valor_imagem_ok(link):
            await interaction.response.send_message(
                "❌ Link inválido. Ele precisa começar com http:// ou https://.",
                ephemeral=True
            )
            return

        if self.tipo == "imagem":
            self.editor.estado.imagem = link
        else:
            self.editor.estado.miniatura = link

        await self.editor.atualizar(interaction)


class ModalCampo(ModalEditor):
    def __init__(self, editor):
        super().__init__(editor, "Adicionar campo")

        self.nome = discord.ui.TextInput(
            label="Nome do campo",
            required=True,
            max_length=256,
        )
        self.valor = discord.ui.TextInput(
            label="Texto do campo",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1024,
        )
        self.lado = discord.ui.TextInput(
            label="Lado a lado com outros? (sim/não)",
            default="não",
            required=False,
            max_length=3,
        )
        self.add_item(self.nome)
        self.add_item(self.valor)
        self.add_item(self.lado)

    async def on_submit(self, interaction):
        e = self.editor.estado

        if len(e.campos) >= MAX_CAMPOS:
            await interaction.response.send_message(
                f"❌ Limite de {MAX_CAMPOS} campos atingido.",
                ephemeral=True
            )
            return

        lado = self.lado.value.strip().lower() in ("sim", "s", "yes", "y", "1")
        e.campos.append((self.nome.value.strip(), self.valor.value.strip(), lado))
        await self.editor.atualizar(interaction)


class ModalRemoverCampo(ModalEditor):
    def __init__(self, editor):
        super().__init__(editor, "Remover campo")

        self.numero = discord.ui.TextInput(
            label=f"Número do campo (1 a {len(editor.estado.campos)})",
            placeholder="Conte de cima para baixo no embed",
            required=True,
            max_length=2,
        )
        self.add_item(self.numero)

    async def on_submit(self, interaction):
        e = self.editor.estado
        texto = self.numero.value.strip()

        if not texto.isdigit() or not (1 <= int(texto) <= len(e.campos)):
            await interaction.response.send_message(
                f"❌ Digite um número entre 1 e {len(e.campos)}.",
                ephemeral=True
            )
            return

        e.campos.pop(int(texto) - 1)
        await self.editor.atualizar(interaction)


# ==========================================================
# EDITOR DE EMBED (mensagem com botões)
# ==========================================================

class EditorEmbed(discord.ui.View):
    def __init__(self, usuario, estado, destino, guild, bot_user, interacao):
        super().__init__(timeout=TEMPO_EDITOR)
        self.usuario = usuario
        self.estado = estado
        self.destino = destino
        self.guild = guild
        self.bot_user = bot_user
        self.interacao = interacao
        self.finalizado = False

    # ---------- utilidades ----------

    def variaveis(self):
        return montar_variaveis(self.usuario, self.guild, self.destino, self.bot_user)

    def conteudo(self, aviso=None):
        linhas = [
            "🛠️ **Editor de embed**",
            f"📍 **Destino:** {self.destino.mention}",
            "Use os botões para montar o embed. Clique em **Variáveis** para "
            "ver os campos dinâmicos, como `{author.name}`.",
        ]
        if aviso:
            linhas.append(aviso)
        return "\n".join(linhas)

    async def atualizar(self, interaction, aviso=None):
        embed = self.estado.construir(self.variaveis())
        erro = validar_embed(embed)

        if erro:
            aviso = f"⚠️ {erro}"
            embed = None

        try:
            await interaction.response.edit_message(
                content=self.conteudo(aviso), embed=embed, view=self
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ O Discord recusou o embed. Confira os links de imagem.",
                ephemeral=True
            )

    def desativar(self):
        for item in self.children:
            item.disabled = True

    async def interaction_check(self, interaction):
        if interaction.user.id != self.usuario.id:
            await interaction.response.send_message(
                "❌ Apenas quem executou o comando pode usar este editor.",
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        if self.finalizado:
            return

        self.desativar()
        try:
            await self.interacao.edit_original_response(
                content="⌛ O editor expirou. Use `/create embed` para começar de novo.",
                view=self
            )
        except discord.HTTPException:
            pass

    # ---------- linha 1 ----------

    @discord.ui.button(label="Autor", emoji="👤", style=discord.ButtonStyle.primary, row=0)
    async def botao_autor(self, interaction, button):
        await interaction.response.send_modal(ModalAutor(self))

    @discord.ui.button(label="Título", emoji="🏷️", style=discord.ButtonStyle.secondary, row=0)
    async def botao_titulo(self, interaction, button):
        await interaction.response.send_modal(ModalTitulo(self))

    @discord.ui.button(label="Descrição", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def botao_descricao(self, interaction, button):
        await interaction.response.send_modal(ModalDescricao(self))

    @discord.ui.button(label="Cor", emoji="🎨", style=discord.ButtonStyle.secondary, row=0)
    async def botao_cor(self, interaction, button):
        await interaction.response.send_modal(ModalCor(self))

    @discord.ui.button(label="Rodapé", emoji="📌", style=discord.ButtonStyle.secondary, row=0)
    async def botao_rodape(self, interaction, button):
        await interaction.response.send_modal(ModalRodape(self))

    # ---------- linha 2 ----------

    @discord.ui.button(label="Imagem", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def botao_imagem(self, interaction, button):
        await interaction.response.send_modal(ModalImagem(self, "imagem"))

    @discord.ui.button(label="Miniatura", emoji="🔳", style=discord.ButtonStyle.secondary, row=1)
    async def botao_miniatura(self, interaction, button):
        await interaction.response.send_modal(ModalImagem(self, "miniatura"))

    @discord.ui.button(label="Campo", emoji="➕", style=discord.ButtonStyle.secondary, row=1)
    async def botao_campo(self, interaction, button):
        if len(self.estado.campos) >= MAX_CAMPOS:
            await interaction.response.send_message(
                f"❌ Limite de {MAX_CAMPOS} campos atingido.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ModalCampo(self))

    @discord.ui.button(label="Campo", emoji="➖", style=discord.ButtonStyle.secondary, row=1)
    async def botao_remover_campo(self, interaction, button):
        if not self.estado.campos:
            await interaction.response.send_message(
                "❌ Este embed ainda não tem campos.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ModalRemoverCampo(self))

    @discord.ui.button(label="Data: ligada", emoji="🕒", style=discord.ButtonStyle.secondary, row=1)
    async def botao_data(self, interaction, button):
        self.estado.timestamp = not self.estado.timestamp
        button.label = "Data: ligada" if self.estado.timestamp else "Data: desligada"
        await self.atualizar(interaction)

    # ---------- linha 3 ----------

    @discord.ui.button(label="Variáveis", emoji="🧩", style=discord.ButtonStyle.secondary, row=2)
    async def botao_variaveis(self, interaction, button):
        await interaction.response.send_message(AJUDA_VARIAVEIS, ephemeral=True)

    @discord.ui.button(label="Enviar", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def botao_enviar(self, interaction, button):
        embed = self.estado.construir(self.variaveis())
        erro = validar_embed(embed)

        if erro:
            await interaction.response.send_message(f"❌ {erro}", ephemeral=True)
            return

        permissoes = self.destino.permissions_for(self.guild.me)
        if not (
            permissoes.view_channel
            and permissoes.send_messages
            and permissoes.embed_links
        ):
            await interaction.response.send_message(
                f"❌ Não tenho permissão para enviar embeds em "
                f"{self.destino.mention}.",
                ephemeral=True
            )
            return

        try:
            mensagem = await self.destino.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissão para enviar nesse canal.",
                ephemeral=True
            )
            return
        except discord.HTTPException as erro_http:
            print(f"Erro ao enviar embed: {erro_http}")
            await interaction.response.send_message(
                "❌ Não consegui enviar o embed. Confira os links de imagem.",
                ephemeral=True
            )
            return

        self.finalizado = True
        self.desativar()
        self.stop()

        await interaction.response.edit_message(
            content=(
                f"✅ Embed enviado em {self.destino.mention}. "
                f"[Ir para a mensagem]({mensagem.jump_url})"
            ),
            embed=embed,
            view=self
        )

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.danger, row=2)
    async def botao_cancelar(self, interaction, button):
        self.finalizado = True
        self.desativar()
        self.stop()

        await interaction.response.edit_message(
            content="❌ Criação do embed cancelada.", embed=None, view=self
        )

    # ---------- linha 4 ----------

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        placeholder="Canal de destino (padrão: este canal)",
        min_values=1,
        max_values=1,
        row=3,
    )
    async def escolher_canal(self, interaction, select):
        canal = self.guild.get_channel(select.values[0].id)

        if canal is None or not hasattr(canal, "send"):
            await interaction.response.send_message(
                "❌ Não consegui encontrar esse canal.", ephemeral=True
            )
            return

        self.destino = canal
        await self.atualizar(interaction)


# ==========================================================
# COG CRIADOR
# ==========================================================

class Criador(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # ======================================================
    # IMAGEM DA SUGESTÃO (mesmo estilo dos logs)
    # ======================================================

    async def gerar_imagem_sugestao(self, usuario, destino, texto):
        try:
            avatar_bytes = await usuario.display_avatar.replace(
                size=128, static_format="png"
            ).read()
        except Exception:
            avatar_bytes = b""

        horario = f"Hoje às {datetime.now(FUSO):%H:%M}"

        dados = await asyncio.to_thread(
            renderizar_cartao,
            avatar_bytes,
            usuario.display_name,
            getattr(destino, "name", "sugestões"),
            "sugestao",
            texto,
            None,
            horario,
            None,
            0,
        )

        return discord.File(dados, filename="sugestao.png")

    @staticmethod
    def citar(texto, limite=1500):
        if len(texto) > limite:
            texto = texto[:limite].rstrip() + " …"
        return "\n".join(f"> {linha}" if linha else ">" for linha in texto.split("\n"))

    # ======================================================
    # /SUGESTAO
    # ======================================================

    @app_commands.command(
        name="sugestao",
        description="Envia uma sugestão para a equipe do servidor."
    )
    @app_commands.describe(
        texto="Escreva sua sugestão com o máximo de detalhes possível."
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1, 60.0, key=lambda i: (i.guild_id, i.user.id)
    )
    async def sugestao(
        self,
        interaction: discord.Interaction,
        texto: app_commands.Range[str, 3, 1500]
    ):
        if CANAL_SUGESTOES_ID:
            destino = interaction.guild.get_channel(CANAL_SUGESTOES_ID)
        else:
            destino = interaction.channel

        if destino is None or not hasattr(destino, "send"):
            await interaction.response.send_message(
                "❌ Não encontrei o canal de sugestões. "
                "Avise a equipe para conferir a configuração.",
                ephemeral=True
            )
            return

        permissoes = destino.permissions_for(interaction.guild.me)
        faltando = [
            nome for nome, ok in (
                ("Enviar mensagens", permissoes.send_messages),
                ("Inserir links", permissoes.embed_links),
                ("Anexar arquivos", permissoes.attach_files),
                ("Adicionar reações", permissoes.add_reactions),
            ) if not ok
        ]

        if faltando:
            await interaction.response.send_message(
                "❌ Não tenho as permissões necessárias no canal de "
                f"sugestões: **{', '.join(faltando)}**.",
                ephemeral=True
            )
            return

        # Gerar a imagem pode passar de 3 segundos.
        await interaction.response.defer(ephemeral=True)

        usuario = interaction.user

        descricao = "\n\n".join([
            f"{usuario.mention} enviou uma nova sugestão para a equipe.",
            f"**Sugestão:**\n{self.citar(texto)}",
            "**Como votar:** reaja com 👍 para apoiar ou 👎 para discordar.",
        ])

        embed = discord.Embed(
            title="💡 Nova sugestão",
            description=descricao,
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_author(
            name=f"{usuario.display_name} ({usuario})",
            icon_url=usuario.display_avatar.url
        )
        embed.add_field(name="👤 Autor", value=usuario.mention, inline=True)
        embed.add_field(
            name="📍 Enviada em",
            value=getattr(interaction.channel, "mention", "—"),
            inline=True
        )
        embed.add_field(name="📊 Status", value="⏳ Em análise", inline=True)
        embed.set_footer(text=f"ID do usuário: {usuario.id}")

        arquivo = None
        if renderizar_cartao is not None:
            try:
                arquivo = await self.gerar_imagem_sugestao(usuario, destino, texto)
                embed.set_image(url="attachment://sugestao.png")
            except Exception as erro:
                print(f"Erro ao gerar imagem da sugestão: {erro}")
                arquivo = None

        try:
            mensagem = await destino.send(embed=embed, file=arquivo)

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não tenho permissão para enviar mensagens nesse canal.",
                ephemeral=True
            )
            return

        except discord.HTTPException as erro:
            print(f"Erro ao publicar sugestão: {erro}")
            await interaction.followup.send(
                "❌ Não consegui publicar a sugestão. Tente novamente.",
                ephemeral=True
            )
            return

        for emoji in ("👍", "👎"):
            try:
                await mensagem.add_reaction(emoji)
            except discord.HTTPException:
                break

        await interaction.followup.send(
            f"✅ Sua sugestão foi enviada para {destino.mention}! "
            f"[Ver sugestão]({mensagem.jump_url})",
            ephemeral=True
        )

    # ======================================================
    # /CREATE EMBED
    # ======================================================

    create = app_commands.Group(
        name="create",
        description="Ferramentas de criação para a equipe do servidor.",
        guild_only=True,
        default_permissions=discord.Permissions(administrator=True)
    )

    @create.command(
        name="embed",
        description="Abre o editor para criar um embed personalizado."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def create_embed(self, interaction: discord.Interaction):
        destino = interaction.channel

        if destino is None or not hasattr(destino, "send"):
            await interaction.response.send_message(
                "❌ Não consegui encontrar o canal de destino.",
                ephemeral=True
            )
            return

        estado = EstadoEmbed()

        editor = EditorEmbed(
            usuario=interaction.user,
            estado=estado,
            destino=destino,
            guild=interaction.guild,
            bot_user=interaction.client.user,
            interacao=interaction
        )

        await interaction.response.send_message(
            content=editor.conteudo(),
            embed=estado.construir(editor.variaveis()),
            view=editor,
            ephemeral=True
        )

    # ======================================================
    # ERROS DOS COMANDOS
    # ======================================================

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            mensagem = "❌ Apenas administradores podem usar esse comando."

        elif isinstance(error, app_commands.CommandOnCooldown):
            mensagem = (
                "⏳ Você enviou uma sugestão há pouco tempo. "
                f"Tente novamente em {error.retry_after:.0f}s."
            )

        else:
            print(f"Erro no cog Criador: {error}")
            mensagem = "❌ Ocorreu um erro ao executar o comando."

        if interaction.response.is_done():
            await interaction.followup.send(mensagem, ephemeral=True)
        else:
            await interaction.response.send_message(mensagem, ephemeral=True)


# ==========================================================
# CARREGAR COG
# ==========================================================

async def setup(bot):
    if renderizar_cartao is None and LOGS_DESATUALIZADO:
        print(
            "⚠️ cogs/logs.py está desatualizado: a imagem da /sugestao "
            "foi desativada. Substitua pelo logs.py novo."
        )

    await bot.add_cog(Criador(bot))
