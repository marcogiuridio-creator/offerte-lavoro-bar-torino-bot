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
