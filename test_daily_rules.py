import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import bot


class DailyRulesScheduleTests(unittest.TestCase):
    def test_before_eleven_schedules_same_day(self):
        now = datetime(2026, 8, 13, 10, 30, tzinfo=ZoneInfo("Europe/Rome"))
        self.assertEqual(bot.seconds_until_daily_summary(now), 30 * 60)

    def test_after_eleven_schedules_next_day(self):
        now = datetime(2026, 8, 13, 11, 1, tzinfo=ZoneInfo("Europe/Rome"))
        self.assertEqual(bot.seconds_until_daily_summary(now), 23 * 3600 + 59 * 60)


class DailyRulesPublishTests(unittest.IsolatedAsyncioTestCase):
    async def test_replaces_previous_message_and_pins_silently(self):
        new_message = SimpleNamespace(message_id=222)
        telegram_bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username="lavorotorinobot")),
            delete_message=AsyncMock(),
            send_message=AsyncMock(return_value=new_message),
            pin_chat_message=AsyncMock(),
        )
        application = SimpleNamespace(bot=telegram_bot)

        with patch("bot.config.GROUP_ID", -100123), patch("bot.db.get_setting", return_value="111"), patch("bot.db.set_setting") as set_setting:
            result = await bot.publish_daily_rules_summary(application)

        self.assertIs(result, new_message)
        telegram_bot.delete_message.assert_awaited_once_with(chat_id=-100123, message_id=111)
        send_call = telegram_bot.send_message.await_args
        self.assertTrue(send_call.kwargs["disable_notification"])
        self.assertIn("CERCHI PERSONALE", send_call.kwargs["text"])
        urls = [row[0].url for row in send_call.kwargs["reply_markup"].inline_keyboard]
        self.assertEqual(urls[-1], "https://t.me/lavorotorinobot?start=regole")
        set_setting.assert_called_once_with("daily_rules_message_id", 222)
        telegram_bot.pin_chat_message.assert_awaited_once_with(
            chat_id=-100123,
            message_id=222,
            disable_notification=True,
        )

    async def test_first_start_publishes_rules_when_no_message_is_saved(self):
        application = SimpleNamespace(bot=SimpleNamespace(set_my_commands=AsyncMock()))
        created_coroutines = []

        def close_background(coro):
            created_coroutines.append(coro)
            coro.close()
            return SimpleNamespace()

        with patch("bot.asyncio.create_task", side_effect=close_background), patch("bot.db.get_setting", return_value=None), patch("bot.publish_daily_rules_summary", new=AsyncMock()) as publish:
            await bot.post_init(application)
        publish.assert_awaited_once_with(application)
        self.assertEqual(len(created_coroutines), 2)


if __name__ == "__main__":
    unittest.main()
