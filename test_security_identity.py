import os
import tempfile
import unittest
from collections import namedtuple
from types import SimpleNamespace

from telegram import MessageEntity

import bot
import database as db


Entity = namedtuple("Entity", "type url")


class FakeMessage:
    def __init__(self, entities):
        self.text = "test"
        self.caption = None
        self._entities = entities

    def parse_entities(self):
        return self._entities

    def parse_caption_entities(self):
        return {}


class SecurityIdentityTests(unittest.TestCase):
    def test_author_reference_is_bound_to_numeric_telegram_id(self):
        self.assertEqual(
            bot.author_identity_markdown(12345, "datoretorino"),
            "[@datoretorino](tg://user?id=12345)",
        )

    def test_rejects_contact_pointing_to_another_telegram_user(self):
        user = SimpleNamespace(id=10, username="datoretorino")
        ok, reason = bot.validate_author_contact("@lucasm", user)
        self.assertFalse(ok)
        self.assertIn("lucasm", reason)

    def test_accepts_own_username_or_phone(self):
        user = SimpleNamespace(id=10, username="datoretorino")
        self.assertTrue(bot.validate_author_contact("@datoretorino", user)[0])
        self.assertTrue(bot.validate_author_contact("340 1234567", user)[0])

    def test_blocks_hidden_profile_link(self):
        user = SimpleNamespace(id=10, username="datoretorino")
        entity = Entity(MessageEntity.TEXT_LINK, "https://t.me/lucasm")
        result = bot.suspicious_identity_link(
            FakeMessage({entity: "Hola"}), user, "OFFERTA"
        )
        self.assertEqual(result[0], "masked_text_link")
        self.assertEqual(result[2], "https://t.me/lucasm")

    def test_blocks_visible_mismatched_username_in_offer(self):
        user = SimpleNamespace(id=10, username="datoretorino")
        entity = Entity(MessageEntity.MENTION, None)
        result = bot.suspicious_identity_link(
            FakeMessage({entity: "@lucasm"}), user, "OFFERTA"
        )
        self.assertEqual(result[0], "author_link_mismatch")

    def test_allows_own_username_in_offer(self):
        user = SimpleNamespace(id=10, username="datoretorino")
        entity = Entity(MessageEntity.MENTION, None)
        self.assertIsNone(bot.suspicious_identity_link(
            FakeMessage({entity: "@datoretorino"}), user, "OFFERTA"
        ))

    def test_blocks_visible_url_with_different_hidden_destination(self):
        user = SimpleNamespace(id=10, username="datoretorino")
        entity = Entity(MessageEntity.TEXT_LINK, "https://t.me/lucasm")
        result = bot.suspicious_identity_link(
            FakeMessage({entity: "https://t.me/datoretorino"}), user, "OFFERTA"
        )
        self.assertEqual(result[0], "masked_destination_mismatch")

    def test_security_events_are_persisted(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        old_path = db.DB_PATH
        try:
            db.DB_PATH = path
            db.init_db()
            db.record_security_event(
                "masked_text_link", user_id=10, username="hola",
                visible_text="Hola", target="https://t.me/lucasm",
            )
            event = db.get_security_events(1)[0]
            self.assertEqual(event["event_type"], "masked_text_link")
            self.assertEqual(event["user_id"], 10)
            self.assertEqual(event["target"], "https://t.me/lucasm")
        finally:
            db.DB_PATH = old_path
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
