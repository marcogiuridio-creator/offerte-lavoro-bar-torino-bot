"""
Modulo di Matching e Notifiche Smart per Offerte Lavoro Bar Torino.
Analizza gli annunci e li incrocia con i profili dei candidati registrati.
"""

import re
import json
import logging
import database as db

logger = logging.getLogger(__name__)

# Keywords per estrazione ruoli
ROLE_KEYWORDS = {
    "Barista": ["barista", "baristi", "caffetteria", "banco bar"],
    "Bartender": ["bartender", "mixology", "cocktail", "barman", "barmaid"],
    "Cameriere": ["cameriere", "cameriera", "camerieri", "sala", "servizio al tavolo"],
    "Cuoco": ["cuoco", "cuoca", "chef", "primi piatti", "secondi"],
    "Aiuto Cuoco": ["aiuto cuoco", "aiuto cuoca", "commis di cucina", "preparazione cibi"],
    "Lavapiatti": ["lavapiatti", "plonge", "pulizia cucina"],
    "Pizzaiolo": ["pizzaiolo", "pizzaiola", "fornaio", "stesura pizza"],
    "Banconista": ["banconista", "gelateria", "gastronomia", "pasticceria"],
    "Responsabile": ["responsabile", "maître", "head bartender", "direttore locale"]
}

# Keywords per estrazione zone
ZONE_KEYWORDS = {
    "Centro": ["centro", "piazza castello", "via roma", "piazza san carlo", "porta nuova"],
    "San Salvario": ["san salvario", "via nizza", "marconi"],
    "Crocetta": ["crocetta", "corso duca degli abruzzi"],
    "Vanchiglia": ["vanchiglia", "piazza vittorio", "palazzo nuovo"],
    "Santa Rita": ["santa rita", "corso siracusa", "stadio olimpico"],
    "Pozzo Strada": ["pozzo strada", "pellerina", "corso francia"],
    "Barriera di Milano": ["barriera di milano", "corso palermo", "piazza rebaudengo"],
    "Lingotto": ["lingotto", "via nizza sud", "spezia"],
    "San Donato": ["san donato", "piazza statuto"],
    "Parella": ["parella", "corso monte cucco"],
    "Cit Turin": ["cit turin", "piazza bernini"],
    "Mirafiori": ["mirafiori", "corso unione sovietica"],
    "Provincia di Torino": ["provincia", "moncalieri", "rivoli", "collegno", "grugliasco", "settimo", "venaria", "nichelino"]
}

# Keywords per disponibilità
AVAIL_KEYWORDS = {
    "Full-time": ["full time", "full-time", "tempo pieno", "40 ore"],
    "Part-time": ["part time", "part-time", "mezza giornata", "20 ore"],
    "Extra / Chiamata": ["extra", "chiamata", "weekend", "fine settimana", "venerdì", "sabato"],
    "Turni Notturni": ["notturno", "notte", "serale", "tardi", "locale notturno", "pub"]
}

# Keywords per skill
SKILL_KEYWORDS = {
    "Espresso & Estratti": ["espresso", "caffè", "estrazione", "macinatura"],
    "Latte Art": ["latte art", "cappuccini decorati", "montatura latte"],
    "Cappuccini Veloci": ["cappuccini veloci", "colazioni", "servizio colazione"],
    "Caffetteria Avanzata": ["caffetteria avanzata", "speciality coffee"],
    "Pulizia Macchina": ["pulizia macchina", "manutenzione bar"],
    "Preparazione Aperitivi": ["aperitivi", "spritz", "apericena"],
    "Cocktails Classici": ["cocktail", "mixology", "drink", "cocktail classici"],
    "Mixology & Home-made": ["mixology", "home-made", "sciroppi", "preparazioni"],
    "Speakeasy / Flair": ["flair", "speakeasy", "flair bartending"],
    "Carta Cocktails & Spirits": ["spirits", "distillati", "carta cocktail"],
    "Barman Discoteca / Eventi": ["discoteca", "pub", "eventi veloci", "feste"],
    "Servizio al Tavolo": ["servizio al tavolo", "vassoio", "sala"],
    "Presa Comande": ["comande", "palmare", "tablet"],
    "Cassa & POS": ["cassa", "pos", "chiusura cassa"],
    "Sommelier & Vini": ["sommelier", "vino", "vini", "carta dei vini"],
    "Taglieri & Apericena": ["taglieri", "affettati", "apericena"],
    "Inglese Ristorazione": ["inglese", "english", "lingua inglese"],
    "Cucina Calda": ["cucina calda", "primi", "secondi", "padelle"],
    "Antipasti & Linea Fredda": ["linea fredda", "antipasti", "insalate"],
    "Stesura Pizza & Forno": ["stesura pizza", "forno a legna", "forno elettrico"],
    "Pasticceria & Dolci": ["pasticceria", "dolci", "torte"],
    "Preparazione Linea Cucina": ["linea cucina", "preparazione ingredienti"],
    "Attestato HACCP": ["haccp", "attestato haccp", "igiene alimentare"],
    "Primo Soccorso": ["primo soccorso", "addetto primo soccorso"],
    "Antincendio": ["antincendio", "rischio medio", "rischio basso"],
    "Sicurezza Lavoro D.Lgs 81/08": ["81/08", "sicurezza lavoro", "sicurezza sui luoghi"],
    "Automunito / Patente B": ["automunito", "patente", "patente b", "auto propria"],
    "Disponibilità Festivi & Notturni": ["festivi", "notturni", "weekend", "turni notturni"]
}



def extract_job_details(text: str) -> dict:
    """Estrae ruoli, zone, turni e skill presenti nel testo di un annuncio di lavoro."""
    text_lower = text.lower()

    found_roles = []
    for role, kws in ROLE_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            found_roles.append(role)

    found_zones = []
    for zone, kws in ZONE_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            found_zones.append(zone)

    found_avail = []
    for avail, kws in AVAIL_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            found_avail.append(avail)

    found_skills = []
    for skill, kws in SKILL_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            found_skills.append(skill)

    return {
        "roles": found_roles,
        "zones": found_zones,
        "availability": found_avail,
        "skills": found_skills
    }


def calculate_match_score(candidate: dict, job_details: dict) -> int:
    """
    Calcola il punteggio di affinità tra un candidato e un annuncio (0-100%).
    """
    score = 0
    max_score = 0

    # Parse data del candidato
    c_roles = json.loads(candidate["roles"]) if candidate["roles"] else []
    c_zones = json.loads(candidate["zones"]) if candidate["zones"] else []
    c_avail = json.loads(candidate["availability"]) if candidate["availability"] else []
    c_skills = json.loads(candidate["skills"]) if candidate["skills"] else []

    j_roles = job_details["roles"]
    j_zones = job_details["zones"]
    j_avail = job_details["availability"]
    j_skills = job_details["skills"]

    # 1. Ruolo (Peso 45%)
    if j_roles:
        max_score += 45
        if any(r in c_roles for r in j_roles):
            score += 45
    else:
        # Se l'annuncio non specifica ruoli chiari, assegna un valore base
        score += 20
        max_score += 20

    # 2. Zona (Peso 30%)
    if j_zones:
        max_score += 30
        if any(z in c_zones for z in j_zones) or "Provincia di Torino" in c_zones:
            score += 30
    else:
        score += 15
        max_score += 15

    # 3. Turni / Disponibilità (Peso 15%)
    if j_avail:
        max_score += 15
        if any(a in c_avail for a in j_avail):
            score += 15
    else:
        score += 10
        max_score += 10

    # 4. Skill (Peso 10%)
    if j_skills:
        max_score += 10
        if any(s in c_skills for s in j_skills):
            score += 10
    else:
        score += 5
        max_score += 5

    if max_score == 0:
        return 50

    return int((score / max_score) * 100)


def get_matching_candidates(job_text: str, min_score: int = 50) -> list:
    """Trova tutti i candidati in target per l'annuncio dato."""
    job_details = extract_job_details(job_text)
    all_candidates = db.get_all_candidates(limit=200)

    matches = []
    for cand in all_candidates:
        score = calculate_match_score(cand, job_details)
        if score >= min_score:
            cand_dict = dict(cand)
            cand_dict["match_score"] = score
            cand_dict["extracted_details"] = job_details
            matches.append(cand_dict)

    # Ordina dal match più alto a quello più basso
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return matches


async def notify_matched_candidates(bot, job_text: str, employer_username: str, group_msg_id: int):
    """
    Invia la notifica push in privato ai candidati idonei.
    """
    matches = get_matching_candidates(job_text, min_score=60)
    if not matches:
        logger.info("ℹ️ Nessun candidato in target trovato per questo annuncio.")
        return 0

    logger.info(f"🎯 Trovati {len(matches)} candidati in target per l'annuncio!")
    notified_count = 0

    contact_ref = f"@{employer_username}" if employer_username else "il titolare nel gruppo"

    for cand in matches[:50]: # Considera i candidati idonei in target
        user_id = cand["user_id"]
        score = cand["match_score"]
        is_premium = db.is_user_premium(user_id)

        # La notifica push arriva ESCLUSIVAMENTE agli utenti Premium!
        if not is_premium:
            continue

        # Utente Premium: notifica completa con contatti diretti
        preview_text = job_text[:400] + ("..." if len(job_text) > 400 else "")
        msg = (
            f"⭐ *NUOVA OFFERTA IN TARGET (RISERVATA PREMIUM)* (Affinità: *{score}%*)\n\n"
            f"📝 *Annuncio:* \n_{preview_text}_\n\n"
            f"👤 *Pubblicato da:* {contact_ref}\n"
            f"💡 *Per candidarti:* scrivi subito in privato a {contact_ref} per riservarti il colloquio!"
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=msg,
                parse_mode="Markdown"
            )
            notified_count += 1
        except Exception as e:
            # L'utente potrebbe aver bloccato il bot in privato
            logger.warning(f"Impossibile notificare utente {user_id}: {e}")

    return notified_count


