import asyncio
import unittest
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


def make_update():
    message = SimpleNamespace(
        message_id=321,
        text="Cercasi barista full-time in centro con esperienza",
        caption=None,
    )
    user = SimpleNamespace(id=12345, username="datoretorino")
    chat = SimpleNamespace(id=-100987, type="supergroup")
    return SimpleNamespace(message=message, effective_user=user, effective_chat=chat)


class ManualOfferInviteTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_invite_does_not_post_in_group(self):
        telegram_bot = SimpleNamespace(
            send_message=AsyncMock(return_value=SimpleNamespace()),
            get_me=AsyncMock(),
        )
        context = SimpleNamespace(bot=telegram_bot)

        await bot.invite_manual_offer_author(make_update(), context)

        telegram_bot.send_message.assert_awaited_once()
        private_call = telegram_bot.send_message.await_args
        self.assertEqual(private_call.kwargs["chat_id"], 12345)
        self.assertEqual(private_call.kwargs["text"], bot.MANUAL_OFFER_INVITE)
        button = private_call.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "🚀 Completa gratuitamente l’annuncio")
        params = parse_qs(urlparse(button.web_app.url).query)
        self.assertEqual(params["prefill"], ["manual"])
        self.assertEqual(params["role"], ["Barista"])
        self.assertEqual(params["zone"], ["Centro"])
        self.assertEqual(params["shift"], ["Full-time"])
        self.assertEqual(params["contact"], ["@datoretorino"])
        telegram_bot.get_me.assert_not_awaited()

    def test_prefill_maps_combined_form_options(self):
        user = SimpleNamespace(id=55, username="locale")
        url = bot.build_manual_offer_prefill_url(
            "Cerchiamo aiuto cuoco serale a San Donato", user
        )
        params = parse_qs(urlparse(url).query)
        self.assertEqual(params["role"], ["Cuoco / Aiuto Cuoco"])
        self.assertEqual(params["zone"], ["San Donato / Cit Turin"])
        self.assertEqual(params["shift"], ["Turno Serale / Notturno"])

    async def test_failed_private_invite_posts_temporary_deep_link_reply(self):
        temp_message = SimpleNamespace(delete=AsyncMock())
        telegram_bot = SimpleNamespace(
            send_message=AsyncMock(side_effect=[RuntimeError("private chat unavailable"), temp_message]),
            get_me=AsyncMock(return_value=SimpleNamespace(username="lavorotorinobot")),
        )
        context = SimpleNamespace(bot=telegram_bot)

        async def no_wait(_seconds):
            return None

        created_tasks = []

        def capture_task(coro):
            task = asyncio.get_running_loop().create_task(coro)
            created_tasks.append(task)
            return task

        with patch("bot.asyncio.sleep", new=no_wait), patch("bot.asyncio.create_task", side_effect=capture_task):
            await bot.invite_manual_offer_author(make_update(), context)
            await asyncio.gather(*created_tasks)

        fallback_call = telegram_bot.send_message.await_args_list[1]
        self.assertEqual(fallback_call.kwargs["chat_id"], -100987)
        self.assertEqual(fallback_call.kwargs["reply_to_message_id"], 321)
        button = fallback_call.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "📢 Pubblica con il bot")
        self.assertEqual(button.url, "https://t.me/lavorotorinobot?start=pubblica")
        temp_message.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
