"""
Script di simulazione dell'intero sistema Reclutamento Horeca Telegram Stile Restworld
"""
import sys
import json

sys.path.append("/Users/marcogiuridio/Desktop/CHAT TELEGRAM/bot")

import database as db
import matcher

def run_simulation():
    print("=" * 60)
    print("🚀 SIMULAZIONE PIATTAFORMA RECLUTAMENTO HORECA TORINO")
    print("=" * 60)

    # 1. Inizializzazione DB
    db.init_db()

    # 2. Creazione Profilo Candidato (Mario Rossi)
    print("\n--- 1. REGISTRAZIONE CANDIDATO (Mini-App WebApp) ---")
    cand_id = 999901
    db.save_candidate_profile(
        user_id=cand_id,
        username="mario_barista",
        first_name="Mario Rossi",
        roles=json.dumps(["Barista", "Bartender"]),
        skills=json.dumps(["Espresso & Estratti", "Latte Art", "Attestato HACCP", "Corso Primo Soccorso"]),
        experience="1-3 anni",
        availability=json.dumps(["Full-time", "Turni Notturni"]),
        zones=json.dumps(["Centro", "San Salvario", "Crocetta"]),
        phone="+39 340 1234567",
        bio="Barista con 3 anni di esperienza in caffetteria e cocktail bar in centro a Torino."
    )
    print("✅ Profilo Candidato salvato per Mario Rossi (@mario_barista)")

    # Attivazione Premium per la simulazione
    db.make_user_premium(cand_id, days=30)
    print("⭐ Account Mario Rossi aggiornato a CANDIDATO PREMIUM (Valido 30 giorni)")

    # 3. Creazione Offerta di Lavoro da Datore (Caffè Torino)
    print("\n--- 2. PUBBLICAZIONE ANNUNCIO IN EVIDENZA (Datore via /pubblica) ---")
    job_id = db.create_job_offer(
        user_id=888801,
        username="titolare_caffetorino",
        business_name="Caffè Torino Centro",
        role="Barista",
        zone="Centro",
        shift="Full-time",
        salary="1.300€ / mese",
        description="Cercasi barista esperto per gestione banco e caffetteria mattina in piazza Castello. Richiesto attestato HACCP ed esperienza espresso.",
        contact="@titolare_caffetorino",
        package="evidenza",
        is_verified=1
    )
    print(f"✅ Annuncio 🔝 IN EVIDENZA creato con ID: {job_id} per 'Caffè Torino Centro'")

    # 4. Simulazione Matching Engine
    print("\n--- 3. ESECUZIONE ALGORITMO DI MATCHING HORECA ---")
    job = db.get_job_offer(job_id)
    job_text = f"Caffè Torino Centro - Barista Centro {job['description']}"
    details = matcher.extract_job_details(job_text)
    profile = db.get_candidate_profile(cand_id)
    score = matcher.calculate_match_score(profile, details)

    print(f"📊 Ruoli identificati: {details['roles']}")
    print(f"📍 Zone identificate: {details['zones']}")
    print(f"🎯 Punteggio di Affinità/Match per Mario Rossi: {score}%")

    # 5. Simulazione Notifica Push al Candidato Premium
    print("\n--- 4. NOTIFICA PUSH IN PRIVATO (Trasmessa solo ai Candidati Premium) ---")
    print(f"📲 NOTIFICA INVIATA A @mario_barista:")
    print("┌─────────────────────────────────────────────────────────────┐")
    print("│ ⭐ NUOVA OFFERTA IN TARGET (RISERVATA PREMIUM) (Match: 88%) │")
    print("│                                                             │")
    print("│ 🏪 LOCALE: Caffè Torino Centro                              │")
    print("│ 💼 Ruolo: Barista | 📍 Zona: Centro Torino                  │")
    print("│ 💰 Paga: 1.300€ / mese                                      │")
    print("│ 👤 Pubblicato da: @titolare_caffetorino                     │")
    print("│                                                             │")
    print("│ [ 📩 Candidati Ora in 1-Click ]                             │")
    print("└─────────────────────────────────────────────────────────────┘")

    # 6. Simulazione Pre-Screening 1-Click
    print("\n--- 5. FLUSSO PRE-SCREENING AUTOMATIZZATO (Chat Bot) ---")
    print("👤 Mario Rossi clicca [ 📩 Candidati Ora in 1-Click ]")
    print("🤖 Bot: 'Confermi la disponibilità per la zona e gli orari?'")
    print("👤 Mario Rossi: '✅ Sì, Disponibile Subito'")
    print("🤖 Bot: 'Possiedi l'attestato HACCP e i requisiti?'")
    print("👤 Mario Rossi: '📜 Sì, HACCP Valido / Requisiti OK'")

    app_id = db.save_application(
        job_id=job_id,
        candidate_id=cand_id,
        candidate_user="mario_barista",
        match_score=score,
        screening_q1="Disponibile Subito",
        screening_q2="HACCP Valido",
        screening_notes="Candidatura inoltrata via Pre-Screening Telegram Bot"
    )
    print(f"✅ Candidatura registrata con successo (App ID: {app_id})")

    # 7. Simulazione Invio Scheda CV al Titolare
    print("\n--- 6. RECAPITO SCHEDA CANDIDATO CV AL TITOLARE ---")
    print(f"📲 SCHEDA RICEVUTA DA @titolare_caffetorino SU TELEGRAM:")
    print("┌─────────────────────────────────────────────────────────────┐")
    print("│ 🌟 NUOVA CANDIDATURA INOLTRATA PER CAFFÈ TORINO CENTRO!     │")
    print("│                                                             │")
    print("│ 💼 Ruolo Cercato: Barista                                   │")
    print("│ 👤 Candidato: Mario Rossi (@mario_barista)                 │")
    print("│ 🏷️ Status: ⭐ CANDIDATO PREMIUM (Affinità Match: 88%)        │")
    print("│                                                             │")
    print("│ 📋 SCHEDA PROFILO & COMPETENZE:                             │")
    print("│ • Esperienza: 1-3 anni (Intermedio)                         │")
    print("│ • Ruoli: Barista, Bartender                                 │")
    print("│ • Skill: Espresso & Estratti, Latte Art, HACCP, Primo Socc. │")
    print("│ • Telefono: +39 340 1234567                                 │")
    print("│                                                             │")
    print("│ ✅ RISPOSTE PRE-SCREENING:                                  │")
    print("│ • Disponibilità Turni: Disponibile Subito                   │")
    print("│ • HACCP & Requisiti: HACCP Valido                           │")
    print("│                                                             │")
    print("│ [ 💬 Scrivi su Telegram ] [ 📞 Chiama +39 340 1234567 ]     │")
    print("│ [ ✅ Convoca a Colloquio ] [ ❌ Non Idoneo ]                │")
    print("└─────────────────────────────────────────────────────────────┘")

    # 8. Decisione Titolare
    print("\n--- 7. DECISIONE TITOLARE (1-Tap Status Update) ---")
    db.update_application_status(app_id, "interview")
    print("👤 Titolare clicca [ ✅ Convoca a Colloquio ]")
    print("🟢 Stato Aggiornato nel DB: CONVOCATO A COLLOQUIO")
    print("🤖 Bot notifica Mario Rossi: '🎉 Il Caffè Torino ti ha convocato a colloquio!'")
    print("\n=" * 60)
    print("🎉 SIMULAZIONE COMPLETATA CON SUCCESSO!")
    print("=" * 60)

if __name__ == "__main__":
    run_simulation()
