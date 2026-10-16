GIBS DISCORD BOT – PERSONÁL, HODNOSTI, TICKETY, SPISY A VÝSLECHY
==============================================================

CO BOT VYTVOŘÍ
---------------
1) POUZE 9 VLASTNÍCH ROLÍ:
   Ředitel GIBS                  – zlatá; plná personální agenda
   Náměstek ředitele            – fialová; personální agenda s omezeními
   Vedoucí oddělení             – ocelově modrá; správa spisů, NE povyšování
   Vrchní komisař               – tmavě modrá
   Komisař                      – modrá
   Vrchní inspektor             – šedomodrá
   Inspektor                    – šedomodrá
   Generální inspekce bezpečnostních sborů – společná role personálu
   Civilista                    – veřejný návštěvník

   Discord navíc automaticky vede systémovou roli @everyone a roli aplikace.
   Člen GIBS má DVĚ role: společnou roli personálu + JEDNU hodnost.
   Civilista má pouze roli Civilista. Mezi těmito stavy bot přepíná automaticky.
   Na seznamu členů se zobrazí dvě skupiny (personál a civilisté).
   Výslednou barvu příslušníka určuje jeho nejvyšší hodnost.

2) VEŘEJNÉ KANÁLY (emoji | název):
   📜 | pravidla, 📢 | oznámení, 🏛️ | vedení-inspekce
   💬 | veřejný-chat, ❓ | dotazy, 🎫 | podat-oznámení (tickety)

3) INTERNÍ KANÁLY:
   📨 | nábor, 👥 | seznam-příslušníků, 📈 | povýšení
   💬 | služební-chat, 🚨 | plánované-realizace, 📄 | šablony-dokumentů
   📁 | evidence-spisů, 👑 | vedení-chat, 🗂️ | evidence-ticketů

4) HLASOVÉ KANÁLY:
   VEŘEJNÉ: ⏳ | Čekárna
   SLUŽEBNÍ: 📻 | Operační místnost, ⚖️ | Trestní řízení,
             🗣️ | Poradní místnost
   KANCELÁŘ: 🏛️ | Kancelář ředitele
   VÝSLECHY: 🎙️ | Výslech 1,  🎙️ | Výslech 2, 🎙️ | Výslech 3
   Civilista se do místnosti Výslech dostane POUZE po pozvání příkazem.

5) SOUKROMÁ FÓRA SPISŮ:
   📁 | spis-0001, 📁 | spis-0002 ...
   Uvnitř fóra: Přehled, Důkazy, Výslechy, Úřední záznamy,
   Zadržení, Rozhodnutí, Časová osa, Přílohy.
   Každý spis vidí jen vedení a osoby přímo přidané ke spisu.

6) TICKETY:
   Formuláře stížnost / oznámení / dotaz.
   Tlačítka otevřou soukromý kanál, funkce převzít / uzavřít / obnovit.
   Textový export do #evidence-ticketu při uzavření.
   Tlačítka fungují i po restartu bota.
   Tickety se zakládají jako 🎫 | ticket-0001, 🎫 | ticket-0002 ...

PRAVOMOCI
----------
Inspektor / Vrchní inspektor / Komisař / Vrchní komisař:
  běžná práce, spisy podle přidělení, tickety, pozvání na výslech;
  NEMÁ Spravovat role, kanály, Administrator ani právo povyšovat.
Vedoucí oddělení:
  stejné + může přidat vyšetřovatele ke spisu a archivovat spisy;
  NEMÁ právo povyšovat členy.
Náměstek ředitele:
  může přidělovat nižší hodnosti a vyřazovat níže postavené;
  nesmí přidělit roli ředitele ani spravovat jiného náměstka.
Ředitel GIBS:
  správa hodností, spisů a interního provozu.
Vlastník serveru:
  může přidělit i funkci ředitele.

Oprávnění Spravovat role nejsou přímo v žádné hodnosti GIBS.
Úpravy rolí dělá BOT a před každým personálním příkazem kontroluje hodnost.
Pozor: vlastníka serveru a osoby s oprávněním Administrator z jiných rolí
není možné Discord botem bezpečně omezit.

PŘÍKAZY
--------
/prislusnik_zaradit osoba:... hodnost:...
/prislusnik_vyradit osoba:...
/spis_zalozit nazev:... prideleny:...
/spis_pridat cislo:... osoba:...
/spis_odebrat cislo:... osoba:...
/spis_uzavrit cislo:... duvod:...
/spis_opravit cislo:...
/spis_seznam
/vyslech_pozvat mistnost:1 osoba:...
/vyslech_odebrat mistnost:1 osoba:...
/ticket_panel
/ticket_pridat osoba:...
/ticket_odebrat osoba:...
/ticket_uzavrit
/ticket_otevrit
/ticket_export

PŘECHOD ZE STARÉ VERZE
-----------------------
1. Vypni původního bota. Nespouštěj dvě instance současně.
2. ROZBAL tento ZIP do NOVÉ složky na PC.
3. Spusť START.bat, zadej NOVÝ TOKEN lokálně (nikoliv sem do chatu).
4. V Developer Portal > Bot zapni "Server Members Intent".
5. V Discordu zapni Komunitu pro fóra spisů.
6. Bota dej v nastavení rolí NAD všechny hodnosti, Civilistu i roli personálu.
7. Nech program dokončit přejmenování kanálů na emoji | název.
   Existující spravované kanály, spisy a tickety se přejmenují, NE smažou.
   Zprávy a oprávnění ke spisům tím zůstanou zachovány.
8. Při nasazení nové verze se mohou oprávnění již spravovaných kanálů
   upravit na aktuální vzor. Staré nadbytečné role známé z dřívějších
   verzí se bot pokusí odebrat. Před prvním spuštěním si ověř/zálohuj
   důležitá oprávnění a v případě potřeby využij testovací server.
9. Pokud by role zůstaly špatně seřazené, přesuň ručně role v Discordu:
   nejvýš BOT, pod něj Ředitel, Náměstek ... Inspektor,
   pak společná role personálu a nakonec Civilista.

TOKEN
------
Pokud jsi jakýkoli bot token zveřejnil, resetuj ho v Discord Developer Portal.
Soubor .env se vytváří na tvém počítači. Je v .gitignore a .dockerignore.
Token nikdy neposílej do chatu ani na GitHub.

24/7 HOSTING
-------------
START.bat znamená online jen při zapnutém PC a otevřeném programu.
Pro dlouhodobý provoz použij např. Railway.com:
- Nahraj rozbalené soubory do soukromého GitHub repozitáře (bez .env).
- Railway > New Project > Deploy from GitHub Repo.
- Variables: DISCORD_TOKEN a DISCORD_GUILD_ID.
- Na hostingu ponech jen 1 instanci; vypni lokálního bota.
- Nenechávej běžet dvě instance pod jedním tokenem.
Hosting může být placený a je nutné kontrolovat logy.

FUNKČNOST
----------
Kód prošel kontrolou syntaxe, neproběhl však test na živém Discord serveru.
Před ostrým používáním vyzkoušej účet Civilista a Inspektor,
a také uzavření testovacího ticketu a spuštění výslechu.

EMOJI NÁZVY KANÁLŮ
------------------
Textové, hlasové i fórum-kanály (a příspěvky nově založených spisů)
mají podobu "emoji | název". Interní názvy jsou stále stejné a příkazy
/spis_zalozit, /vyslech_pozvat a tickety fungují i po přejmenování.
Při nasazení aktualizace bot vyhledává staré názvy a přejmenuje je,
aby nevytvářel duplicity. Máš-li ručně upravené názvy/kanály,
založ nejdřív kopii serveru pro test.
