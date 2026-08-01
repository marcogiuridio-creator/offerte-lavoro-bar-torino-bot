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
👋 Benvenuto/a nel gruppo *Offerte Lavoro Bar Torino*! ☕🍹

Siamo la più grande community Horeca di Torino con oltre **9.000 professionisti** (baristi, bartender, camerieri, chef, aiuto cuochi e titolari di locali).

━━━━━━━━━━━━━━━━━━━━━━━

📌 *REGOLE FONDAMENTALI DEL GRUPPO:*

1️⃣ **Solo annunci HORECA**: Pubblica esclusivamente offerte o ricerche di lavoro per bar, ristoranti, pizzerie, catering e locali a Torino e provincia.
2️⃣ **Limite messaggi**: Massimo *2 annunci al giorno* per utente (intervallo minimo di 6 ore tra i post).
3️⃣ **Moderazione Link**: I link a siti esterni sono bloccati per sicurezza e richiedono l'approvazione dell'amministratore.
4️⃣ **Annunci chiari**: Scrivi testi dettagliati di almeno 5 caratteri spiegando ruolo, zona e contatti.
5️⃣ **Rispetto ed Educazione**: Vietati insulti, spam, catene, vendita prodotti o offerte di guadagno online.

━━━━━━━━━━━━━━━━━━━━━━━

🤖 *COMANDI UTILI DEL BOT:*

Puoi usare questi comandi sia nel gruppo che in privato col bot:

• `/start` ── Avvia il bot e mostra questo benvenuto
• `/regole` ── Leggi le regole ufficiali della community
• `/stats` ── Guarda le statistiche aggiornate del gruppo
• `/evidenza` ── Scopri come mettere in evidenza il tuo annuncio (solo 5€)

━━━━━━━━━━━━━━━━━━━━━━━

📝 *FORMATO CONSIGLIATO PER GLI ANNUNCI:*

🏷️ OFFERTA / RICERCA
💼 Ruolo: (es. Barista / Cameriere / Cuoco)
📍 Zona: (quartiere/zona di Torino)
⏰ Turni: (Full-time / Part-time / Extra / Notturno)
💰 Paga/Contratto: (es. Contratto CCNL / Paga oraria)
📞 Contatto: @username o numero di telefono
📝 Dettagli: (breve descrizione del lavoro o esperienza)

━━━━━━━━━━━━━━━━━━━━━━━

💎 *ANNUNCI IN EVIDENZA & SPONSOR:*
Se hai urgenza di trovare personale e vuoi il tuo annuncio **in evidenza a 5€** o **fissato in cima al gruppo per 7 giorni**, contatta in privato: @{admin_username}

Buon lavoro e buona ricerca a tutti! 🍀
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
