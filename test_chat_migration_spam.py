import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class FakeMessage:
    def __init__(self):
        self.text = (
            "‼️ This сhat is moving to a nеw one beсausе wе have lost "
            "аccess to the administrator's account. Join thе new сhat"
        )
        self.caption = None
        self.from_user = SimpleNamespace(
            id=1803516751, username="Mxx55z", first_name="MX", last_name="", is_bot=False
        )
        self.sender_business_bot = SimpleNamespace(
            id=8653511602,
            username="kingofkingsinteligente_bot",
            first_name="🌙🌙",
            last_name="",
            is_bot=True,
        )
        self.via_bot = None
        self.chat_id = -1001456564882
        self.message_id = 625
        self.delete = AsyncMock()

    def parse_entities(self):
        return {}

    def parse_caption_entities(self):
        return {}


class ChatMigrationDetectionTests(unittest.TestCase):
    def test_detects_campaign_with_cyrillic_homographs(self):
        self.assertTrue(bot.is_forbidden_chat_migration_ad(FakeMessage().text))

    def test_detects_italian_chat_move_campaign(self):
        self.assertTrue(bot.is_forbidden_chat_migration_ad(
            "Abbiamo perso l'accesso all'account amministratore. Clicca per unirti alla nuova chat"
        ))

    def test_does_not_block_ordinary_chat_discussion(self):
        self.assertFalse(bot.is_forbidden_chat_migration_ad(
            "La chat di lavoro funziona regolarmente: non cliccate link sospetti."
        ))


class ChatMigrationModerationTests(unittest.IsolatedAsyncioTestCase):
    @patch("bot.db.record_security_event")
    @patch("bot.db.record_spam_blocked")
    @patch("bot.db.ban_user")
    @patch("bot.db.upsert_user")
    async def test_deletes_and_bans_business_account_and_sender_bot(
        self, upsert_user, ban_user, record_spam_blocked, record_security_event
    ):
        message = FakeMessage()
        telegram_bot = SimpleNamespace(
            id=8746458534,
            ban_chat_member=AsyncMock(),
            send_message=AsyncMock(),
        )
        context = SimpleNamespace(bot=telegram_bot)

        await bot.block_forbidden_chat_migration(message, context)

        message.delete.assert_awaited_once()
        self.assertEqual(
            [call.kwargs["user_id"] for call in telegram_bot.ban_chat_member.await_args_list],
            [1803516751, 8653511602],
        )
        self.assertEqual([call.args[0] for call in ban_user.call_args_list], [1803516751, 8653511602])
        self.assertEqual(upsert_user.call_count, 2)
        record_spam_blocked.assert_called_once_with()
        self.assertEqual(
            record_security_event.call_args.kwargs["event_type"],
            "forbidden_chat_migration",
        )


if __name__ == "__main__":
    unittest.main()
