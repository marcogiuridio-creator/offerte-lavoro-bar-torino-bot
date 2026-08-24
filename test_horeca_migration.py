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


if __name__ == "__main__":
    unittest.main()
