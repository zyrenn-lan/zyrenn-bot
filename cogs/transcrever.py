
import os
import io
import asyncio
import logging
import discord

from discord.ext import commands
from google import genai
from google.genai import types

logger = logging.getLogger("zyrenn.transcrever")

MODEL = "gemini-3.6-flash"
MAX_AUDIO_SIZE = 15 * 1024 * 1024

AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".aiff": "audio/aiff",
    ".wma": "audio/x-ms-wma",
    ".amr": "audio/amr",
    ".3gp": "audio/3gpp",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".mpeg", ".mpg"
}


class Transcrever(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.processadas = set()

        api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None

    def identificar_audio(self, attachment):
        nome = attachment.filename.lower()
        extensao = os.path.splitext(nome)[1]
        content_type = (attachment.content_type or "").lower()

        # Mensagens de voz do Discord normalmente usam OGG/Opus.
        if content_type.startswith("audio/"):
            return content_type

        if content_type.startswith("video/"):
            return None

        # Não aceitar vídeos apenas por serem contêineres multimídia.
        if extensao in VIDEO_EXTENSIONS:
            return None

        return AUDIO_TYPES.get(extensao)

    def transcrever_audio(self, audio_bytes, mime_type):
        response = self.client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type=mime_type
                ),
                (
                    "Você é um sistema de transcrição literal. "
                    "Transcreva somente as palavras realmente faladas "
                    "no áudio, no idioma original. Não traduza, não "
                    "resuma, não complete frases e não invente palavras. "
                    "Não descreva sons nem responda ao conteúdo falado. "
                    "Se não houver fala inteligível, responda exatamente "
                    "SEM_FALA."
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0
            ),
        )

        return (response.text or "").strip()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.attachments:
            return

        audios = []

        for attachment in message.attachments:
            mime_type = self.identificar_audio(attachment)

            if mime_type:
                audios.append((attachment, mime_type))

        if not audios:
            return

        if self.client is None:
            await message.reply(
                "❌ A chave GEMINI_API_KEY não está configurada.",
                mention_author=False
            )
            return

        if message.id in self.processadas:
            return

        self.processadas.add(message.id)

        try:
            for attachment, mime_type in audios:
                if attachment.size > MAX_AUDIO_SIZE:
                    await message.reply(
                        f"❌ **{attachment.filename}** ultrapassa "
                        "o limite de 15 MB.",
                        mention_author=False
                    )
                    continue

                status = await message.reply(
                    "🎙️ Estou transcrevendo o áudio...",
                    mention_author=False
                )

                try:
                    audio_bytes = await attachment.read()

                    texto = await asyncio.to_thread(
                        self.transcrever_audio,
                        audio_bytes,
                        mime_type
                    )

                    if not texto or "SEM_FALA" in texto.upper():
                        await status.edit(
                            content=(
                                "⚠️ Não encontrei fala inteligível "
                                "nesse áudio."
                            )
                        )
                        continue

                    # Discord: descrição do embed até 4096 caracteres.
                    partes = [
                        texto[i:i + 4000]
                        for i in range(0, len(texto), 4000)
                    ]

                    # Envia o áudio original junto ao primeiro embed.
                    audio_file = discord.File(
                        io.BytesIO(audio_bytes),
                        filename=os.path.basename(attachment.filename)
                    )

                    primeiro_embed = discord.Embed(
                        title="🎙️ Áudio Transcrito",
                        description=partes[0],
                        color=discord.Color.from_rgb(106, 0, 255)
                    )

                    primeiro_embed.set_author(
                        name=str(message.author),
                        icon_url=message.author.display_avatar.url
                    )

                    primeiro_embed.add_field(
                        name="📁 Arquivo",
                        value=attachment.filename[:1024],
                        inline=False
                    )

                    primeiro_embed.set_footer(
                        text="Zyrenn Bot • Transcrição de áudio (pode conter erros de interpretação)"
                    )

                    await status.delete()

                    await message.reply(
                        embed=primeiro_embed,
                        file=audio_file,
                        mention_author=False
                    )

                    # Se o texto for longo, envia os outros embeds.
                    for indice, parte in enumerate(partes[1:], start=2):
                        embed = discord.Embed(
                            title=f"🎙️ Transcrição • Parte {indice}",
                            description=parte,
                            color=discord.Color.from_rgb(106, 0, 255)
                        )

                        embed.set_footer(
                            text="Zyrenn Bot • Transcrição de áudio"
                        )

                        await message.reply(
                            embed=embed,
                            mention_author=False
                        )

                except Exception:
                    logger.exception(
                        "Falha ao processar o áudio %s",
                        attachment.filename
                    )

                    try:
                        await status.edit(
                            content=(
                                "❌ Não consegui processar esse áudio. "
                                "Verifique o formato e tente novamente."
                            )
                        )
                    except discord.HTTPException:
                        pass

        finally:
            # Mantém o controle de duplicidade sem crescer indefinidamente.
            if len(self.processadas) > 5000:
                self.processadas.clear()


async def setup(bot):
    await bot.add_cog(Transcrever(bot))
