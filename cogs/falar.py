import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from dotenv import load_dotenv
import os

load_dotenv()


class Falar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError("❌ GEMINI_API_KEY não encontrada no .env")

        self.gemini = genai.Client(api_key=api_key)

    @app_commands.command(
        name="falar",
        description="Faz o bot enviar uma mensagem personalizada."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        mensagem="Mensagem que o bot vai enviar.",
        estilo="Estilo que a IA deve usar.",
        canal="Canal onde a mensagem será enviada.",
        reply="ID da mensagem que o bot deve responder."
    )
    @app_commands.choices(
        estilo=[
            app_commands.Choice(name="Normal", value="normal"),
            app_commands.Choice(name="Engraçado", value="engracado"),
            app_commands.Choice(name="Formal", value="formal"),
            app_commands.Choice(name="Sério", value="serio"),
            app_commands.Choice(name="Meme", value="meme"),
            app_commands.Choice(name="Anime", value="anime")
        ]
    )
    async def falar(
        self,
        interaction: discord.Interaction,
        mensagem: str,
        estilo: app_commands.Choice[str] = None,
        canal: discord.TextChannel = None,
        reply: str = None
    ):

        # Verifica se é administrador
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Você precisa ter a permissão de **Administrador** para usar esse comando.",
                ephemeral=True
            )
            return

        canal_destino = canal or interaction.channel

        await interaction.response.defer(ephemeral=True)

        try:

            # ==========================================
            # SEM ESTILO = NÃO USA IA
            # ==========================================
            if estilo is None:
                mensagem_final = mensagem

            # ==========================================
            # COM ESTILO = USA IA
            # ==========================================
            else:

                estilos = {
                    "normal": (
                        "Escreva de forma natural, clara e simples."
                    ),

                    "engracado": (
                        "Deixe a mensagem engraçada, descontraída e divertida. "
                        "Pode usar gírias e humor."
                    ),

                    "formal": (
                        "Deixe a mensagem formal, educada e profissional."
                    ),

                    "serio": (
                        "Deixe a mensagem séria, direta e objetiva."
                    ),

                    "meme": (
                        "Transforme a mensagem em um estilo de meme, "
                        "com humor e gírias de internet."
                    ),

                    "anime": (
                        "Deixe a mensagem com uma vibe de anime, "
                        "épica e divertida."
                    )
                }

                instrucao = estilos[estilo.value]

                prompt = f"""
Você é responsável por personalizar mensagens para um bot do Discord.

Mensagem original:
{mensagem}

Estilo escolhido:
{estilo.name}

Instrução do estilo:
{instrucao}

REGRAS IMPORTANTES:
- Aplique obrigatoriamente o estilo escolhido.
- Mantenha o significado original da mensagem.
- Não invente informações importantes.
- Não explique o que você fez.
- Não coloque aspas.
- Retorne somente a mensagem final.
"""

                resposta = await self.bot.loop.run_in_executor(
                    None,
                    lambda: self.gemini.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=prompt
                    )
                )

                if not resposta.text:
                    await interaction.followup.send(
                        "❌ O Gemini não retornou nenhuma mensagem.",
                        ephemeral=True
                    )
                    return

                mensagem_final = resposta.text.strip()

            # ==========================================
            # LIMITE DO DISCORD
            # ==========================================
            if len(mensagem_final) > 2000:
                mensagem_final = mensagem_final[:1997] + "..."

            # ==========================================
            # REPLY
            # ==========================================
            referencia = None

            if reply:

                try:
                    mensagem_id = int(reply)

                except ValueError:
                    await interaction.followup.send(
                        "❌ O ID da mensagem precisa ser apenas números.",
                        ephemeral=True
                    )
                    return

                try:
                    mensagem_reply = await canal_destino.fetch_message(
                        mensagem_id
                    )

                    referencia = mensagem_reply

                except discord.NotFound:
                    await interaction.followup.send(
                        "❌ Não encontrei essa mensagem nesse canal.",
                        ephemeral=True
                    )
                    return

                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ Não tenho permissão para acessar essa mensagem.",
                        ephemeral=True
                    )
                    return

            # ==========================================
            # ENVIA A MENSAGEM
            # ==========================================
            await canal_destino.send(
                mensagem_final,
                reference=referencia
            )

            # ==========================================
            # CONFIRMAÇÃO
            # ==========================================
            if estilo is None:
                await interaction.followup.send(
                    f"✅ Mensagem enviada em {canal_destino.mention}!\n"
                    f"🤖 IA: **Desativada**",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ Mensagem enviada em {canal_destino.mention}!\n"
                    f"🎨 Estilo: **{estilo.name}**\n"
                    f"🤖 IA: **Ativada**",
                    ephemeral=True
                )

        except Exception as e:

            print(f"❌ Erro no /falar: {e}")

            await interaction.followup.send(
                "❌ Ocorreu um erro ao tentar enviar a mensagem. "
                "Veja o console para mais detalhes.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Falar(bot))