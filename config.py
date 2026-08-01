import os
from dotenv import load_dotenv

load_dotenv()

# ─── Token & IDs ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))          # ID numerico del gruppo (negativo)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "21773014").split(",") if x]

# ─── Rate limiting ─────────────────────────────────────────────────────────────
RATE_LIMIT_HOURS = int(os.getenv("RATE_LIMIT_HOURS", "6"))   # ore tra un post e l'altro
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", "2")) # max post per utente/giorno

# ─── Messaggi del bot ──────────────────────────────────────────────────────────
WELCOME_MESSAGE = """
👋 Benvenuto/a in *Offerte Lavoro Bar Torino*!

Siamo una community di +9.000 professionisti del settore bar & ristorazione a Torino.

📋 *Regole del gruppo:*

1️⃣ Pubblica solo annunci di lavoro nel settore bar/ristorazione
2️⃣ Max *2 annunci al giorno* per utente
3️⃣ No link esterni, no spam, no pubblicità
4️⃣ Indica sempre zona e tipo di contratto
5️⃣ Rispetta gli altri membri

📝 *Formato consigliato per gli annunci:*

```
🏷️ OFFERTA / RICERCA
💼 Ruolo: (es. Barista, Cameriere, Aiuto cuoco)
📍 Zona: (quartiere/zona di Torino)
⏰ Contratto: (Full-time / Part-time / Extra / Stagionale)
📞 Contatto: @username o numero
📝 Note: breve descrizione
```

✨ Vuoi mettere il tuo annuncio *in evidenza*? Contatta @{admin_username}

In bocca al lupo! 🍀
""".strip()

RATE_LIMIT_MESSAGE = """
⏳ Hai già pubblicato un annuncio di recente.

Puoi pubblicare al massimo *{max_per_day} annunci al giorno*, con almeno *{hours}h di intervallo* tra un post e l'altro.

Prossimo post disponibile: *{next_time}*
""".strip()

SPAM_LINK_MESSAGE = """
🚫 I link esterni non sono permessi nel gruppo.

Per pubblicità o collaborazioni contatta l'admin: @{admin_username}
""".strip()

SHORT_MESSAGE_WARNING = """
⚠️ Il tuo annuncio sembra troppo breve o incompleto.

Usa il formato consigliato per avere più visibilità:

```
🏷️ OFFERTA / RICERCA
💼 Ruolo:
📍 Zona:
⏰ Contratto:
📞 Contatto:
```
""".strip()

FEATURED_INFO = """
⭐ *Annuncio in Evidenza*

Il tuo post verrà *pinnato in cima al gruppo per 24 ore* con visibilità massima.

💰 Costo: *5€*
📲 Pagamento: Satispay / PayPal / Bonifico

Scrivi a @{admin_username} per prenotare!
""".strip()

# ─── Testo admin username ──────────────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "marcogiuridio")

# ─── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "bot_data.db")
