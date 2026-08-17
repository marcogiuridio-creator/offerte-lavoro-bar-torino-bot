import os
import http.server
import socketserver
import threading
import logging
import json
import urllib.request
import urllib.parse
import hashlib
import hmac
import time
from typing import Optional

import config
import database as db

logger = logging.getLogger(__name__)


BOT_DIR = os.path.dirname(__file__)
WEBAPP_DIR = os.path.join(BOT_DIR, "webapp")
MAX_REQUEST_BODY = 64 * 1024
MAX_INIT_DATA_AGE = 15 * 60


def escape_telegram_markdown(value):
    return str(value or "").translate(str.maketrans({"_": "\\_", "*": "\\*", "[": "\\[", "`": "\\`"}))


def validate_telegram_init_data(init_data: str, now: Optional[int] = None):
    """Validate Telegram WebApp initData and return the authenticated user."""
    if not init_data or not config.BOT_TOKEN:
        return None
    values = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    supplied_hash = next((value for key, value in values if key == "hash"), "")
    if not supplied_hash:
        return None
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(values) if key != "hash")
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_hash):
        return None
    parsed = dict(values)
    try:
        auth_date = int(parsed.get("auth_date", "0"))
        if abs((now or int(time.time())) - auth_date) > MAX_INIT_DATA_AGE:
            return None
        user = json.loads(parsed.get("user", "{}"))
        user["id"] = int(user["id"])
        return user
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


class WebAppHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEBAPP_DIR, **kwargs)

    def _json(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' https://telegram.org; script-src 'self' 'unsafe-inline' https://telegram.org; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _principal(self):
        return validate_telegram_init_data(self.headers.get("X-Telegram-Init-Data", ""))

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid content length")
        if length <= 0 or length > MAX_REQUEST_BODY:
            raise ValueError("request body too large or empty")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        if self.path.startswith("/webapp/"):
            self.path = self.path[len("/webapp"):]
        # Se la richiesta chiama direttamente /index.html, /pubblica.html, /dashboard.html, reindirizza a /webapp/
        if self.path in ("/", "/index.html"):
            self.path = "/index.html"
        elif self.path.startswith("/pubblica.html"):
            self.path = self.path
        elif self.path.startswith("/dashboard.html"):
            self.path = "/webapp" + self.path
        elif self.path.startswith("/manuale_candidati.html"):
            self.path = "/webapp" + self.path
        elif self.path.startswith("/manuale_datori.html"):
            self.path = "/webapp" + self.path

        if self.path.startswith("/api/get_profile"):
            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                principal = self._principal()
                if not principal:
                    return self._json(401, {"status": "error", "error": "unauthorized"})
                user_id = int(params.get("user_id", [principal["id"]])[0])
                if user_id != principal["id"] and principal["id"] not in config.ADMIN_IDS:
                    return self._json(403, {"status": "error", "error": "forbidden"})

                profile = db.get_candidate_profile(user_id)
                if profile:
                    res = {
                        "status": "ok",
                        "profile": {
                            "user_id": profile["user_id"],
                            "first_name": profile.get("first_name", ""),
                            "username": profile.get("username", ""),
                            "roles": json.loads(profile["roles"]) if profile.get("roles") else [],
                            "skills": json.loads(profile["skills"]) if profile.get("skills") else [],
                            "experience": profile.get("experience", ""),
                            "availability": json.loads(profile["availability"]) if profile.get("availability") else [],
                            "zones": json.loads(profile["zones"]) if profile.get("zones") else [],
                            "phone": profile.get("phone", ""),
                            "bio": profile.get("bio", ""),
                            "is_premium": profile.get("is_premium", 0)
                        }
                    }
                else:
                    res = {"status": "not_found"}

                return self._json(200, res)
            except Exception as e:
                logger.error(f"Errore GET profile API: {e}")

        if self.path.startswith("/api/get_job_offer"):
            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                principal = self._principal()
                if not principal:
                    return self._json(401, {"status": "error", "error": "unauthorized"})
                job_id = int(params.get("job_id", [0])[0])

                job = db.get_job_offer(job_id) if job_id > 0 else None

                if job and (job["user_id"] == principal["id"] or principal["id"] in config.ADMIN_IDS):
                    res = {
                        "status": "ok",
                        "job": {
                            "job_id": job["job_id"],
                            "user_id": job["user_id"],
                            "username": job["username"],
                            "business_name": job["business_name"],
                            "role": job["role"],
                            "zone": job["zone"],
                            "shift": job["shift"],
                            "salary": job["salary"],
                            "description": job["description"],
                            "contact": job["contact"],
                            "package": job["package"],
                            "message_id": job["message_id"] if "message_id" in job.keys() else None
                        }
                    }
                else:
                    res = {"status": "not_found"}

                return self._json(200, res)
            except Exception as e:
                logger.error(f"Errore GET job_offer API: {e}")

        if self.path.startswith("/api/get_employer_candidates"):


            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                principal = self._principal()
                if not principal:
                    return self._json(401, {"status": "error", "error": "unauthorized"})
                job_id = int(params.get("job_id", [0])[0])

                job = db.get_job_offer(job_id)
                candidates_res = []

                if job and (job["user_id"] == principal["id"] or principal["id"] in config.ADMIN_IDS):
                    import matcher
                    job_text = f"{job['business_name']} - {job['role']} {job['description']}"
                    matches = matcher.get_matching_candidates(job_text, min_score=40)

                    # Recupera anche eventuali risposte pre-screening inoltrate
                    apps = db.get_job_applications(job_id)
                    app_dict = {a["candidate_id"]: a for a in apps}

                    for c in matches:
                        uid = c["user_id"]
                        is_prem = db.is_user_premium(uid)
                        app_data = app_dict.get(uid)

                        cand_obj = {
                            "user_id": uid,
                            "first_name": c.get("first_name", "Candidato"),
                            "username": c.get("username", ""),
                            "phone": c.get("phone", ""),
                            "experience": c.get("experience", ""),
                            "roles": json.loads(c.get("roles", "[]")) if c.get("roles") else [],
                            "skills": json.loads(c.get("skills", "[]")) if c.get("skills") else [],
                            "match_score": c.get("match_score", 50),
                            "is_premium": is_prem,
                            "application_status": app_data["status"] if app_data else "nessuna",
                            "screening_q1": app_data["screening_q1"] if app_data else "In attesa candidatura",
                            "screening_q2": app_data["screening_q2"] if app_data else ""
                        }
                        candidates_res.append(cand_obj)

                    # Priorità ordinamento:
                    # 1. Candidati che si sono CANDIDATI attivamente via Pre-screening (Prima Premium ⭐, poi Free ⚪)
                    # 2. Altri candidati registrati in target nel DB (Prima Premium ⭐, poi Free ⚪)
                    candidates_res.sort(key=lambda x: (
                        x["application_status"] == "nessuna",
                        not x["is_premium"],
                        -x["match_score"]
                    ))


                return self._json(200, {"status": "ok", "candidates": candidates_res})
            except Exception as e:
                logger.error(f"Errore GET candidati API: {e}")

        if self.path.startswith("/api/"):
            return self._json(404, {"status": "error", "error": "not_found"})
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/save_profile":
            try:
                principal = self._principal()
                if not principal:
                    return self._json(401, {"status": "error", "error": "unauthorized"})
                data = self._read_json()
                user_id = principal["id"]
                if user_id:
                    roles = json.dumps(data.get("roles", []))
                    skills = json.dumps(data.get("skills", []))
                    experience = data.get("experience", "")
                    availability = json.dumps(data.get("availability", []))
                    zones = json.dumps(data.get("zones", []))
                    phone = data.get("phone", "")
                    bio = data.get("bio", "")

                    db.save_candidate_profile(
                        user_id=int(user_id),
                        username=principal.get("username", ""),
                        first_name=principal.get("first_name", ""),
                        roles=roles,
                        skills=skills,
                        experience=experience,
                        availability=availability,
                        zones=zones,
                        phone=phone,
                        bio=bio
                    )
                    logger.info(f"✅ Profilo candidato salvato via API per user_id {user_id}")

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
                    return
            except Exception as e:
                logger.error(f"Errore salvataggio API: {e}")

            self.send_response(400)
            self.end_headers()
            return

        elif self.path == "/api/update_application_status":
            try:
                principal = self._principal()
                if not principal:
                    return self._json(401, {"status": "error", "error": "unauthorized"})
                data = self._read_json()
                app_id = data.get("app_id")
                new_status = data.get("status")
                if app_id and new_status in {"interview", "rejected"} and db.application_owned_by(int(app_id), principal["id"]):
                    db.update_application_status(int(app_id), str(new_status))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
                    return
            except Exception as e:
                logger.error(f"Errore update status API: {e}")

            self.send_response(400)
            self.end_headers()
            return

        elif self.path.startswith("/api/update_job_offer"):
            try:
                principal = self._principal()
                if not principal:
                    return self._json(401, {"status": "error", "error": "unauthorized"})
                data = self._read_json()
                job_id = data.get("job_id")
                if job_id:
                    job_id = int(job_id)
                    existing_job = db.get_job_offer(job_id)
                    if not existing_job:
                        raise ValueError(f"Offerta #{job_id} inesistente")
                    if existing_job["user_id"] != principal["id"] and principal["id"] not in config.ADMIN_IDS:
                        return self._json(403, {"status": "error", "error": "forbidden"})
                    db.update_job_offer(
                        job_id=job_id,
                        business_name=data.get("business_name", ""),
                        role=data.get("role", ""),
                        zone=data.get("zone", ""),
                        shift=data.get("shift", ""),
                        salary=data.get("salary", ""),
                        description=data.get("description", ""),
                        # L'identità Telegram non può essere sostituita da questa API.
                        contact=existing_job["contact"]
                    )
                    db.record_security_event(
                        event_type="api_offer_update",
                        user_id=existing_job["user_id"],
                        username=existing_job["username"] or "",
                        visible_text=existing_job["contact"] or "",
                        target=f"tg://user?id={existing_job['user_id']}",
                        details=f"Offerta #{job_id} aggiornata; contatto identità preservato.",
                    )
                    logger.info(f"✅ Annuncio #{job_id} aggiornato via API")

                    # Sincronizza immediatamente il messaggio nel gruppo Telegram via HTTP Direct Request (Zero Asyncio Overhead)
                    job = db.get_job_offer(job_id)
                    if job and config.BOT_TOKEN and config.GROUP_ID != 0:
                        msg_id = job["message_id"] if "message_id" in job.keys() else None
                        
                        # Se message_id non è ancora salvato nel DB per questo annuncio, tenta di recuperare l'ID del messaggio pinnato
                        if not msg_id:
                            try:
                                get_pin_url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/getChat?chat_id={config.GROUP_ID}"
                                with urllib.request.urlopen(get_pin_url) as p_resp:
                                    chat_data = json.loads(p_resp.read().decode('utf-8'))
                                    if chat_data.get("ok") and "pinned_message" in chat_data["result"]:
                                        msg_id = chat_data["result"]["pinned_message"]["message_id"]
                                        db.update_job_offer_message_id(job_id, msg_id)
                            except Exception:
                                logger.warning("Impossibile recuperare pinned_message via HTTP")

                        if msg_id:
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
                                f"🏪 *LOCALE:* {escape_telegram_markdown(job['business_name'].upper())}\n"
                                f"💼 *Ruolo Cercato:* {escape_telegram_markdown(job['role'])}\n"
                                f"📍 *Zona:* {escape_telegram_markdown(job['zone'])}\n"
                                f"⏰ *Turni:* {escape_telegram_markdown(job['shift'])}\n"
                                f"💰 *Paga:* {escape_telegram_markdown(job['salary'] if job['salary'] else 'Trattabile')}\n\n"
                                f"📝 *Descrizione & Requisiti:*\n_{escape_telegram_markdown(job['description'])}_\n\n"
                                f"📞 *Contatto Candidature:* {escape_telegram_markdown(job['contact'])}\n"
                                f"👤 *Pubblicato da:* "
                                f"[{'@' + job['username'] if job['username'] else 'Profilo Telegram verificato'}]"
                                f"(tg://user?id={job['user_id']})\n"
                                f"✏️ _(Annuncio Aggiornato dal Datore)_"
                            )

                            edit_url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/editMessageText"
                            payload_md = {
                                "chat_id": config.GROUP_ID,
                                "message_id": msg_id,
                                "text": updated_text,
                                "parse_mode": "Markdown"
                            }
                            req_md = urllib.request.Request(edit_url, data=json.dumps(payload_md).encode('utf-8'), headers={'Content-Type': 'application/json'})
                            try:
                                with urllib.request.urlopen(req_md) as resp_md:
                                    logger.info(f"✅ Messaggio Telegram #{msg_id} modificato con successo nel gruppo per job #{job_id}")
                            except Exception:
                                logger.warning(f"Fallback Markdown fallito per job #{job_id}. Invio in Plain Text...")
                                if pkg == "evidenza":
                                    plain_header = "🔝 OFFERTA IN EVIDENZA (SPONSOR 24H) 🔝"
                                elif pkg == "vip":
                                    plain_header = "👑 SPONSOR VIP (7 GIORNI IN CIMA) 👑"
                                elif pkg == "vip_mensile":
                                    plain_header = "💎 SPONSOR VIP MENSILE (30 GIORNI IN CIMA) 💎"
                                else:
                                    plain_header = "📢 OFFERTA DI LAVORO"
                                plain_text = (
                                    f"{plain_header}\n\n"
                                    f"LOCALE: {job['business_name'].upper()}\n"
                                    f"Ruolo Cercato: {job['role']}\n"
                                    f"Zona: {job['zone']}\n"
                                    f"Turni: {job['shift']}\n"
                                    f"Paga: {job['salary'] if job['salary'] else 'Trattabile'}\n\n"
                                    f"Descrizione & Requisiti:\n{job['description']}\n\n"
                                    f"Contatto Candidature: {job['contact']}\n"
                                    f"Pubblicato da: ID Telegram verificato {job['user_id']}\n"
                                    f"(Annuncio Aggiornato dal Datore)"
                                )
                                payload_plain = {
                                    "chat_id": config.GROUP_ID,
                                    "message_id": msg_id,
                                    "text": plain_text
                                }
                                req_plain = urllib.request.Request(edit_url, data=json.dumps(payload_plain).encode('utf-8'), headers={'Content-Type': 'application/json'})
                                try:
                                    with urllib.request.urlopen(req_plain) as resp_plain:
                                        logger.info(f"✅ Messaggio Telegram #{msg_id} modificato in Plain Text per job #{job_id}")
                                except Exception:
                                    logger.error(f"❌ Impossibile aggiornare messaggio #{msg_id} in Plain Text")


                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
                    return
            except Exception as e:
                logger.error(f"Errore update_job_offer API: {e}")

            self.send_response(400)
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()



    def log_message(self, format, *args):
        # Disattiva log rumorosi per le richieste HTTP
        pass



def start_web_server(port: int = None):
    if port is None:
        port = int(os.getenv("PORT", 8080))

    def run_server():
        try:
            handler = WebAppHTTPRequestHandler
            with http.server.ThreadingHTTPServer(("0.0.0.0", port), handler) as httpd:
                logger.info(f"🌐 Server WebApp in ascolto sulla porta {port}")
                httpd.serve_forever()
        except Exception as e:
            logger.error(f"Errore avvio server WebApp: {e}")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread
