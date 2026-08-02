"""
IMPORTAZIONE MASSIVA TITOLARI & LAVORATORI da result.json → bot_data.db
Questo script analizza l'export Telegram e importa tutti gli utenti classificati
come 'datore' o 'lavoratore' nel database SQLite del bot, pronti per il CRM admin.
"""
import sys
import json

sys.path.append("/Users/marcogiuridio/Desktop/CHAT TELEGRAM/bot")

import database as db

def import_users():
    file_path = "/Users/marcogiuridio/Desktop/CHAT TELEGRAM/result.json"
    print("⏳ Caricamento export Telegram (13.8 MB)...")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = data.get("messages", [])

    # Keyword patterns
    offerta_keywords = [
        "cercasi", "cerchiamo", "cerca", "assumiamo", "offerta di lavoro",
        "locale in centro", "locale a torino", "cerca barista", "cerca cameriere",
        "cerca cuoco", "cerca pizzaiolo", "inviare cv", "mandare cv", "retribuzione",
        "paga oraria", "paga mensile", "contratto", "inviare candidatura"
    ]
    richiesta_keywords = [
        "cerco lavoro", "cerco posto", "disponibile come", "disponibile subito",
        "ho esperienza", "esperienze lavorative", "anni di esperienza",
        "automunito", "attestato haccp", "in privato per cv", "disponibile per extra",
        "disponibile nel weekend", "cerco turno"
    ]

    datori = {}
    lavoratori = {}

    for msg in messages:
        if not isinstance(msg, dict) or msg.get("type") != "message":
            continue

        from_id_raw = msg.get("from_id")
        if not from_id_raw:
            continue

        # Estrai user_id numerico
        if isinstance(from_id_raw, str) and from_id_raw.startswith("user"):
            try:
                user_id = int(from_id_raw.replace("user", ""))
            except ValueError:
                continue
        elif isinstance(from_id_raw, int):
            user_id = from_id_raw
        else:
            continue

        from_name = msg.get("from") or "Utente"

        text_content = ""
        t = msg.get("text")
        if isinstance(t, str):
            text_content = t
        elif isinstance(t, list):
            for part in t:
                if isinstance(part, str):
                    text_content += part
                elif isinstance(part, dict):
                    text_content += part.get("text", "")

        text_lower = text_content.lower()
        if not text_lower:
            continue

        is_offerta = any(k in text_lower for k in offerta_keywords)
        is_richiesta = any(k in text_lower for k in richiesta_keywords)

        if is_offerta and not is_richiesta:
            if user_id not in datori:
                datori[user_id] = {"name": from_name, "count": 0}
            datori[user_id]["count"] += 1

        elif is_richiesta and not is_offerta:
            if user_id not in lavoratori:
                lavoratori[user_id] = {"name": from_name, "count": 0}
            lavoratori[user_id]["count"] += 1

    # Inizializza DB (crea tabelle + migration)
    db.init_db()

    # Importa datori
    imported_datori = 0
    for uid, info in datori.items():
        db.import_user_with_role(
            user_id=uid,
            username="",
            first_name=info["name"],
            role="datore",
            offerte_count=info["count"]
        )
        imported_datori += 1

    # Importa lavoratori
    imported_lavoratori = 0
    for uid, info in lavoratori.items():
        if uid not in datori:  # Non sovrascrivere chi è già titolare
            db.import_user_with_role(
                user_id=uid,
                username="",
                first_name=info["name"],
                role="lavoratore",
                offerte_count=0
            )
            imported_lavoratori += 1

    # Verifica
    counts = db.count_users_by_role()

    print("\n" + "=" * 60)
    print("✅ IMPORTAZIONE COMPLETATA CON SUCCESSO!")
    print("=" * 60)
    print(f"🏪 Datori di lavoro importati: {imported_datori}")
    print(f"👨‍🍳 Lavoratori importati: {imported_lavoratori}")
    print(f"\n📊 CONTEGGIO FINALE NEL DATABASE:")
    print(f"   🏪 Datori:     {counts['datori']}")
    print(f"   👨‍🍳 Lavoratori: {counts['lavoratori']}")
    print(f"   👥 Totale:      {counts['totale']}")
    print("=" * 60)

if __name__ == "__main__":
    import_users()
