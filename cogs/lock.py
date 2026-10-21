import discord
from discord.ext import commands
from discord import app_commands


class Lock(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="lock",
        description="Bloqueia o canal para membros comuns."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def lock(self, interaction: discord.Interaction):

        canal = interaction.channel

        if not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Esse comando só pode ser usado em canais de texto.",
                ephemeral=True
            )
            return

        try:
            await canal.set_permissions(
                interaction.guild.default_role,
                send_messages=False
            )

            embed = discord.Embed(
                title="🔒 Canal bloqueado",
                description=(
                    f"Este canal foi bloqueado por {interaction.user.mention}.\n\n"
                    "🔒 Apenas membros com permissão para enviar mensagens "
                    "poderão falar aqui."
                ),
                color=discord.Color.red()
            )

            embed.set_footer(
                text=f"Zyrenn Bot • {canal.name}"
            )

            await interaction.response.send_message(embed=embed)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissão para bloquear este canal.",
                ephemeral=True
            )

        except Exception as e:
            print(f"Erro no /lock: {e}")

            await interaction.response.send_message(
                "❌ Ocorreu um erro ao bloquear o canal.",
                ephemeral=True
            )

    @app_commands.command(
        name="unlock",
        description="Desbloqueia o canal para membros comuns."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def unlock(self, interaction: discord.Interaction):

        canal = interaction.channel

        if not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Esse comando só pode ser usado em canais de texto.",
                ephemeral=True
            )
            return

        try:
            await canal.set_permissions(
                interaction.guild.default_role,
                send_messages=None
            )

            embed = discord.Embed(
                title="🔓 Canal desbloqueado",
                description=(
                    f"Este canal foi desbloqueado por {interaction.user.mention}.\n\n"
                    "🔓 Os membros podem enviar mensagens novamente."
                ),
                color=discord.Color.green()
            )

            embed.set_footer(
                text=f"Zyrenn Bot • {canal.name}"
            )

            await interaction.response.send_message(embed=embed)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissão para desbloquear este canal.",
                ephemeral=True
            )

        except Exception as e:
            print(f"Erro no /unlock: {e}")

            await interaction.response.send_message(
                "❌ Ocorreu um erro ao desbloquear o canal.",
                ephemeral=True
            )

    @lock.error
    async def lock_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa ter **Administrador** para usar esse comando.",
                ephemeral=True
            )

    @unlock.error
    async def unlock_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa ter **Administrador** para usar esse comando.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Lock(bot))