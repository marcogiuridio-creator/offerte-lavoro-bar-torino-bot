import logging
import unittest

import bot


class LoggingAndAutobumpTests(unittest.TestCase):
    def test_http_clients_do_not_log_token_bearing_urls_at_info(self):
        self.assertGreaterEqual(logging.getLogger("httpx").getEffectiveLevel(), logging.WARNING)
        self.assertGreaterEqual(logging.getLogger("httpcore").getEffectiveLevel(), logging.WARNING)

    def test_autobump_group_keyboard_uses_url_not_web_app(self):
        keyboard = bot.autobump_job_keyboard(42)
        dashboard = keyboard.inline_keyboard[1][0]
        self.assertIsNone(dashboard.web_app)
        self.assertIn("job_id=42", dashboard.url)


if __name__ == "__main__":
    unittest.main()
