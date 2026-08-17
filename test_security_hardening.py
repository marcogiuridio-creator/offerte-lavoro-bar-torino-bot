import hashlib
import hmac
import json
import os
import tempfile
import unittest
import urllib.parse
from types import SimpleNamespace

import bot
import config
import database as db
import server


class SecurityHardeningTests(unittest.TestCase):
    def setUp(self):
        self.old_path = db.DB_PATH
        self.old_token = config.BOT_TOKEN
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self.tmp.name, "test.db")
        config.BOT_TOKEN = "123456:test-secret"
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_path
        config.BOT_TOKEN = self.old_token
        self.tmp.cleanup()

    def signed_init_data(self, user_id=123, auth_date=1_700_000_000):
        values = {
            "auth_date": str(auth_date),
            "query_id": "test-query",
            "user": json.dumps({"id": user_id, "first_name": "Test", "username": "tester"}, separators=(",", ":")),
        }
        check = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
        secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return urllib.parse.urlencode(values)

    def test_telegram_init_data_signature_and_freshness(self):
        signed = self.signed_init_data()
        self.assertEqual(server.validate_telegram_init_data(signed, now=1_700_000_010)["id"], 123)
        self.assertIsNone(server.validate_telegram_init_data(signed + "x", now=1_700_000_010))
        self.assertIsNone(server.validate_telegram_init_data(signed, now=1_700_001_000))

    def test_mutable_username_never_grants_admin(self):
        self.assertFalse(bot.is_admin(SimpleNamespace(id=999999, username="marcogiuridio")))

    def test_telegram_markdown_is_escaped(self):
        self.assertEqual(bot.safe_markdown("[clicca](https://evil.example)_x*"), "\\[clicca](https://evil.example)\\_x\\*")

    def test_payment_transaction_is_idempotent(self):
        self.assertTrue(db.record_payment_once("charge-1", 123, "premium", "XTR", 100))
        self.assertFalse(db.record_payment_once("charge-1", 123, "premium", "XTR", 100))

    def test_offer_ownership_uses_numeric_id_only(self):
        db.create_job_offer(1, "shared", "Bar", "Barista", "Centro", "Full", "", "Desc", "@shared", "free")
        self.assertEqual(len(db.get_user_job_offers(2, "shared")), 0)

    def test_duplicate_application_is_idempotent(self):
        job_id = db.create_job_offer(10, "owner", "Bar", "Barista", "Centro", "Full", "", "Desc", "@owner", "free")
        first = db.save_application(job_id, 20, "candidate", 80, "yes", "yes", "")
        second = db.save_application(job_id, 20, "candidate", 80, "yes", "yes", "")
        self.assertEqual(first, second)

    def test_static_root_is_webapp_only(self):
        self.assertEqual(server.WEBAPP_DIR, os.path.join(server.BOT_DIR, "webapp"))
        self.assertFalse(os.path.commonpath([server.WEBAPP_DIR, db.DB_PATH]) == server.WEBAPP_DIR)


if __name__ == "__main__":
    unittest.main()
