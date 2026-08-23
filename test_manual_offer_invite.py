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
        self.assertIn("più visibile", private_call.kwargs["text"])
        self.assertIn("un clic", private_call.kwargs["text"])
        self.assertIn("dashboard", private_call.kwargs["text"])
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


class AutomaticManualOfferConversionTests(unittest.IsolatedAsyncioTestCase):
    def test_extracts_fields_with_safe_defaults(self):
        user = SimpleNamespace(id=12, username="datore")
        fields = bot.automatic_offer_fields(
            "Cercasi barista full-time in centro, paga 1300 euro al mese", user
        )
        self.assertEqual(fields["role"], "Barista")
        self.assertEqual(fields["zone"], "Centro")
        self.assertEqual(fields["shift"], "Full-time")
        self.assertIn("1300", fields["salary"])
        self.assertEqual(fields["business"], "Locale non specificato")
        self.assertEqual(fields["contact"], "@datore")

        no_salary = bot.automatic_offer_fields(
            "Cercasi barista, telefono 3331234567, riferimento estate 2026", user
        )
        self.assertEqual(no_salary["salary"], "")

    async def test_publishes_before_deleting_original_and_activates_features(self):
        update = make_update()
        update.message.delete = AsyncMock()
        published = SimpleNamespace(message_id=777)
        telegram_bot = SimpleNamespace(send_message=AsyncMock(return_value=published))
        context = SimpleNamespace(bot=telegram_bot)

        with patch("bot.db.create_job_offer", return_value=42) as create_job, \
             patch("bot.db.update_job_offer_message_id") as update_message_id, \
             patch("bot.db.mark_post_converted") as mark_converted, \
             patch("bot.db.record_security_event") as security_event, \
             patch("bot.matcher.notify_matched_candidates", new=AsyncMock()) as notify, \
             patch("bot.send_free_employer_preview", new=AsyncMock()) as preview:
            result = await bot.convert_manual_offer_automatically(update, context)

        self.assertTrue(result)
        create_job.assert_called_once()
        telegram_bot.send_message.assert_awaited_once()
        update_message_id.assert_called_once_with(42, 777)
        update.message.delete.assert_awaited_once()
        mark_converted.assert_called_once_with(12345, 321, 42)
        notify.assert_awaited_once()
        preview.assert_awaited_once()
        security_event.assert_called_once()
        post_call = telegram_bot.send_message.await_args
        self.assertIn("ORGANIZZATA AUTOMATICAMENTE", post_call.kwargs["text"])
        buttons = post_call.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(buttons[0][0].callback_data, "apply_start:42")
        self.assertIn("job_id=42", buttons[2][0].url)

    async def test_publish_failure_keeps_original_and_rolls_back_database(self):
        update = make_update()
        update.message.delete = AsyncMock()
        telegram_bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("Telegram unavailable")))
        context = SimpleNamespace(bot=telegram_bot)

        with patch("bot.db.create_job_offer", return_value=51), \
             patch("bot.db.delete_job_offer") as delete_job:
            result = await bot.convert_manual_offer_automatically(update, context)

        self.assertFalse(result)
        update.message.delete.assert_not_awaited()
        delete_job.assert_called_once_with(51)

    async def test_delete_failure_removes_conversion_and_rolls_back_database(self):
        update = make_update()
        update.message.delete = AsyncMock(side_effect=RuntimeError("missing delete permission"))
        telegram_bot = SimpleNamespace(
            send_message=AsyncMock(return_value=SimpleNamespace(message_id=888)),
            delete_message=AsyncMock(),
        )
        context = SimpleNamespace(bot=telegram_bot)

        with patch("bot.db.create_job_offer", return_value=61), \
             patch("bot.db.update_job_offer_message_id"), \
             patch("bot.db.delete_job_offer") as delete_job:
            result = await bot.convert_manual_offer_automatically(update, context)

        self.assertFalse(result)
        telegram_bot.delete_message.assert_awaited_once_with(chat_id=-100987, message_id=888)
        delete_job.assert_called_once_with(61)

    async def test_historical_backfill_is_idempotent_and_suppresses_notifications(self):
        rows = [{
            "message_id": 321,
            "text": "Cercasi barista full-time in centro",
            "user_id": 12345,
            "username": "datoretorino",
        }]
        application = SimpleNamespace(bot=SimpleNamespace(delete_message=AsyncMock()))
        with patch("bot.config.GROUP_ID", -100987), \
             patch("bot.db.get_setting", return_value=None), \
             patch("bot.db.get_unconverted_manual_offers", return_value=rows), \
             patch("bot.db.set_setting") as set_setting, \
             patch("bot.convert_manual_offer_automatically", new=AsyncMock(return_value=True)) as convert:
            result = await bot.convert_recent_manual_offers(application)

        self.assertEqual(result["converted"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertFalse(convert.await_args.kwargs["activate_notifications"])
        set_setting.assert_called_once_with("manual_offer_backfill_48h_v1", "complete")

    async def test_historical_backfill_does_not_repeat_after_completion(self):
        application = SimpleNamespace(bot=SimpleNamespace())
        with patch("bot.db.get_setting", return_value="complete"), \
             patch("bot.db.get_unconverted_manual_offers") as get_rows:
            result = await bot.convert_recent_manual_offers(application)

        self.assertTrue(result["already_complete"])
        get_rows.assert_not_called()


if __name__ == "__main__":
    unittest.main()
