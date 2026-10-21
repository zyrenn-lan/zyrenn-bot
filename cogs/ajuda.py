import discord
from discord.ext import commands
from discord import app_commands


class AjudaView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="🔵 Utilidade",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def utilidade(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🔵 Utilidade",
            description=(
                "`/ajuda` — Mostra este painel\n"
                "`/ping` — Mostra a latência do bot\n"
                "`/avatar` — Mostra o avatar de um usuário\n"
                "`/userinfo` — Mostra informações de um usuário\n"
                "`/serverinfo` — Mostra informações do servidor"
            ),
            color=discord.Color.blue()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=VoltarView()
        )

    @discord.ui.button(
        label="🟢 Entretenimento",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def entretenimento(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🟢 Entretenimento",
            description=(
                "`/meme` — Envia um meme\n"
                "`/ship` — Cria um ship\n"
                "`/8ball` — Faz uma pergunta para a 8ball\n"
                "`/dado` — Rola um dado\n"
                "`/caraoucoroa` — Cara ou coroa\n"
                "`/batalha` — Batalha entre usuários"
            ),
            color=discord.Color.green()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=VoltarView()
        )

    @discord.ui.button(
        label="🔴 Moderação",
        style=discord.ButtonStyle.danger,
        row=0
    )
    async def moderacao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🔴 Moderação",
            description=(
                "`/ban` — Bane um usuário\n"
                "`/kick` — Expulsa um usuário\n"
                "`/mute` — Silencia um usuário\n"
                "`/avisar` — Avisa um usuário\n"
                "`/clear` — Apaga mensagens\n"
                "`/lock` — Tranca um canal\n"
                "`/unlock` — Destranca um canal\n"
                "`/autolink` — Configura o sistema automático de links"
            ),
            color=discord.Color.red()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=VoltarView()
        )

    @discord.ui.button(
        label="🟡 Edição",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def edicao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🟡 Edição",
            description=(
                "`/xml` — Comandos relacionados a XML\n"
                "`/edit` — Ferramentas para edição\n"
                "`/benchmark` — Mostra informações de benchmark"
            ),
            color=discord.Color.gold()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=VoltarView()
        )

    @discord.ui.button(
        label="⚪ IA",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def ia(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="⚪ Inteligência Artificial",
            description=(
                "`/chat_on` — Ativa o chat de IA\n"
                "`/chat_off` — Desativa o chat de IA\n"
                "`/memoria` — Gerencia a memória do chat"
            ),
            color=discord.Color.light_grey()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=VoltarView()
        )

    @discord.ui.button(
        label="❤️ Eventos",
        style=discord.ButtonStyle.danger,
        row=2
    )
    async def eventos(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="❤️ Eventos",
            description=(
                "`/evento` — Cria um evento\n"
                "`/eventos` — Mostra os eventos disponíveis"
            ),
            color=discord.Color.red()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=VoltarView()
        )


class VoltarView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="↩️ Voltar",
        style=discord.ButtonStyle.secondary
    )
    async def voltar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="🤖 Central de Ajuda",
            description=(
                "Selecione uma categoria abaixo para ver "
                "os comandos disponíveis.\n\n"
                "🔵 **Utilidade**\n"
                "🟢 **Entretenimento**\n"
                "🔴 **Moderação**\n"
                "🟡 **Edição**\n"
                "⚪ **IA**\n"
                "❤️ **Eventos**"
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.edit_message(
            embed=embed,
            view=AjudaView()
        )


class Ajuda(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="ajuda",
        description="Mostra todos os comandos do Zyrenn Bot."
    )
    async def ajuda(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="🤖 Central de Ajuda",
            description=(
                "Selecione uma categoria abaixo para ver "
                "os comandos disponíveis.\n\n"
                "🔵 **Utilidade**\n"
                "🟢 **Entretenimento**\n"
                "🔴 **Moderação**\n"
                "🟡 **Edição**\n"
                "⚪ **IA**\n"
                "❤️ **Eventos**"
            ),
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text="Zyrenn Bot • Sistema de Ajuda"
        )

        await interaction.response.send_message(
            embed=embed,
            view=AjudaView(),
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Ajuda(bot))
    print("✅ Cog carregado: ajuda.py")