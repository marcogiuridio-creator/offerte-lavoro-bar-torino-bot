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
        """)


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
