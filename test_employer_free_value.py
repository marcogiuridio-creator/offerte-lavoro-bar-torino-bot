import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class FreeEmployerValueTests(unittest.IsolatedAsyncioTestCase):
    async def test_compatible_candidate_preview_and_dashboard(self):
        telegram_bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(bot=telegram_bot)
        user = SimpleNamespace(id=77)
        matches = [{
            "user_id": 9,
            "first_name": "Anna",
            "roles": '["Barista"]',
            "match_score": 85,
        }]
        with patch("bot.matcher.get_matching_candidates", return_value=matches), patch("bot.db.is_user_premium", return_value=True):
            await bot.send_free_employer_preview(context, user, 42, "Cerco barista")

        call = telegram_bot.send_message.await_args
        self.assertEqual(call.kwargs["chat_id"], 77)
        self.assertIn("1 profili", call.kwargs["text"])
        self.assertIn("Anna", call.kwargs["text"])
        button = call.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertIn("job_id=42", button.web_app.url)
        self.assertIn("user_id=77", button.web_app.url)


if __name__ == "__main__":
    unittest.main()
