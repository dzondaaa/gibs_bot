"""GIBS Discord server: role/channel provisioning, private case forums and persistent tickets.
Runs only under an official Discord bot account. Keep DISCORD_TOKEN private.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands

BASE = Path(__file__).resolve().parent
LOG = logging.getLogger("gibs")


def load_local_env() -> None:
    path = BASE / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()
TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.environ.get("DISCORD_GUILD_ID", "0") or 0)

try:
    CZ_TZ = ZoneInfo("Europe/Prague")
except ZoneInfoNotFoundError:
    CZ_TZ = timezone.utc
    LOG.warning("Chybí tzdata; používá se čas UTC. Nainstalujte tzdata.")


def now() -> str:
    return datetime.now(CZ_TZ).strftime("%d.%m.%Y %H:%M")


def clean(value: str, limit: int = 200) -> str:
    # Pro názvy spisů i oznámení, bez hromadných zmínek.
    return discord.utils.escape_mentions(value.strip())[:limit]


RANKS = ["Ředitel GIBS", "Náměstek ředitele", "Vedoucí oddělení",
         "Vrchní komisař", "Komisař", "Vrchní inspektor", "Inspektor"]
LEADERS = RANKS[:3]  # právo spravovat spisy a zásahy
PROMOTERS = RANKS[:2]  # personální rozhodnutí pouze ředitel + náměstek
STAFF_ROLE = "Generální inspekce bezpečnostních sborů"
CIVILIAN_ROLE = "Civilista"
# Pro příslušníka: společná role personálu + jedna konkrétní hodnost.
# Člen veřejnosti: jen Civilista. Žádné další samostatné role oddělení.
ROLE_COLORS = {
    "Ředitel GIBS": 0xC2A35C,       # zlatá
    "Náměstek ředitele": 0x9D91C8,  # fialová
    "Vedoucí oddělení": 0x547D9B,   # ocelově modrá
    "Vrchní komisař": 0x496A8B,
    "Komisař": 0x376487,
    "Vrchní inspektor": 0x47677A,
    "Inspektor": 0x55717F,
    STAFF_ROLE: 0x303843,           # tmavě šedá, níže než hodnosti
    CIVILIAN_ROLE: 0xA1A7AE,        # neutrální světle šedá
}
LEGACY_ROLES = ["Příslušník GIBS", "Příjem oznámení", "Trestní řízení",
                "Závažná trestná činnost", "Operativní dokumentace", "Novinář",
                "Uchazeč o službu", "Policie ČR", "Celní správa", "Vězeňská služba"]
CASE_PREFIX = "spis-"
OPEN_CASE_CAT = "📂 OTEVŘENÉ SPISY"
ARCH_CASE_CAT = "🗄️ ARCHIV SPISŮ"
TICKET_CATEGORY = "🎫 TICKETY"
ARCH_TICKET_CAT = "🗃️ UZAVŘENÉ TICKETY"
TICKET_PANEL_CHANNEL = "podat-oznameni"
TICKET_LOG_CHANNEL = "evidence-ticketu"
CASE_INDEX = "evidence-spisu"

# Čitelné názvy kanálů: emoji | název. Interní identifikátory se nemění,
# takže se po aktualizaci přejmenují původní kanály bez mazání zpráv.
CHANNEL_LABELS = {
    "pravidla": "📜 | pravidla",
    "oznameni": "📢 | oznámení",
    "vedeni-inspekce": "🏛️ | vedení-inspekce",
    "verejny-chat": "💬 | veřejný-chat",
    "dotazy": "❓ | dotazy",
    "podat-oznameni": "🎫 | podat-oznámení",
    "nabor": "📨 | nábor",
    "seznam-prislusniku": "👥 | seznam-příslušníků",
    "povyseni": "📈 | povýšení",
    "sluzebni-chat": "💬 | služební-chat",
    "planovane-realizace": "🚨 | plánované-realizace",
    "sablony-dokumentu": "📄 | šablony-dokumentů",
    "evidence-spisu": "📁 | evidence-spisů",
    "vedeni-chat": "👑 | vedení-chat",
    "evidence-ticketu": "🗂️ | evidence-ticketů",
}
VOICE_LABELS = {
    "Čekárna": "⏳ | Čekárna",
    "Operační místnost": "📻 | Operační místnost",
    "Trestní řízení": "⚖️ | Trestní řízení",
    "Poradní místnost": "🗣️ | Poradní místnost",
    "Kancelář ředitele": "🏛️ | Kancelář ředitele",
    "Výslech 1": "🎙️ | Výslech 1",
    "Výslech 2": "🎙️ | Výslech 2",
    "Výslech 3": "🎙️ | Výslech 3",
}
CASE_NAME_RE = re.compile(r"(?:^|\s*\|\s*)spis-(\d{4})$")
TICKET_NAME_RE = re.compile(r"(?:^|\s*\|\s*)ticket-(\d{4,6})$")


def text_label(slug: str) -> str:
    return CHANNEL_LABELS.get(slug, slug)


def voice_label(name: str) -> str:
    return VOICE_LABELS.get(name, name)


def case_number(name: str) -> int | None:
    match = CASE_NAME_RE.search(name)
    return int(match.group(1)) if match else None


def case_label(number: int) -> str:
    return f"📁 | spis-{number:04d}"


def ticket_number(name: str) -> int | None:
    match = TICKET_NAME_RE.search(name)
    return int(match.group(1)) if match else None


def ticket_label(number: int) -> str:
    return f"🎫 | ticket-{number:04d}"


def text_channel(guild: discord.Guild, slug: str) -> discord.TextChannel | None:
    """Najde kanál s novým názvem i původní verzi bez emoji."""
    wanted = (text_label(slug), slug)
    return next((ch for name in wanted for ch in guild.text_channels if ch.name == name), None)


def voice_channel(guild: discord.Guild, name: str) -> discord.VoiceChannel | None:
    wanted = (voice_label(name), name)
    return next((ch for label in wanted for ch in guild.voice_channels if ch.name == label), None)


CASE_SECTIONS = [
    ("📌 | Přehled spisu", "**SPIS {code}**\n**Věc:** {subject}\n**Založeno:** {date}\n**Založil:** {author}\n**Stav:** Otevřen\n\n**Popis skutku:**\nDoplnit.\n\n**Pověření příslušníci:**\nDoplnit."),
    ("📁 | Důkazy", "**DŮKAZY**\nD-001 | Druh důkazu | Zajistil | Datum/čas | Místo | Popis | Kde je originál | Příloha"),
    ("🗣️ | Výslechy", "**VÝSLECHY A VÝPOVĚDI**\nOsoba | Procesní postavení | Datum/čas | Místo | Provádějící | Poučení | Záznam/protokol"),
    ("📝 | Úřední záznamy", "**ÚŘEDNÍ ZÁZNAMY**\nČíslo záznamu | Datum/čas | Zpracoval | Předmět | Zjištění | Přílohy"),
    ("🚔 | Zadržení a úkony", "**ZADRŽENÍ A DALŠÍ ÚKONY**\nDruh úkonu | Právní podklad | Osoba | Datum/čas/místo | Provedl | Předání/propuštění | Dokumentace"),
    ("⚖️ | Rozhodnutí", "**ROZHODNUTÍ A POKYNY**\nDatum | Vydal | Právní podklad | Rozhodnutí | Přílohy"),
    ("🕒 | Časová osa", "**CHRONOLOGIE**\n`DD.MM.RRRR HH:MM — událost — kdo provedl — odkaz na důkaz/záznam`"),
    ("📎 | Přílohy", "**DOKUMENTY A PŘÍLOHY**\nNázev | Autor | Datum | Souvislost se spisem | Soubor/odkaz"),
]

PUBLIC_CATS = [
    ("📌 INFORMACE", [
        ("pravidla", True, "Základní pravidla serveru."),
        ("oznameni", True, "Sdělení vedení inspekce."),
        ("vedeni-inspekce", True, "Aktuální vedení a organizační informace."),
    ]),
    ("🌐 PRO VEŘEJNOST", [
        ("verejny-chat", False, "Běžná komunikace členů serveru a veřejnosti."),
        ("dotazy", False, "Dotazy a veřejné informace."),
        (TICKET_PANEL_CHANNEL, True, "Zde se podává soukromá stížnost, oznámení nebo žádost."),
    ]),
]
PRIVATE_CATS = [
    ("👥 PERSONÁLNÍ", [
        ("nabor", False, "Interní agenda náboru."),
        ("seznam-prislusniku", True, "Služební přehled příslušníků."),
        ("povyseni", True, "Personální rozhodnutí."),
    ]),
    ("🔎 TRESTNÍ ŘÍZENÍ", [
        ("sluzebni-chat", False, "Služební komunikace příslušníků."),
        ("planovane-realizace", False, "Interní koordinace."),
        ("sablony-dokumentu", True, "Pracovní formuláře a vzory."),
        (CASE_INDEX, True, "Odkazy na soukromá fóra spisů."),
    ]),
    ("🏛️ VEDENÍ", [
        ("vedeni-chat", False, "Komunikace vedení."),
        (TICKET_LOG_CHANNEL, True, "Interní evidence ticketů a exporty."),
    ]),
]

INFO_TEXT = {
    "pravidla": "**PRAVIDLA SERVERU**\n1. Zachovávejte slušné vystupování.\n2. Nezveřejňujte osobní ani soukromé informace bez souhlasu.\n3. Důvěrná oznámení a stížnosti řešte přes ticket.\n4. Nezahlcujte kanály a nezneužívejte ticket systém.\n5. Interní spisy jsou přístupné jen pověřeným osobám.",
    "oznameni": "**OZNÁMENÍ VEDENÍ**\nOficiální sdělení se zveřejňují zde.",
    "vedeni-inspekce": "**VEDENÍ GENERÁLNÍ INSPEKCE BEZPEČNOSTNÍCH SBORŮ**\nŘeditel: —\nNáměstek: —\nVedoucí oddělení: —",
    "verejny-chat": "**VEŘEJNÝ CHAT**\nPro běžné zprávy a komunikaci členů serveru.",
    "dotazy": "**DOTAZY**\nVeřejné otázky pište sem. Pro soukromou stížnost nebo oznámení použijte ticket.",
    CASE_INDEX: "**EVIDENCE SPISŮ**\nKaždý spis má vlastní soukromé fórum se sekcemi Důkazy, Výslechy, Úřední záznamy, Zadržení, Rozhodnutí, Časová osa a Přílohy.\n`/spis_zalozit`, `/spis_pridat`, `/spis_odebrat`, `/spis_uzavrit`, `/spis_seznam`",
}

intents = discord.Intents.default()
# Automatické přidání role Civilista při příchodu vyžaduje SERVER MEMBERS INTENT
# zapnutý rovněž v Discord Developer Portal > Bot.
intents.members = True
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents,
                    allowed_mentions=discord.AllowedMentions.none(), help_command=None)
case_lock = asyncio.Lock()
ticket_lock = asyncio.Lock()
started = False


def role(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)


def manager(member: discord.Member) -> bool:
    return (member.id == member.guild.owner_id or member.guild_permissions.administrator
            or any(r.name in LEADERS for r in member.roles))


def personnel_manager(member: discord.Member) -> bool:
    """Personální práva nemá vedoucí oddělení ani inspektoři."""
    return (member.id == member.guild.owner_id
            or any(r.name in PROMOTERS for r in member.roles))


def staff(member: discord.Member) -> bool:
    # Nestačí pouze společná role; vyžadujeme také služební hodnost.
    return (member.id == member.guild.owner_id or member.guild_permissions.administrator
            or any(r.name in RANKS for r in member.roles))


def active_rank(member: discord.Member) -> str | None:
    for rank_name in RANKS:
        if any(r.name == rank_name for r in member.roles):
            return rank_name
    return None


def ticket_staff(member: discord.Member) -> bool:
    return staff(member)


def overwrites_public(guild: discord.Guild, *, readonly: bool = False) -> dict:
    # Bez role lze číst pravidla, oznámení a ticket panel; pro psaní je role Civilista / GIBS.
    perms: dict = {guild.default_role: discord.PermissionOverwrite(
        view_channel=True, read_message_history=True,
        send_messages=False, attach_files=False, add_reactions=False)}
    if readonly:
        names = LEADERS
    else:
        names = [STAFF_ROLE, CIVILIAN_ROLE]
    for name in names:
        r = role(guild, name)
        if r:
            perms[r] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True,
                send_messages=True, attach_files=True, add_reactions=True, embed_links=True)
    return perms


def overwrites_private(guild: discord.Guild, *, leaders_only: bool = False) -> dict:
    perms: dict = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
    names = LEADERS if leaders_only else [STAFF_ROLE]
    for name in names:
        r = role(guild, name)
        if r:
            perms[r] = discord.PermissionOverwrite(
                view_channel=True, read_message_history=True, send_messages=True,
                attach_files=True, connect=True, speak=True, send_messages_in_threads=True,
                manage_messages=name in LEADERS, manage_threads=name in LEADERS)
    return perms


def overwrites_voice_public(guild: discord.Guild) -> dict:
    perms = {guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False)}
    for name in [STAFF_ROLE, CIVILIAN_ROLE]:
        r = role(guild, name)
        if r:
            perms[r] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
    for name in LEADERS:
        r = role(guild, name)
        if r:
            perms[r] = discord.PermissionOverwrite(view_channel=True, connect=True,
                                                    speak=True, move_members=True)
    return perms


def overwrites_voice_staff(guild: discord.Guild, *, directors: bool = False) -> dict:
    perms = {guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False)}
    names = PROMOTERS if directors else [STAFF_ROLE]
    for name in names:
        r = role(guild, name)
        if r:
            perms[r] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True,
                                                    move_members=name in LEADERS)
    return perms


async def ensure_voice(guild: discord.Guild, cat: discord.CategoryChannel,
                       name: str, perms: dict, *, limit: int = 0) -> discord.VoiceChannel:
    display = voice_label(name)
    voice = voice_channel(guild, name)
    if voice:
        if (voice.name != display or voice.category_id != cat.id
                or voice.overwrites != perms or voice.user_limit != limit):
            # Změní jen spravované místnosti; místnosti výslechů jsou nepřístupné veřejnosti,
            # s výjimkou jednotlivých osob povolených příkazem /vyslech_pozvat.
            preserved = dict(perms)
            if name.startswith("Výslech "):
                for target, setting in voice.overwrites.items():
                    if isinstance(target, discord.Member) and setting.connect:
                        preserved[target] = setting
            await voice.edit(name=display, category=cat, overwrites=preserved, user_limit=limit,
                             reason="Aktualizace hlasových místností GIBS")
        return voice
    return await guild.create_voice_channel(display, category=cat, overwrites=perms,
                                             user_limit=limit, reason="Místnost GIBS")


def overwrites_tickets(guild: discord.Guild, member: discord.Member | None = None) -> dict:
    # Přístup mají všichni skuteční příslušníci podle hodnosti, nikdo další.
    perms = overwrites_private(guild)
    if member:
        perms[member] = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=True, attach_files=True)
    return perms


async def find_category(guild: discord.Guild, name: str, perms: dict) -> discord.CategoryChannel:
    cat = discord.utils.get(guild.categories, name=name)
    if cat:
        if cat.overwrites != perms:
            await cat.edit(overwrites=perms, reason="Aktualizace role a oprávnění GIBS")
        return cat
    return await guild.create_category(name, overwrites=perms, reason="Založení struktury GIBS")


async def room(guild: discord.Guild, cat: discord.CategoryChannel, name: str,
               perms: dict, topic: str = "") -> discord.TextChannel:
    # Nezakládá duplicity; u kanálů spravovaných botem aktualizuje oprávnění
    # (aby starý veřejný chat nebyl dál otevřený všem bez role).
    display = text_label(name)
    ch = text_channel(guild, name)
    if ch:
        if ch.name != display or ch.category_id != cat.id or ch.overwrites != perms:
            await ch.edit(name=display, category=cat, overwrites=perms,
                          reason="Nové emoji názvy a oprávnění kanálů GIBS")
        return ch
    return await guild.create_text_channel(display, category=cat, overwrites=perms, topic=topic,
                                          reason="Založení struktury GIBS")


async def post_once(ch: discord.TextChannel, content: str) -> None:
    try:
        async for msg in ch.history(limit=25):
            if msg.author.id == bot.user.id and msg.content == content:
                return
        m = await ch.send(content)
        try:
            await m.pin(reason="Úvodní informace")
        except discord.HTTPException:
            pass
    except discord.Forbidden:
        LOG.warning("Nelze zapisovat do #%s", ch.name)


async def capacity_category(guild: discord.Guild, root: str, perms: dict) -> discord.CategoryChannel:
    # Každá kategorie může obsahovat nejvýše 50 kanálů.
    for i in range(1, 100):
        name = root if i == 1 else f"{root} {i:02d}"
        cat = discord.utils.get(guild.categories, name=name)
        if cat is None:
            return await find_category(guild, name, perms)
        if len(cat.channels) < 47:
            return cat
    raise RuntimeError("Byl dosažen limit kategorií.")


async def ensure_roles(guild: discord.Guild) -> None:
    # Bez globálních správních oprávnění! Personální agenda výhradně přes příkaz.
    for n in [CIVILIAN_ROLE, STAFF_ROLE] + list(reversed(RANKS)):
        r = role(guild, n)
        if r is None:
            r = await guild.create_role(name=n, colour=discord.Colour(ROLE_COLORS[n]),
                                        permissions=discord.Permissions.none(),
                                        hoist=n in (STAFF_ROLE, CIVILIAN_ROLE), mentionable=False, reason="Zřízení hodností a personálu GIBS")
            LOG.info("Vytvořena role %s", n)
        elif (r.colour.value != ROLE_COLORS[n] or r.permissions != discord.Permissions.none()
              or r.hoist != (n in (STAFF_ROLE, CIVILIAN_ROLE))):
            try:
                await r.edit(colour=discord.Colour(ROLE_COLORS[n]),
                             permissions=discord.Permissions.none(),
                             hoist=n in (STAFF_ROLE, CIVILIAN_ROLE),
                             reason="Barvy a omezení oprávnění GIBS")
            except discord.Forbidden:
                LOG.warning("Nelze upravit roli %s – přesuň roli bota nad GIBS hodnosti.", n)

    # Viditelnou barvu určuje nejvyšší role: hodnosti proto mají být nad společnou rolí.
    ordering = [CIVILIAN_ROLE, STAFF_ROLE] + list(reversed(RANKS))
    if guild.me and guild.me.top_role.position > 1:
        try:
            await guild.edit_role_positions(positions={role(guild, n): i + 1
                                                         for i, n in enumerate(ordering)})
        except (discord.Forbidden, discord.HTTPException) as exc:
            LOG.warning("Pořadí rolí nelze nastavit automaticky: %s", exc)


async def ensure_structure(guild: discord.Guild) -> None:
    await ensure_roles(guild)

    for catname, channels in PUBLIC_CATS:
        cat = await find_category(guild, catname, overwrites_public(guild))
        for chname, readonly, topic in channels:
            ch = await room(guild, cat, chname, overwrites_public(guild, readonly=readonly), topic)
            if chname in INFO_TEXT:
                await post_once(ch, INFO_TEXT[chname])

    for catname, channels in PRIVATE_CATS:
        leaders_only = catname == "🏛️ VEDENÍ"
        cat = await find_category(guild, catname, overwrites_private(guild, leaders_only=leaders_only))
        for chname, readonly, topic in channels:
            perms = overwrites_private(guild, leaders_only=leaders_only)
            if chname == TICKET_LOG_CHANNEL:
                perms = overwrites_tickets(guild)
            elif readonly:
                r = role(guild, STAFF_ROLE)
                if r in perms:
                    perms[r].send_messages = False
                for n in LEADERS:
                    senior = role(guild, n)
                    if senior:
                        perms[senior] = discord.PermissionOverwrite(view_channel=True,
                            read_message_history=True, send_messages=True, attach_files=True)
            ch = await room(guild, cat, chname, perms, topic)
            if chname in INFO_TEXT:
                await post_once(ch, INFO_TEXT[chname])

    await find_category(guild, OPEN_CASE_CAT, overwrites_private(guild, leaders_only=True))
    await find_category(guild, ARCH_CASE_CAT, overwrites_private(guild, leaders_only=True))
    await find_category(guild, TICKET_CATEGORY, overwrites_tickets(guild))
    await find_category(guild, ARCH_TICKET_CAT, overwrites_tickets(guild))
    # Čekárna pro civilisty, kanceláře a interní výslechové místnosti.
    public_voice_cat = await find_category(guild, "🌐 VEŘEJNÉ HLASOVÉ MÍSTNOSTI",
                                           overwrites_voice_public(guild))
    await ensure_voice(guild, public_voice_cat, "Čekárna", overwrites_voice_public(guild))

    staff_voice_cat = await find_category(guild, "🔊 SLUŽEBNÍ HLASOVÉ MÍSTNOSTI",
                                          overwrites_voice_staff(guild))
    for name in ("Operační místnost", "Trestní řízení", "Poradní místnost"):
        await ensure_voice(guild, staff_voice_cat, name, overwrites_voice_staff(guild))

    office_cat = await find_category(guild, "🏛️ KANCELÁŘE",
                                     overwrites_voice_staff(guild, directors=True))
    await ensure_voice(guild, office_cat, "Kancelář ředitele",
                       overwrites_voice_staff(guild, directors=True))

    interview_cat = await find_category(guild, "🎙️ VÝSLECHOVÉ MÍSTNOSTI",
                                        overwrites_voice_staff(guild))
    for n in range(1, 4):
        await ensure_voice(guild, interview_cat, f"Výslech {n}",
                           overwrites_voice_staff(guild))

    # Zachová otevřené tickety (včetně jejich podavatelů) ze starého bota.
    for ch in guild.text_channels:
        if ticket_data(ch):
            number = ticket_number(ch.name)
            if number is not None and ch.name != ticket_label(number):
                try:
                    await ch.edit(name=ticket_label(number), reason="Jednotný název ticketu s emoji")
                except (discord.Forbidden, discord.HTTPException):
                    LOG.exception("Ticket %s nejde přejmenovat", ch.name)
            perms = overwrites_tickets(guild)
            for target, setting in ch.overwrites.items():
                if isinstance(target, discord.Member):
                    perms[target] = setting
            if ch.overwrites != perms:
                await ch.edit(overwrites=perms, reason="Přístup k ticketu podle hodností GIBS")

    panel = text_channel(guild, TICKET_PANEL_CHANNEL)
    if panel:
        await ensure_ticket_panel(panel)

    if "COMMUNITY" in guild.features:
        forums = [f for f in guild.forums if case_number(f.name) is not None]
        for f in forums:
            number = case_number(f.name)
            if f.name != case_label(number):
                try:
                    await f.edit(name=case_label(number), reason="Jednotný název fóra s emoji")
                except (discord.Forbidden, discord.HTTPException):
                    LOG.exception("Fórum %s nejde přejmenovat", f.name)
        if not forums:
            try:
                await create_case(guild, "Případ – doplnit údaje", None)
            except discord.HTTPException:
                LOG.exception("První fórum spisu se nepodařilo vytvořit")
        else:
            for f in forums:
                if f.category and f.category.name.startswith(ARCH_CASE_CAT):
                    continue
                await repair_case(f)
    else:
        LOG.warning("Není zapnutá Komunita: ticket systém funguje, ale fóra spisů potřebují Komunitu.")

    # Staré extra role odstraníme až po převodu oprávnění kanálů.
    for name in LEGACY_ROLES:
        stale = role(guild, name)
        if stale and not stale.managed:
            try:
                await stale.delete(reason="GIBS nyní používá jen sedm hodností a Civilista")
                LOG.info("Odstraněna nepotřebná role: %s", name)
            except (discord.Forbidden, discord.HTTPException):
                LOG.warning("Nelze odebrat starou roli %s (zkontroluj pořadí rolí bota).", name)

    # Stávajícím členům doplní personální roli podle jejich skutečné hodnosti.
    # Neodhadujeme hodnosti dle starých skupin. Po restartu nic neduplikuje.
    for member in guild.members:
        if not member.bot:
            await sync_member_roles(member)


# ---- Automatická role Civilista / personál -------------------------------------

async def sync_member_roles(member: discord.Member) -> None:
    if member.bot or (GUILD_ID and member.guild.id != GUILD_ID):
        return
    shared = role(member.guild, STAFF_ROLE)
    civ = role(member.guild, CIVILIAN_ROLE)
    if not shared or not civ:
        return
    has_rank = active_rank(member) is not None
    wanted = shared if has_rank else civ
    unwanted = civ if has_rank else shared
    to_add = [wanted] if wanted not in member.roles else []
    to_remove = [unwanted] if unwanted in member.roles else []
    try:
        if to_add:
            await member.add_roles(*to_add, reason="Automatické přiřazení GIBS / Civilista")
        if to_remove:
            await member.remove_roles(*to_remove, reason="Synchronizace role s hodností")
    except (discord.Forbidden, discord.HTTPException):
        LOG.warning("Nelze synchronizovat role člena %s; pozice bota musí být nad hodnostmi.", member.id)


@bot.event
async def on_member_join(member: discord.Member) -> None:
    await sync_member_roles(member)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    if before.roles != after.roles:
        await sync_member_roles(after)


# ---- Soukromé trestní spisy / fóra ------------------------------------------------

async def repair_case(f: discord.ForumChannel) -> int:
    """Doplní chybějící sekce, ale nezdvojuje archivované existující sekce."""
    existing = {t.name.replace(" | ", " ", 1) for t in f.threads}
    if len(existing) >= len(CASE_SECTIONS):
        return 0
    try:
        async for t in f.archived_threads(limit=100):
            existing.add(t.name.replace(" | ", " ", 1))
    except (discord.HTTPException, discord.Forbidden):
        # Bez ověření archivu raději neděláme duplicity.
        LOG.warning("Archivní příspěvky ve spisu %s nelze načíst.", f.name)
        return 0
    fmt = {"code": f"SPIS-{case_number(f.name) or 0:04d}", "subject": f.topic or "Doplnit údaje",
           "date": now(), "author": "vedení inspekce"}
    created = 0
    for title, template in CASE_SECTIONS:
        if title.replace(" | ", " ", 1) not in existing:
            try:
                await f.create_thread(name=title, content=template.format(**fmt),
                                      auto_archive_duration=10080)
                created += 1
            except discord.HTTPException:
                LOG.exception("Nelze doplnit %s ve spisu %s", title, f.name)
    if created:
        LOG.info("Doplněno %s příspěvků ve spisu %s", created, f.name)
    return created


def get_case(guild: discord.Guild, no: int) -> discord.ForumChannel | None:
    return next((f for f in guild.forums if case_number(f.name) == no), None)


async def create_case(guild: discord.Guild, subject: str, author: discord.Member | None,
                      assignee: discord.Member | None = None) -> discord.ForumChannel:
    async with case_lock:
        if "COMMUNITY" not in guild.features:
            raise RuntimeError("Nejdřív v Nastavení serveru zapni Komunitu (fórum-kanály).")
        all_numbers = [no for f in guild.forums if (no := case_number(f.name)) is not None]
        n = max(all_numbers, default=0) + 1
        if n > 9999:
            raise RuntimeError("Limit čísel spisů.")
        code = f"spis-{n:04d}"
        cat = await capacity_category(guild, OPEN_CASE_CAT, overwrites_private(guild, leaders_only=True))
        perms = overwrites_private(guild, leaders_only=True)
        for m in (author, assignee):
            if m and not manager(m):
                perms[m] = discord.PermissionOverwrite(view_channel=True,
                    read_message_history=True, send_messages_in_threads=True,
                    send_messages=False, attach_files=True)
        f = await guild.create_forum(case_label(n), category=cat, overwrites=perms,
                                    topic=f"{code.upper()} | {clean(subject, 80)} | {now()}",
                                    default_auto_archive_duration=10080,
                                    reason=f"Založení spisu {code}")
        fmt = {"code": code.upper(), "subject": clean(subject), "date": now(),
               "author": author.display_name if author else "vedení inspekce"}
        failed = []
        for title, template in CASE_SECTIONS:
            try:
                await f.create_thread(name=title, content=template.format(**fmt),
                                      auto_archive_duration=10080)
            except discord.HTTPException as exc:
                failed.append(f"{title}: {exc}")
        if failed:
            LOG.error("Vytvořen spis %s, ale chybí sekce: %s", code, "; ".join(failed))
        ch = text_channel(guild, CASE_INDEX)
        if ch:
            await ch.send(f"📁 **{code.upper()}** — {clean(subject, 150)} — {f.mention}")
        return f


async def private_response(i: discord.Interaction, msg: str) -> None:
    if i.response.is_done():
        await i.followup.send(msg, ephemeral=True)
    else:
        await i.response.send_message(msg, ephemeral=True)


def in_guild(i: discord.Interaction) -> bool:
    return i.guild is not None and isinstance(i.user, discord.Member)


@bot.tree.command(name="spis_zalozit", description="Založí neveřejné fórum se sekcemi dokumentace.")
@app_commands.describe(nazev="Název případu", prideleny="Další příslušník, kterému dáš přístup")
async def spis_zalozit(i: discord.Interaction, nazev: str, prideleny: discord.Member | None = None):
    if not in_guild(i) or not staff(i.user):
        return await private_response(i, "⛔ Spisy zakládají jen příslušníci GIBS.")
    if not (3 <= len(nazev.strip()) <= 120):
        return await private_response(i, "Název spisu musí mít 3–120 znaků.")
    if prideleny is not None and not staff(prideleny):
        return await private_response(i, "Přidělená osoba musí být příslušníkem GIBS.")
    await i.response.defer(ephemeral=True, thinking=True)
    try:
        forum = await create_case(i.guild, nazev, i.user, prideleny)
        await i.followup.send(f"✅ Založen **SPIS-{case_number(forum.name):04d}**: {forum.mention}", ephemeral=True)
    except (discord.HTTPException, RuntimeError) as e:
        await i.followup.send(f"❌ Spis se nepodařilo založit: {e}", ephemeral=True)


@bot.tree.command(name="spis_pridat", description="Zpřístupní vybraný spis příslušníkovi.")
async def spis_pridat(i: discord.Interaction, cislo: int, osoba: discord.Member):
    if not in_guild(i) or not manager(i.user):
        return await private_response(i, "⛔ Pouze vedení GIBS.")
    forum = get_case(i.guild, cislo)
    if not forum or not staff(osoba):
        return await private_response(i, "Spis neexistuje nebo osoba není příslušníkem.")
    await forum.set_permissions(osoba, view_channel=True, read_message_history=True,
                                send_messages=False, send_messages_in_threads=True, attach_files=True)
    await private_response(i, f"✅ Přístup povolen pro {osoba.display_name}: {forum.mention}")


@bot.tree.command(name="spis_odebrat", description="Odebere přístup příslušníkovi ke spisu.")
async def spis_odebrat(i: discord.Interaction, cislo: int, osoba: discord.Member):
    if not in_guild(i) or not manager(i.user):
        return await private_response(i, "⛔ Pouze vedení GIBS.")
    forum = get_case(i.guild, cislo)
    if not forum or manager(osoba):
        return await private_response(i, "Spis neexistuje nebo je členem vedení.")
    await forum.set_permissions(osoba, view_channel=False)
    await private_response(i, f"✅ Přístup odebrán: {forum.name}")


@bot.tree.command(name="spis_uzavrit", description="Přesune spis do archivu a uzamkne zápisy.")
async def spis_uzavrit(i: discord.Interaction, cislo: int, duvod: str):
    if not in_guild(i) or not manager(i.user):
        return await private_response(i, "⛔ Pouze vedení GIBS.")
    f = get_case(i.guild, cislo)
    if not f:
        return await private_response(i, "Spis nenalezen.")
    await i.response.defer(ephemeral=True)
    cat = await capacity_category(i.guild, ARCH_CASE_CAT, overwrites_private(i.guild, leaders_only=True))
    perms = dict(f.overwrites)
    for target, p in perms.items():
        if isinstance(target, discord.Role) and target.name in LEADERS:
            continue
        if isinstance(target, discord.Member) and manager(target):
            continue
        p.send_messages = False
        p.send_messages_in_threads = False
    await f.edit(category=cat, overwrites=perms,
                 topic=f"ARCHIV | {f.topic or f.name} | {now()} | {clean(duvod, 100)}")
    await i.followup.send(f"✅ Spis {f.mention} uzavřen.", ephemeral=True)


@bot.tree.command(name="spis_opravit", description="Doplní chybějící sekce staršího spisu.")
async def spis_opravit(i: discord.Interaction, cislo: int):
    if not in_guild(i) or not manager(i.user):
        return await private_response(i, "⛔ Pouze vedení GIBS.")
    f = get_case(i.guild, cislo)
    if not f:
        return await private_response(i, "Spis nebyl nalezen.")
    await i.response.defer(ephemeral=True, thinking=True)
    count = await repair_case(f)
    await i.followup.send(f"✅ Ve {f.mention} doplněno {count} chybějících sekcí.", ephemeral=True)


@bot.tree.command(name="spis_seznam", description="Vypíše spisy, ke kterým máš přístup.")
async def spis_seznam(i: discord.Interaction):
    if not in_guild(i) or not staff(i.user):
        return await private_response(i, "⛔ Pouze pro příslušníky.")
    forums = [f for f in i.guild.forums if case_number(f.name) is not None
              and f.permissions_for(i.user).view_channel]
    txt = "\n".join(f"{f.mention} — SPIS-{case_number(f.name):04d}" for f in sorted(forums, key=lambda c: case_number(c.name))[:40])
    await private_response(i, txt or "Nemáš zatím přístup k žádnému spisu.")


# ---- Tickety / civilní oznámení ---------------------------------------------------

TICKET_NAMES = {"stiznost": "Stížnost", "oznameni": "Oznámení", "dotaz": "Žádost / dotaz"}
TICKET_TOPIC_RE = re.compile(r"^GIBS-TICKET\|(\d+)\|(stiznost|oznameni|dotaz)\|(open|closed)")


def ticket_data(ch: discord.abc.GuildChannel | None) -> tuple[int, str, str] | None:
    if not isinstance(ch, discord.TextChannel):
        return None
    match = TICKET_TOPIC_RE.match(ch.topic or "")
    if not match:
        return None
    return int(match.group(1)), match.group(2), match.group(3)


def can_manage_ticket(i: discord.Interaction) -> bool:
    return in_guild(i) and ticket_staff(i.user)


async def log_ticket(guild: discord.Guild, msg: str, file: discord.File | None = None) -> None:
    ch = text_channel(guild, TICKET_LOG_CHANNEL)
    if ch:
        try:
            await ch.send(msg, file=file)
        except discord.HTTPException:
            LOG.exception("Nepodařilo se zapsat do evidence ticketů")


async def export_ticket(ch: discord.TextChannel) -> discord.File:
    lines = [f"TICKET #{ch.name}", f"Export: {now()}", "=" * 72]
    async for msg in ch.history(limit=None, oldest_first=True):
        at = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        message = msg.content or "[bez textu]"
        lines.append(f"[{at}] {msg.author.display_name} ({msg.author.id}): {message}")
        for a in msg.attachments:
            lines.append(f"  PŘÍLOHA: {a.filename} | {a.url}")
        for e in msg.embeds:
            lines.append(f"  EMBED: {e.title or ''} | {e.description or ''}")
    data = "\n".join(lines).encode("utf-8")
    # Limit velikosti vyřešit přiměřeně. Discord má různé limity podle serveru.
    if len(data) > 7_000_000:
        data = data[:7_000_000] + b"\n[EXPORT ZKRACEN - prilis mnoho zprav]\n"
    return discord.File(io.BytesIO(data), filename=f"ticket-{ticket_number(ch.name) or 0:04d}-export.txt")


async def change_ticket(i: discord.Interaction, close: bool) -> None:
    data = ticket_data(i.channel)
    if not data:
        return await private_response(i, "Tento kanál není ticket.")
    owner_id, kind, status = data
    if not can_manage_ticket(i):
        return await private_response(i, "⛔ Ticket uzavírá a znovu otevírá pouze pověřený příslušník.")
    if close == (status == "closed"):
        return await private_response(i, "Ticket už má požadovaný stav.")
    await i.response.defer(ephemeral=True, thinking=True)
    ch: discord.TextChannel = i.channel
    member = i.guild.get_member(owner_id)
    cat = await capacity_category(i.guild, ARCH_TICKET_CAT if close else TICKET_CATEGORY,
                                  overwrites_tickets(i.guild))
    await ch.edit(category=cat,
            topic=f"GIBS-TICKET|{owner_id}|{kind}|{'closed' if close else 'open'}|{now()}")
    if member:
        await ch.set_permissions(member, view_channel=True, read_message_history=True,
                                 send_messages=not close, attach_files=not close)
    if close:
        await ch.send("🔒 **Ticket uzavřen.** Konverzace je uzamčena pro podavatele. Pověřený příslušník může ticket znovu otevřít.")
        try:
            file = await export_ticket(ch)
            await log_ticket(i.guild, f"🔒 Ticket **{ch.name}** uzavřel {i.user.display_name} | {now()}", file)
        except (discord.Forbidden, discord.HTTPException):
            LOG.exception("Export ticketu nevyšel")
    else:
        await ch.send("🔓 **Ticket znovu otevřen.** Podavatel může pokračovat v komunikaci.")
        await log_ticket(i.guild, f"🔓 Ticket **{ch.name}** otevřel {i.user.display_name} | {now()}")
    await i.followup.send("✅ Hotovo.", ephemeral=True)


class TicketModal(discord.ui.Modal):
    def __init__(self, kind: str):
        super().__init__(title=f"{TICKET_NAMES[kind]} – GIBS", timeout=300)
        self.kind = kind
        self.subject = discord.ui.TextInput(label="Předmět", min_length=4, max_length=100,
                                            placeholder="Stručně popiš, čeho se případ týká")
        self.description = discord.ui.TextInput(label="Popis oznámení", style=discord.TextStyle.paragraph,
                                                min_length=15, max_length=1800,
                                                placeholder="Co se stalo? Kdy, kde a kdo byl přítomen?")
        self.evidence = discord.ui.TextInput(label="Důkazy / svědci (nepovinné)",
                                             style=discord.TextStyle.paragraph,
                                             required=False, max_length=600)
        self.add_item(self.subject)
        self.add_item(self.description)
        self.add_item(self.evidence)

    async def on_submit(self, i: discord.Interaction) -> None:
        if not in_guild(i):
            return await private_response(i, "Ticket lze otevřít jen na serveru.")
        await i.response.defer(ephemeral=True, thinking=True)
        async with ticket_lock:
            for c in i.guild.text_channels:
                data = ticket_data(c)
                if data and data[0] == i.user.id and data[1] == self.kind and data[2] == "open":
                    return await i.followup.send(f"Už máš otevřený ticket tohoto typu: {c.mention}", ephemeral=True)
            cat = await capacity_category(i.guild, TICKET_CATEGORY, overwrites_tickets(i.guild))
            # ID se odvozuje z existujících textových kanálů, je stabilní po restartu.
            nums = [n for c in i.guild.text_channels if (n := ticket_number(c.name)) is not None]
            number = max(nums, default=0) + 1
            ch = await i.guild.create_text_channel(
                ticket_label(number), category=cat,
                overwrites=overwrites_tickets(i.guild, i.user),
                topic=f"GIBS-TICKET|{i.user.id}|{self.kind}|open|{now()}",
                reason=f"Soukromé oznámení {self.kind}")
            intro = discord.Embed(title=f"📩 {TICKET_NAMES[self.kind]} — #{number:04d}",
                                  description=clean(str(self.description), 1800),
                                  colour=discord.Colour.dark_blue())
            intro.add_field(name="Předmět", value=clean(str(self.subject), 100), inline=False)
            intro.add_field(name="Podavatel", value=f"{i.user.display_name} ({i.user.id})", inline=False)
            intro.add_field(name="Důkazy / svědci", value=clean(str(self.evidence), 600) or "Zatím neuvedeno", inline=False)
            intro.set_footer(text=f"Založeno {now()} | Přílohy lze přidat přímo do kanálu")
            await ch.send(embed=intro, view=TicketControlView())
            await log_ticket(i.guild, f"📩 Nový **{TICKET_NAMES[self.kind]}**: {ch.mention} — {i.user.display_name} | {now()}")
            await i.followup.send(f"✅ Soukromý ticket vytvořen: {ch.mention}\nDo kanálu můžeš přidat fotografie a další přílohy.", ephemeral=True)


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Podat stížnost", emoji="📝", style=discord.ButtonStyle.danger,
                       custom_id="gibs:v2:ticket:stiznost")
    async def complaint(self, i: discord.Interaction, button: discord.ui.Button):
        await i.response.send_modal(TicketModal("stiznost"))

    @discord.ui.button(label="Podat oznámení", emoji="📨", style=discord.ButtonStyle.primary,
                       custom_id="gibs:v2:ticket:oznameni")
    async def report(self, i: discord.Interaction, button: discord.ui.Button):
        await i.response.send_modal(TicketModal("oznameni"))

    @discord.ui.button(label="Žádost / dotaz", emoji="❔", style=discord.ButtonStyle.secondary,
                       custom_id="gibs:v2:ticket:dotaz")
    async def question(self, i: discord.Interaction, button: discord.ui.Button):
        await i.response.send_modal(TicketModal("dotaz"))


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Převzít", emoji="✋", style=discord.ButtonStyle.primary,
                       custom_id="gibs:v2:ticket:claim")
    async def claim(self, i: discord.Interaction, button: discord.ui.Button):
        if not ticket_data(i.channel) or not can_manage_ticket(i):
            return await private_response(i, "⛔ Pouze příslušníci GIBS.")
        if "|CLAIMED=" in (i.channel.topic or ""):
            return await private_response(i, "Ticket už je převzatý.")
        await i.channel.edit(topic=(i.channel.topic or "") + f"|CLAIMED={i.user.id}")
        await i.response.send_message("✅ Ticket převzat.", ephemeral=True)
        await i.channel.send(f"✋ Ticket převzal **{i.user.display_name}**.")
        await log_ticket(i.guild, f"✋ {i.channel.name} — převzal {i.user.display_name}")

    @discord.ui.button(label="Uzavřít", emoji="🔒", style=discord.ButtonStyle.danger,
                       custom_id="gibs:v2:ticket:close")
    async def close(self, i: discord.Interaction, button: discord.ui.Button):
        await change_ticket(i, close=True)

    @discord.ui.button(label="Otevřít znovu", emoji="🔓", style=discord.ButtonStyle.secondary,
                       custom_id="gibs:v2:ticket:reopen")
    async def reopen(self, i: discord.Interaction, button: discord.ui.Button):
        await change_ticket(i, close=False)


async def ensure_ticket_panel(ch: discord.TextChannel) -> None:
    async for m in ch.history(limit=50):
        if m.author.id == bot.user.id and m.embeds and m.embeds[0].title == "Podání oznámení a stížností":
            return
    embed = discord.Embed(title="Podání oznámení a stížností",
        description=("Potřebuješ podat **stížnost**, **oznámení** nebo **žádost**?\n"
                     "Klikni na tlačítko. Vznikne soukromý kanál přístupný pouze tobě a "
                     "pověřeným příslušníkům inspekce.\n\n"
                     "**Neposílej veřejně citlivé osobní údaje.** Důkazy a fotografie lze "
                     "připojit až uvnitř ticketu."), colour=discord.Colour.dark_blue())
    msg = await ch.send(embed=embed, view=TicketPanelView())
    try:
        await msg.pin()
    except discord.HTTPException:
        pass


@bot.tree.command(name="ticket_panel", description="Znovu odešle panel pro stížnosti a oznámení.")
async def ticket_panel_cmd(i: discord.Interaction):
    if not in_guild(i) or not manager(i.user):
        return await private_response(i, "⛔ Pouze vedení.")
    ch = text_channel(i.guild, TICKET_PANEL_CHANNEL)
    if not ch:
        return await private_response(i, "Kanál pro oznámení nebyl nalezen.")
    await ch.send(embed=discord.Embed(title="Podání oznámení a stížností",
         description="Použij tlačítko. Otevře se soukromý ticket.", colour=discord.Colour.dark_blue()),
         view=TicketPanelView())
    await private_response(i, f"✅ Panel odeslán do {ch.mention}.")


@bot.tree.command(name="ticket_pridat", description="Přidá osobu do tohoto ticketu.")
async def ticket_pridat(i: discord.Interaction, osoba: discord.Member):
    if not ticket_data(i.channel) or not can_manage_ticket(i):
        return await private_response(i, "⛔ Jen pověřený příslušník uvnitř ticketu.")
    await i.channel.set_permissions(osoba, view_channel=True, send_messages=ticket_data(i.channel)[2] == "open",
                                    read_message_history=True, attach_files=True)
    await private_response(i, f"✅ Do ticketu přidána osoba {osoba.display_name}.")


@bot.tree.command(name="ticket_odebrat", description="Odebere osobu z tohoto ticketu.")
async def ticket_odebrat(i: discord.Interaction, osoba: discord.Member):
    data = ticket_data(i.channel)
    if not data or not can_manage_ticket(i):
        return await private_response(i, "⛔ Jen pověřený příslušník uvnitř ticketu.")
    if osoba.id == data[0] or ticket_staff(osoba):
        return await private_response(i, "Nelze odebrat podavatele ani pověřeného příslušníka.")
    await i.channel.set_permissions(osoba, overwrite=None)
    await private_response(i, f"✅ Osobě {osoba.display_name} odebrán přístup.")


@bot.tree.command(name="ticket_uzavrit", description="Uzavře tento ticket a uloží textový přepis.")
async def ticket_uzavrit(i: discord.Interaction):
    await change_ticket(i, close=True)


@bot.tree.command(name="ticket_otevrit", description="Znovu otevře tento ticket.")
async def ticket_otevrit(i: discord.Interaction):
    await change_ticket(i, close=False)


@bot.tree.command(name="ticket_export", description="Uloží přepis tohoto ticketu do interní evidence.")
async def ticket_export(i: discord.Interaction):
    if not ticket_data(i.channel) or not can_manage_ticket(i):
        return await private_response(i, "⛔ Pouze oprávněný příslušník uvnitř ticketu.")
    await i.response.defer(ephemeral=True)
    f = await export_ticket(i.channel)
    await log_ticket(i.guild, f"📄 Export ticketu {i.channel.mention} | provedl {i.user.display_name}", file=f)
    await i.followup.send("✅ Přepis uložen do interní evidence ticketů.", ephemeral=True)


# ---- Vstup civilistů na výslech -----------------------------------------------

@bot.tree.command(name="vyslech_pozvat", description="Zpřístupní civilistovi konkrétní výslechovou místnost.")
async def vyslech_pozvat(i: discord.Interaction, mistnost: app_commands.Range[int, 1, 3],
                         osoba: discord.Member):
    if not in_guild(i) or not staff(i.user):
        return await private_response(i, "⛔ Pouze pro příslušníky GIBS.")
    if osoba.bot:
        return await private_response(i, "Bota nelze pozvat k výslechu.")
    voice = voice_channel(i.guild, f"Výslech {mistnost}")
    if not voice:
        return await private_response(i, "Výslechová místnost zatím neexistuje.")
    if len([k for k in voice.overwrites if isinstance(k, discord.Member)]) >= 15:
        return await private_response(i, "Místnost má příliš mnoho individuálních povolení.")
    try:
        await voice.set_permissions(osoba, view_channel=True, connect=True, speak=True,
                                    reason=f"Pozvání k výslechu: {i.user.display_name}")
        await private_response(i, f"✅ {osoba.mention} má přístup do **{voice.name}**. "
                               "Po skončení použij `/vyslech_odebrat`.")
    except (discord.Forbidden, discord.HTTPException):
        await private_response(i, "❌ Nelze zpřístupnit místnost. Bot potřebuje Spravovat kanály.")


@bot.tree.command(name="vyslech_odebrat", description="Odebere individuální vstup do výslechové místnosti.")
async def vyslech_odebrat(i: discord.Interaction, mistnost: app_commands.Range[int, 1, 3],
                          osoba: discord.Member):
    if not in_guild(i) or not staff(i.user):
        return await private_response(i, "⛔ Pouze pro příslušníky GIBS.")
    voice = voice_channel(i.guild, f"Výslech {mistnost}")
    if not voice:
        return await private_response(i, "Místnost neexistuje.")
    try:
        if osoba in voice.overwrites:
            await voice.set_permissions(osoba, overwrite=None,
                                        reason=f"Ukončení přístupu: {i.user.display_name}")
        if osoba.voice and osoba.voice.channel == voice and not staff(osoba):
            await osoba.move_to(None, reason="Ukončení výslechu")
        await private_response(i, f"✅ Přístup do **{voice.name}** odebrán: {osoba.display_name}.")
    except (discord.Forbidden, discord.HTTPException):
        await private_response(i, "❌ Oprávnění nebylo možné změnit.")


# ---- Hodnosti GIBS ------------------------------------------------------------

@bot.tree.command(name="prislusnik_zaradit", description="Přidělí příslušníkovi jedinou hodnost GIBS.")
@app_commands.choices(hodnost=[app_commands.Choice(name=n, value=n) for n in RANKS])
async def prislusnik_zaradit(i: discord.Interaction, osoba: discord.Member,
                             hodnost: app_commands.Choice[str]):
    if not in_guild(i) or not personnel_manager(i.user):
        return await private_response(i, "⛔ Hodnosti přiděluje pouze ředitel nebo náměstek.")
    if osoba.bot or (osoba.id == i.guild.owner_id and i.user.id != i.guild.owner_id):
        return await private_response(i, "Této osobě nelze takto přidělit hodnost.")
    actor_rank = active_rank(i.user)
    prev_rank = active_rank(osoba)
    if osoba.id == i.user.id and i.user.id != i.guild.owner_id:
        return await private_response(i, "⛔ Vlastní povýšení není dovoleno.")
    if i.user.id != i.guild.owner_id:
        if hodnost.value == RANKS[0]:
            return await private_response(i, "⛔ Ředitele může zařadit pouze vlastník serveru.")
        if actor_rank == RANKS[1] and (hodnost.value in RANKS[:2] or prev_rank in RANKS[:2]):
            return await private_response(i, "⛔ Náměstek nemůže měnit vedení na své nebo vyšší úrovni.")
    target = role(i.guild, hodnost.value)
    shared = role(i.guild, STAFF_ROLE)
    if not target or not shared:
        return await private_response(i, "⛔ Chybí hodnost nebo společná role personálu.")
    updated = [r for r in osoba.roles if r != i.guild.default_role
               and r.name not in RANKS + [CIVILIAN_ROLE, STAFF_ROLE]]
    updated.extend([shared, target])
    try:
        await osoba.edit(roles=updated, reason=f"Hodnost GIBS: {i.user.display_name}")
    except (discord.Forbidden, discord.HTTPException):
        return await private_response(i, "⛔ Bot nemůže upravit role. Přesuň jeho roli nad hodnosti GIBS.")
    audit = text_channel(i.guild, "povyseni")
    if audit:
        await audit.send(f"📋 **PERSONÁLNÍ ZÁZNAM** | {osoba.mention}: "
                         f"{prev_rank or 'Civilista'} → **{hodnost.value}** | "
                         f"Provedl: {i.user.display_name} | {now()}")
    await private_response(i, f"✅ {osoba.display_name}: **{hodnost.value}** + společná role GIBS")


@bot.tree.command(name="prislusnik_vyradit", description="Odebere hodnost GIBS a nastaví Civilistu.")
async def prislusnik_vyradit(i: discord.Interaction, osoba: discord.Member):
    if not in_guild(i) or not personnel_manager(i.user):
        return await private_response(i, "⛔ Pouze ředitel nebo náměstek.")
    if osoba.id == i.guild.owner_id or osoba.bot or osoba.id == i.user.id:
        return await private_response(i, "⛔ Tento příkaz nelze použít na uvedenou osobu.")
    prev_rank = active_rank(osoba)
    if i.user.id != i.guild.owner_id and active_rank(i.user) == RANKS[1] and prev_rank in RANKS[:2]:
        return await private_response(i, "⛔ Náměstek nemůže vyřadit ředitele ani jiného náměstka.")
    try:
        civ = role(i.guild, CIVILIAN_ROLE)
        updated = [r for r in osoba.roles if r != i.guild.default_role
               and r.name not in RANKS + [CIVILIAN_ROLE, STAFF_ROLE]]
        if civ:
            updated.append(civ)
        await osoba.edit(roles=updated, reason=f"Vyřazení GIBS: {i.user.display_name}")
        for f in i.guild.forums:
            if case_number(f.name) is not None and osoba in f.overwrites:
                await f.set_permissions(osoba, view_channel=False, reason="Vyřazení")
        for v in i.guild.voice_channels:
            if (v.name.startswith("Výslech ") or v.name.startswith("🎙️ | Výslech ")) and osoba in v.overwrites:
                await v.set_permissions(osoba, overwrite=None, reason="Vyřazení GIBS")
    except (discord.Forbidden, discord.HTTPException):
        return await private_response(i, "⛔ Bot nemůže odebrat hodnost. Přesuň jeho roli nad hodnosti.")
    audit = text_channel(i.guild, "povyseni")
    if audit:
        await audit.send(f"📋 **PERSONÁLNÍ ZÁZNAM** | {osoba.mention}: "
                         f"{prev_rank or 'bez hodnosti'} → Civilista | "
                         f"Provedl: {i.user.display_name} | {now()}")
    await private_response(i, f"✅ {osoba.display_name}: **Civilista**")


# ---- Spuštění a obnova persistent views ------------------------------------------

@bot.event
async def on_ready() -> None:
    global started
    if started:
        return
    started = True
    guild = bot.get_guild(GUILD_ID) if GUILD_ID else (bot.guilds[0] if len(bot.guilds) == 1 else None)
    if guild is None:
        LOG.error("Nelze určit server. Nastav DISCORD_GUILD_ID (ID tvého Discord serveru).")
        return
    LOG.info("Přihlášen jako %s na %s (%s)", bot.user, guild.name, guild.id)
    try:
        await ensure_structure(guild)
        # Slash příkazy se objeví během sekund na vybraném serveru.
        obj = discord.Object(id=guild.id)
        bot.tree.copy_global_to(guild=obj)
        synced = await bot.tree.sync(guild=obj)
        LOG.info("HOTOVO: %s příkazů | tickety a veřejný chat běží.", len(synced))
        print("\n✅ GIBS BOT ONLINE – personál + hodnosti + Civilista, tickety, spisy a výslechy připraveny.\n", flush=True)
    except (discord.Forbidden, discord.HTTPException):
        LOG.exception("Chyba oprávnění / Discord API. Zkontroluj práva bota.")
    except Exception:
        LOG.exception("Neočekávaná chyba při přípravě serveru.")


@bot.tree.error
async def on_command_error(i: discord.Interaction, error: app_commands.AppCommandError):
    LOG.error("Chyba slash příkazu: %s", error, exc_info=True)
    try:
        await private_response(i, "❌ Příkaz se nepodařilo dokončit. Zkontroluj konzoli bota a oprávnění.")
    except discord.HTTPException:
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if not TOKEN:
        raise SystemExit("Chybí DISCORD_TOKEN. Spusť nejdřív START.bat nebo nastav proměnnou DISCORD_TOKEN.")
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControlView())
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
