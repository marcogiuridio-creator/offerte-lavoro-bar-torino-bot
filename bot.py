"""
Bot principale — Offerte Lavoro Bar Torino
"""

import logging
import json
from datetime import datetime

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
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

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def get_text(message) -> str:
    """Estrae testo dal messaggio (anche caption per foto/video)."""
    return message.text or message.caption or ""


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

    # ── 2. Controlla link esterni ──
    if has_external_link(text):
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
    category = classify(text)

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

        # Aggiungi emoji categoria come reazione (reaction) o risposta silenziosa
        emoji = get_category_emoji(category)
        logger.info(f"{emoji} {format_category_label(category)} da {user.first_name}: {text[:60]}...")

        # Aggiunge tag categoria come risposta automatica (opzionale, commentabile)
        # await msg.reply_text(f"{emoji} *{format_category_label(category)}*", parse_mode=ParseMode.MARKDOWN)


# ─── Comandi Admin ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start — info base."""
    await update.message.reply_text(
        "👋 Sono il bot di *Offerte Lavoro Bar Torino*!\n\n"
        "Gestisco il gruppo automaticamente. Per aiuto: /help",
        parse_mode=ParseMode.MARKDOWN,
    )


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
        )
    else:
        text = (
            "ℹ️ *Offerte Lavoro Bar Torino*\n\n"
            "Pubblica annunci di lavoro nel settore bar & ristorazione a Torino.\n\n"
            "/regole — Mostra le regole\n"
            "/formato — Mostra il formato consigliato\n"
            "/evidenza — Info su annunci in evidenza\n"
        )
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
    await update.message.reply_text(rules, parse_mode=ParseMode.MARKDOWN)


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
    await update.message.reply_text(fmt, parse_mode=ParseMode.MARKDOWN)


async def cmd_evidenza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /evidenza — info monetizzazione."""
    msg = config.FEATURED_INFO.format(admin_username=config.ADMIN_USERNAME)
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
    """Comando /registrati — apre la Telegram WebApp per registrare il profilo candidato."""
    reply_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🍸 Apri Scheda Registrazione Profilo", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True
    )
    inline_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🍸 Compila Profilo Candidato", web_app=WebAppInfo(url=config.WEBAPP_URL))]
    ])
    msg = (
        "💼 *REGISTRAZIONE PROFILO CANDIDATO*\n\n"
        "Crea o aggiorna la tua scheda profilo per ricevere offerte di lavoro su misura a Torino!\n\n"
        "Clicca sul pulsante in basso per aprire la scheda di registrazione:"
    )
    await update.message.reply_text(msg, reply_markup=reply_keyboard, parse_mode=ParseMode.MARKDOWN)


async def cmd_profilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /profilo — mostra il profilo candidato salvato."""
    user = update.effective_user
    profile = db.get_candidate_profile(user.id)

    if not profile:
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📝 Crea Profilo Ora", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            "❌ Non hai ancora registrato il tuo profilo candidato!\n\n"
            "Clicca sul pulsante qui sotto per crearlo in 1 minuto:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    roles = ", ".join(json.loads(profile["roles"])) if profile["roles"] else "Non specificato"
    skills = ", ".join(json.loads(profile["skills"])) if profile["skills"] else "Nessuna"
    zones = ", ".join(json.loads(profile["zones"])) if profile["zones"] else "Tutta Torino"
    avail = ", ".join(json.loads(profile["availability"])) if profile["availability"] else "Non specificata"

    msg = (
        f"👤 *IL TUO PROFILO CANDIDATO HORECA*\n\n"
        f"💼 *Ruoli:* {roles}\n"
        f"⚡ *Skill:* {skills}\n"
        f"⏳ *Esperienza:* {profile['experience'] or 'N/D'}\n"
        f"⏰ *Disponibilità:* {avail}\n"
        f"📍 *Zone preferite:* {zones}\n"
        f"📱 *Telefono:* {profile['phone'] or 'Non fornito'}\n"
        f"📝 *Note:* {profile['bio'] or 'Nessuna'}\n\n"
        f"🔄 Per aggiornare i dati, usa `/registrati` o clicca sul pulsante in basso."
    )

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("✏️ Modifica Profilo", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True
    )

    await update.message.reply_text(msg, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)



async def on_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Riceve i dati inviati dalla Telegram WebApp."""
    user = update.effective_user
    data_str = update.effective_message.web_app_data.data

    try:
        data = json.loads(data_str)
        if data.get("action") == "save_candidate_profile":
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
    except Exception as e:
        logger.error(f"Errore salvataggio dati WebApp: {e}")
        await update.effective_message.reply_text("❌ Si è verificato un errore durante il salvataggio. Riprova con `/registrati`.")


# ─── Main ──────────────────────────────────────────────────────────────────────────────

def main():
    db.init_db()
    logger.info("✅ Database inizializzato")

    # Avvia server WebApp in background per la porta Railway
    server.start_web_server()

    if not config.BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN mancante! Imposta la variabile d'ambiente BOT_TOKEN.")

    app = Application.builder().token(config.BOT_TOKEN).build()

    # Comandi
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("verify", cmd_verify))
    app.add_handler(CommandHandler("featured", cmd_featured))
    app.add_handler(CommandHandler("regole", cmd_regole))
    app.add_handler(CommandHandler("formato", cmd_formato))
    app.add_handler(CommandHandler("evidenza", cmd_evidenza))
    app.add_handler(CommandHandler("registrati", cmd_registrati))
    app.add_handler(CommandHandler("profilo", cmd_profilo))

    # Data da WebApp Telegram
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp_data))

    # Messaggi nel gruppo
    app.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION,
        on_group_message
    ))

    # Approvazione link (callback dei bottoni inline)
    app.add_handler(CallbackQueryHandler(on_link_approval, pattern="^link_"))

    # Nuovi membri
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))

    logger.info("🚀 Bot avviato — in ascolto...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)



if __name__ == "__main__":
    main()
