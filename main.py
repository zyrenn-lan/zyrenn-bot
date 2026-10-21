
import discord
from discord.ext import commands
import os
import asyncio
import json
import urllib.request
import aiohttp
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("ZYRENN_WEBHOOK_URL", "").strip()

intents = discord.Intents.all()

bot = commands.Bot(
    command_prefix="-",
    intents=intents
)


def enviar_webhook(titulo, descricao, cor):
    if not WEBHOOK_URL:
        print("[WEBHOOK] ZYRENN_WEBHOOK_URL não está no .env.")
        return

    payload = {
        "embeds": [{
            "title": titulo,
            "description": descricao,
            "color": cor,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {
                "text": "Zyrenn Bot • Monitoramento"
            }
        }]
    }

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://discord.com, 1.0)"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(f"[WEBHOOK] Confirmação enviada: HTTP {response.status}")
    except Exception as erro:
        print(f"[WEBHOOK] Erro ao enviar confirmação: {erro}")


async def load_cogs():
    path = os.path.join(BASE_DIR, "cogs")
    for filename in os.listdir(path):

        if filename.endswith(".py") and not filename.startswith("_"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Cog carregado: {filename}")
            except Exception as e:
                print(f"❌ Erro ao carregar {filename}: {e}")


def contar_comandos(comandos):
    total = 0

    for comando in comandos:
        if isinstance(comando, discord.app_commands.Group):
            total += contar_comandos(comando.commands)
        else:
            total += 1

    return total


@bot.event
async def on_ready():
    print(f"🤖 Bot conectado como {bot.user}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="/ajuda | Zyrenn Bot"
        )
    )

    try:
        synced = await bot.tree.sync()
        total = contar_comandos(bot.tree.get_commands())

        print(f"✅ {len(synced)} comandos principais sincronizados!")
        print(f"📋 Total com subcomandos: {total}")

    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")



async def main():
    if not TOKEN:
        print("❌ DISCORD_TOKEN não encontrado no arquivo .env!")
        return

    async with bot:
        await load_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
