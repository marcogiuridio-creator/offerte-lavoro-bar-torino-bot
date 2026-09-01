import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "horeca" / "database" / "export_sqlite.py"
SPEC = importlib.util.spec_from_file_location("export_sqlite", MODULE_PATH)
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)
BUILD_SPEC = importlib.util.spec_from_file_location(
    "build_horeca", Path(__file__).parent / "horeca" / "build_package.py"
)
BUILDER = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(BUILDER)
SQL_SPEC = importlib.util.spec_from_file_location(
    "json_to_mysql_sql", Path(__file__).parent / "horeca" / "database" / "json_to_mysql_sql.py"
)
SQL_EXPORTER = importlib.util.module_from_spec(SQL_SPEC)
SQL_SPEC.loader.exec_module(SQL_EXPORTER)


class HorecaMigrationTests(unittest.TestCase):
    def test_export_is_complete_deterministic_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.db"
            output = Path(tmp) / "export.json"
            with sqlite3.connect(source) as conn:
                for table in EXPORTER.TABLES:
                    conn.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, value TEXT)')
                    conn.execute(f'INSERT INTO "{table}" (id,value) VALUES (1,?)', (table,))
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            report = EXPORTER.export_database(source, output)
            after = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = json.loads(output.read_text())
            self.assertEqual(before, after)
            self.assertEqual(report["integrity"], "ok")
            self.assertEqual(set(payload["tables"]), set(EXPORTER.TABLES))
            self.assertTrue(all(value == 1 for value in report["counts"].values()))
            self.assertEqual(report["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())

    def test_schema_has_all_source_tables_and_update_deduplication(self):
        schema = (Path(__file__).parent / "horeca" / "database" / "schema.sql").read_text()
        for table in EXPORTER.TABLES + ("telegram_updates", "application_sessions"):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", schema)
        self.assertIn("promotion_expires_at", schema)
        self.assertIn("last_bumped_at", schema)
        migration = (Path(__file__).parent / "horeca" / "database" / "migrate_paid_promotions.sql").read_text()
        self.assertIn("ALTER TABLE job_offers", migration)

    def test_aruba_webhook_converts_manual_offers_with_safe_rollback(self):
        source = (Path(__file__).parent / "horeca" / "src" / "WebhookHandler.php").read_text()
        self.assertIn("handleAutomaticOffer", source)
        self.assertIn("looksLikeJobOffer", source)
        self.assertIn("OFFERTA ORGANIZZATA AUTOMATICAMENTE DAL BOT", source)
        publish = source.index("$this->telegram->call('sendMessage'", source.index("handleAutomaticOffer"))
        delete_original = source.index("$this->telegram->call('deleteMessage'", publish)
        attach = source.index("$repository->attachMessage", delete_original)
        self.assertLess(publish, delete_original)
        self.assertLess(delete_original, attach)
        self.assertIn("$repository->rollbackFreeJob", source[attach:])

    def test_aruba_manual_offer_recognition_covers_common_employer_language(self):
        source = (Path(__file__).parent / "horeca" / "src" / "WebhookHandler.php").read_text()
        for marker in ("si\\\\s+cerca", "stiamo\\\\s+cercando", "abbiamo\\\\s+bisogno", "barback", "runner", "receptionist"):
            self.assertIn(marker, source)
        self.assertIn("automatic_rate_hours", source)
        self.assertIn("automatic_daily_max", source)

    def test_aruba_group_commands_are_deleted_after_seven_seconds(self):
        source = (Path(__file__).parent / "horeca" / "src" / "WebhookHandler.php").read_text()
        self.assertIn("deleteGroupCommandAfterDelay", source)
        self.assertIn("usleep(7_000_000)", source)
        self.assertIn("$mustDeleteGroupCommand", source)
        self.assertIn("} finally {", source)
        dispatch = source.index("try {", source.index("$mustDeleteGroupCommand"))
        cleanup = source.index("$this->deleteGroupCommandAfterDelay", dispatch)
        self.assertIn("finally", source[dispatch:cleanup])
        cleanup = source.index("private function deleteGroupCommandAfterDelay")
        self.assertIn("deleteMessage", source[cleanup:])

    def test_aruba_webhook_keeps_core_profiles_offers_admin_and_stars_flows(self):
        handler = (Path(__file__).parent / "horeca" / "src" / "WebhookHandler.php").read_text()
        repository = (Path(__file__).parent / "horeca" / "src" / "HorecaRepository.php").read_text()
        for command in ("/profilo", "/mie_offerte", "/premium", "/stats"):
            self.assertIn(command, handler)
        for marker in ("pre_checkout_query", "answerPreCheckoutQuery", "successful_payment", "sendInvoice"):
            self.assertIn(marker, handler)
        self.assertIn("premium_subscription_stars", handler)

    def test_publish_command_opens_private_chat_and_uses_senddata_compatible_keyboard(self):
        handler = (Path(__file__).parent / "horeca" / "src" / "WebhookHandler.php").read_text()
        self.assertIn("['pubblica', 'offerta']", handler)
        self.assertIn("sendPublishLauncher", handler)
        self.assertIn("'https://t.me/' . $username . '?start=pubblica'", handler)
        launcher = handler[handler.index("private function sendPublishLauncher"):]
        self.assertIn("'keyboard' =>", launcher)
        self.assertIn("'web_app' => ['url' => $base . '/webapp/pubblica.html']", launcher)
        self.assertNotIn("'inline_keyboard' => [[['text' => $label, 'web_app'", launcher)

    def test_aruba_paid_promotions_and_cron_are_present(self):
        root = Path(__file__).parent
        repository = (root / "horeca/src/HorecaRepository.php").read_text()
        handler = (root / "horeca/src/WebhookHandler.php").read_text()
        cron = (root / "horeca/src/CronRunner.php").read_text()
        endpoint = (root / "horeca/api/cron.php").read_text()
        for package, amount in (("evidenza", "250"), ("vip", "500"), ("vip_mensile", "1400")):
            self.assertIn(package, repository)
            self.assertIn(amount, repository)
        self.assertIn("job_offer_id_", handler)
        self.assertIn("activePremiumCandidates", handler)
        self.assertIn("dueVipBumps", cron)
        self.assertIn("daily_rules_date", cron)
        self.assertIn("X_HORECA_CRON_SECRET", endpoint.upper())
        self.assertIn("activatePremiumPayment", repository)
        self.assertIn("INSERT IGNORE INTO payment_events", repository)
        self.assertIn("DATE_ADD", repository)

    def test_aruba_package_contains_webapp_and_no_local_secrets(self):
        repository = Path(__file__).parent
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "horeca"
            BUILDER.build(repository, destination)
            self.assertTrue((destination / "api" / "telegram-webhook.php").is_file())
            self.assertTrue((destination / "webapp" / "pubblica.html").is_file())
            self.assertFalse((destination / "config" / "local.php").exists())
            dashboard = (destination / "webapp" / "dashboard.html").read_text()
            self.assertIn("/horeca/api/get_employer_candidates", dashboard)
            publish = (destination / "webapp" / "pubblica.html").read_text()
            self.assertIn("const API_BASE_URL = '/horeca';", publish)
            self.assertNotIn("offerte-lavoro-bar-torino-bot.up.railway.app", publish)

    def test_mysql_export_uses_hex_literals_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "export.json"
            destination = Path(tmp) / "import.sql"
            tables = {name: [] for name in SQL_EXPORTER.TABLE_ORDER}
            tables["users"] = [{
                "user_id": 1,
                "username": "",
                "first_name": "L'Ora",
                "joined_at": "2026-08-24T18:00:00",
            }]
            source.write_text(json.dumps({"format": 1, "tables": tables}))
            SQL_EXPORTER.convert(source, destination, "Sql1948040_5")
            sql = destination.read_text()
            self.assertTrue(sql.startswith("USE `Sql1948040_5`;"))
            self.assertIn("ON DUPLICATE KEY UPDATE", sql)
            self.assertIn("CONVERT(0x", sql)
            self.assertNotIn("0x USING", sql)
            self.assertNotIn("L'Ora", sql)
            self.assertIn("START TRANSACTION", sql)

    def test_mysql_export_rejects_unsafe_database_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "export.json"
            destination = Path(tmp) / "import.sql"
            source.write_text(json.dumps({
                "format": 1,
                "tables": {name: [] for name in SQL_EXPORTER.TABLE_ORDER},
            }))
            with self.assertRaises(ValueError):
                SQL_EXPORTER.convert(source, destination, "db`; DROP TABLE users")


if __name__ == "__main__":
    unittest.main()
