import os
import http.server
import socketserver
import threading
import logging

logger = logging.getLogger(__name__)

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "webapp")


class WebAppHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEBAPP_DIR, **kwargs)

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
