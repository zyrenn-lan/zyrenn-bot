import discord
from discord.ext import commands


# =========================
# MENU DE COMANDOS
# =========================

class ComandosView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(
        label="Utilidade",
        emoji="🔵",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def utilidade(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🔵 Comandos de Utilidade",
            description=(
                "`/comando1` — descrição\n"
                "`/comando2` — descrição"
            ),
            color=discord.Color.blue()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

    @discord.ui.button(
        label="Entretenimento",
        emoji="🟢",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def entretenimento(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🟢 Comandos de Entretenimento",
            description=(
                "`/comando1` — descrição\n"
                "`/comando2` — descrição"
            ),
            color=discord.Color.green()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

    @discord.ui.button(
        label="Moderação",
        emoji="🔴",
        style=discord.ButtonStyle.danger,
        row=0
    )
    async def moderacao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🔴 Comandos de Moderação",
            description=(
                "`/ban` — descrição\n"
                "`/kick` — descrição\n"
                "`/mute` — descrição"
            ),
            color=discord.Color.red()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

    @discord.ui.button(
        label="Edição",
        emoji="🟡",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def edicao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🟡 Comandos de Edição",
            description=(
                "`/comando1` — descrição\n"
                "`/comando2` — descrição"
            ),
            color=discord.Color.gold()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

    @discord.ui.button(
        label="IA",
        emoji="⚪",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def ia(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="⚪ Comandos de Inteligência Artificial",
            description=(
                "`/comando1` — descrição\n"
                "`/comando2` — descrição"
            ),
            color=discord.Color.light_grey()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

    @discord.ui.button(
        label="Eventos",
        emoji="❤️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def eventos(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="❤️ Atalhos e Eventos",
            description=(
                "`/comando1` — descrição\n"
                "`/comando2` — descrição"
            ),
            color=discord.Color.red()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

    # VOLTAR FICA SOZINHO EMBAIXO
    @discord.ui.button(
        label="Voltar",
        emoji="↩️",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def voltar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        embed = criar_embed_inicial()

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )


# =========================
# EMBED INICIAL
# =========================

def criar_embed_inicial():

    embed = discord.Embed(
        title="👋 Bem-vindo ao Zyrenn Bot!",
        description="Escolha uma categoria abaixo para ver os comandos disponíveis.",
        color=discord.Color.from_str("#6A00FF")
    )

    # PRIMEIRA LINHA
    embed.add_field(
        name="🔵 Utilidade",
        value="\u200b",
        inline=True
    )

    embed.add_field(
        name="🟢 Entretenimento",
        value="\u200b",
        inline=True
    )

    embed.add_field(
        name="🔴 Moderação (staff)",
        value="\u200b",
        inline=True
    )

    # SEGUNDA LINHA
    embed.add_field(
        name="🟡 Edição",
        value="\u200b",
        inline=True
    )

    embed.add_field(
        name="⚪ Inteligência Artificial",
        value="\u200b",
        inline=True
    )

    embed.add_field(
        name="❤️ Atalhos e Eventos",
        value="\u200b",
        inline=True
    )

    return embed


# =========================
# BOTÃO DO EMBED INICIAL
# =========================

class InitialView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(
        label="Ver Comandos",
        emoji="📖",
        style=discord.ButtonStyle.primary
    )
    async def ver_comandos(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            embed=criar_embed_inicial(),
            view=ComandosView(),
            ephemeral=True
        )


# =========================
# AUTOREPLY
# =========================

class AutoReply(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if message.content.strip() in (
            f"<@{self.bot.user.id}>",
            f"<@!{self.bot.user.id}>"
        ):

            embed = discord.Embed(
                title=f"Olá, {message.author.display_name}!",
                description=(
                    "Eu sou o **Zyrenn Bot**, o melhor bot de edição brasileiro "
                    "— contenho comandos de edição de vídeo, moderação, IA e etc, "
                    "via slash e prefix.\n\n"
                    "Use o botão abaixo para ver tudo que eu faço."
                ),
                color=discord.Color.from_str("#6A00FF")
            )

            embed.set_image(
                url="https://cdn.discordapp.com/attachments/1482897856208572487/1552313085912551434/1790134652473.png?ex=6ab527b8&is=6ab3d638&hm=398cc7b07ac1b00dfbe205e6934c1c3ddfaa655a475d1769e53ac2f2090fd817&"
            )

            await message.channel.send(
                embed=embed,
                view=InitialView()
            )


async def setup(bot):
    await bot.add_cog(AutoReply(bot))