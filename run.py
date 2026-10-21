
import os
import sys
import time
import subprocess
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

URL = "https://dbac1b2c-8b3c-45e4-a41a-78ed570227bd-00-3gchdqpk4pnur.spock.replit.dev"
SECRET = os.getenv("FAILOVER_SECRET", "").strip()

if not SECRET:
    print("ERRO: FAILOVER_SECRET não encontrado no .env")
    input("Pressione Enter para sair...")
    sys.exit(1)

HEADERS = {"X-Secret": SECRET}

print("[ZYRENN] Verificando o backup no Replit...")

try:
    resposta = requests.post(
        f"{URL}/handoff",
        headers=HEADERS,
        timeout=20
    )
    resposta.raise_for_status()
    print("[ZYRENN] Replit confirmou que o backup foi parado.")
except requests.RequestException as erro:
    print(f"[ERRO] Não consegui confirmar a parada do backup: {erro}")
    print("[SEGURANÇA] O bot local NÃO será iniciado.")
    input("Pressione Enter para sair...")
    sys.exit(1)

print("[ZYRENN] Iniciando o bot local...")
proc = subprocess.Popen(
    [sys.executable, os.path.join(BASE_DIR, "main.py")],
    cwd=BASE_DIR
)

try:
    while proc.poll() is None:
        try:
            requests.post(
                f"{URL}/heartbeat",
                headers=HEADERS,
                timeout=5
            )
        except requests.RequestException as erro:
            print(f"[AVISO] Falha no heartbeat: {erro}")

        time.sleep(10)

finally:
    if proc.poll() is None:
        proc.terminate()
