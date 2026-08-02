"""
Simulazione della Gerarchia a 4 Livelli nella Dashboard Candidati del Titolare
"""
import sys
import json

sys.path.append("/Users/marcogiuridio/Desktop/CHAT TELEGRAM/bot")

import database as db
import matcher

def run_dashboard_simulation():
    db.init_db()

    # Create dummy candidates
    # Cand 1: Active Applicant + Premium
    c1 = 991
    db.save_candidate_profile(c1, "marco_prem_active", "Marco (Attivo Premium)", json.dumps(["Barista"]), json.dumps(["Latte Art", "HACCP"]), "3 anni", json.dumps(["Full-time"]), json.dumps(["Centro"]), "+39 340 1111111", "Barista esperto")
    db.make_user_premium(c1, days=30)

    # Cand 2: Active Applicant + Free
    c2 = 992
    db.save_candidate_profile(c2, "luca_free_active", "Luca (Attivo Free)", json.dumps(["Barista"]), json.dumps(["Espresso"]), "1 anno", json.dumps(["Full-time"]), json.dumps(["Centro"]), "+39 340 2222222", "Barista junior")

    # Cand 3: Registered DB + Premium (No application)
    c3 = 993
    db.save_candidate_profile(c3, "elena_prem_db", "Elena (DB Premium)", json.dumps(["Barista"]), json.dumps(["Cocktails"]), "5 anni", json.dumps(["Full-time"]), json.dumps(["Centro"]), "+39 340 3333333", "Senior Barmaid")
    db.make_user_premium(c3, days=30)

    # Cand 4: Registered DB + Free (No application)
    c4 = 994
    db.save_candidate_profile(c4, "giovanni_free_db", "Giovanni (DB Free)", json.dumps(["Barista"]), json.dumps(["Caffetteria"]), "6 mesi", json.dumps(["Part-time"]), json.dumps(["Centro"]), "+39 340 4444444", "Aiuto Barista")

    # Create Job Offer
    job_id = db.create_job_offer(888, "caffetorino", "Caffè Torino", "Barista", "Centro", "Full-time", "1.300€", "Cercasi barista centro", "@caffetorino", "evidenza", 1)

    # Record applications for c1 and c2
    db.save_application(job_id, c1, "marco_prem_active", 95, "Disponibile subito", "HACCP OK", "Noto bar centro")
    db.save_application(job_id, c2, "luca_free_active", 85, "Disponibile subito", "HACCP OK", "Disponibile extra")

    # Fetch candidates using the exact sorting key:
    matches = matcher.get_matching_candidates("Caffè Torino - Barista Centro", min_score=40)
    apps = db.get_job_applications(job_id)
    app_dict = {a["candidate_id"]: a for a in apps}

    res = []
    for c in matches:
        uid = c["user_id"]
        is_prem = db.is_user_premium(uid)
        app_data = app_dict.get(uid)
        res.append({
            "name": c["first_name"],
            "username": c["username"],
            "phone": c["phone"],
            "is_premium": is_prem,
            "has_applied": app_data is not None,
            "status": app_data["status"] if app_data else "nessuna",
            "q1": app_data["screening_q1"] if app_data else None,
            "match": c["match_score"]
        })

    # Exact sorting key
    res.sort(key=lambda x: (not x["has_applied"], not x["is_premium"], -x["match"]))

    print("=" * 65)
    print("📊 GERARCHIA VISUALIZZATA NELLA DASHBOARD WEBAPP DEL TITOLARE")
    print("=" * 65)

    tier_labels = {
        (True, True): "🥇 TIER 1: CANDIDATO ATTIVO + ⭐ PREMIUM (MASSIMA PRIORITÀ)",
        (True, False): "🥈 TIER 2: CANDIDATO ATTIVO + ⚪ FREE (PRIORITÀ SECONDA)",
        (False, True): "🥉 TIER 3: REGISTRATO NEL DB + ⭐ PREMIUM (TERZA PRIORITÀ)",
        (False, False): "🎖️ TIER 4: REGISTRATO NEL DB + ⚪ FREE (QUARTA PRIORITÀ)"
    }

    for idx, r in enumerate(res, 1):
        tier_title = tier_labels.get((r["has_applied"], r["is_premium"]))
        print(f"\nPOSIZIONE #{idx} | {tier_title}")
        print("┌─────────────────────────────────────────────────────────────┐")
        applied_str = " 📩 CANDIDATO (PRIORITÀ)" if r["has_applied"] else ""
        prem_str = "⭐ PREMIUM" if r["is_premium"] else "⚪ BASE"
        print(f"│ 👤 {r['name']} (@{r['username']}) {applied_str} [{prem_str}] │")
        print(f"│ 🎯 Match: {r['match']}% | 📱 Tel: {r['phone']}                  │")
        if r["has_applied"]:
            print(f"│ 📋 Pre-screening: {r['q1']}                          │")
        print(f"│ [ 💬 Telegram ] [ 📱 Chiama ] [ ✅ Convoca ] [ ❌ Archivia ] │")
        print("└─────────────────────────────────────────────────────────────┘")

if __name__ == "__main__":
    run_dashboard_simulation()
