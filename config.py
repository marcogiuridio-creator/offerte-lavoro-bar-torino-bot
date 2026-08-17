import os
from dotenv import load_dotenv

load_dotenv()

# ─── Token & IDs ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))          # ID numerico del gruppo (negativo)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "21773014").split(",") if x]
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "marcogiuridio o @banu80")

STRIPE_PROVIDER_TOKEN = os.getenv("STRIPE_PROVIDER_TOKEN", "")
RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("RAILWAY_STATIC_URL", ""))
if RAILWAY_DOMAIN:
    if not RAILWAY_DOMAIN.startswith("http"):
        RAILWAY_DOMAIN = f"https://{RAILWAY_DOMAIN}"
    BASE_WEB_URL = RAILWAY_DOMAIN
else:
    BASE_WEB_URL = os.getenv("BASE_WEBAPP_URL", "https://marcogiuridio-creator.github.io/offerte-lavoro-bar-torino-bot")

WEBAPP_URL = os.getenv("WEBAPP_URL", f"{BASE_WEB_URL}/webapp/index.html?v=20260803_autobump")
WEBAPP_PUBBLICA_URL = os.getenv("WEBAPP_PUBBLICA_URL", f"{BASE_WEB_URL}/webapp/pubblica.html?v=20260803_autobump")
WEBAPP_DASHBOARD_URL = os.getenv("WEBAPP_DASHBOARD_URL", f"{BASE_WEB_URL}/webapp/dashboard.html?v=20260803_autobump")
WEBAPP_MANUALE_CANDIDATI_URL = os.getenv("WEBAPP_MANUALE_CANDIDATI_URL", f"{BASE_WEB_URL}/webapp/manuale_candidati.html?v=20260803_autobump")
WEBAPP_MANUALE_DATORI_URL = os.getenv("WEBAPP_MANUALE_DATORI_URL", f"{BASE_WEB_URL}/webapp/manuale_datori.html?v=20260803_autobump")





# ─── Rate limiting ─────────────────────────────────────────────────────────────
RATE_LIMIT_HOURS = int(os.getenv("RATE_LIMIT_HOURS", "6"))   # ore tra un post e l'altro
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", "2")) # max post per utente/giorno

# ─── Messaggi del bot ──────────────────────────────────────────────────────────
WELCOME_MESSAGE = """
👋 Benvenuto/a nel gruppo *Offerte Lavoro Bar Torino*! ☕🍹

Siamo la più grande community Horeca di Torino con oltre **9.000 professionisti** (baristi, bartender, camerieri, chef, aiuto cuochi e titolari di locali).

━━━━━━━━━━━━━━━━━━━━━━━

📌 *REGOLE FONDAMENTALI DEL GRUPPO:*

1️⃣ **Solo offerte HORECA**: Nel gruppo possono pubblicare annunci i datori che cercano personale per bar, ristoranti, pizzerie, catering e locali a Torino e provincia.
2️⃣ **Cerchi lavoro?** Non pubblicare annunci personali: registrati gratuitamente come candidato con `/registrati`.
3️⃣ **Limite messaggi**: Massimo *2 offerte al giorno* per utente (intervallo minimo di 6 ore tra i post).
4️⃣ **Moderazione Link**: I link a siti esterni sono bloccati per sicurezza e richiedono l'approvazione dell'amministratore.
5️⃣ **Annunci chiari**: Scrivi testi dettagliati spiegando ruolo, zona e contatti.
6️⃣ **Rispetto ed Educazione**: Vietati insulti, spam, catene, vendita prodotti o offerte di guadagno online.

━━━━━━━━━━━━━━━━━━━━━━━

🤖 *COMANDI UTILI DEL BOT:*

Puoi usare questi comandi sia nel gruppo che in privato col bot:

• `/start` ── Avvia il bot e mostra questo benvenuto
• `/regole` ── Leggi le regole ufficiali della community
• `/stats` ── Guarda le statistiche aggiornate del gruppo
• `/evidenza` ── Scopri come mettere in evidenza il tuo annuncio (solo 5€)

━━━━━━━━━━━━━━━━━━━━━━━

📝 *FORMATO CONSIGLIATO PER GLI ANNUNCI:*

🏷️ OFFERTA DI LAVORO
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
🏷️ OFFERTA DI LAVORO
💼 Ruolo:
📍 Zona:
⏰ Contratto:
📞 Contatto:
```
""".strip()

FEATURED_INFO = """
🚀 *Pacchetti Promozionali & Visibilità per Datori di Lavoro*

Aumenta la visibilità del tuo annuncio e trova subito personale qualificato a Torino!

⭐ *In Evidenza 24 Ore (5,39€ / 250 Stelle)*
• Post in evidenza + Pinnato 24h + Notifica Push istantanea ai candidati

👑 *Sponsor VIP 7 Giorni (10,90€ / 500 Stelle)*
• Post VIP + Pinnato per 7 giorni + 🚀 *Auto-Bump ogni 3h* (ripubblicazione in fondo + nuovo Pin) + Multi-push

💎 *Pass VIP Mensile 30 Giorni (29,90€ / 1.400 Stelle)*
• Post VIP + Pinnato per 30 giorni + 🚀 *Auto-Bump ogni 3h per 1 mese intero* + Post illimitati + Push prioritario + Badge VIP

📲 Pubblica direttamente via WebApp dal bot col comando `/pubblica` oppure contatta l'admin @{admin_username}
""".strip()

# ─── Testo admin username ──────────────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "marcogiuridio o @banu80")



# ─── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "bot_data.db")
ENABLE_SEED_IMPORT = os.getenv("ENABLE_SEED_IMPORT", "false").lower() == "true"
