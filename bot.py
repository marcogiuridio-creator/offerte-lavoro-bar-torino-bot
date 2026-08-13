"""
Bot principale — Offerte Lavoro Bar Torino
"""

import logging
import json
import asyncio
import re
from datetime import datetime

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    LabeledPrice,
    BotCommand,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

from telegram.constants import ParseMode

import config
import database as db
import server
from classifier import classify, has_external_link, get_category_emoji, format_category_label


# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def is_admin(user_or_id) -> bool:
    """Verifica se l'utente è amministratore (per ID numerico o username)."""
    if isinstance(user_or_id, int):
        return user_or_id in config.ADMIN_IDS
    if hasattr(user_or_id, "id") and user_or_id.id in config.ADMIN_IDS:
        return True
    uname = getattr(user_or_id, "username", "") or ""
    if uname:
        clean_user = uname.lower().replace("@", "").strip()
        if clean_user in ["marcogiuridio", "banu80"]:
            return True
    return False



def get_text(message) -> str:
    """Estrae testo dal messaggio (anche caption per foto/video)."""
    return message.text or message.caption or ""


def classify_group_text(text: str) -> str:
    """Classifica il contenuto ignorando gli URL, gestiti da una regola separata."""
    classification_text = re.sub(r"https?://\S+|www\.\S+\.\S+", " ", text)
    return classify(classification_text)


MANUAL_OFFER_INVITE = """📢 Vuoi dare più visibilità al tuo annuncio?

Abbiamo visto che hai pubblicato un’offerta di lavoro direttamente nella chat.

Puoi continuare a farlo, ma utilizzando il bot puoi rendere il tuo annuncio molto più efficace. 🚀

Con il bot puoi:

🎯 raggiungere candidati compatibili con il ruolo che stai cercando
📍 selezionare zona, posizione e requisiti
⭐ comparire tra le offerte organizzate e facilmente consultabili
🔔 raggiungere direttamente gli utenti Premium compatibili, che ricevono una notifica privata

👉 Pubblica la tua offerta tramite il bot per aumentare le possibilità di trovare la persona giusta.

Scrivi /pubblica per iniziare."""


async def invite_manual_offer_author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invita l'autore di un'offerta manuale a ripubblicarla tramite il bot."""
    msg = update.message
    user = update.effective_user
    if not msg or not user:
        return

    try:
        await context.bot.send_message(chat_id=user.id, text=MANUAL_OFFER_INVITE)
        logger.info(f"📩 Invito /pubblica inviato in privato a {user.id}")
        return
    except Exception as e:
        logger.info(f"Invio privato non disponibile per {user.id}; uso il fallback nel gruppo: {e}")

    try:
        bot_info = await context.bot.get_me()
        deep_link = f"https://t.me/{bot_info.username}?start=pubblica"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Pubblica con il bot", url=deep_link)]
        ])
        temp_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📢 Per dare più visibilità a questo annuncio, pubblicalo anche tramite il bot.",
            reply_to_message_id=msg.message_id,
            reply_markup=keyboard,
        )

        async def delete_temp_reply():
            await asyncio.sleep(15)
            try:
                await temp_msg.delete()
            except Exception as e:
                logger.warning(f"Impossibile eliminare il fallback temporaneo: {e}")

        asyncio.create_task(delete_temp_reply())
    except Exception as e:
        logger.warning(f"Impossibile mostrare il fallback per l'offerta manuale di {user.id}: {e}")


def candidate_search_invite(user_id: int):
    """Restituisce testo e pulsanti adatti allo stato del candidato."""
    profile = db.get_candidate_profile(user_id)
    is_premium = db.is_user_premium(user_id) if profile else False

    if is_premium:
        text = (
            "⭐ Il tuo profilo Premium è già attivo.\n\n"
            "Nel gruppo non sono ammessi annunci personali di ricerca lavoro, per questo il tuo messaggio è stato rimosso.\n\n"
            "Non è necessario pubblicare annunci personali: riceverai direttamente dal bot le offerte compatibili. "
            "Controlla che disponibilità, ruoli e zone siano aggiornati."
        )
        buttons = [[InlineKeyboardButton("👤 Aggiorna il profilo", callback_data="candidate_profile")]]
        return text, InlineKeyboardMarkup(buttons), "premium"

    if profile:
        text = (
            "👋 Il tuo messaggio di ricerca lavoro è stato rimosso perché nel gruppo sono ammesse soltanto offerte pubblicate dai datori.\n\n"
            "Il tuo profilo candidato Base è già registrato. Controlla che ruolo, disponibilità, zone ed esperienza siano aggiornati.\n\n"
            "Con Premium ricevi in privato le offerte compatibili e il tuo profilo viene mostrato prima ai titolari."
        )
        buttons = [
            [InlineKeyboardButton("👤 Controlla il profilo", callback_data="candidate_profile")],
            [InlineKeyboardButton("⭐ Scopri Premium", callback_data="candidate_premium")],
        ]
        return text, InlineKeyboardMarkup(buttons), "base"

    text = (
        "👋 Stai cercando lavoro nel settore bar e ristorazione?\n\n"
        "Nel gruppo non sono ammessi annunci personali di ricerca lavoro, per questo il tuo messaggio è stato rimosso.\n\n"
        "Puoi creare gratuitamente il tuo profilo candidato sul bot. Inserisci ruoli, competenze, esperienza, zone di Torino, disponibilità e contatti.\n\n"
        "La registrazione Base è gratuita. Con Premium ricevi anche le offerte compatibili in privato e il tuo profilo viene mostrato prima ai titolari."
    )
    buttons = [
        [InlineKeyboardButton("✅ Registrati gratis", callback_data="candidate_register")],
        [InlineKeyboardButton("⭐ Scopri Premium", callback_data="candidate_premium")],
    ]
    return text, InlineKeyboardMarkup(buttons), "unregistered"


async def redirect_candidate_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rimuove una ricerca di lavoro e indirizza l'autore al profilo candidato."""
    msg = update.message
    user = update.effective_user
    if not msg or not user:
        return

    try:
        await msg.delete()
    except Exception as e:
        logger.warning(f"Impossibile eliminare la ricerca lavoro {msg.message_id}: {e}")

    text, keyboard, candidate_state = candidate_search_invite(user.id)
    try:
        await context.bot.send_message(chat_id=user.id, text=text, reply_markup=keyboard)
        logger.info(f"📩 Ricerca lavoro rimossa; invito candidato {candidate_state} inviato a {user.id}")
        return
    except Exception as e:
        logger.info(f"Privato non disponibile per candidato {user.id}; uso fallback: {e}")

    try:
        bot_info = await context.bot.get_me()
        deep_link = f"https://t.me/{bot_info.username}?start=registrati"
        temp_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👋 Il tuo annuncio di ricerca lavoro è stato rimosso. Registrati gratuitamente come candidato per essere trovato dai titolari.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Registrati come candidato", url=deep_link)
            ]]),
        )

        async def delete_temp_candidate_reply():
            await asyncio.sleep(15)
            try:
                await temp_msg.delete()
            except Exception as e:
                logger.warning(f"Impossibile eliminare il fallback candidato: {e}")

        asyncio.create_task(delete_temp_candidate_reply())
    except Exception as e:
        logger.warning(f"Impossibile mostrare fallback candidato per {user.id}: {e}")


# ─── Handler: nuovo membro ─────────────────────────────────────────────────────

async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia messaggio di benvenuto privato ai nuovi membri."""
    result = update.chat_member
    if not result:
        return

    new_member = result.new_chat_member.user
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    # Solo nuovi membri (non admin rimossi/aggiunti, ecc.)
    if old_status in ("left", "kicked") and new_status == "member":
        db.upsert_user(
            new_member.id,
            new_member.username or "",
            new_member.first_name or "",
            new_member.last_name or "",
        )
        db.record_new_member()

        welcome = config.WELCOME_MESSAGE.format(admin_username=config.ADMIN_USERNAME)
        try:
            await context.bot.send_message(
                chat_id=new_member.id,
                text=welcome,
                parse_mode=ParseMode.MARKDOWN,
            )
            logger.info(f"✅ Benvenuto inviato a {new_member.first_name} ({new_member.id})")
        except Exception as e:
            # L'utente potrebbe avere i messaggi privati disabilitati
            logger.warning(f"⚠️ Impossibile inviare messaggio privato a {new_member.id}: {e}")
            # Manda benvenuto nel gruppo (meno invasivo)
            await context.bot.send_message(
                chat_id=result.chat.id,
                text=f"👋 Benvenuto/a *{new_member.first_name}*! Leggi le regole prima di pubblicare.",
                parse_mode=ParseMode.MARKDOWN,
            )


# ─── Handler: messaggi nel gruppo ─────────────────────────────────────────────

async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analizza ogni messaggio nel gruppo."""
    msg = update.message
    if not msg or not msg.from_user:
        return

    if update.effective_chat.type not in ("group", "supergroup"):
        return

    user = msg.from_user
    user_id = user.id
    text = get_text(msg)

    # Aggiorna utente nel DB
    db.upsert_user(user_id, user.username or "", user.first_name or "", user.last_name or "")

    # Gli admin sono esenti da ogni controllo
    if is_admin(user_id):
        return

    # ── 1. Utente bannato ──
    if db.is_banned(user_id):
        await msg.delete()
        logger.info(f"🚫 Messaggio bannato eliminato da {user.first_name} ({user_id})")
        return

    if not text.strip():
        # Messaggio senza testo (foto, sticker, ecc.) → ignora
        return

    # I link sono valutati separatamente: rimuoverli temporaneamente permette
    # di riconoscere frasi come "cerco lavoro, ecco il mio CV https://...".
    category = classify_group_text(text)

    # ── 2. Controlla link esterni ──
    # Una ricerca lavoro con link al CV segue comunque il percorso candidati.
    if has_external_link(text) and category != "RICHIESTA":
        db.record_spam_blocked()
        # Notifica l'admin con bottoni Approva/Rifiuta
        chat_id   = msg.chat_id
        msg_id    = msg.message_id
        user_name = user.first_name + (f" (@{user.username})" if user.username else "")

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Approva",
                    callback_data=f"link_approve:{chat_id}:{msg_id}:{user_id}"
                ),
                InlineKeyboardButton(
                    "❌ Rifiuta",
                    callback_data=f"link_reject:{chat_id}:{msg_id}:{user_id}"
                ),
            ]
        ])

        preview = text[:200] + ("..." if len(text) > 200 else "")
        for admin_id in config.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"🔗 *Richiesta approvazione link*\n\n"
                        f"👤 Utente: {user_name}\n"
                        f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                        f"📝 Testo:\n`{preview}`"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                )
            except Exception as e:
                logger.warning(f"Impossibile notificare admin {admin_id}: {e}")

        logger.info(f"🔗 Link rilevato da {user.first_name} — in attesa approvazione admin")
        return

    # ── 3. Classifica il messaggio ──
    # ── 4. Spam rilevato ──
    if category == "SPAM":
        await msg.delete()
        db.record_spam_blocked()
        logger.info(f"🚫 Spam eliminato da {user.first_name}")
        return

    # ── 5. Annuncio troppo corto ──
    if category == "CORTO":
        # Non elimina, ma avvisa privatamente
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=config.SHORT_MESSAGE_WARNING,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass
        return

    # ── 6. Rate limiting (solo per offerte/richieste) ──
    if category in ("OFFERTA", "RICHIESTA"):
        can, next_time = db.can_post(user_id, config.RATE_LIMIT_HOURS, config.MAX_POSTS_PER_DAY)
        if not can:
            await msg.delete()
            rate_msg = config.RATE_LIMIT_MESSAGE.format(
                max_per_day=config.MAX_POSTS_PER_DAY,
                hours=config.RATE_LIMIT_HOURS,
                next_time=next_time,
            )
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=rate_msg,
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass
            logger.info(f"⏳ Rate limit attivato per {user.first_name}")
            return

        # Registra il post
        db.record_post(user_id, msg.message_id, category, text)

        # Auto-tagging CRM: classifica automaticamente l'utente come datore o lavoratore
        if category == "OFFERTA":
            db.tag_user_role(user_id, "datore")
        elif category == "RICHIESTA":
            db.tag_user_role(user_id, "lavoratore")

        # Aggiungi emoji categoria come reazione (reaction) o risposta silenziosa
        emoji = get_category_emoji(category)
        logger.info(f"{emoji} {format_category_label(category)} da {user.first_name}: {text[:60]}...")

        # Le offerte scritte manualmente restano nel gruppo e nel CRM, ma non
        # generano notifiche Premium. Le notifiche sono riservate al flusso
        # strutturato avviato con /pubblica.
        if category == "OFFERTA":
            await invite_manual_offer_author(update, context)
            logger.info("📢 Offerta manuale registrata senza notifiche Premium")
        elif category == "RICHIESTA":
            await redirect_candidate_search(update, context)



# ─── Smart Reply & Deep Linking ────────────────────────────────────────────────

async def send_smart_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, deep_link_arg: str = "start"):
    """
    Invia risposte ai comandi in modo intelligente:
    - Se l'utente digita un comando nel GRUPPO (es. /evidenza, /regole):
      1. Cancella il messaggio del comando dal gruppo per non intasare la chat.
      2. Invia la risposta in privato all'utente (dove non viene persa o sommersa dagli altri messaggi).
      3. Se l'utente non ha mai avviato il bot in privato, manda una notifica temporanea di 15s con un bottone deep-link.
    - Se invocato in PRIVATO: risponde normalmente.
    """
    msg = update.message
    if not msg:
        return

    chat_type = update.effective_chat.type
    user = update.effective_user

    if chat_type in ("group", "supergroup"):
        # 1. Elimina il messaggio del comando nel gruppo
        try:
            await msg.delete()
        except Exception as e:
            logger.warning(f"Impossibile eliminare messaggio del comando nel gruppo: {e}")

        # 2. Invia in privato
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"📩 Risposta inviata in privato a {user.first_name} per comando /{deep_link_arg}")
        except Exception:
            # 3. Fallback se l'utente non ha mai avviato il bot privatamente
            bot_info = await context.bot.get_me()
            deep_link = f"https://t.me/{bot_info.username}?start={deep_link_arg}"
            inline_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Leggi in Privato", url=deep_link)]
            ])
            temp_msg = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"👋 Ciao {user.mention_markdown_v2()}, per non intasare la chat del gruppo ti ho inviato le informazioni in privato! Clicca il tasto qui sotto per leggerle:",
                reply_markup=inline_kb,
                parse_mode=ParseMode.MARKDOWN
            )
            import asyncio
            async def delete_temp():
                await asyncio.sleep(15)
                try:
                    await temp_msg.delete()
                except Exception:
                    pass
            asyncio.create_task(delete_temp())
    else:
        await msg.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start — benvenuto e deep linking."""
    user = update.effective_user
    db.upsert_user(user.id, user.username or "", user.first_name or "", user.last_name or "")

    # Deep linking per reindirizzamento da comandi del gruppo
    if context.args:
        arg = context.args[0].lower()
        if arg == "evidenza":
            await cmd_evidenza(update, context)
            return
        elif arg == "regole":
            await cmd_regole(update, context)
            return
        elif arg == "registrati":
            await cmd_registrati(update, context)
            return
        elif arg == "formato":
            await cmd_formato(update, context)
            return
        elif arg in ["pubblica", "offerta"]:
            await cmd_pubblica(update, context)
            return
        elif arg == "premium":
            await cmd_premium(update, context)
            return



    welcome = config.WELCOME_MESSAGE.format(admin_username=config.ADMIN_USERNAME)
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🍸 Compila / Modifica Profilo", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True
    )
    await send_smart_reply(update, context, welcome, reply_markup=keyboard, deep_link_arg="start")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help."""
    if is_admin(update.message.from_user.id):
        text = (
            "🛠️ *Comandi Admin:*\n\n"
            "/stats — Statistiche gruppo\n"
            "/ban `@username` — Banna utente\n"
            "/unban `@username` — Rimuovi ban\n"
            "/verify `@username` — Verifica locale/agenzia\n"
            "/featured `ID_messaggio` — Metti in evidenza post\n"
            "/regole — Mostra regole nel gruppo\n"
            "/match `testo` — Analisi matching candidati\n"
        )
    else:
        text = (
            "ℹ️ *Offerte Lavoro Bar Torino*\n\n"
            "Pubblica annunci di lavoro nel settore bar & ristorazione a Torino.\n\n"
            "/registrati — Crea il tuo profilo candidato Horeca\n"
            "/profilo — Visualizza/modifica la tua scheda salvata\n"
            "/regole — Mostra le regole\n"
            "/formato — Mostra il formato consigliato\n"
            "/evidenza — Info su annunci in evidenza\n"
        )
    await send_smart_reply(update, context, text, deep_link_arg="help")

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats — solo admin."""
    if not is_admin(update.message.from_user.id):
        return

    stats = db.get_stats(days=7)
    total_users = db.get_total_users()

    lines = [f"📊 *Statistiche — ultimi 7 giorni*\n", f"👥 Utenti totali nel DB: {total_users}\n"]
    for row in stats:
        lines.append(
            f"📅 *{row['date']}*\n"
            f"   👥 Nuovi: {row['new_members']}  "
            f"📋 Offerte: {row['offerte']}  "
            f"🙋 Richieste: {row['richieste']}  "
            f"🚫 Spam: {row['spam_blocked']}\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ban @username o reply."""
    if not is_admin(update.message.from_user.id):
        return

    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        # Cerca per username (limitato senza API premium)
        await update.message.reply_text("⚠️ Per bannare, fai reply al messaggio dell'utente con /ban")
        return

    if not target:
        await update.message.reply_text("❌ Fai reply al messaggio dell'utente da bannare.")
        return

    db.ban_user(target.id)
    try:
        await context.bot.ban_chat_member(update.message.chat_id, target.id)
    except Exception as e:
        logger.warning(f"Impossibile bannare via API: {e}")

    await update.message.reply_text(
        f"🚫 {target.first_name} è stato bannato.",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"🚫 Admin ha bannato {target.first_name} ({target.id})")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /unban — reply al messaggio."""
    if not is_admin(update.message.from_user.id):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Fai reply al messaggio dell'utente da sbannare.")
        return

    target = update.message.reply_to_message.from_user
    db.unban_user(target.id)
    try:
        await context.bot.unban_chat_member(update.message.chat_id, target.id)
    except Exception as e:
        logger.warning(f"Impossibile sbannare via API: {e}")

    await update.message.reply_text(f"✅ {target.first_name} è stato sbannato.")


async def cmd_bannati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando Admin: /bannati — mostra la lista di tutti gli utenti bannati dal bot."""
    if not is_admin(update.effective_user.id):
        return

    banned_list = db.get_banned_users()

    if not banned_list:
        await update.message.reply_text(
            "✅ *Nessun utente bannato dal bot al momento.*\n\n"
            "💡 _Nota: questa lista include solo i ban eseguiti dal bot con /ban. "
            "I ban fatti manualmente dall'interfaccia Telegram non vengono tracciati qui._",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    lines = [f"🚫 *LISTA UTENTI BANNATI DAL BOT* ({len(banned_list)} totali)\n"]
    for idx, b in enumerate(banned_list, 1):
        fname = b["first_name"] or ""
        lname = b["last_name"] or ""
        name = (fname + " " + lname).strip() or "Utente"
        uname = f" (@{b['username']})" if b["username"] else ""
        uid = b["user_id"]
        lines.append(f"{idx}. *{name}*{uname}\n    `ID: {uid}`")

    lines.append(f"\n💡 _Per sbannare: rispondi al messaggio dell'utente con /unban_")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /verify — segna utente come verificato."""
    if not is_admin(update.message.from_user.id):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Fai reply al messaggio dell'utente da verificare.")
        return

    target = update.message.reply_to_message.from_user
    db.verify_user(target.id)
    await update.message.reply_text(f"✅ {target.first_name} è ora *verificato* ⭐", parse_mode=ParseMode.MARKDOWN)


async def cmd_featured(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /featured ID_messaggio — mette in evidenza un post."""
    if not is_admin(update.message.from_user.id):
        return

    if update.message.reply_to_message:
        msg_id = update.message.reply_to_message.message_id
    elif context.args:
        try:
            msg_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ ID messaggio non valido.")
            return
    else:
        await update.message.reply_text("❌ Fai reply al post da mettere in evidenza, o scrivi /featured ID")
        return

    db.set_featured(msg_id, hours=24)
    try:
        await context.bot.pin_chat_message(update.message.chat_id, msg_id, disable_notification=True)
    except Exception as e:
        logger.warning(f"Impossibile pinnare: {e}")

    await update.message.reply_text("⭐ Post messo in evidenza per 24 ore!", parse_mode=ParseMode.MARKDOWN)


async def cmd_regole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /regole — mostra le regole."""
    rules = (
        "📋 *Regole del gruppo — Offerte Lavoro Bar Torino*\n\n"
        "1️⃣ Solo annunci di lavoro nel settore bar/ristorazione a Torino\n"
        "2️⃣ Max *2 annunci al giorno* per utente\n"
        "3️⃣ Niente link esterni, spam o pubblicità\n"
        "4️⃣ Indica sempre zona e tipo di contratto\n"
        "5️⃣ Rispetta gli altri membri\n\n"
        "Per info sugli annunci in evidenza: /evidenza"
    )
    await send_smart_reply(update, context, rules, deep_link_arg="regole")


async def cmd_formato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /formato — mostra il formato consigliato."""
    fmt = (
        "📝 *Formato consigliato per gli annunci:*\n\n"
        "```\n"
        "🏷️ OFFERTA / RICERCA\n"
        "💼 Ruolo: (es. Barista, Cameriere, Cuoco)\n"
        "📍 Zona: (quartiere/zona di Torino)\n"
        "⏰ Contratto: (Full-time / Part-time / Extra)\n"
        "📞 Contatto: @username o numero\n"
        "📝 Note: breve descrizione\n"
        "```\n\n"
        "Più informazioni dai, più risposte ricevi! 💪"
    )
    await send_smart_reply(update, context, fmt, deep_link_arg="formato")


async def cmd_evidenza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /evidenza — info monetizzazione."""
    msg = config.FEATURED_INFO.format(admin_username=config.ADMIN_USERNAME)
    await send_smart_reply(update, context, msg, deep_link_arg="evidenza")


async def cmd_guida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /guida o /manuale — invia i PDF direttamente in chat e offre le Mini App interattive."""
    pdf_dir = os.path.join(os.path.dirname(__file__), "webapp")
    pdf_candidati = os.path.join(pdf_dir, "Guida_Candidati_Horeca_Torino.pdf")
    pdf_datori = os.path.join(pdf_dir, "Guida_Datori_Horeca_Torino.pdf")

    try:
        if os.path.exists(pdf_candidati):
            with open(pdf_candidati, "rb") as f:
                await update.effective_message.reply_document(
                    document=f,
                    filename="Guida_Candidati_Horeca_Torino.pdf",
                    caption="📖 *Guida Ufficiale Candidati & Lavoratori Horeca Torino*",
                    parse_mode=ParseMode.MARKDOWN
                )
        if os.path.exists(pdf_datori):
            with open(pdf_datori, "rb") as f:
                await update.effective_message.reply_document(
                    document=f,
                    filename="Guida_Datori_Horeca_Torino.pdf",
                    caption="🏪 *Guida Ufficiale Datori di Lavoro & Titolari Horeca Torino*",
                    parse_mode=ParseMode.MARKDOWN
                )
    except Exception as e:
        logger.error(f"Errore invio file PDF: {e}")

    import time
    ts = int(time.time())
    url_candidati = f"{config.WEBAPP_MANUALE_CANDIDATI_URL}&t={ts}" if "?" in config.WEBAPP_MANUALE_CANDIDATI_URL else f"{config.WEBAPP_MANUALE_CANDIDATI_URL}?t={ts}"
    url_datori = f"{config.WEBAPP_MANUALE_DATORI_URL}&t={ts}" if "?" in config.WEBAPP_MANUALE_DATORI_URL else f"{config.WEBAPP_MANUALE_DATORI_URL}?t={ts}"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Apri Guida Interattiva Candidati", web_app=WebAppInfo(url=url_candidati))],
        [InlineKeyboardButton("🏪 Apri Guida Interattiva Datori", web_app=WebAppInfo(url=url_datori))]
    ])

    msg = (
        "📚 *MANUALI D'USO E GUIDE UFFICIALI*\n\n"
        "📎 Ti abbiamo inviato i due file PDF scaricabili qui sopra!\n\n"
        "Puoi anche consultare la versione interattiva cliccando sui pulsanti in basso."
    )
    await send_smart_reply(update, context, msg, reply_markup=reply_markup, deep_link_arg="guida")



async def cmd_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /match [testo] — analizza il testo e mostra i candidati in target."""
    if not is_admin(update.effective_user.id):
        return

    text = " ".join(context.args) if context.args else get_text(update.message)
    if not text:
        await update.message.reply_text("Uso: `/match Cerco barista con esperienza in centro`", parse_mode=ParseMode.MARKDOWN)
        return

    import matcher
    details = matcher.extract_job_details(text)
    candidates = matcher.get_matching_candidates(text, min_score=40)

    roles = ", ".join(details["roles"]) if details["roles"] else "Tutti"
    zones = ", ".join(details["zones"]) if details["zones"] else "Tutta Torino"

    cand_list = ""
    for c in candidates[:10]:
        cand_list += f"• @{c['username'] or c['first_name']} (Match: *{c['match_score']}%*)\n"

    if not cand_list:
        cand_list = "Nessun candidato trovato col punteggio minimo."

    msg = (
        f"🎯 *ANALISI MATCHING*\n\n"
        f"💼 *Ruoli identificati:* {roles}\n"
        f"📍 *Zone identificate:* {zones}\n\n"
        f"👥 *Candidati in Target trovati ({len(candidates)} totali):*\n{cand_list}"
    )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)



async def on_link_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce approvazione/rifiuto link da parte dell'admin (bottoni inline)."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    action  = parts[0]        # link_approve o link_reject
    chat_id = int(parts[1])
    msg_id  = int(parts[2])
    user_id = int(parts[3])

    if action == "link_approve":
        await query.edit_message_text(
            "✅ *Link approvato* — il messaggio rimane nel gruppo.",
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info(f"✅ Admin ha approvato link (msg {msg_id})")

    elif action == "link_reject":
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.warning(f"Impossibile eliminare msg {msg_id}: {e}")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=config.SPAM_LINK_MESSAGE.format(admin_username=config.ADMIN_USERNAME),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass
        await query.edit_message_text(
            "🚫 *Link rifiutato* — messaggio eliminato dal gruppo.",
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info(f"🚫 Admin ha rifiutato link (msg {msg_id})")


# ─── WebApp & Profilo Candidato ─────────────────────────────────────────────

async def cmd_registrati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /registrati — apre la Telegram WebApp per registrare o modificare il profilo candidato."""
    user = update.effective_user
    webapp_user_url = f"{config.WEBAPP_URL}&user_id={user.id}" if "?" in config.WEBAPP_URL else f"{config.WEBAPP_URL}?user_id={user.id}"

    reply_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🍸 Apri Scheda Profilo & Skill", web_app=WebAppInfo(url=webapp_user_url))]],
        resize_keyboard=True
    )
    msg = (
        "💼 *REGISTRAZIONE & MODIFICA PROFILO CANDIDATO*\n\n"
        "Crea o modifica la tua scheda profilo e aggiungi/rimuovi le tue skill Horeca su misura per Torino!\n\n"
        "Clicca sul pulsante in basso per aprire la scheda:"
    )
    await send_smart_reply(update, context, msg, reply_markup=reply_keyboard, deep_link_arg="registrati")



async def cmd_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /premium — info ed attivazione abbonamento Premium con bottoni di pagamento."""
    user = update.effective_user
    is_prem = db.is_user_premium(user.id)
    profile = db.get_candidate_profile(user.id)

    status_str = "⭐ *ATTIVO (Candidato Verificato)*" if is_prem else "⚪ *BASE (Gratuito)*"

    until_str = ""
    if is_prem and profile and profile.get("premium_until"):
        try:
            until_dt = datetime.fromisoformat(profile["premium_until"])
            until_str = f"\n📅 *Scadenza:* {until_dt.strftime('%d/%m/%Y')}"
        except Exception:
            pass

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌟 Paga 100 Telegram Stars (2,19€)", callback_data="pay_stars")],
        [InlineKeyboardButton("💳 Paga 2,19€ con Carta / Stripe", callback_data="pay_stripe")],
        [InlineKeyboardButton("💬 Paga con Satispay / PayPal (Admin)", url="https://t.me/marcogiuridio")]
    ])

    msg = (
        f"💎 *SERVIZIO CANDIDATO PREMIUM*\n\n"
        f"Stato attuale: {status_str}{until_str}\n\n"
        f"🏆 *VANTAGGI ESCLUSIVI PREMIUM:*\n"
        f"⚡ *Notifiche Push Istantanee*: Ricevi in privato gli avvisi con il **contatto diretto del titolare** (@username / telefono) appena viene pubblicato un annuncio in target!\n"
        f"⭐ *Posizionamento in Cima*: Il tuo profilo compare in **prima posizione** quando i bar cercano personale a Torino.\n"
        f"📄 *Invio CV in PDF*: Sblocca il caricamento del tuo CV in formato PDF.\n"
        f"🏷️ *Badge Verificato*: Distintivo di massima serietà.\n\n"
        f"💰 *Costo:* soli *2,19€ / mese*\n\n"
        f"👇 Scegli la modalità di pagamento che preferisci:"
    )

    await send_smart_reply(update, context, msg, reply_markup=keyboard, deep_link_arg="premium")


async def on_candidate_redirect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i pulsanti inviati dopo la rimozione di una ricerca lavoro."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if query.data in ("candidate_register", "candidate_profile"):
        webapp_user_url = f"{config.WEBAPP_URL}&user_id={user.id}" if "?" in config.WEBAPP_URL else f"{config.WEBAPP_URL}?user_id={user.id}"
        label = "✏️ Apri e aggiorna il profilo" if query.data == "candidate_profile" else "✅ Crea il profilo gratuito"
        await context.bot.send_message(
            chat_id=user.id,
            text="Apri la scheda candidato per completare o aggiornare ruoli, competenze, zone e disponibilità.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(label, web_app=WebAppInfo(url=webapp_user_url))
            ]]),
        )
        return

    if query.data == "candidate_premium":
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "⭐ Candidato Premium — 2,19 € al mese\n\n"
                "Ricevi in privato le offerte compatibili e il tuo profilo viene mostrato prima ai titolari.\n\n"
                "Usa /premium per vedere i metodi di attivazione."
            ),
        )


async def on_payment_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i bottoni di pagamento per Telegram Stars e Stripe."""
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id

    if data == "pay_stars":
        title = "Candidato Premium Horeca (30 Giorni)"
        description = "Notifiche push istantanee con contatti diretti dei datori a Torino!"
        payload = "premium_subscription_stars"
        currency = "XTR"
        prices = [LabeledPrice("Abbonamento Premium 30 giorni", 100)]

        try:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # Vuoto per Telegram Stars
                currency=currency,
                prices=prices,
            )
        except Exception as e:
            logger.error(f"Errore invio fattura Stars: {e}")
            await query.message.reply_text("❌ Errore durante l'invio della fattura Telegram Stars. Riprova più tardi.")

    elif data == "pay_stripe":
        stripe_token = config.STRIPE_PROVIDER_TOKEN
        if not stripe_token:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 Contatta Admin @marcogiuridio", url="https://t.me/marcogiuridio")],
                [InlineKeyboardButton("💬 Contatta Admin @banu80", url="https://t.me/banu80")]
            ])
            await query.message.reply_text(
                "💳 Per pagare via Satispay, PayPal o Carte di Credito, contatta direttamente gli admin:",
                reply_markup=kb
            )
            return

        title = "Candidato Premium Horeca (30 Giorni)"
        description = "Notifiche push istantanee con contatti diretti dei datori a Torino!"
        payload = "premium_subscription_stripe"
        currency = "EUR"
        prices = [LabeledPrice("Abbonamento Premium 30 giorni", 219)] # 219 centesimi = 2,19€


        try:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token=stripe_token,
                currency=currency,
                prices=prices,
            )
        except Exception as e:
            logger.error(f"Errore invio fattura Stripe: {e}")
            await query.message.reply_text("❌ Errore invio fattura Stripe. Contatta l'admin per pagare via PayPal/Satispay.")


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Risponde alla verifica pre-checkout del pagamento."""
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce l'avvenuto pagamento automatico per candidati o annunci datori."""
    user = update.effective_user
    payment_info = update.message.successful_payment
    payload = payment_info.invoice_payload

    # SE È UN ANNUNCIO DI LAVORO A PAGAMENTO (250 o 500 STELLE)
    if payload.startswith("job_offer_") or "pending_job" in context.user_data:
        job = None
        job_id = None

        if payload.startswith("job_offer_id_"):
            try:
                job_id_val = int(payload.replace("job_offer_id_", ""))
                job_db = db.get_job_offer(job_id_val)
                if job_db:
                    db.verify_job_offer(job_id_val)
                    job_id = job_id_val
                    job = {
                        "pkg": job_db["package"],
                        "business": job_db["business_name"],
                        "role": job_db["role"],
                        "zone": job_db["zone"],
                        "shift": job_db["shift"],
                        "salary": job_db["salary"],
                        "desc": job_db["description"],
                        "contact": job_db["contact"]
                    }
            except Exception as e:
                logger.warning(f"Errore parsing job_offer_id: {e}")

        if not job:
            job = context.user_data.get("pending_job", {})

        pkg = job.get("pkg", "evidenza")
        business = job.get("business", "BAR / LOCALE TORINO")
        role = job.get("role", "")
        zone = job.get("zone", "")
        shift = job.get("shift", "")
        salary = job.get("salary", "")
        desc = job.get("desc", "")
        contact = job.get("contact", "")

        if pkg == "evidenza":
            header = "🔝 *OFFERTA IN EVIDENZA (SPONSOR 24H)* 🔝"
        elif pkg == "vip":
            header = "👑 *SPONSOR VIP (7 GIORNI IN CIMA)* 👑"
        elif pkg == "vip_mensile":
            header = "💎 *SPONSOR VIP MENSILE (30 GIORNI IN CIMA)* 💎"
        else:
            header = "📢 *OFFERTA DI LAVORO*"

        post_text = (
            f"{header}\n\n"
            f"🏪 *LOCALE:* {business.upper()}\n"
            f"💼 *Ruolo Cercato:* {role}\n"
            f"📍 *Zona:* {zone}\n"
            f"⏰ *Turni:* {shift}\n"
            f"💰 *Paga:* {salary if salary else 'Trattabile'}\n\n"
            f"📝 *Descrizione & Requisiti:*\n_{desc}_\n\n"
            f"📞 *Contatto Candidature:* {contact}\n"
            f"👤 *Pubblicato da:* @{user.username if user.username else user.first_name}"
        )

        if not job_id:
            job_id = db.create_job_offer(
                user_id=user.id,
                username=user.username or "",
                business_name=business,
                role=role,
                zone=zone,
                shift=shift,
                salary=salary,
                description=desc,
                contact=contact,
                package=pkg,
                is_verified=1
            )


        msg_id = None
        if config.GROUP_ID != 0:
            try:
                pub_msg = await context.bot.send_message(
                    chat_id=config.GROUP_ID,
                    text=post_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                msg_id = pub_msg.message_id
                db.update_job_offer_message_id(job_id, msg_id)
                # Fissa il post in cima al gruppo (Pin)
                try:
                    await context.bot.pin_chat_message(
                        chat_id=config.GROUP_ID,
                        message_id=pub_msg.message_id
                    )
                except Exception as pe:
                    logger.warning(f"Impossibile fissare post in cima: {pe}")

                import matcher
                # 1. Notifica PUSH ai candidati Premium con tasto Candidati 1-Click
                await matcher.notify_matched_candidates(context.bot, post_text, user.username or "", pub_msg.message_id, job_id=job_id)

                # 2. Rapporto candidati (Premium in cima + Free) inviato in privato al datore di lavoro
                await matcher.send_employer_candidates_report(context.bot, user.id, post_text)
            except Exception as e:
                logger.error(f"Errore pubblicazione offerta a pagamento: {e}")

        # Pulisci pending_job
        context.user_data.pop("pending_job", None)

        dash_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Apri Dashboard Candidati (Mini-App)", web_app=WebAppInfo(url=f"{config.WEBAPP_DASHBOARD_URL}?job_id={job_id}"))]
        ])

        await update.message.reply_text(
            "🎉 *PAGAMENTO RICEVUTO CON SUCCESSO!*\n\n"
            "Il tuo annuncio in evidenza è stato pubblicato, **fissato in cima al gruppo** e notificato in privato ai candidati Premium!\n\n"
            "📋 *Ti abbiamo inviato qui sopra il Rapporto Completo dei Candidati compatibili a Torino.*\n"
            "Puoi anche aprire la tua **Dashboard Candidati riservata nella Mini-App** col pulsante qui sotto:",
            reply_markup=dash_kb,
            parse_mode=ParseMode.MARKDOWN
        )


    # SE È UN ABBONAMENTO CANDIDATO PREMIUM (100 STELLE / 2,19€)
    else:
        new_date = db.make_user_premium(user.id, days=30)
        logger.info(f"🎉 Pagamento completato da {user.first_name} ({user.id})! Premium attivo fino al {new_date}")

        msg = (
            f"🎉 *PAGAMENTO RICEVUTO CON SUCCESSO!*\n\n"
            f"Il tuo account è stato aggiornato a *CANDIDATO PREMIUM* fino al *{new_date}*!\n\n"
            f"✨ *Da ora sei attivo:* riceverai in tempo reale le notifiche push in privato con i contatti diretti (@username o numero di telefono) dei datori di lavoro di Torino appena pubblicano un'offerta!"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ─── Pre-Screening & Candidate Applications ───────────────────────────────────

async def on_candidate_apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inizia il flusso di Pre-screening quando il candidato clicca su 'Candidati Ora in 1-Click'."""
    query = update.callback_query
    await query.answer()
    job_id = int(query.data.split(":")[1])

    user = update.effective_user
    profile = db.get_candidate_profile(user.id)
    if not profile:
        await query.message.reply_text(
            "❌ Non hai ancora registrato il tuo profilo candidato!\n"
            "Usa il comando `/registrati` per registrarlo in 1 minuto prima di candidarti.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    context.user_data[f"app_flow_{job_id}"] = {"job_id": job_id}

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Sì, Disponibile Subito", callback_data=f"apply_q1:{job_id}:Disponibile")],
        [InlineKeyboardButton("⚠️ Da Concordare col Titolare", callback_data=f"apply_q1:{job_id}:Da Concordare")]
    ])

    await query.message.reply_text(
        "📝 *PRE-SCREENING CANDIDATURA (Passo 1 di 2)*\n\n"
        "❓ *Confermi la tua disponibilità per la zona e gli orari indicati nell'annuncio?*",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )


async def on_candidate_apply_q1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve la risposta alla Domanda 1 di Pre-screening."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    job_id = int(parts[1])
    ans_q1 = parts[2]

    flow = context.user_data.get(f"app_flow_{job_id}", {})
    flow["q1"] = ans_q1
    context.user_data[f"app_flow_{job_id}"] = flow

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Sì, HACCP Valido / Requisiti OK", callback_data=f"apply_q2:{job_id}:HACCP OK")],
        [InlineKeyboardButton("⏳ In Corso / Da Rinnovare", callback_data=f"apply_q2:{job_id}:HACCP Da Rinnovare")]
    ])

    await query.message.reply_text(
        "📝 *PRE-SCREENING CANDIDATURA (Passo 2 di 2)*\n\n"
        "❓ *Possiedi l'attestato HACCP e/o le certificazioni richieste per la ristorazione?*",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )


async def on_candidate_apply_q2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve la risposta alla Domanda 2 di Pre-screening e chiede l'invio finale."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    job_id = int(parts[1])
    ans_q2 = parts[2]

    flow = context.user_data.get(f"app_flow_{job_id}", {})
    flow["q2"] = ans_q2
    context.user_data[f"app_flow_{job_id}"] = flow

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Invia Candidatura Ufficiale al Titolare", callback_data=f"apply_submit:{job_id}")]
    ])

    await query.message.reply_text(
        "🎯 *PRE-SCREENING COMPLETATO!*\n\n"
        "Clicca sul pulsante qui sotto per trasmettere la tua candidatura ufficiale direttamente al datore di lavoro del locale:",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )


async def on_candidate_apply_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trasmette la candidatura completa con Scheda CV al datore di lavoro."""
    query = update.callback_query
    await query.answer()
    job_id = int(query.data.split(":")[1])

    user = update.effective_user
    flow = context.user_data.pop(f"app_flow_{job_id}", {})
    q1 = flow.get("q1", "Disponibile")
    q2 = flow.get("q2", "HACCP OK")

    profile = db.get_candidate_profile(user.id)
    job = db.get_job_offer(job_id)

    if not profile or not job:
        await query.message.reply_text("❌ Si è verificato un errore con l'annuncio. Riprova più tardi.")
        return

    is_prem = db.is_user_premium(user.id)

    import matcher
    job_details = matcher.extract_job_details(job["description"] or "")
    score = matcher.calculate_match_score(profile, job_details)

    app_id = db.save_application(
        job_id=job_id,
        candidate_id=user.id,
        candidate_user=user.username or user.first_name,
        match_score=score,
        screening_q1=q1,
        screening_q2=q2,
        screening_notes="Candidatura inoltrata via Pre-Screening Telegram Bot"
    )

    employer_user_id = job["user_id"]
    status_badge = "⭐ CANDIDATO PREMIUM" if is_prem else "⚪ UTENTE BASE"

    roles = ", ".join(json.loads(profile["roles"])) if profile["roles"] else "N/D"
    skills = ", ".join(json.loads(profile["skills"])) if profile["skills"] else "N/D"

    # SCHEDA CANDIDATO CV GENERATA PER IL TITOLARE
    cv_card = (
        f"🌟 *NUOVA CANDIDATURA INOLTRATA PER {job['business_name'].upper()}!*\n\n"
        f"💼 *Ruolo Cercato:* {job['role']}\n"
        f"👤 *Candidato:* {profile['first_name']} (@{profile['username'] or 'N/D'})\n"
        f"🏷️ *Status:* {status_badge} (Affinità Match: *{score}%*)\n\n"
        f"📋 *SCHEDA PROFILO & COMPETENZE:*\n"
        f"• *Esperienza:* {profile['experience'] or 'N/D'}\n"
        f"• *Ruoli:* {roles}\n"
        f"• *Skill:* {skills}\n"
        f"• *Telefono:* {profile['phone'] or 'Non fornito'}\n\n"
        f"✅ *RISPOSTE PRE-SCREENING:*\n"
        f"• Disponibilità Turni: *{q1}*\n"
        f"• HACCP & Requisiti: *{q2}*"
    )

    btn_contact = InlineKeyboardButton("💬 Scrivi su Telegram", url=f"https://t.me/{profile['username']}") if profile['username'] else InlineKeyboardButton("📱 Chiama", url=f"tel:{profile['phone']}")

    employer_kb = InlineKeyboardMarkup([
        [
            btn_contact,
            InlineKeyboardButton("✅ Convoca a Colloquio", callback_data=f"app_status:{app_id}:interview")
        ],
        [InlineKeyboardButton("❌ Non Idoneo", callback_data=f"app_status:{app_id}:rejected")]
    ])

    try:
        await context.bot.send_message(
            chat_id=employer_user_id,
            text=cv_card,
            reply_markup=employer_kb,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Errore invio candidatura a titolare {employer_user_id}: {e}")

    await query.message.reply_text(
        "🎉 *CANDIDATURA INVIATA CON SUCCESSO!*\n\n"
        "La tua scheda profilo e le risposte del pre-screening sono state trasmesse direttamente al titolare del locale su Telegram!\n"
        "Se il tuo profilo verrà selezionato, verrai contattato a breve per il colloquio.",
        parse_mode=ParseMode.MARKDOWN
    )


async def on_employer_app_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce la decisione del titolare (Convoca a Colloquio / Rifiuta) e notifica il candidato."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    app_id = int(parts[1])
    new_status = parts[2]

    db.update_application_status(app_id, new_status)

    if new_status == "interview":
        await query.edit_message_text(
            query.message.text + "\n\n🟢 *STATO: CANDIDATO CONVOCATO A COLLOQUIO*",
            parse_mode=ParseMode.MARKDOWN
        )

        # Invia notifica automatica in privato al candidato
        try:
            with db.get_conn() as conn:
                app_info = conn.execute("""
                    SELECT a.candidate_id, j.business_name, j.role, j.username as employer_user
                    FROM applications a
                    JOIN job_offers j ON a.job_id = j.job_id
                    WHERE a.app_id = ?
                """, (app_id,)).fetchone()

                if app_info:
                    cand_id = app_info["candidate_id"]
                    biz_name = app_info["business_name"]
                    role_name = app_info["role"]
                    emp_user = app_info["employer_user"]
                    emp_ref = f"@{emp_user}" if emp_user else "il titolare del locale"

                    msg_cand = (
                        f"🎉 *SPLENDIDA NOTIZIA! SEI STATO SELEZIONATO PER UN COLLOQUIO!*\n\n"
                        f"🏪 *Locale:* {biz_name}\n"
                        f"💼 *Ruolo:* {role_name}\n\n"
                        f"Il titolare del locale ha esaminato la tua candidatura ed è interessato al tuo profilo!\n"
                        f"Ti contatteranno a breve oppure puoi scrivergli subito su Telegram: {emp_ref}"
                    )
                    await context.bot.send_message(chat_id=cand_id, text=msg_cand, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Impossibile notificare candidato per colloquio: {e}")

    elif new_status == "rejected":
        await query.edit_message_text(
            query.message.text + "\n\n🔴 *STATO: CANDIDATURA ARCHIVIATA / NON IDONEA*",
            parse_mode=ParseMode.MARKDOWN
        )





async def cmd_grant_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando Admin: /grant_premium USER_ID [GIORNI] — assegna Premium manualmente."""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Uso: `/grant_premium USER_ID [GIORNI]`\nEs: `/grant_premium 21773014 30`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_user_id = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else 30
        new_date = db.make_user_premium(target_user_id, days=days)

        await update.message.reply_text(f"✅ Stato Premium attivato per user_id `{target_user_id}` fino al *{new_date}*!", parse_mode=ParseMode.MARKDOWN)

        # Notifica l'utente in privato
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 *CONGRATULAZIONI!* Il tuo account è stato aggiornato a *CANDIDATO PREMIUM* fino al *{new_date}*!\n\nDa ora riceverai tutte le notifiche di lavoro in target in tempo reale con i contatti diretti dei datori!",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def cmd_profilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /profilo — mostra il profilo candidato salvato."""
    user = update.effective_user
    profile = db.get_candidate_profile(user.id)
    is_prem = db.is_user_premium(user.id)

    status_badge = "⭐ *CANDIDATO PREMIUM*" if is_prem else "⚪ *UTENTE BASE (Gratuito)*"

    if not profile:
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📝 Crea Profilo Ora", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
            resize_keyboard=True
        )
        msg_empty = (
            f"❌ Non hai ancora registrato il tuo profilo candidato!\n\n"
            f"Stato attuale: {status_badge}\n"
            f"Clicca sul pulsante qui sotto per crearlo in 1 minuto:"
        )
        await send_smart_reply(update, context, msg_empty, reply_markup=keyboard, deep_link_arg="registrati")
        return

    roles = ", ".join(json.loads(profile["roles"])) if profile["roles"] else "Non specificato"
    skills = ", ".join(json.loads(profile["skills"])) if profile["skills"] else "Nessuna"
    zones = ", ".join(json.loads(profile["zones"])) if profile["zones"] else "Tutta Torino"
    avail = ", ".join(json.loads(profile["availability"])) if profile["availability"] else "Non specificata"

    edit_url = f"{config.WEBAPP_URL}&user_id={user.id}" if "?" in config.WEBAPP_URL else f"{config.WEBAPP_URL}?user_id={user.id}"

    msg = (
        f"👤 *IL TUO PROFILO CANDIDATO HORECA*\n"
        f"Stato: {status_badge}\n\n"
        f"💼 *Ruoli:* {roles}\n"
        f"⚡ *Skill:* {skills}\n"
        f"⏳ *Esperienza:* {profile['experience'] or 'N/D'}\n"
        f"⏰ *Disponibilità:* {avail}\n"
        f"📍 *Zone preferite:* {zones}\n"
        f"📱 *Telefono:* {profile['phone'] or 'Non fornito'}\n"
        f"📝 *Note:* {profile['bio'] or 'Nessuna'}\n\n"
        f"💡 *Vuoi aggiungere nuove skill o modificare i tuoi dati? Clicca il tasto qui sotto:*"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Modifica Scheda & Skill (Mini-App)", web_app=WebAppInfo(url=edit_url))],
        [InlineKeyboardButton("⭐ Passa a Premium (2,19€)", callback_data="pay_stars")]
    ])

    await send_smart_reply(update, context, msg, reply_markup=keyboard, deep_link_arg="profilo")







async def cmd_pubblica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /pubblica — apre il form di pubblicazione per datori di lavoro."""
    import time
    ts = int(time.time())
    base_url = config.WEBAPP_PUBBLICA_URL
    fresh_url = f"{base_url}&t={ts}" if "?" in base_url else f"{base_url}?t={ts}"

    reply_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📢 Apri Modulo Pubblicazione Offerta", web_app=WebAppInfo(url=fresh_url))]],
        resize_keyboard=True
    )
    msg = (
        "💼 *PUBBLICA UN'OFFERTA DI LAVORO HORECA*\n\n"
        "Trova subito personale qualificato (Baristi, Camerieri, Cuochi, Pizzaioli) a Torino!\n\n"
        "Puoi scegliere tra:\n"
        "• 🆓 *Annuncio Gratuito (0€)*\n"
        "• ⭐ *In Evidenza 24h (250 Stelle / 5,39€)* — Post 🔝 + Pin 24h + Push ai candidati!\n"
        "• 👑 *Sponsor VIP 7 Giorni (500 Stelle / 10,90€)* — Pin 7d + 🚀 *Auto-Bump ogni 3h* + Multi-Push!\n"
        "• 💎 *Pass VIP Mensile (1400 Stelle / 29,90€)* — Pin 30d + 🚀 *Auto-Bump ogni 3h per 1 mese* + Post illimitati!\n\n"
        "Clicca sul pulsante qui sotto per aprire il modulo di compilazione:"
    )
    await send_smart_reply(update, context, msg, reply_markup=reply_keyboard, deep_link_arg="pubblica")


async def on_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve i dati inviati dalla Telegram WebApp."""
    user = update.effective_user
    data_str = update.effective_message.web_app_data.data

    try:
        data = json.loads(data_str)
        action = data.get("action")

        if action == "save_candidate_profile":
            roles = json.dumps(data.get("roles", []))
            skills = json.dumps(data.get("skills", []))
            experience = data.get("experience", "")
            availability = json.dumps(data.get("availability", []))
            zones = json.dumps(data.get("zones", []))
            phone = data.get("phone", "")
            bio = data.get("bio", "")

            db.save_candidate_profile(
                user_id=user.id,
                username=user.username or "",
                first_name=user.first_name or "",
                roles=roles,
                skills=skills,
                experience=experience,
                availability=availability,
                zones=zones,
                phone=phone,
                bio=bio
            )

            logger.info(f"✅ Profilo candidato salvato per user_id {user.id} (@{user.username})")

            await update.effective_message.reply_text(
                "🎉 *PROFILO SALVATO CON SUCCESSO!*\n\n"
                "Le tue preferenze e competenze sono state registrate nel sistema.\n"
                "Ora riceverai notifiche mirate quando vengono pubblicati annunci in target con il tuo profilo a Torino!\n\n"
                "Per rivedere i tuoi dati in qualsiasi momento scrivi `/profilo`.",
                parse_mode=ParseMode.MARKDOWN
            )

        elif action == "publish_job_offer":
            pkg = data.get("package", "free")
            business = data.get("business_name", "").strip()
            role = data.get("role", "").strip()
            zone = data.get("zone", "").strip()
            shift = data.get("shift", "").strip()
            salary = data.get("salary", "").strip()
            desc = data.get("description", "").strip()
            contact = data.get("contact", "").strip()

            job_details = {
                "user_id": user.id,
                "username": user.username or "",
                "business": business,
                "role": role,
                "zone": zone,
                "shift": shift,
                "salary": salary,
                "desc": desc,
                "contact": contact,
                "pkg": pkg
            }

            if pkg == "free":
                job_id = db.create_job_offer(
                    user_id=user.id,
                    username=user.username or "",
                    business_name=business,
                    role=role,
                    zone=zone,
                    shift=shift,
                    salary=salary,
                    description=desc,
                    contact=contact,
                    package="free",
                    is_verified=0
                )

                post_text = (
                    f"📢 *OFFERTA DI LAVORO — {business.upper()}*\n\n"
                    f"💼 *Ruolo Cercato:* {role}\n"
                    f"📍 *Zona:* {zone}\n"
                    f"⏰ *Turni:* {shift}\n"
                    f"💰 *Paga:* {salary if salary else 'Trattabile'}\n\n"
                    f"📝 *Descrizione & Requisiti:*\n_{desc}_\n\n"
                    f"📞 *Contatto Candidature:* {contact}\n"
                    f"👤 *Pubblicato da:* @{user.username if user.username else user.first_name}"
                )
                if config.GROUP_ID != 0:
                    try:
                        pub_msg = await context.bot.send_message(
                            chat_id=config.GROUP_ID,
                            text=post_text,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        db.update_job_offer_message_id(job_id, pub_msg.message_id)
                    except Exception as e:
                        logger.error(f"Errore pubblicazione gruppo: {e}")

                await update.effective_message.reply_text(
                    "✅ *ANNUNCIO GRATUITO PUBBLICATO!*\n\n"
                    f"Il tuo annuncio `#{job_id}` è stato pubblicato nel gruppo.\n\n"
                    "💡 *Puoi modificarlo o rivederlo in qualsiasi momento digitando `/mie_offerte`!*",
                    parse_mode=ParseMode.MARKDOWN
                )



            elif pkg in ["evidenza", "vip", "vip_mensile"]:
                job_id = db.create_job_offer(
                    user_id=user.id,
                    username=user.username or "",
                    business_name=business,
                    role=role,
                    zone=zone,
                    shift=shift,
                    salary=salary,
                    description=desc,
                    contact=contact,
                    package=pkg,
                    is_verified=0
                )

                context.user_data["pending_job"] = job_details
                if pkg == "evidenza":
                    stars = 250
                    eur_cents = 539
                    pkg_name = "In Evidenza 24h"
                elif pkg == "vip":
                    stars = 500
                    eur_cents = 1090
                    pkg_name = "Sponsor VIP 7 Giorni"
                elif pkg == "vip_mensile":
                    stars = 1400
                    eur_cents = 2990
                    pkg_name = "Pass VIP Mensile (30d)"
                else:
                    stars = 250
                    eur_cents = 539
                    pkg_name = "In Evidenza"

                title = f"Offerta {pkg_name} Horeca"
                description = f"Annuncio {business} ({role} - {zone}) con Pin e Push Broadcast"
                payload = f"job_offer_id_{job_id}"
                currency = "XTR"
                prices = [LabeledPrice(f"Annuncio {pkg_name}", stars)]

                await context.bot.send_invoice(
                    chat_id=user.id,
                    title=title,
                    description=description,
                    payload=payload,
                    provider_token="",  # Telegram Stars
                    currency=currency,
                    prices=prices,
                )

        elif action == "edit_job_offer":
            job_id = data.get("job_id")
            if job_id:
                job_id = int(job_id)
                business = data.get("business_name", "").strip()
                role = data.get("role", "").strip()
                zone = data.get("zone", "").strip()
                shift = data.get("shift", "").strip()
                salary = data.get("salary", "").strip()
                desc = data.get("description", "").strip()
                contact = data.get("contact", "").strip()

                db.update_job_offer(
                    job_id=job_id,
                    business_name=business,
                    role=role,
                    zone=zone,
                    shift=shift,
                    salary=salary,
                    description=desc,
                    contact=contact
                )

                job = db.get_job_offer(job_id)
                if job and job.get("message_id") and config.GROUP_ID != 0:
                    try:
                        pkg = job["package"]
                        if pkg == "evidenza":
                            header = "🔝 *OFFERTA IN EVIDENZA (SPONSOR 24H)* 🔝"
                        elif pkg == "vip":
                            header = "👑 *SPONSOR VIP (7 GIORNI IN CIMA)* 👑"
                        elif pkg == "vip_mensile":
                            header = "💎 *SPONSOR VIP MENSILE (30 GIORNI IN CIMA)* 💎"
                        else:
                            header = "📢 *OFFERTA DI LAVORO*"
                        updated_text = (
                            f"{header}\n\n"
                            f"🏪 *LOCALE:* {business.upper()}\n"
                            f"💼 *Ruolo Cercato:* {role}\n"
                            f"📍 *Zona:* {zone}\n"
                            f"⏰ *Turni:* {shift}\n"
                            f"💰 *Paga:* {salary if salary else 'Trattabile'}\n\n"
                            f"📝 *Descrizione & Requisiti:*\n_{desc}_\n\n"
                            f"📞 *Contatto Candidature:* {contact}\n"
                            f"👤 *Pubblicato da:* @{user.username if user.username else user.first_name}\n"
                            f"✏️ _(Annuncio Aggiornato dal Datore)_"
                        )
                        await context.bot.edit_message_text(
                            chat_id=config.GROUP_ID,
                            message_id=job["message_id"],
                            text=updated_text,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as e_tg:
                        logger.warning(f"Impossibile aggiornare messaggio Telegram per job #{job_id}: {e_tg}")

                await update.effective_message.reply_text(
                    f"✏️ *ANNUNCIO #{job_id} MODIFICATO CON SUCCESSO!*\n\n"
                    "Le modifiche sono state salvate nel database e il messaggio nel gruppo Telegram è stato aggiornato in tempo reale.",
                    parse_mode=ParseMode.MARKDOWN
                )

    except Exception as e:
        logger.error(f"Errore salvataggio dati WebApp: {e}")
        await update.effective_message.reply_text("❌ Si è verificato un errore. Riprova con `/pubblica`.")



async def cmd_test_offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando di test: simula la pubblicazione di un annuncio senza inviare nulla al gruppo pubblico."""
    user = update.effective_user
    username_clean = (user.username or "").lower().replace("@", "").strip()


    job_id = db.create_job_offer(
        user_id=user.id,
        username=user.username or "",
        business_name="Caffè Torino (TEST PRIVATO)",
        role="Barista",
        zone="Centro",
        shift="Full-time",
        salary="1.300€ / mese",
        description="Annuncio di prova riservato per testare il flusso di pre-screening, il report ed la Dashboard Mini-App in privato.",
        contact=f"@{user.username}" if user.username else "Admin",
        package="evidenza",
        is_verified=1
    )

    dash_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Apri Dashboard Candidati (Mini-App)", web_app=WebAppInfo(url=f"{config.WEBAPP_DASHBOARD_URL}?job_id={job_id}"))],
        [InlineKeyboardButton("📩 Simula Candidatura 1-Click (Pre-Screening)", callback_data=f"apply_start:{job_id}")]
    ])

    import matcher
    post_text = "🔝 *OFFERTA DI PROVA IN EVIDENZA (TEST PRIVATO)* 🔝\n\n🏪 *LOCALE:* CAFFÈ TORINO (TEST)\n💼 *Ruolo Cercato:* Barista\n📍 *Zona:* Centro\n⏰ *Turni:* Full-time\n💰 *Paga:* 1.300€ / mese\n\n📝 *Descrizione:* Annuncio di prova per verificare la Dashboard e le candidature."

    # 1. Invia il report candidati in privato all'admin
    await matcher.send_employer_candidates_report(context.bot, user.id, post_text)

    # 2. Invia la scheda di conferma con il tasto Dashboard Mini-App e Tasto Candidati
    await update.message.reply_text(
        "🧪 *TEST PRIVATO AVVIATO (NESSUN MESSAGGIO INVIATO AL GRUPPO)*\n\n"
        f"✅ Creato annuncio di prova #{job_id} per *Caffè Torino (TEST)*!\n\n"
        "📋 Ti abbiamo inviato qui sopra il **Rapporto Candidati** privato.\n"
        "👇 Clicca sui pulsanti qui sotto per testare la **Dashboard Mini-App** e il **Pre-screening 1-Click**:",
        reply_markup=dash_kb,
        parse_mode=ParseMode.MARKDOWN
    )

# ─── CRM Admin: Gestione Titolari & Lavoratori ────────────────────────────────

async def cmd_titolari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando Admin: /titolari — mostra la lista dei titolari/datori di lavoro identificati."""
    if not is_admin(update.effective_user.id):
        return

    counts = db.count_users_by_role()
    top_datori = db.get_users_by_role("datore", limit=30)

    lines = [
        f"🏪 *CRM TITOLARI / DATORI DI LAVORO*\n",
        f"📊 *Datori identificati:* {counts['datori']}",
        f"👨‍🍳 *Lavoratori identificati:* {counts['lavoratori']}",
        f"👥 *Totale nel DB:* {counts['totale']}\n",
        f"👑 *I 30 TITOLARI PIÙ ATTIVI:*\n",
    ]

    for idx, d in enumerate(top_datori, 1):
        name = d["first_name"] or "Utente"
        uname = f" (@{d['username']})" if d["username"] else ""
        cnt = d["offerte_count"] or 0
        lines.append(f"{idx}. *{name}*{uname} — {cnt} offerte")

    lines.append(f"\n💡 _Usa /broadcast\\_titolari \\<messaggio\\> per contattarli tutti in privato_")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_lavoratori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando Admin: /lavoratori — mostra la lista dei lavoratori/candidati identificati."""
    if not is_admin(update.effective_user.id):
        return

    counts = db.count_users_by_role()
    top_lavoratori = db.get_users_by_role("lavoratore", limit=30)

    lines = [
        f"👨‍🍳 *CRM LAVORATORI / CANDIDATI*\n",
        f"👨‍🍳 *Lavoratori identificati:* {counts['lavoratori']}",
        f"🏪 *Datori identificati:* {counts['datori']}",
        f"👥 *Totale nel DB:* {counts['totale']}\n",
        f"🔝 *I 30 LAVORATORI PIÙ ATTIVI:*\n",
    ]

    for idx, d in enumerate(top_lavoratori, 1):
        name = d["first_name"] or "Utente"
        uname = f" (@{d['username']})" if d["username"] else ""
        lines.append(f"{idx}. *{name}*{uname}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)



def parse_json_arr(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        res = json.loads(val)
        return res if isinstance(res, list) else [str(res)]
    except Exception:
        return [str(val)]


async def cmd_candidati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando Admin: /candidati — mostra l'elenco di tutti gli utenti che hanno compilato il profilo candidato nel bot."""
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("❌ Questo comando è riservato agli amministratori.")
        return

    cands = db.get_all_candidates(limit=50)
    if not cands:
        await update.message.reply_text(
            "📋 *Nessun profilo candidato registrato nel database.*",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    dash_url = f"{config.WEBAPP_DASHBOARD_URL}&user_id={user.id}" if "?" in config.WEBAPP_DASHBOARD_URL else f"{config.WEBAPP_DASHBOARD_URL}?user_id={user.id}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Apri Dashboard Candidati Completa", web_app=WebAppInfo(url=dash_url))]
    ])

    await update.message.reply_text(
        f"👨‍🍳 *PANNELLO ADMIN — {len(cands)} CANDIDATI REGISTRATI CON PROFILO:*",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN
    )

    for c in cands:
        uname = f"@{c['username']}" if c["username"] else f"ID `{c['user_id']}`"
        name = c["first_name"] or "Candidato"
        is_prem = db.is_user_premium(c["user_id"])
        badge = "⭐ *PREMIUM*" if is_prem else "⚪ *BASE*"

        roles_list = parse_json_arr(c["roles"])
        skills_list = parse_json_arr(c["skills"])

        roles = ", ".join(roles_list) if roles_list else "Non specificato"
        skills = ", ".join(skills_list) if skills_list else "Nessuna"
        phone = c["phone"] or "Non specificato"

        msg = (
            f"👤 *{name}* ({uname}) — {badge}\n"
            f"💼 *Ruoli:* {roles}\n"
            f"⚡ *Skill:* {skills}\n"
            f"⏳ *Esperienza:* {c['experience'] or 'N/D'}\n"
            f"📱 *Tel:* `{phone}`"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)



async def cmd_broadcast_titolari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando Admin: /broadcast_titolari <messaggio> — invia un messaggio promozionale in privato a tutti i titolari."""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "📢 *Uso:* `/broadcast_titolari <messaggio>`\n\n"
            "Esempio:\n"
            "`/broadcast_titolari 🔝 Ciao! Vuoi mettere il tuo annuncio IN EVIDENZA per 24h a soli 5,39€? Rispondi a questo messaggio per info!`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    message_text = " ".join(context.args)
    datori_ids = db.get_all_datori_ids()

    await update.message.reply_text(
        f"📢 *Broadcast avviato verso {len(datori_ids)} titolari...*\n"
        f"⏳ Questo potrebbe richiedere qualche minuto.",
        parse_mode=ParseMode.MARKDOWN
    )

    sent = 0
    failed = 0
    for uid in datori_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN
            )
            sent += 1
        except Exception:
            failed += 1

        # Rispetta rate limit Telegram (30 msg/sec max)
        if sent % 25 == 0:
            import asyncio
            await asyncio.sleep(1.5)

    await update.message.reply_text(
        f"✅ *Broadcast completato!*\n\n"
        f"📬 Inviati con successo: *{sent}*\n"
        f"❌ Non recapitati (bot non avviato): *{failed}*\n"
        f"📊 Totale destinatari: *{len(datori_ids)}*",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_mie_offerte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra le offerte pubblicate dallo specifico datore di lavoro."""
    user = update.effective_user
    offers = db.get_user_job_offers(user.id, user.username or "")

    if not offers:
        await update.message.reply_text(
            "📋 *Nessuna offerta registrata a tuo nome.*\n\n"
            "Puoi pubblicare una nuova offerta di lavoro in 30 secondi con il comando `/pubblica`!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await update.message.reply_text(f"📋 *LE TUE OFFERTE DI LAVORO REGISTRATE* ({len(offers)} totali):", parse_mode=ParseMode.MARKDOWN)

    for job in offers:
        job_id = job["job_id"]
        business = job["business_name"]
        role = job["role"]
        pkg = job["package"]
        created = job["created_at"]

        edit_url = f"{config.WEBAPP_PUBBLICA_URL}&edit_job_id={job_id}&user_id={user.id}" if "?" in config.WEBAPP_PUBBLICA_URL else f"{config.WEBAPP_PUBBLICA_URL}?edit_job_id={job_id}&user_id={user.id}"
        dash_url = f"{config.WEBAPP_DASHBOARD_URL}&job_id={job_id}&user_id={user.id}" if "?" in config.WEBAPP_DASHBOARD_URL else f"{config.WEBAPP_DASHBOARD_URL}?job_id={job_id}&user_id={user.id}"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Modifica Annuncio (Mini-App)", web_app=WebAppInfo(url=edit_url))],
            [InlineKeyboardButton("📊 Dashboard Candidati", web_app=WebAppInfo(url=dash_url))]
        ])

        msg = (
            f"🏪 *{business.upper()}*\n"
            f"💼 Ruolo: *{role}* | Pacchetto: *{pkg.upper()}*\n"
            f"📅 Data: {created}\n"
            f"🆔 ID Annuncio: `#{job_id}`"
        )
        await update.message.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


async def cmd_edit_offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando Admin: /edit_offerta JOB_ID — permette all'admin di modificare qualsiasi annuncio."""
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("❌ Questo comando è riservato agli amministratori.")
        return

    if not context.args:
        await update.message.reply_text("Uso Admin: `/edit_offerta JOB_ID`\nEs: `/edit_offerta 1`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        job_id = int(context.args[0])
        job = db.get_job_offer(job_id)
        if not job:
            await update.message.reply_text(f"❌ Annuncio #{job_id} non trovato nel database.")
            return

        edit_url = f"{config.WEBAPP_PUBBLICA_URL}&edit_job_id={job_id}&user_id={user.id}" if "?" in config.WEBAPP_PUBBLICA_URL else f"{config.WEBAPP_PUBBLICA_URL}?edit_job_id={job_id}&user_id={user.id}"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Modifica Annuncio come Admin", web_app=WebAppInfo(url=edit_url))]
        ])

        msg = (
            f"🛠️ *PANNELLO MODIFICA ADMIN ANNUNCIO #{job_id}*\n\n"
            f"🏪 *Locale:* {job['business_name']}\n"
            f"💼 *Ruolo:* {job['role']}\n"
            f"👤 *Datore:* @{job['username']} (`ID: {job['user_id']}`)\n\n"
            f"Clicca sul pulsante qui sotto per modificare l'annuncio in tempo reale:"
        )
        await update.message.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def cmd_offerte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando Admin: /offerte — mostra l'elenco di tutte le ultime offerte pubblicate nel DB con pulsante modifica."""
    user = update.effective_user
    if not is_admin(user):
        await update.message.reply_text("❌ Questo comando è riservato agli amministratori.")
        return

    all_jobs = db.get_all_job_offers(limit=20)
    if not all_jobs:
        await update.message.reply_text("📋 Nessuna offerta di lavoro trovata nel database.")
        return

    await update.message.reply_text(f"📋 *PANNELLO ADMIN — ULTIME {len(all_jobs)} OFFERTE PUBBLICATE:*", parse_mode=ParseMode.MARKDOWN)

    for job in all_jobs:
        job_id = job["job_id"]
        business = job["business_name"]
        role = job["role"]
        pkg = job["package"]
        created = job["created_at"]
        uname = f"@{job['username']}" if job["username"] else f"ID {job['user_id']}"

        edit_url = f"{config.WEBAPP_PUBBLICA_URL}&edit_job_id={job_id}&user_id={user.id}" if "?" in config.WEBAPP_PUBBLICA_URL else f"{config.WEBAPP_PUBBLICA_URL}?edit_job_id={job_id}&user_id={user.id}"
        dash_url = f"{config.WEBAPP_DASHBOARD_URL}&job_id={job_id}&user_id={user.id}" if "?" in config.WEBAPP_DASHBOARD_URL else f"{config.WEBAPP_DASHBOARD_URL}?job_id={job_id}&user_id={user.id}"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Modifica Annuncio come Admin", web_app=WebAppInfo(url=edit_url))],
            [InlineKeyboardButton("📊 Dashboard Candidati", web_app=WebAppInfo(url=dash_url))]
        ])

        msg = (
            f"🆔 *JOB ID: `#{job_id}`*\n"
            f"🏪 *Locale:* {business}\n"
            f"💼 *Ruolo:* {role} | Pacchetto: *{pkg.upper()}*\n"
            f"👤 *Datore:* {uname}\n"
            f"📅 *Data:* {created}"
        )
        await update.message.reply_text(msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)







async def start_vip_autobump_loop(application: Application):
    """Loop di background nativo che ripubblica e fissa in cima gli annunci VIP (7d e Mensili) ogni 3 ore."""
    await asyncio.sleep(30)
    while True:
        try:
            if config.GROUP_ID != 0:
                logger.info("🔄 Esecuzione Auto-Bump triorario annunci VIP & VIP Mensile...")
                active_vips = db.get_active_vip_jobs()
                if active_vips:
                    for job in active_vips:
                        job_id = job["job_id"]
                        pkg = job["package"]
                        old_msg_id = job.get("message_id")
                        business = job["business_name"]
                        role = job["role"]
                        zone = job["zone"]
                        shift = job["shift"]
                        salary = job["salary"]
                        desc = job["description"]
                        contact = job["contact"]
                        user_name = job["username"]

                        # 1. Elimina il vecchio post nel gruppo (se presente) per mantenere la chat pulita
                        if old_msg_id:
                            try:
                                await application.bot.delete_message(chat_id=config.GROUP_ID, message_id=old_msg_id)
                                logger.info(f"🗑️ Vecchio post #{old_msg_id} eliminato per job VIP #{job_id}")
                            except Exception as e_del:
                                logger.warning(f"Impossibile eliminare vecchio post #{old_msg_id} per job #{job_id}: {e_del}")

                        # 2. Prepara l'header grafico in base al pacchetto
                        if pkg == "vip":
                            header = "👑 *SPONSOR VIP (7 GIORNI IN CIMA)* 👑"
                        elif pkg == "vip_mensile":
                            header = "💎 *SPONSOR VIP MENSILE (30 GIORNI IN CIMA)* 💎"
                        else:
                            header = "🔝 *OFFERTA IN EVIDENZA* 🔝"

                        post_text = (
                            f"{header}\n\n"
                            f"🏪 *LOCALE:* {business.upper()}\n"
                            f"💼 *Ruolo Cercato:* {role}\n"
                            f"📍 *Zona:* {zone}\n"
                            f"⏰ *Turni:* {shift}\n"
                            f"💰 *Paga:* {salary if salary else 'Trattabile'}\n\n"
                            f"📝 *Descrizione & Requisiti:*\n_{desc}_\n\n"
                            f"📞 *Contatto Candidature:* {contact}\n"
                            f"👤 *Pubblicato da:* @{user_name if user_name else 'Datore'}"
                        )

                        reply_markup = InlineKeyboardMarkup([
                            [InlineKeyboardButton("⚡ Candidati in 1-Click", callback_data=f"apply_start:{job_id}")],
                            [InlineKeyboardButton("📊 Apri Dashboard Candidati (Mini-App)", web_app=WebAppInfo(url=f"{config.WEBAPP_DASHBOARD_URL}?job_id={job_id}"))]
                        ])

                        # 3. Ripubblica l'annuncio in fondo alla chat del gruppo
                        try:
                            new_msg = await application.bot.send_message(
                                chat_id=config.GROUP_ID,
                                text=post_text,
                                parse_mode=ParseMode.MARKDOWN,
                                reply_markup=reply_markup
                            )
                            new_msg_id = new_msg.message_id
                            db.update_job_offer_message_id(job_id, new_msg_id)

                            # 4. Fissa l'annuncio fresco in cima al gruppo (Pin)
                            try:
                                await application.bot.pin_chat_message(
                                    chat_id=config.GROUP_ID,
                                    message_id=new_msg_id,
                                    disable_notification=False
                                )
                                logger.info(f"📌 Nuovo post #{new_msg_id} pinnato in cima per job VIP #{job_id}")
                            except Exception as e_pin:
                                logger.warning(f"Errore pin post #{new_msg_id}: {e_pin}")

                        except Exception as e_pub:
                            logger.error(f"Errore ripubblicazione Auto-Bump per job VIP #{job_id}: {e_pub}")

        except Exception as e_loop:
            logger.error(f"Errore nel loop Auto-Bump VIP: {e_loop}")

        # Attende 3 ore (10800 secondi) prima della successiva esecuzione
        await asyncio.sleep(10800)


async def post_init(application: Application):
    """Configura automaticamente il menu comandi nativo di Telegram e avvia il loop Auto-Bump VIP."""
    commands = [
        BotCommand("registrati", "🍸 Registra / Modifica Profilo Candidato"),
        BotCommand("profilo", "👤 Il Mio Profilo & Stato Premium"),
        BotCommand("premium", "⭐ Passa a Premium (2,19€/mese)"),
        BotCommand("pubblica", "📢 Pubblica Offerta Lavoro (Gratis / Evidenza)"),
        BotCommand("regole", "📜 Regole del Gruppo"),
        BotCommand("evidenza", "🔝 Info Post in Evidenza"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Menu comandi nativo Telegram impostato con successo!")

    # Avvia il loop di background Auto-Bump per gli annunci VIP & VIP Mensili (ogni 3 ore)
    asyncio.create_task(start_vip_autobump_loop(application))
    logger.info("🚀 Loop Auto-Bump triorario per annunci VIP avviato in background!")


# ─── Main ──────────────────────────────────────────────────────────────────────────────

def main():
    db.init_db()
    logger.info("✅ Database inizializzato")

    # Avvia server WebApp in background per la porta Railway
    server.start_web_server()

    if not config.BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN mancante! Imposta la variabile d'ambiente BOT_TOKEN.")

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()


    # Comandi
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("bannati", cmd_bannati))
    app.add_handler(CommandHandler("verify", cmd_verify))
    app.add_handler(CommandHandler("featured", cmd_featured))
    app.add_handler(CommandHandler("regole", cmd_regole))
    app.add_handler(CommandHandler("formato", cmd_formato))
    app.add_handler(CommandHandler("evidenza", cmd_evidenza))
    app.add_handler(CommandHandler("guida", cmd_guida))
    app.add_handler(CommandHandler("manuale", cmd_guida))
    app.add_handler(CommandHandler("registrati", cmd_registrati))
    app.add_handler(CommandHandler("pubblica", cmd_pubblica))
    app.add_handler(CommandHandler("offerta", cmd_pubblica))
    app.add_handler(CommandHandler("profilo", cmd_profilo))

    app.add_handler(CommandHandler("premium", cmd_premium))
    app.add_handler(CommandHandler("grant_premium", cmd_grant_premium))
    app.add_handler(CommandHandler("match", cmd_match))
    app.add_handler(CommandHandler("test_offerta", cmd_test_offerta))

    # CRM Admin: Gestione Titolari, Lavoratori & Candidati Registrati
    app.add_handler(CommandHandler("titolari", cmd_titolari))
    app.add_handler(CommandHandler("lavoratori", cmd_lavoratori))
    app.add_handler(CommandHandler("candidati", cmd_candidati))
    app.add_handler(CommandHandler("broadcast_titolari", cmd_broadcast_titolari))
    app.add_handler(CommandHandler("mie_offerte", cmd_mie_offerte))
    app.add_handler(CommandHandler("edit_offerta", cmd_edit_offerta))
    app.add_handler(CommandHandler("offerte", cmd_offerte))


    # Data da WebApp Telegram
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp_data))

    # Messaggi nel gruppo
    app.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION,
        on_group_message
    ))

    # Approvazione link e pagamenti (callback dei bottoni inline)
    app.add_handler(CallbackQueryHandler(on_link_approval, pattern="^link_"))
    app.add_handler(CallbackQueryHandler(on_payment_button, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(on_candidate_redirect, pattern="^candidate_"))

    # Candidature 1-Click e Pre-Screening (Stile Restworld)
    app.add_handler(CallbackQueryHandler(on_candidate_apply_start, pattern="^apply_start:"))
    app.add_handler(CallbackQueryHandler(on_candidate_apply_q1, pattern="^apply_q1:"))
    app.add_handler(CallbackQueryHandler(on_candidate_apply_q2, pattern="^apply_q2:"))
    app.add_handler(CallbackQueryHandler(on_candidate_apply_submit, pattern="^apply_submit:"))
    app.add_handler(CallbackQueryHandler(on_employer_app_status, pattern="^app_status:"))

    # Gestione Pagamenti Telegram Stars & Stripe
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))


    # Nuovi membri
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))


    logger.info("🚀 Bot avviato — in ascolto...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)



if __name__ == "__main__":
    main()
