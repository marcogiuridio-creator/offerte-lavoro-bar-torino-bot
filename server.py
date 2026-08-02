import os
import http.server
import socketserver
import threading
import logging

import json
import database as db

logger = logging.getLogger(__name__)

BOT_DIR = os.path.dirname(__file__)


class WebAppHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BOT_DIR, **kwargs)

    def do_GET(self):
        # Se la richiesta chiama direttamente /index.html, /pubblica.html, /dashboard.html, reindirizza a /webapp/
        if self.path in ("/", "/index.html"):
            self.path = "/webapp/index.html"
        elif self.path.startswith("/pubblica.html"):
            self.path = "/webapp" + self.path
        elif self.path.startswith("/dashboard.html"):
            self.path = "/webapp" + self.path

        if self.path.startswith("/api/get_profile"):
            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                user_id = int(params.get("user_id", [0])[0])

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

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))
                return
            except Exception as e:
                logger.error(f"Errore GET profile API: {e}")

        if self.path.startswith("/api/get_job_offer"):
            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                job_id = int(params.get("job_id", [0])[0])

                job = db.get_job_offer(job_id) if job_id > 0 else None

                if job:
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

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(res).encode('utf-8'))
                return
            except Exception as e:
                logger.error(f"Errore GET job_offer API: {e}")

        if self.path.startswith("/api/get_employer_candidates"):


            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                job_id = int(params.get("job_id", [0])[0])

                job = db.get_job_offer(job_id)
                candidates_res = []

                if job:
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


                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "candidates": candidates_res}).encode('utf-8'))
                return
            except Exception as e:
                logger.error(f"Errore GET candidati API: {e}")

        super().do_GET()

    def do_POST(self):
        if self.path == "/api/save_profile":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                user_id = data.get("user_id")
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
                        username=data.get("username", ""),
                        first_name=data.get("first_name", ""),
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
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                app_id = data.get("app_id")
                new_status = data.get("status")
                if app_id and new_status:
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

        elif self.path == "/api/update_job_offer":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                job_id = data.get("job_id")
                if job_id:
                    job_id = int(job_id)
                    db.update_job_offer(
                        job_id=job_id,
                        business_name=data.get("business_name", ""),
                        role=data.get("role", ""),
                        zone=data.get("zone", ""),
                        shift=data.get("shift", ""),
                        salary=data.get("salary", ""),
                        description=data.get("description", ""),
                        contact=data.get("contact", "")
                    )
                    logger.info(f"✅ Annuncio #{job_id} aggiornato via API")

                    # Se presente o recuperabile un message_id nel gruppo, aggiorna anche il testo nel gruppo Telegram!
                    job = db.get_job_offer(job_id)
                    if job:
                        import config
                        from telegram import Bot
                        from telegram.constants import ParseMode
                        if config.BOT_TOKEN and config.GROUP_ID != 0:
                            import asyncio
                            async def update_tg_msg():
                                try:
                                    async with Bot(token=config.BOT_TOKEN) as bot:
                                        msg_id = job.get("message_id")

                                        # Se message_id è nullo nel DB, tenta il recupero del messaggio pinnato nel gruppo
                                        if not msg_id:
                                            try:
                                                chat = await bot.get_chat(chat_id=config.GROUP_ID)
                                                if chat.pinned_message:
                                                    msg_id = chat.pinned_message.message_id
                                                    db.update_job_offer_message_id(job_id, msg_id)
                                            except Exception as e_pin:
                                                logger.warning(f"Impossibile recuperare messaggio pinnato: {e_pin}")

                                        if msg_id:
                                            pkg = job["package"]
                                            header = "📢 *OFFERTA DI LAVORO*" if pkg == "free" else ("🔝 *OFFERTA IN EVIDENZA (SPONSOR 24H)* 🔝" if pkg == "evidenza" else "👑 *SPONSOR VIP (7 GIORNI IN CIMA)* 👑")
                                            updated_text = (
                                                f"{header}\n\n"
                                                f"🏪 *LOCALE:* {job['business_name'].upper()}\n"
                                                f"💼 *Ruolo Cercato:* {job['role']}\n"
                                                f"📍 *Zona:* {job['zone']}\n"
                                                f"⏰ *Turni:* {job['shift']}\n"
                                                f"💰 *Paga:* {job['salary'] if job['salary'] else 'Trattabile'}\n\n"
                                                f"📝 *Descrizione & Requisiti:*\n_{job['description']}_\n\n"
                                                f"📞 *Contatto Candidature:* {job['contact']}\n"
                                                f"👤 *Pubblicato da:* @{job['username'] if job['username'] else 'Datore'}\n"
                                                f"✏️ _(Annuncio Aggiornato dal Datore)_"
                                            )
                                            try:
                                                await bot.edit_message_text(
                                                    chat_id=config.GROUP_ID,
                                                    message_id=msg_id,
                                                    text=updated_text,
                                                    parse_mode=ParseMode.MARKDOWN
                                                )
                                                logger.info(f"✅ Messaggio Telegram #{msg_id} modificato con successo nel gruppo per job #{job_id}")
                                            except Exception as e_md:
                                                logger.warning(f"Fallback Markdown fallito per job #{job_id}: {e_md}. Invio in formato testo semplice...")
                                                plain_header = "📢 OFFERTA DI LAVORO" if pkg == "free" else ("🔝 OFFERTA IN EVIDENZA (SPONSOR 24H) 🔝" if pkg == "evidenza" else "👑 SPONSOR VIP (7 GIORNI IN CIMA) 👑")
                                                plain_text = (
                                                    f"{plain_header}\n\n"
                                                    f"LOCALE: {job['business_name'].upper()}\n"
                                                    f"Ruolo Cercato: {job['role']}\n"
                                                    f"Zona: {job['zone']}\n"
                                                    f"Turni: {job['shift']}\n"
                                                    f"Paga: {job['salary'] if job['salary'] else 'Trattabile'}\n\n"
                                                    f"Descrizione & Requisiti:\n{job['description']}\n\n"
                                                    f"Contatto Candidature: {job['contact']}\n"
                                                    f"Pubblicato da: @{job['username'] if job['username'] else 'Datore'}\n"
                                                    f"(Annuncio Aggiornato dal Datore)"
                                                )
                                                await bot.edit_message_text(
                                                    chat_id=config.GROUP_ID,
                                                    message_id=msg_id,
                                                    text=plain_text
                                                )
                                                logger.info(f"✅ Messaggio Telegram #{msg_id} modificato in formato testo semplice per job #{job_id}")
                                except Exception as e_tg:
                                    logger.warning(f"Impossibile aggiornare messaggio Telegram per job #{job_id}: {e_tg}")

                            asyncio.run(update_tg_msg())

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
            with socketserver.TCPServer(("0.0.0.0", port), handler) as httpd:
                logger.info(f"🌐 Server WebApp in ascolto sulla porta {port}")
                httpd.serve_forever()
        except Exception as e:
            logger.error(f"Errore avvio server WebApp: {e}")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread
