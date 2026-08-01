# Bot Telegram — Offerte Lavoro Bar Torino

Bot di moderazione e organizzazione per il gruppo Telegram **"Offerte Lavoro Bar Torino"** (9.000+ membri).

---

## 🚀 Funzionalità

- 👋 **Benvenuto automatico** ai nuovi membri (messaggio privato con regole)
- 🏷️ **Classificazione messaggi** (Offerta / Richiesta / Spam)
- ⏳ **Rate limiting** (max 2 post/giorno, 6h di intervallo)
- 🔗 **Blocco link esterni** automatico
- 🚫 **Anti-spam** con keyword detection
- 📊 **Statistiche** per l'admin
- ⭐ **Post in evidenza** (monetizzazione)

---

## ⚙️ Setup

### 1. Crea il bot su Telegram
1. Apri [@BotFather](https://t.me/BotFather)
2. Scrivi `/newbot` → scegli nome e username
3. Copia il **token**

### 2. Configura le variabili d'ambiente
```bash
cp .env.example .env
# Modifica .env con il tuo token e i tuoi ID
```

### 3. Installa dipendenze (per test locale)
```bash
pip install -r requirements.txt
```

### 4. Avvia in locale (test)
```bash
python bot.py
```

---

## ☁️ Deploy su Railway

### 1. Crea account su [railway.app](https://railway.app)

### 2. Installa Railway CLI (opzionale) o usa la UI web

### 3. Deploy via GitHub
1. Metti la cartella `bot/` su GitHub (repo privato)
2. Su Railway: **New Project → Deploy from GitHub repo**
3. Seleziona il repo

### 4. Aggiungi le variabili d'ambiente
Su Railway → tab **Variables**, aggiungi:
```
BOT_TOKEN = il_tuo_token
GROUP_ID = -1001456564882
ADMIN_IDS = 21773014
ADMIN_USERNAME = marcogiuridio
RATE_LIMIT_HOURS = 6
MAX_POSTS_PER_DAY = 2
```

### 5. Deploy automatico ✅

---

## 🤖 Comandi disponibili

### Per tutti
| Comando | Funzione |
|---------|----------|
| `/regole` | Mostra le regole del gruppo |
| `/formato` | Mostra il formato consigliato per gli annunci |
| `/evidenza` | Info sugli annunci in evidenza (a pagamento) |

### Solo admin
| Comando | Funzione |
|---------|----------|
| `/stats` | Statistiche ultimi 7 giorni |
| `/ban` | Banna utente (reply al suo messaggio) |
| `/unban` | Rimuovi ban (reply al suo messaggio) |
| `/verify` | Segna utente come verificato |
| `/featured` | Metti post in evidenza (reply al messaggio) |

---

## 💰 Monetizzazione — Annunci in Evidenza

1. L'utente ti scrive chiedendo visibilità
2. Paga 10€ (Satispay/PayPal)
3. Tu fai reply al suo post con `/featured`
4. Il post viene pinnato per 24h automaticamente

---

## 📁 Struttura file

```
bot/
├── bot.py           # Bot principale
├── classifier.py    # Classificatore messaggi
├── database.py      # Database SQLite
├── config.py        # Configurazione
├── requirements.txt # Dipendenze
├── Procfile         # Per Railway
├── railway.toml     # Config Railway
└── .env.example     # Variabili d'ambiente (esempio)
```
