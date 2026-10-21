import os
import time
import hashlib
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

URL = "https://hospedagem--zyrennedits.replit.app"
SECRET = os.getenv("FAILOVER_SECRET", "").strip()

INTERVALO = 10
MAX_BYTES = 2 * 1024 * 1024
ESPERA_429 = 60

HEADERS = {"X-Secret": SECRET}
enviados = {}
proxima_tentativa = {}


def arquivos_monitorados():
    ignorar = {
        ".env",
        "sync_zyrenn.py",
        "teste_sync.json",
    }

    for arquivo in BASE_DIR.glob("*.json"):
        if arquivo.is_file() and arquivo.name not in ignorar:
            yield arquivo

    for nome_pasta in ("cogs", "ai"):
        pasta = BASE_DIR / nome_pasta

        if not pasta.is_dir():
            continue

        for arquivo in pasta.rglob("*"):
            if not arquivo.is_file():
                continue

            if "__pycache__" in arquivo.parts:
                continue

            if arquivo.suffix.lower() in (".json", ".py"):
                yield arquivo

    main_file = BASE_DIR / "main.py"
    if main_file.is_file():
        yield main_file


def sincronizar(arquivo, sessao):
    relativo = arquivo.relative_to(BASE_DIR).as_posix()

    if time.monotonic() < proxima_tentativa.get(relativo, 0):
        return

    try:
        conteudo = arquivo.read_bytes()

        if len(conteudo) > MAX_BYTES:
            print(f"[IGNORADO] {relativo}: excede 2 MB.")
            enviados[relativo] = hashlib.sha256(conteudo).hexdigest()
            return

        assinatura = hashlib.sha256(conteudo).hexdigest()

        if enviados.get(relativo) == assinatura:
            return

        resposta = sessao.post(
            f"{URL}/sync-file",
            headers=HEADERS,
            json={
                "path": relativo,
                "content": conteudo.decode("utf-8-sig"),
            },
            timeout=20,
        )

        if resposta.status_code in (200, 201):
            dados = resposta.json()

            if dados.get("ok"):
                enviados[relativo] = assinatura
                proxima_tentativa.pop(relativo, None)
                print(f"[OK] Sincronizado: {relativo}")
            else:
                print(f"[ERRO] {relativo}: {dados}")

        elif resposta.status_code == 429:
            proxima_tentativa[relativo] = (
                time.monotonic() + ESPERA_429
            )
            print(f"[LIMITE] {relativo}: aguardando 60 segundos.")

        elif resposta.status_code in (401, 403):
            print(
                f"[ERRO] {relativo}: autenticação recusada "
                f"(HTTP {resposta.status_code})."
            )
            proxima_tentativa[relativo] = time.monotonic() + 60

        else:
            print(
                f"[ERRO] {relativo}: HTTP {resposta.status_code} "
                f"- {resposta.text[:200]}"
            )
            proxima_tentativa[relativo] = time.monotonic() + 30

    except (OSError, UnicodeError, ValueError, requests.RequestException) as erro:
        print(f"[ERRO] {relativo}: {erro}")
        proxima_tentativa[relativo] = time.monotonic() + 15


def main():
    if not SECRET:
        print("[ERRO] FAILOVER_SECRET não encontrado no .env.")
        return

    print("[ZYRENN SYNC] Monitoramento iniciado.")
    print(f"[ZYRENN SYNC] Destino: {URL}")

    with requests.Session() as sessao:
        while True:
            for arquivo in arquivos_monitorados():
                sincronizar(arquivo, sessao)

            time.sleep(INTERVALO)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ZYRENN SYNC] Monitoramento encerrado.")