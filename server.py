import os
import http.server
import socketserver
import threading
import logging

import json
import database as db

logger = logging.getLogger(__name__)

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")


class WebAppHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEBAPP_DIR, **kwargs)

    def do_GET(self):
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

                    # Ordina con PREMIUM IN CIMA
                    candidates_res.sort(key=lambda x: (not x["is_premium"], -x["match_score"]))

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
