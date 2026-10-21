
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

COR = 0x6A00FF
TEMPO_LIMITE = 300


class Casamento(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pedidos = {}

    @app_commands.command(
        name="casamento",
        description="Peça alguém em casamento 💍"
    )
    @app_commands.describe(
        membro2="A pessoa ou o bot que receberá o pedido"
    )
    async def casamento(
        self,
        interaction: discord.Interaction,
        membro2: discord.Member
    ):
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message(
                "❌ Use esse comando dentro de um servidor.",
                ephemeral=True
            )
            return

        if membro2.id == self.bot.user.id:
            await interaction.response.send_message(
                "💍 Eu não posso pedir a mim mesmo em casamento KKKK.",
                ephemeral=True
            )
            return

        if membro2.id == interaction.user.id:
            await interaction.response.send_message(
                "💍 Você não pode se casar consigo mesmo!",
                ephemeral=True
            )
            return

        chave = (
            interaction.guild.id,
            interaction.channel.id,
            membro2.id
        )

        agora = asyncio.get_running_loop().time()
        pedido_existente = self.pedidos.get(chave)

        if pedido_existente:
            if agora - pedido_existente["tempo"] < TEMPO_LIMITE:
                await interaction.response.send_message(
                    "💍 Já existe um pedido pendente para esse membro neste canal.",
                    ephemeral=True
                )
                return

            self.pedidos.pop(chave, None)

        self.pedidos[chave] = {
            "tempo": agora,
            "membro": membro2,
            "guild_id": interaction.guild.id,
            "channel_id": interaction.channel.id,
        }

        embed = discord.Embed(
            title="💍 Pedido de casamento!",
            description=(
                f"{self.bot.user.mention} está pedindo "
                f"{membro2.mention} em casamento!\n\n"
                f"💌 {membro2.mention}, se aceitar, escreva "
                "**aceito** neste canal.\n\n"
                "⏳ Você tem 5 minutos para responder."
            ),
            color=COR
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Zyrenn Bot • Casamentos")

        await interaction.response.send_message(
            "✅ Pedido enviado! A confirmação é privada.",
            ephemeral=True
        )

        try:
            await interaction.channel.send(embed=embed)
        except discord.HTTPException:
            self.pedidos.pop(chave, None)
            await interaction.followup.send(
                "❌ Não consegui publicar o pedido neste canal.",
                ephemeral=True
            )

    async def iniciar_cerimonia(self, canal, noivo1, noivo2):
        etapas = [
            discord.Embed(
                title="💒 A CERIMÔNIA VAI COMEÇAR!",
                description=(
                    "🔔 **Atenção, convidados!**\n\n"
                    f"Hoje vamos celebrar a união de "
                    f"**{noivo1.display_name}** e "
                    f"**{noivo2.display_name}**!\n\n"
                    "💐 Preparem-se para esse momento especial."
                ),
                color=COR
            ),
            discord.Embed(
                title="🎶 A ENTRADA DOS NOIVOS",
                description=(
                    f"✨ Recebam os noivos: {noivo1.mention} "
                    f"e {noivo2.mention}!\n\n"
                    "🎵 A marcha nupcial está tocando...\n"
                    "💐 Os convidados estão de pé!"
                ),
                color=COR
            ),
            discord.Embed(
                title="❤️ O MOMENTO DOS VOTOS",
                description=(
                    f"**{noivo1.display_name}:**\n"
                    "Prometo compartilhar meus códigos, meus comandos "
                    "e meus melhores momentos contigo! 🤖❤️\n\n"
                    f"**{noivo2.display_name}:**\n"
                    "Aceito essa união e prometo responder com carinho! 💖"
                ),
                color=COR
            ),
            discord.Embed(
                title="💖 DECLARO VOCÊS CASADOS!",
                description=(
                    f"💍 **{noivo1.mention} + {noivo2.mention}**\n\n"
                    "🎉 O casamento está oficialmente celebrado!\n"
                    "💋 Podem trocar os anéis virtuais!\n\n"
                    "🥳 PARABÉNS AOS NOIVOS!"
                ),
                color=COR
            )
        ]

        for etapa in etapas:
            try:
                await canal.send(embed=etapa)
            except discord.HTTPException:
                break

            await asyncio.sleep(3)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return

        if not message.guild or not message.channel:
            return

        if message.content.strip().casefold() != "aceito":
            return

        chave = (
            message.guild.id,
            message.channel.id,
            message.author.id
        )

        pedido = self.pedidos.get(chave)

        if not pedido:
            return

        agora = asyncio.get_running_loop().time()

        if agora - pedido["tempo"] > TEMPO_LIMITE:
            self.pedidos.pop(chave, None)

            try:
                await message.channel.send(
                    f"⌛ O pedido para {message.author.mention} expirou."
                )
            except discord.HTTPException:
                pass

            return

        # Confirma que o pedido continua sendo para esse destinatário.
        if pedido["membro"].id != message.author.id:
            return

        self.pedidos.pop(chave, None)

        await self.iniciar_cerimonia(
            message.channel,
            self.bot.user,
            message.author
        )


async def setup(bot):
    await bot.add_cog(Casamento(bot))
