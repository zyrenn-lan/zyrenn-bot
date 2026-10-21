import os
import time
import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from google import genai
from google.genai import types

from ai.zyrenn_ai import ZyrennAI


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

MODEL = "gemini-3.6-flash"

# Tempo mínimo entre mensagens que usam Gemini
COOLDOWN_SEGUNDOS = 8

# Quantidade máxima de mensagens do histórico enviadas ao Gemini
MAX_HISTORICO = 8

# Tamanho máximo da mensagem enviada ao Gemini
MAX_MENSAGEM = 1500

# Tamanho máximo da resposta
MAX_RESPOSTA = 4000

# Mensagens que não precisam gastar Gemini
MENSAGENS_SIMPLES = {
    "oi",
    "olá",
    "ola",
    "opa",
    "eae",
    "eai",
    "salve",
    "fala",
    "kkk",
    "kkkk",
    "kkkkk",
    "kk",
    "haha",
    "hahaha",
    "bruh",
    "67",
    "six seven",
    "vlw",
    "valeu",
    "tmj"
}


# ==========================================================
# CLIENTE GEMINI
# ==========================================================

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

if not GEMINI_API_KEY:
    print(
        "⚠️ GEMINI_API_KEY não encontrada no .env"
    )

    gemini = None

else:

    gemini = genai.Client(
        api_key=GEMINI_API_KEY
    )


# ==========================================================
# PERSONALIDADE
# ==========================================================

SYSTEM_INSTRUCTION = """
Você é o Zyrenn AI, a inteligência artificial do Zyrenn Bot.

PERSONALIDADE:
- Brasileiro.
- Fala português do Brasil.
- Amigável.
- Engraçado quando combina com a conversa.
- Pode usar KKKKK, mano, véi e gírias brasileiras com moderação.
- Pode ser irônico de forma leve.
- Nunca precisa começar todas as respostas com "KKKK".
- Não repita a mesma frase.
- Não fale como um robô.
- Não diga que é uma IA sem motivo.
- Responda diretamente ao que o usuário perguntou.
- Não invente informações sobre o usuário.
- Use a memória fornecida apenas quando ela realmente for relevante.
- Se não souber alguma coisa, diga que não sabe.
- Não transforme uma mensagem normal em uma pergunta.
- Não tente adivinhar o assunto quando não estiver claro.
- Mantenha respostas relativamente curtas para Discord.
"""


# ==========================================================
# GRUPO /CHAT
# ==========================================================

chat_group = app_commands.Group(
    name="chat",
    description="Comandos do Zyrenn AI"
)


# ==========================================================
# VIEW DO BOTÃO DE MEMÓRIA
# ==========================================================

class MemoriaView(discord.ui.View):

    def __init__(
        self,
        ai,
        canal_id
    ):

        super().__init__(
            timeout=300
        )

        self.ai = ai
        self.canal_id = canal_id

    @discord.ui.button(
        label="Deletar memória",
        emoji="🗑️",
        style=discord.ButtonStyle.danger
    )
    async def deletar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.user.guild_permissions.administrator:

            await interaction.response.send_message(
                "❌ Apenas administradores podem deletar a memória.",
                ephemeral=True
            )

            return

        view = ConfirmarMemoriaView(
            self.ai,
            self.canal_id
        )

        await interaction.response.send_message(
            "🧠 Você quer deletar a memória do chat do bot?",
            view=view,
            ephemeral=True
        )


# ==========================================================
# PRIMEIRA CONFIRMAÇÃO
# ==========================================================

class ConfirmarMemoriaView(
    discord.ui.View
):

    def __init__(
        self,
        ai,
        canal_id
    ):

        super().__init__(
            timeout=60
        )

        self.ai = ai
        self.canal_id = canal_id

    @discord.ui.button(
        label="Sim",
        style=discord.ButtonStyle.danger
    )
    async def sim(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        view = SegundaConfirmacaoView(
            self.ai,
            self.canal_id
        )

        await interaction.response.edit_message(
            content="⚠️ Tem certeza?",
            view=view
        )

    @discord.ui.button(
        label="Não",
        style=discord.ButtonStyle.secondary
    )
    async def nao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content="❌ Cancelado.",
            view=None
        )


# ==========================================================
# SEGUNDA CONFIRMAÇÃO
# ==========================================================

class SegundaConfirmacaoView(
    discord.ui.View
):

    def __init__(
        self,
        ai,
        canal_id
    ):

        super().__init__(
            timeout=60
        )

        self.ai = ai
        self.canal_id = canal_id

    @discord.ui.button(
        label="Sim",
        style=discord.ButtonStyle.danger
    )
    async def sim(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        self.ai.apagar_memoria_canal(
            self.canal_id
        )

        await interaction.response.edit_message(
            content="🗑️ Memória do canal apagada com sucesso.",
            view=None
        )

    @discord.ui.button(
        label="Não",
        style=discord.ButtonStyle.secondary
    )
    async def nao(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content="❌ Cancelado.",
            view=None
        )


# ==========================================================
# COG
# ==========================================================

class Chat(commands.Cog):

    def __init__(
        self,
        bot
    ):

        self.bot = bot

        self.ai = ZyrennAI()

        # Canais onde o chat está ativado
        self.canais_ativos = set()

        # Última requisição Gemini por canal
        self.ultimo_uso = {}

        # Evita duas requisições simultâneas
        self.locks = {}

    # ======================================================
    # LOCK POR CANAL
    # ======================================================

    def pegar_lock(
        self,
        canal_id
    ):

        if canal_id not in self.locks:

            self.locks[canal_id] = asyncio.Lock()

        return self.locks[canal_id]

    # ======================================================
    # EMBED
    # ======================================================

    def criar_embed(
        self,
        usuario,
        resposta
    ):

        embed = discord.Embed(
            description=resposta,
            color=discord.Color.blurple()
        )

        embed.set_author(
            name="Zyrenn AI",
            icon_url=self.bot.user.display_avatar.url
        )

        embed.set_footer(
            text=f"Falando com {usuario.display_name}"
        )

        return embed

    # ======================================================
    # MENSAGEM SIMPLES
    # ======================================================

    def mensagem_simples(
        self,
        mensagem
    ):

        texto = mensagem.lower().strip()

        if texto in MENSAGENS_SIMPLES:
            return True

        # Mensagens muito pequenas também não gastam IA
        if len(texto) <= 2:
            return True

        return False

    # ======================================================
    # COOLDOWN
    # ======================================================

    def verificar_cooldown(
        self,
        canal_id
    ):

        agora = time.monotonic()

        ultimo = self.ultimo_uso.get(
            canal_id,
            0
        )

        restante = (
            COOLDOWN_SEGUNDOS
            - (agora - ultimo)
        )

        if restante > 0:
            return restante

        return 0

    # ======================================================
    # HISTÓRICO PEQUENO
    # ======================================================

    def pegar_historico_curto(
        self,
        canal_id
    ):

        canal = self.ai.memoria["canais"].get(
            str(canal_id)
        )

        if not canal:
            return ""

        historico = canal.get(
            "historico",
            []
        )

        historico = historico[
            -MAX_HISTORICO:
        ]

        partes = []

        for item in historico:

            nome = item.get(
                "usuario_nome",
                "Usuário"
            )

            mensagem = item.get(
                "mensagem",
                ""
            )

            resposta = item.get(
                "zyrenn",
                ""
            )

            partes.append(
                f"{nome}: {mensagem}"
            )

            partes.append(
                f"Zyrenn: {resposta}"
            )

        return "\n".join(
            partes
        )

    # ======================================================
    # CHAMAR GEMINI
    # ======================================================

    async def gerar_gemini(
        self,
        usuario_id,
        canal_id,
        nome_usuario,
        mensagem
    ):

        if gemini is None:

            return (
                "❌ A chave do Gemini não foi encontrada."
            )

        # ----------------------------------------------
        # MEMÓRIA DO USUÁRIO
        # ----------------------------------------------

        memoria_usuario = (
            self.ai.pegar_memoria_usuario(
                usuario_id
            )
        )

        # ----------------------------------------------
        # HISTÓRICO CURTO
        # ----------------------------------------------

        historico = (
            self.pegar_historico_curto(
                canal_id
            )
        )

        # ----------------------------------------------
        # CONTEXTO
        # ----------------------------------------------

        contexto = ""

        if memoria_usuario:

            contexto += (
                "\nMEMÓRIA DO USUÁRIO:\n"
                + memoria_usuario
            )

        if historico:

            contexto += (
                "\n\nHISTÓRICO RECENTE:\n"
                + historico
            )

        # ----------------------------------------------
        # PROMPT
        # ----------------------------------------------

        prompt = f"""
USUÁRIO ATUAL:
{nome_usuario}

MENSAGEM:
{mensagem[:MAX_MENSAGEM]}

{contexto}

Responda à mensagem atual do usuário.
Não responda ao histórico inteiro.
Use o histórico somente para entender o contexto.
"""

        try:

            resposta = await asyncio.to_thread(
                gemini.models.generate_content,
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.8,
                    max_output_tokens=1000,
                    candidate_count=1
                )
            )

            texto = getattr(
                resposta,
                "text",
                None
            )

            if not texto:

                return (
                    "🤖 Não consegui gerar uma resposta agora."
                )

            texto = texto.strip()

            # Limite de segurança para Discord
            if len(texto) > MAX_RESPOSTA:

                texto = (
                    texto[:MAX_RESPOSTA - 3]
                    + "..."
                )

            return texto

        except Exception as erro:

            erro_texto = str(
                erro
            ).lower()

            print(
                f"❌ Erro Gemini: {erro}"
            )

            # ------------------------------------------
            # RATE LIMIT
            # ------------------------------------------

            if (
                "429" in erro_texto
                or "resource_exhausted" in erro_texto
                or "quota" in erro_texto
            ):

                return (
                    "⏳ A cota do Gemini foi atingida. "
                    "Espera um pouco e tenta novamente."
                )

            # ------------------------------------------
            # SERVIÇO TEMPORARIAMENTE INDISPONÍVEL
            # ------------------------------------------

            if (
                "503" in erro_texto
                or "unavailable" in erro_texto
            ):

                return (
                    "⚠️ O Gemini está temporariamente "
                    "indisponível. Tenta novamente daqui a pouco."
                )

            return (
                "❌ Deu um problema ao falar com o Gemini."
            )

    # ======================================================
    # COMANDOS /CHAT
    # ======================================================

    async def responder_chat_on(
        self,
        interaction: discord.Interaction
    ):

        canal_id = interaction.channel.id

        self.canais_ativos.add(
            canal_id
        )

        embed = discord.Embed(
            title="🧠 Zyrenn AI ativado",
            description=(
                "O chat com o Zyrenn AI foi ativado neste canal.\n\n"
                "Agora você pode conversar comigo normalmente."
            ),
            color=discord.Color.green()
        )

        await interaction.response.send_message(
            embed=embed
        )

    async def responder_chat_off(
        self,
        interaction: discord.Interaction
    ):

        canal_id = interaction.channel.id

        self.canais_ativos.discard(
            canal_id
        )

        embed = discord.Embed(
            title="🔴 Zyrenn AI desativado",
            description=(
                "O chat com o Zyrenn AI foi desativado neste canal."
            ),
            color=discord.Color.red()
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ======================================================
    # MENSAGENS
    # ======================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message
    ):

        # Bot não responde a bots

        if message.author.bot:
            return

        # Só funciona em canais ativados

        if message.channel.id not in self.canais_ativos:
            return

        # Não responde comandos

        if message.content.startswith("!"):
            return

        # Mensagem vazia

        if not message.content.strip():
            return

        # ==============================================
        # MENSAGEM SIMPLES
        # ==============================================

        if self.mensagem_simples(
            message.content
        ):

            return

        # ==============================================
        # COOLDOWN
        # ==============================================

        restante = self.verificar_cooldown(
            message.channel.id
        )

        if restante > 0:

            # Não manda nada para o Gemini.
            # Assim spam não gasta cota.

            return

        # ==============================================
        # LOCK
        # ==============================================

        lock = self.pegar_lock(
            message.channel.id
        )

        if lock.locked():
            return

        async with lock:

            # Confere o cooldown novamente
            # depois de pegar o lock.

            restante = self.verificar_cooldown(
                message.channel.id
            )

            if restante > 0:
                return

            # ==========================================
            # MARCA USO
            # ==========================================

            self.ultimo_uso[
                message.channel.id
            ] = time.monotonic()

            # ==========================================
            # MOSTRA DIGITANDO
            # ==========================================

            async with message.channel.typing():

                # ======================================
                # APRENDE MEMÓRIA
                # ======================================

                self.ai.aprender_usuario(
                    message.author.id,
                    message.author.display_name,
                    message.content
                )

                # ======================================
                # GEMINI
                # ======================================

                resposta = await self.gerar_gemini(
                    message.author.id,
                    message.channel.id,
                    message.author.display_name,
                    message.content
                )

                # ======================================
                # SALVA HISTÓRICO
                # ======================================

                self.ai.adicionar_historico(
                    message.channel.id,
                    message.author.id,
                    message.author.display_name,
                    message.content,
                    resposta
                )

                # ======================================
                # EMBED
                # ======================================

                embed = self.criar_embed(
                    message.author,
                    resposta
                )

                view = MemoriaView(
                    self.ai,
                    message.channel.id
                )

                await message.reply(
                    embed=embed,
                    view=view,
                    mention_author=False
                )

    # ======================================================
    # ERRO DOS COMANDOS
    # ======================================================

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):

        print(f"❌ Erro /chat: {error}")

        if isinstance(
            error,
            app_commands.errors.MissingPermissions
        ):

            if not interaction.response.is_done():

                await interaction.response.send_message(
                    "❌ Apenas administradores podem usar este comando.",
                    ephemeral=True
                )

            return

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "❌ Ocorreu um erro ao executar este comando.",
                ephemeral=True
            )



# ==========================================================
# GRUPO /CHAT
# ==========================================================

chat_group = app_commands.Group(
    name="chat",
    description="Comandos do Zyrenn AI"
)


@chat_group.command(
    name="on",
    description="Ativa o chat com o Zyrenn AI neste canal."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def chat_on_command(
    interaction: discord.Interaction
):

    cog = interaction.client.get_cog("Chat")

    if cog is None:

        await interaction.response.send_message(
            "❌ O sistema de chat não está carregado.",
            ephemeral=True
        )

        return

    await cog.responder_chat_on(
        interaction
    )


@chat_group.command(
    name="off",
    description="Desativa o chat com o Zyrenn AI neste canal."
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def chat_off_command(
    interaction: discord.Interaction
):

    cog = interaction.client.get_cog("Chat")

    if cog is None:

        await interaction.response.send_message(
            "❌ O sistema de chat não está carregado.",
            ephemeral=True
        )

        return

    await cog.responder_chat_off(
        interaction
    )


async def setup(bot):

    await bot.add_cog(
        Chat(bot)
    )

    if bot.tree.get_command("chat") is None:

        bot.tree.add_command(
            chat_group
        )
