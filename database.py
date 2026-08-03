import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea le tabelle se non esistono."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            last_name   TEXT,
            joined_at   TEXT DEFAULT (datetime('now')),
            last_post   TEXT,
            posts_today INTEGER DEFAULT 0,
            last_date   TEXT,
            is_banned   INTEGER DEFAULT 0,
            is_verified INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            message_id  INTEGER,
            category    TEXT,
            text        TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            is_featured INTEGER DEFAULT 0,
            featured_until TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS banned_words (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            word    TEXT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS stats_daily (
            date        TEXT PRIMARY KEY,
            new_members INTEGER DEFAULT 0,
            posts_total INTEGER DEFAULT 0,
            offerte     INTEGER DEFAULT 0,
            richieste   INTEGER DEFAULT 0,
            spam_blocked INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS candidate_profiles (
            user_id         INTEGER PRIMARY KEY,
            username        TEXT,
            first_name      TEXT,
            roles           TEXT,
            skills          TEXT,
            experience      TEXT,
            availability    TEXT,
            zones           TEXT,
            phone           TEXT,
            bio             TEXT,
            is_premium      INTEGER DEFAULT 0,
            premium_until   TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS job_offers (
            job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER,
            username        TEXT,
            business_name   TEXT,
            role            TEXT,
            zone            TEXT,
            shift           TEXT,
            salary          TEXT,
            description     TEXT,
            contact         TEXT,
            package         TEXT,
            is_verified     INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS applications (
            app_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          INTEGER,
            candidate_id    INTEGER,
            candidate_user  TEXT,
            match_score     INTEGER,
            screening_q1    TEXT,
            screening_q2    TEXT,
            screening_notes TEXT,
            status          TEXT DEFAULT 'pending',
            created_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (job_id) REFERENCES job_offers(job_id),
            FOREIGN KEY (candidate_id) REFERENCES candidate_profiles(user_id)
        );
        """)


        # Migration colonna premium_until
        try:
            conn.execute("ALTER TABLE candidate_profiles ADD COLUMN premium_until TEXT")
        except Exception:
            pass

        # Migration colonna role per tagging datori/lavoratori
        try:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT NULL")
        except Exception:
            pass

        # Migration colonna offerte_count per tracciare attività datori
        try:
            conn.execute("ALTER TABLE users ADD COLUMN offerte_count INTEGER DEFAULT 0")
        except Exception:
            pass

        # Migration colonna message_id per collegare l'annuncio al messaggio Telegram nel gruppo
        try:
            conn.execute("ALTER TABLE job_offers ADD COLUMN message_id INTEGER DEFAULT NULL")
        except Exception:
            pass

        # Auto-seed: importa utenti da seed_users.json se la tabella users è vuota
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            import json
            import os
            seed_path = os.path.join(os.path.dirname(__file__), "seed_users.json")
            if os.path.exists(seed_path):
                with open(seed_path, "r", encoding="utf-8") as f:
                    seed_data = json.load(f)
                for u in seed_data:
                    conn.execute("""
                        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, role, offerte_count)
                        VALUES (?, '', ?, '', ?, ?)
                    """, (u["user_id"], u.get("name", "Utente"), u.get("role", ""), u.get("count", 0)))
                print(f"🌱 Auto-seed completato: {len(seed_data)} utenti importati da seed_users.json")

        # Auto-seed: importa offerte da seed_jobs.json se la tabella job_offers è vuota
        jobs_count = conn.execute("SELECT COUNT(*) FROM job_offers").fetchone()[0]
        if jobs_count == 0:
            import json
            import os
            seed_jobs_path = os.path.join(os.path.dirname(__file__), "seed_jobs.json")
            if os.path.exists(seed_jobs_path):
                with open(seed_jobs_path, "r", encoding="utf-8") as f:
                    seed_jobs_data = json.load(f)
                for j in seed_jobs_data:
                    conn.execute("""
                        INSERT OR IGNORE INTO job_offers (
                            job_id, user_id, username, business_name, role, zone, shift, salary, description, contact, package, is_verified
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        j["job_id"], j["user_id"], j.get("username", ""), j["business_name"], j["role"],
                        j["zone"], j["shift"], j["salary"], j["description"], j["contact"], j["package"], j.get("is_verified", 1)
                    ))
                print(f"🌱 Auto-seed offerte completato: {len(seed_jobs_data)} offerte importate da seed_jobs.json")

        # Auto-seed: importa profili candidati da seed_candidates.json se candidate_profiles è vuota
        cands_count = conn.execute("SELECT COUNT(*) FROM candidate_profiles").fetchone()[0]
        if cands_count == 0:
            import json
            import os
            seed_cands_path = os.path.join(os.path.dirname(__file__), "seed_candidates.json")
            if os.path.exists(seed_cands_path):
                with open(seed_cands_path, "r", encoding="utf-8") as f:
                    seed_cands_data = json.load(f)
                for c in seed_cands_data:
                    conn.execute("""
                        INSERT OR IGNORE INTO candidate_profiles (
                            user_id, username, first_name, roles, skills, experience, availability, zones, phone, bio, is_premium
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        c["user_id"], c.get("username", ""), c.get("first_name", "Candidato"),
                        c.get("roles", "[]"), c.get("skills", "[]"), c.get("experience", ""),
                        c.get("availability", "[]"), c.get("zones", "[]"), c.get("phone", ""),
                        c.get("bio", ""), c.get("is_premium", 0)
                    ))
                print(f"🌱 Auto-seed candidati completato: {len(seed_cands_data)} profili importati da seed_candidates.json")




# ─── Users ────────────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                last_name  = excluded.last_name
        """, (user_id, username, first_name, last_name))


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def is_banned(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and row["is_banned"])


def ban_user(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))


def unban_user(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))


def verify_user(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (user_id,))


def get_banned_users():
    """Recupera la lista di tutti gli utenti bannati."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT user_id, username, first_name, last_name, joined_at, last_post
            FROM users WHERE is_banned = 1
            ORDER BY last_post DESC
        """).fetchall()


def tag_user_role(user_id: int, role: str):
    """Tagga un utente come 'datore' o 'lavoratore'."""
    with get_conn() as conn:
        conn.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))


def import_user_with_role(user_id: int, username: str, first_name: str, role: str, offerte_count: int = 0):
    """Importa un utente con ruolo e conteggio offerte (per import massivo da result.json)."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, role, offerte_count)
            VALUES (?, ?, ?, '', ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(NULLIF(excluded.username, ''), users.username),
                first_name = COALESCE(NULLIF(excluded.first_name, ''), users.first_name),
                role = excluded.role,
                offerte_count = excluded.offerte_count
        """, (user_id, username, first_name, role, offerte_count))


def get_users_by_role(role: str, limit: int = 50):
    """Recupera gli utenti per ruolo ordinati per numero di offerte/post."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM users
            WHERE role = ?
            ORDER BY offerte_count DESC, last_post DESC
            LIMIT ?
        """, (role, limit)).fetchall()


def count_users_by_role():
    """Conta gli utenti per ruolo."""
    with get_conn() as conn:
        datori = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'datore'").fetchone()[0]
        lavoratori = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'lavoratore'").fetchone()[0]
        totale = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return {"datori": datori, "lavoratori": lavoratori, "totale": totale}


def get_all_datori_ids():
    """Restituisce tutti gli user_id dei datori di lavoro per broadcast."""
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users WHERE role = 'datore'").fetchall()
        return [r["user_id"] for r in rows]


# ─── Rate limiting ─────────────────────────────────────────────────────────────

def can_post(user_id: int, rate_limit_hours: int, max_per_day: int) -> tuple[bool, str]:
    """
    Controlla se l'utente può postare.
    Ritorna (True, '') se può, (False, motivo) se non può.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_post, posts_today, last_date FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    if not row:
        return True, ""

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # Reset contatore giornaliero se è un nuovo giorno
    if row["last_date"] != today:
        with get_conn() as conn:
            conn.execute(
                "UPDATE users SET posts_today = 0, last_date = ? WHERE user_id = ?",
                (today, user_id)
            )
        posts_today = 0
    else:
        posts_today = row["posts_today"] or 0

    # Controlla max post giornalieri
    if posts_today >= max_per_day:
        return False, f"Hai già pubblicato {max_per_day} annunci oggi. Riprova domani!"

    # Controlla intervallo minimo tra post
    if row["last_post"]:
        last = datetime.fromisoformat(row["last_post"])
        delta = now - last
        if delta < timedelta(hours=rate_limit_hours):
            next_time = (last + timedelta(hours=rate_limit_hours)).strftime("%H:%M")
            return False, next_time

    return True, ""


def record_post(user_id: int, message_id: int, category: str, text: str):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute("""
            UPDATE users
            SET last_post   = ?,
                posts_today = COALESCE(posts_today, 0) + 1,
                last_date   = ?
            WHERE user_id = ?
        """, (now.isoformat(), today, user_id))
        conn.execute("""
            INSERT INTO posts (user_id, message_id, category, text)
            VALUES (?, ?, ?, ?)
        """, (user_id, message_id, category, text[:1000]))
        # Aggiorna stats giornaliere
        conn.execute("""
            INSERT INTO stats_daily (date, posts_total)
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET posts_total = posts_total + 1
        """, (today,))
        if category == "OFFERTA":
            conn.execute("""
                INSERT INTO stats_daily (date, offerte) VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET offerte = offerte + 1
            """, (today,))
        elif category == "RICHIESTA":
            conn.execute("""
                INSERT INTO stats_daily (date, richieste) VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET richieste = richieste + 1
            """, (today,))


def record_spam_blocked():
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO stats_daily (date, spam_blocked) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET spam_blocked = spam_blocked + 1
        """, (today,))


def record_new_member():
    today = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO stats_daily (date, new_members) VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET new_members = new_members + 1
        """, (today,))


# ─── Stats ─────────────────────────────────────────────────────────────────────

def get_stats(days: int = 7) -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM stats_daily
            ORDER BY date DESC
            LIMIT ?
        """, (days,)).fetchall()


def get_total_users() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
        return row["c"] if row else 0


def get_recent_posts(limit: int = 20) -> list:
    with get_conn() as conn:
        return conn.execute("""
            SELECT p.*, u.username, u.first_name
            FROM posts p
            LEFT JOIN users u ON p.user_id = u.user_id
            ORDER BY p.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


# ─── Featured posts ─────────────────────────────────────────────────────────────

def set_featured(message_id: int, hours: int = 24):
    until = (datetime.now() + timedelta(hours=hours)).isoformat()
    with get_conn() as conn:
        conn.execute("""
            UPDATE posts SET is_featured = 1, featured_until = ?
            WHERE message_id = ?
        """, (until, message_id))


# ─── Candidate Profiles & Premium ──────────────────────────────────────────────

def save_candidate_profile(
    user_id: int,
    username: str,
    first_name: str,
    roles: str,
    skills: str,
    experience: str,
    availability: str,
    zones: str,
    phone: str = "",
    bio: str = ""
):
    """Salva o aggiorna il profilo del candidato."""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO candidate_profiles (
                user_id, username, first_name, roles, skills, experience, availability, zones, phone, bio, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username     = excluded.username,
                first_name   = excluded.first_name,
                roles        = excluded.roles,
                skills       = excluded.skills,
                experience   = excluded.experience,
                availability = excluded.availability,
                zones        = excluded.zones,
                phone        = excluded.phone,
                bio          = excluded.bio,
                updated_at   = excluded.updated_at
        """, (user_id, username, first_name, roles, skills, experience, availability, zones, phone, bio, now))


def get_candidate_profile(user_id: int):
    """Recupera il profilo candidato di un utente."""
    with get_conn() as conn:
        return conn.execute("SELECT * FROM candidate_profiles WHERE user_id = ?", (user_id,)).fetchone()


def get_all_candidates(limit: int = 200):
    """Recupera la lista dei candidati salvati."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM candidate_profiles
            ORDER BY is_premium DESC, updated_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


def make_user_premium(user_id: int, days: int = 30):
    """Attiva o prolunga lo stato Premium per un utente."""
    now = datetime.now()
    profile = get_candidate_profile(user_id)

    current_until = None
    if profile and profile["premium_until"]:
        try:
            current_until = datetime.fromisoformat(profile["premium_until"])
        except Exception:
            pass

    if current_until and current_until > now:
        new_until = current_until + timedelta(days=days)
    else:
        new_until = now + timedelta(days=days)

    new_until_str = new_until.isoformat()

    with get_conn() as conn:
        conn.execute("""
            UPDATE candidate_profiles
            SET is_premium = 1, premium_until = ?
            WHERE user_id = ?
        """, (new_until_str, user_id))

    return new_until.strftime("%d/%m/%Y")


def is_user_premium(user_id: int) -> bool:
    """Verifica se l'utente ha un abbonamento Premium attivo."""
    profile = get_candidate_profile(user_id)
    if not profile or not profile["is_premium"]:
        return False

    if profile["premium_until"]:
        try:
            until = datetime.fromisoformat(profile["premium_until"])
            if until < datetime.now():
                # Scaduto
                with get_conn() as conn:
                    conn.execute("UPDATE candidate_profiles SET is_premium = 0 WHERE user_id = ?", (user_id,))
                return False
        except Exception:
            pass

    return True


# ─── Job Offers & Applications ────────────────────────────────────────────────

def create_job_offer(
    user_id: int,
    username: str,
    business_name: str,
    role: str,
    zone: str,
    shift: str,
    salary: str,
    description: str,
    contact: str,
    package: str,
    is_verified: int = 0
) -> int:
    """Inserisce una nuova offerta di lavoro e restituisce il job_id."""
    with get_conn() as conn:
        cursor = conn.execute("""
            INSERT INTO job_offers (
                user_id, username, business_name, role, zone, shift, salary, description, contact, package, is_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, business_name, role, zone, shift, salary, description, contact, package, is_verified))
        return cursor.lastrowid


def get_job_offer(job_id: int):
    """Recupera un annuncio dal database."""
    with get_conn() as conn:
        return conn.execute("SELECT * FROM job_offers WHERE job_id = ?", (job_id,)).fetchone()


def verify_job_offer(job_id: int):
    """Segna un annuncio di lavoro come verificato/pagato."""
    with get_conn() as conn:
        conn.execute("UPDATE job_offers SET is_verified = 1 WHERE job_id = ?", (job_id,))



def update_job_offer(
    job_id: int,
    business_name: str,
    role: str,
    zone: str,
    shift: str,
    salary: str,
    description: str,
    contact: str
):
    """Aggiorna i campi di un annuncio esistente."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE job_offers
            SET business_name = ?,
                role          = ?,
                zone          = ?,
                shift         = ?,
                salary        = ?,
                description   = ?,
                contact       = ?
            WHERE job_id = ?
        """, (business_name, role, zone, shift, salary, description, contact, job_id))


def update_job_offer_message_id(job_id: int, message_id: int):
    """Associa il message_id Telegram del gruppo al job_id."""
    with get_conn() as conn:
        conn.execute("UPDATE job_offers SET message_id = ? WHERE job_id = ?", (message_id, job_id))


def get_user_job_offers(user_id: int, username: str = ""):
    """Recupera tutte le offerte pubblicate da uno specifico titolare."""
    with get_conn() as conn:
        clean_user = username.lower().replace("@", "").strip() if username else ""
        if clean_user:
            return conn.execute("""
                SELECT * FROM job_offers
                WHERE user_id = ? OR (username IS NOT NULL AND username != '' AND LOWER(username) = ?)
                ORDER BY created_at DESC
            """, (user_id, clean_user)).fetchall()
        else:
            return conn.execute("""
                SELECT * FROM job_offers
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,)).fetchall()




def get_all_job_offers(limit: int = 50):
    """Recupera la lista di tutte le offerte (per pannello Admin)."""
    with get_conn() as conn:
        return conn.execute("SELECT * FROM job_offers ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()



def save_application(
    job_id: int,
    candidate_id: int,
    candidate_user: str,
    match_score: int,
    screening_q1: str,
    screening_q2: str,
    screening_notes: str
) -> int:
    """Salva la candidatura avanzata di un lavoratore."""
    with get_conn() as conn:
        cursor = conn.execute("""
            INSERT INTO applications (
                job_id, candidate_id, candidate_user, match_score, screening_q1, screening_q2, screening_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_id, candidate_id, candidate_user, match_score, screening_q1, screening_q2, screening_notes))
        return cursor.lastrowid


def get_job_applications(job_id: int):
    """Recupera tutte le candidature per uno specifico annuncio."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT a.*, c.first_name, c.roles, c.skills, c.experience, c.phone, c.is_premium
            FROM applications a
            LEFT JOIN candidate_profiles c ON a.candidate_id = c.user_id
            WHERE a.job_id = ?
            ORDER BY c.is_premium DESC, a.match_score DESC
        """, (job_id,)).fetchall()


def update_application_status(app_id: int, status: str):
    """Aggiorna lo stato della candidatura (es. 'interview', 'rejected', 'hired')."""
    with get_conn() as conn:
        conn.execute("UPDATE applications SET status = ? WHERE app_id = ?", (status, app_id))


