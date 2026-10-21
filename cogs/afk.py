import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime


class AFK(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.afks = {}

    @app_commands.command(
        name="afk",
        description="Fica AFK com um motivo opcional."
    )
    @app_commands.describe(
        motivo="O motivo de você estar AFK."
    )
    async def afk(
        self,
        interaction: discord.Interaction,
        motivo: str = "Nenhum motivo informado."
    ):
        self.afks[interaction.user.id] = {
            "motivo": motivo,
            "desde": datetime.now()
        }

        embed = discord.Embed(
            title="💤 AFK ativado",
            description=(
                f"{interaction.user.mention} agora está AFK!\n\n"
                f"**Motivo:** {motivo}"
            ),
            color=discord.Color.orange()
        )

        embed.set_image(
             url="https://cdn.discordapp.com/attachments/1482897856208572487/1553867154821218454/ChatGPT_Image_27_de_set._de_2026_16_45_07.png?ex=6abacf0f&is=6ab97d8f&hm=ca53dcaad7d63d14461957b22be798acc6886e105b3a3c74d9aa8dec7a550a52&"
        )

        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        if message.author.bot:
            return

        # Se a pessoa estava AFK e mandou mensagem, remove o AFK
        if message.author.id in self.afks:

            dados = self.afks.pop(message.author.id)

            embed = discord.Embed(
                title="👋 AFK removido",
                description=(
                    f"{message.author.mention}, você voltou!\n"
                    f"Você estava AFK por **{self.tempo_afk(dados['desde'])}**."
                ),
                color=discord.Color.green()
            )

            embed.set_image(
                url="https://cdn.discordapp.com/attachments/1482897856208572487/1553857471842623529/ChatGPT_Image_27_de_set._de_2026_16_54_23.png?ex=6abac60a&is=6ab9748a&hm=f17389e0afc16615ba7cea6c05a0ff97ac433e71fe6e40e12f2fe391e852fd3c&"
            )

            await message.channel.send(embed=embed)

        # Verifica quem foi mencionado
        for usuario in message.mentions:

            if usuario.id not in self.afks:
                continue

            dados = self.afks[usuario.id]

            embed = discord.Embed(
                title="💤 Usuário AFK",
                description=(
                    f"{usuario.mention} está AFK no momento.\n\n"
                    f"**Motivo:** {dados['motivo']}\n"
                    f"**Desde:** {self.tempo_afk(dados['desde'])}"
                ),
                color=discord.Color.orange()
            )

            embed.set_image(
                url="https://cdn.discordapp.com/attachments/1482897856208572487/1553855834629349497/ChatGPT_Image_27_de_set._de_2026_16_45_07.png?ex=6abac484&is=6ab97304&hm=1d703027046e7c7b86e4cfe8c9cf42804a68eda54768bf2a6620eb974c8e4ee0&"
            )
            
            await message.channel.send(embed=embed)

    def tempo_afk(self, inicio):
        agora = datetime.now()
        segundos = int((agora - inicio).total_seconds())

        minutos = segundos // 60
        horas = minutos // 60

        minutos = minutos % 60

        if horas > 0:
            return f"{horas}h {minutos}min"

        if minutos > 0:
            return f"{minutos}min"

        return f"{segundos}s"


async def setup(bot):
    await bot.add_cog(AFK(bot))