
import asyncio
import shutil
import tempfile
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# CONFIGURAÇÃO
# =========================================================

COR = 0x6A00FF

# Vamos tentar manter o vídeo abaixo deste tamanho.
# 9,2 MiB deixa uma margem de segurança abaixo de 10 MB.
LIMITE_BYTES = int(9.2 * 1024 * 1024)

QUALIDADES = {
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p (4K)": 2160,
}

FPS_DISPONIVEIS = [30, 60, 90, 120]


def formatar_tamanho(tamanho):
    return f"{tamanho / (1024 * 1024):.2f} MB"


async def executar_processo(*args):
    """Executa um programa sem travar o bot."""
    processo = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await processo.communicate()

    if processo.returncode != 0:
        erro = stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(erro[-1800:] or "Erro ao executar o FFmpeg.")

    return stdout


async def descobrir_duracao(caminho):
    """Descobre a duração do vídeo usando o ffprobe."""
    ffprobe = shutil.which("ffprobe")

    if not ffprobe:
        raise RuntimeError(
            "Não encontrei o ffprobe. Verifique se o FFmpeg "
            "está instalado e configurado no PATH."
        )

    resultado = await executar_processo(
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(caminho),
    )

    try:
        duracao = float(resultado.decode().strip())
    except (ValueError, TypeError):
        raise RuntimeError("Não consegui identificar a duração do vídeo.")

    if duracao <= 0:
        raise RuntimeError("O vídeo possui uma duração inválida.")

    return duracao


async def processar_video(entrada, saida, altura, fps):
    """
    Converte o vídeo com H.264 e tenta manter o resultado
    abaixo de 10 MB.

    O FPS é ajustado por duplicação/remoção de quadros.
    Isso é mais rápido que interpolação óptica, mas não
    cria movimentos novos de verdade.
    """
    ffmpeg = shutil.which("ffmpeg")

    if not ffmpeg:
        raise RuntimeError(
            "O FFmpeg não foi encontrado. Instale-o e reinicie "
            "o terminal/VS Code."
        )

    duracao = await descobrir_duracao(entrada)

    # Reservamos espaço para áudio e para o contêiner MP4.
    audio_kbps = 48
    margem_kbps = 8

    bitrate = int(
        (LIMITE_BYTES * 8 / duracao / 1000)
        - audio_kbps
        - margem_kbps
    )

    bitrate = max(12, bitrate)

    for tentativa in range(5):
        if saida.exists():
            saida.unlink()

        filtro = f"scale=-2:{altura}:flags=lanczos,fps={fps}"

        await executar_processo(
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", str(entrada),
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-vf", filtro,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-b:v", f"{bitrate}k",
            "-maxrate", f"{bitrate}k",
            "-bufsize", f"{bitrate * 2}k",
            "-c:a", "aac",
            "-b:a", f"{audio_kbps}k",
            "-ac", "2",
            "-movflags", "+faststart",
            "-threads", "0",
            str(saida),
        )

        tamanho = saida.stat().st_size

        if tamanho <= LIMITE_BYTES:
            return tamanho

        # Diminui a taxa de bits e tenta novamente.
        proporcao = LIMITE_BYTES / tamanho
        novo_bitrate = int(bitrate * proporcao * 0.92)

        if novo_bitrate >= bitrate:
            novo_bitrate = bitrate - 1

        bitrate = max(12, novo_bitrate)

        if bitrate == 12 and tentativa >= 2:
            break

    if saida.exists() and saida.stat().st_size <= 10 * 1024 * 1024:
        return saida.stat().st_size

    raise RuntimeError(
        "O vídeo ficou grande demais mesmo após a compressão. "
        "Tente enviar um vídeo mais curto."
    )


# =========================================================
# PAINEL DO METHOD
# =========================================================

class MethodView(discord.ui.View):

    def __init__(self, usuario_id, anexo):
        super().__init__(timeout=300)

        self.usuario_id = usuario_id
        self.anexo = anexo
        self.qualidade = 1080
        self.fps = 60
        self.processando = False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.usuario_id:
            await interaction.response.send_message(
                "Esse painel não é seu!",
                ephemeral=True,
            )
            return False

        return True

    def criar_embed(self):
        embed = discord.Embed(
            title="🎬 Zyrenn Method",
            description=(
                "Configure seu vídeo antes de aplicar o method.\n\n"
                f"**📺 Qualidade:** {self.qualidade}p\n"
                f"**⚡ FPS:** {self.fps}\n"
                f"**📁 Arquivo:** {self.anexo.filename}\n\n"
                "Clique em **MELHOR METHOD** para selecionar "
                "2160p (4K) e 120 FPS."
            ),
            color=COR,
        )

        embed.set_footer(text="Zyrenn Bot • Edição")

        return embed

    async def atualizar(self, interaction):
        await interaction.response.edit_message(
            embed=self.criar_embed(),
            view=self,
        )

    # ---------------- QUALIDADE ----------------

    @discord.ui.button(label="480p", style=discord.ButtonStyle.secondary, row=0)
    async def qualidade_480(self, interaction, button):
        self.qualidade = 480
        await self.atualizar(interaction)

    @discord.ui.button(label="720p", style=discord.ButtonStyle.secondary, row=0)
    async def qualidade_720(self, interaction, button):
        self.qualidade = 720
        await self.atualizar(interaction)

    @discord.ui.button(label="1080p", style=discord.ButtonStyle.primary, row=0)
    async def qualidade_1080(self, interaction, button):
        self.qualidade = 1080
        await self.atualizar(interaction)

    @discord.ui.button(label="1440p", style=discord.ButtonStyle.secondary, row=0)
    async def qualidade_1440(self, interaction, button):
        self.qualidade = 1440
        await self.atualizar(interaction)

    @discord.ui.button(label="2160p (4K)", style=discord.ButtonStyle.secondary, row=0)
    async def qualidade_2160(self, interaction, button):
        self.qualidade = 2160
        await self.atualizar(interaction)

    # ---------------- FPS ----------------

    @discord.ui.button(label="30 FPS", style=discord.ButtonStyle.secondary, row=1)
    async def fps_30(self, interaction, button):
        self.fps = 30
        await self.atualizar(interaction)

    @discord.ui.button(label="60 FPS", style=discord.ButtonStyle.secondary, row=1)
    async def fps_60(self, interaction, button):
        self.fps = 60
        await self.atualizar(interaction)

    @discord.ui.button(label="90 FPS", style=discord.ButtonStyle.secondary, row=1)
    async def fps_90(self, interaction, button):
        self.fps = 90
        await self.atualizar(interaction)

    @discord.ui.button(label="120 FPS", style=discord.ButtonStyle.secondary, row=1)
    async def fps_120(self, interaction, button):
        self.fps = 120
        await self.atualizar(interaction)

    # ---------------- MELHOR METHOD ----------------

    @discord.ui.button(
        label="MELHOR METHOD",
        style=discord.ButtonStyle.success,
        row=2,
    )
    async def melhor_method(self, interaction, button):
        self.qualidade = 2160
        self.fps = 120
        await self.atualizar(interaction)

    # ---------------- APLICAR ----------------

    @discord.ui.button(
        label="Aplicar",
        style=discord.ButtonStyle.primary,
        emoji="⚡",
        row=3,
    )
    async def aplicar(self, interaction, button):
        if self.processando:
            await interaction.response.send_message(
                "O vídeo já está sendo processado!",
                ephemeral=True,
            )
            return

        self.processando = True

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="⚙️ Processando vídeo...",
                description=(
                    f"**Qualidade:** {self.qualidade}p\n"
                    f"**FPS:** {self.fps}\n\n"
                    "O Zyrenn Bot está preparando seu vídeo. "
                    "Isso pode levar um tempo dependendo do tamanho."
                ),
                color=COR,
            ),
            view=self,
        )

        try:
            with tempfile.TemporaryDirectory(
                prefix="zyrenn_method_"
            ) as pasta_temp:

                pasta = Path(pasta_temp)
                entrada = pasta / "entrada.mp4"
                saida = pasta / "zyrenn_method.mp4"

                await self.anexo.save(entrada)

                tamanho = await processar_video(
                    entrada,
                    saida,
                    self.qualidade,
                    self.fps,
                )

                # O envio é privado e o arquivo temporário
                # só é removido depois que o Discord recebe o envio.
                await interaction.followup.send(
                    content=(
                        "✅ **Method aplicado!**\n"
                        f"📺 Qualidade configurada: {self.qualidade}p\n"
                        f"⚡ FPS configurado: {self.fps}\n"
                        f"📦 Tamanho final: {formatar_tamanho(tamanho)}"
                    ),
                    file=discord.File(
                        str(saida),
                        filename="zyrenn_method.mp4",
                    ),
                    ephemeral=True,
                )

        except Exception as erro:
            mensagem = str(erro)

            if len(mensagem) > 1200:
                mensagem = mensagem[-1200:]

            await interaction.followup.send(
                "❌ **Não consegui processar o vídeo.**\n"
                f"Motivo: {mensagem}",
                ephemeral=True,
            )

        finally:
            self.stop()

    # ---------------- CANCELAR ----------------

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.danger,
        row=3,
    )
    async def cancelar(self, interaction, button):
        self.stop()

        await interaction.response.edit_message(
            content="❌ Processamento cancelado.",
            embed=None,
            view=None,
        )

    async def on_timeout(self):
        self.stop()


# =========================================================
# COMANDO /METHOD — CATEGORIA EDIÇÃO
# =========================================================

class Method(commands.Cog, name="Edição"):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="method",
        description="Configure a qualidade e o FPS de um vídeo MP4.",
    )
    @app_commands.describe(
        anexo="Envie o vídeo no formato MP4."
    )
    async def method(
        self,
        interaction: discord.Interaction,
        anexo: discord.Attachment,
    ):
        if not anexo.filename.lower().endswith(".mp4"):
            await interaction.response.send_message(
                "❌ Envie somente arquivos com extensão `.mp4`.",
                ephemeral=True,
            )
            return

        if anexo.size <= 0:
            await interaction.response.send_message(
                "❌ Esse arquivo está vazio.",
                ephemeral=True,
            )
            return

        view = MethodView(
            usuario_id=interaction.user.id,
            anexo=anexo,
        )

        await interaction.response.send_message(
            embed=view.criar_embed(),
            view=view,
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Method(bot))
