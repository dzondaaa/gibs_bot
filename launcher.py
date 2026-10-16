"""Interactive Windows setup. Stores token only in a local .env file."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import webbrowser

BASE = Path(__file__).resolve().parent
DOTENV = BASE / ".env"


def check_token(token: str) -> tuple[str, str]:
    req = urllib.request.Request("https://discord.com/api/v10/users/@me",
                                 headers={"Authorization": "Bot " + token,
                                          "User-Agent": "GIBS-Discord-Setup/2.0"})
    with urllib.request.urlopen(req, timeout=20) as res:
        data = json.load(res)
    if not data.get("bot"):
        raise RuntimeError("Zadaný klíč není token bota.")
    return str(data["id"]), str(data.get("username", "GIBS Bot"))


def main():
    print("=" * 64)
    print(" GIBS - ZALOŽENÍ SERVERU + TICKETY + SPISY")
    print("=" * 64)
    print("Pro první nastavení potřebuješ NOVÝ bot token.")
    print("Token nezveřejňuj a neposílej nikomu; uloží se jen na tvém PC.\n")

    if DOTENV.exists() and "DISCORD_TOKEN=" in DOTENV.read_text(encoding="utf-8"):
        print("Nastavení .env už existuje. Pokračuji se stávajícím tokenem.")
        print("Chceš-li token změnit, zavři program, smaž .env a spusť START.bat.")
    else:
        token = getpass.getpass("Nový TOKEN bota (nebude vidět): ").strip()
        if not token:
            raise SystemExit("Token nebyl vyplněn.")
        try:
            bot_id, username = check_token(token)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, KeyError) as exc:
            raise SystemExit("Token nelze ověřit. Zkontroluj token a internet. " + str(exc))
        print(f"Bot ověřen: {username}")
        print("\nVolitelné: vlož ID svého GIBS serveru.")
        print("Najdeš ho přes Nastavení Discordu > Rozšířené > Vývojářský režim;")
        print("pravým na ikonu serveru > Kopírovat ID serveru.")
        guild_id = input("ID SERVERU (Enter stačí, pokud je bot jen na jednom serveru): ").strip()
        if guild_id and not guild_id.isdecimal():
            raise SystemExit("ID serveru musí obsahovat pouze číslice.")
        DOTENV.write_text(f"DISCORD_TOKEN={token}\nDISCORD_GUILD_ID={guild_id}\n", encoding="utf-8")
        try:
            os.chmod(DOTENV, 0o600)
        except OSError:
            pass
        url = ("https://discord.com/oauth2/authorize"
               f"?client_id={bot_id}&permissions=8&scope=bot%20applications.commands")
        print("\nPŘIDEJ BOTA NA SERVER – otevřu odkaz v prohlížeči:")
        print(url)
        print("Bota zvu s oprávněním Administrátor pro první nastavení.")
        print("To dá botovi široký přístup, používej ho pouze na vlastním serveru.")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        input("Až bota pozveš na server, stiskni ENTER...")

    print("\nSpouštím GIBS bota. Okno nezavírej, pokud chceš aby běžel lokálně.")
    import gibs_bot
    gibs_bot.main()


if __name__ == "__main__":
    main()
