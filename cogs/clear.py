
import discord
from discord.ext import commands


class Clear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # COMANDO PREFIXO: -clear / -purge
    # ==========================================

    @commands.command(name="clear", aliases=["purge"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(
        manage_messages=True,
        read_message_history=True
    )
    async def clear(self, ctx, quantidade: int):
        if not 1 <= quantidade <= 100:
            return await ctx.reply(
                "❌ Escolha uma quantidade entre 1 e 100.",
                delete_after=5
            )

        try:
            # +1 para incluir a mensagem que contém o comando
            apagadas = await ctx.channel.purge(
                limit=quantidade + 1
            )

            # Desconta a mensagem do comando, caso tenha sido apagada
            total = sum(
                1 for mensagem in apagadas
                if mensagem.id != ctx.message.id
            )

            confirmacao = await ctx.send(
                f"🧹 {ctx.author.mention}, apaguei "
                f"**{total} mensagens**!"
            )
            await confirmacao.delete(delay=5)

        except discord.Forbidden:
            await ctx.reply(
                "❌ Não tenho permissão para apagar mensagens.",
                delete_after=5
            )

        except discord.HTTPException:
            await ctx.reply(
                "❌ Ocorreu um erro ao apagar as mensagens.",
                delete_after=5
            )

    # ==========================================
    # COMANDO SLASH: /clear
    # ==========================================

    @discord.app_commands.command(
        name="clear",
        description="Apaga mensagens do canal."
    )
    @discord.app_commands.describe(
        quantidade="Quantidade de mensagens para apagar (1 a 100)"
    )
    @discord.app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def clear_slash(
        self,
        interaction: discord.Interaction,
        quantidade: discord.app_commands.Range[int, 1, 100]
    ):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message(
                "❌ Use este comando em um servidor.",
                ephemeral=True
            )

        permissoes = interaction.channel.permissions_for(
            interaction.guild.me
        )

        if not permissoes.manage_messages:
            return await interaction.response.send_message(
                "❌ Preciso da permissão **Gerenciar mensagens**.",
                ephemeral=True
            )

        if not permissoes.read_message_history:
            return await interaction.response.send_message(
                "❌ Preciso da permissão **Ler histórico de mensagens**.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        try:
            apagadas = await interaction.channel.purge(
                limit=quantidade
            )

            await interaction.followup.send(
                f"🧹 Apaguei **{len(apagadas)} mensagens**!",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não tenho permissão para apagar mensagens.",
                ephemeral=True
            )

        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Ocorreu um erro ao apagar as mensagens.",
                ephemeral=True
            )

    # ==========================================
    # ERROS DO COMANDO PREFIXO
    # ==========================================

    @clear.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(
                "❌ Você precisa da permissão "
                "**Gerenciar mensagens**.",
                delete_after=5
            )

        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.reply(
                "❌ Preciso das permissões **Gerenciar mensagens** "
                "e **Ler histórico de mensagens**.",
                delete_after=5
            )

        elif isinstance(
            error,
            (
                commands.MissingRequiredArgument,
                commands.BadArgument
            )
        ):
            await ctx.reply(
                "⚠️ Informe uma quantidade válida! "
                "Exemplo: `-clear 50`",
                delete_after=5
            )


    # ==========================================
    # ERROS DO COMANDO SLASH
    # ==========================================

    @clear_slash.error
    async def clear_slash_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError
    ):
        if isinstance(
            error,
            discord.app_commands.errors.MissingPermissions
        ):
            mensagem = (
                "❌ Você precisa da permissão "
                "**Gerenciar mensagens**."
            )
        else:
            mensagem = (
                "❌ Não consegui executar o comando. "
                "Verifique minhas permissões e tente novamente."
            )

        if interaction.response.is_done():
            await interaction.followup.send(
                mensagem,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                mensagem,
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Clear(bot))
