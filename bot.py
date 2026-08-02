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
    LabeledPrice,
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

        # ── FASE 2: Matching Automatico & Notifiche Smart ──
        if category == "OFFERTA":
            import asyncio
            import matcher
            asyncio.create_task(matcher.notify_matched_candidates(
                context.bot,
                text,
                user.username or "",
                msg.message_id
            ))
            logger.info("🎯 Task notifiche smart avviato per nuova offerta di lavoro!")



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
    """Comando /registrati — apre la Telegram WebApp per registrare il profilo candidato."""
    reply_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🍸 Apri Scheda Registrazione Profilo", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True
    )
    msg = (
        "💼 *REGISTRAZIONE PROFILO CANDIDATO*\n\n"
        "Crea o aggiorna la tua scheda profilo per ricevere offerte di lavoro su misura a Torino!\n\n"
        "Clicca sul pulsante in basso per aprire la scheda di registrazione:"
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
        job = context.user_data.get("pending_job", {})
        pkg = job.get("pkg", "evidenza")
        business = job.get("business", "BAR / LOCALE TORINO")
        role = job.get("role", "")
        zone = job.get("zone", "")
        shift = job.get("shift", "")
        salary = job.get("salary", "")
        desc = job.get("desc", "")
        contact = job.get("contact", "")

        header = "🔝 *OFFERTA IN EVIDENZA (SPONSOR 24H)* 🔝" if pkg == "evidenza" else "👑 *SPONSOR VIP (7 GIORNI IN CIMA)* 👑"

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

        msg_id = None
        if config.GROUP_ID != 0:
            try:
                pub_msg = await context.bot.send_message(
                    chat_id=config.GROUP_ID,
                    text=post_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                msg_id = pub_msg.message_id
                # Fissa il post in cima al gruppo (Pin)
                try:
                    await context.bot.pin_chat_message(
                        chat_id=config.GROUP_ID,
                        message_id=pub_msg.message_id
                    )
                except Exception as pe:
                    logger.warning(f"Impossibile fissare post in cima: {pe}")

                import matcher
                await matcher.notify_matched_candidates(context.bot, post_text, user.username or "", pub_msg.message_id)
            except Exception as e:
                logger.error(f"Errore pubblicazione offerta a pagamento: {e}")

        # Pulisci pending_job
        context.user_data.pop("pending_job", None)

        await update.message.reply_text(
            "🎉 *PAGAMENTO RICEVUTO CON SUCCESSO!*\n\n"
            "Il tuo annuncio in evidenza è stato pubblicato, **fissato in cima al gruppo** e notificato in privato a tutti i candidati qualificati a Torino!",
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
        f"🔄 Per aggiornare i dati, usa `/registrati`. Per il Premium: `/premium`"
    )

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("✏️ Modifica Profilo", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True
    )

    await send_smart_reply(update, context, msg, reply_markup=keyboard, deep_link_arg="registrati")





async def cmd_pubblica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /pubblica — apre il form di pubblicazione per datori di lavoro."""
    reply_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📢 Apri Modulo Pubblicazione Offerta", web_app=WebAppInfo(url=config.WEBAPP_PUBBLICA_URL))]],
        resize_keyboard=True
    )
    msg = (
        "💼 *PUBBLICA UN'OFFERTA DI LAVORO HORECA*\n\n"
        "Trova subito personale qualificato (Baristi, Camerieri, Cuochi, Pizzaioli) a Torino!\n\n"
        "Puoi scegliere tra:\n"
        "• 🆓 *Annuncio Gratuito (0€)*\n"
        "• ⭐ *In Evidenza 24h (250 Stelle / 5,39€)* — Post 🔝 + Pin 24h + Push ai candidati!\n"
        "• 👑 *Sponsor VIP 7 Giorni (500 Stelle / 10,90€)* — Post 👑 + Pin 7 Giorni + Multi-Push!\n\n"
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
                        import matcher
                        await matcher.notify_matched_candidates(context.bot, post_text, user.username or "", pub_msg.message_id)
                    except Exception as e:
                        logger.error(f"Errore pubblicazione gruppo: {e}")

                await update.effective_message.reply_text(
                    "✅ *ANNUNCIO GRATUITO PUBBLICATO!*\n\n"
                    "Il tuo annuncio è stato inviato nel gruppo ed è stato elaborato dall'algoritmo di matching per notificare i candidati idonei a Torino!",
                    parse_mode=ParseMode.MARKDOWN
                )

            elif pkg in ["evidenza", "vip"]:
                context.user_data["pending_job"] = job_details
                stars = 250 if pkg == "evidenza" else 500
                eur_cents = 539 if pkg == "evidenza" else 1090
                pkg_name = "In Evidenza 24h" if pkg == "evidenza" else "Sponsor VIP 7 Giorni"

                title = f"Offerta {pkg_name} Horeca"
                description = f"Annuncio {business} ({role} - {zone}) con Pin e Push Broadcast"
                payload = f"job_offer_{pkg}_{stars}"
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
    except Exception as e:
        logger.error(f"Errore salvataggio dati WebApp: {e}")
        await update.effective_message.reply_text("❌ Si è verificato un errore. Riprova con `/pubblica`.")



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
    app.add_handler(CommandHandler("pubblica", cmd_pubblica))
    app.add_handler(CommandHandler("offerta", cmd_pubblica))
    app.add_handler(CommandHandler("profilo", cmd_profilo))

    app.add_handler(CommandHandler("premium", cmd_premium))
    app.add_handler(CommandHandler("grant_premium", cmd_grant_premium))
    app.add_handler(CommandHandler("match", cmd_match))




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

    # Gestione Pagamenti Telegram Stars & Stripe
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # Nuovi membri
    app.add_handler(ChatMemberHandler(on_new_member, ChatMemberHandler.CHAT_MEMBER))


    logger.info("🚀 Bot avviato — in ascolto...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)



if __name__ == "__main__":
    main()
