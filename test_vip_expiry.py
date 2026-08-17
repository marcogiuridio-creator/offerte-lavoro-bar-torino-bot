import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot
import database as db


class VipDatabaseExpiryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "test.db")
        self.db_patch = patch.object(db, "DB_PATH", self.db_path)
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.tempdir.cleanup()

    def insert_vip(self, created_at, package="vip", message_id=100):
        with db.get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO job_offers
                   (user_id, business_name, role, zone, shift, description,
                    contact, package, is_verified, created_at, message_id)
                   VALUES (1, 'Locale', 'Barista', 'Centro', 'Giorno', 'Test',
                           '@locale', ?, 1, ?, ?)""",
                (package, created_at.isoformat(sep=" ", timespec="seconds"), message_id),
            )
            return cursor.lastrowid

    def test_vip_is_active_until_but_not_at_seven_day_deadline(self):
        now = datetime(2026, 8, 17, 12, 0, 0)
        active_id = self.insert_vip(now - timedelta(days=7) + timedelta(seconds=1))
        expired_id = self.insert_vip(now - timedelta(days=7), message_id=101)

        self.assertEqual([j["job_id"] for j in db.get_active_vip_jobs(now)], [active_id])
        self.assertEqual([j["job_id"] for j in db.get_expired_vip_jobs(now)], [expired_id])

    def test_marked_promotion_is_not_processed_again(self):
        now = datetime(2026, 8, 17, 12, 0, 0)
        job_id = self.insert_vip(now - timedelta(days=8))
        db.mark_vip_promotion_ended(job_id, now)
        self.assertEqual(db.get_expired_vip_jobs(now), [])


class VipPromotionProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_post_is_unpinned_not_deleted_or_reposted(self):
        telegram_bot = SimpleNamespace(
            unpin_chat_message=AsyncMock(),
            delete_message=AsyncMock(),
            send_message=AsyncMock(),
        )
        application = SimpleNamespace(bot=telegram_bot)
        expired = {"job_id": 7, "message_id": 321, "package": "vip"}

        with patch.object(bot.config, "GROUP_ID", -100123), \
             patch.object(bot.db, "get_expired_vip_jobs", return_value=[expired]), \
             patch.object(bot.db, "get_active_vip_jobs", return_value=[]), \
             patch.object(bot.db, "mark_vip_promotion_ended") as mark_ended:
            await bot.process_vip_promotions(application)

        telegram_bot.unpin_chat_message.assert_awaited_once_with(
            chat_id=-100123,
            message_id=321,
        )
        telegram_bot.delete_message.assert_not_awaited()
        telegram_bot.send_message.assert_not_awaited()
        mark_ended.assert_called_once_with(7)


if __name__ == "__main__":
    unittest.main()
