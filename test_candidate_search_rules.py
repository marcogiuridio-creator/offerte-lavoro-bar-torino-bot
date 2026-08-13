import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot
from classifier import classify


SEARCH_MESSAGES = [
    "Cerco lavoro", "Sto cercando lavoro come barista", "Cerco impiego come cameriere",
    "Sono alla ricerca di lavoro", "Sono disponibile da subito", "Disponibile per extra",
    "Barista con esperienza disponibile", "Cameriere cerca lavoro", "Posso iniziare subito",
    "Valuto proposte di lavoro", "Qualcuno cerca un barista?", "Sapete se qualche locale assume?",
    "Dove posso mandare il curriculum?", "Ho lavorato come cuoco e cerco lavoro",
    "cerco lavorro come cameriere", "sono disponibbile per extra", "disponibile x extra",
    "I'm looking for a job as a waiter", "Available for work", "Busco trabajo de camarero",
    "Estoy disponible para trabajar", "Cerco lavoro part-time", "Cerco un'opportunità",
]

EMPLOYER_MESSAGES = [
    "Cerchiamo un cameriere disponibile da subito", "Ristorante assume cuoco con esperienza",
    "Cercasi barista per turno serale", "Offerta di lavoro per pizzaiolo",
    "Stiamo cercando personale disponibile nel weekend", "Inviare CV per candidarsi",
]

GENERIC_MESSAGES = [
    "Buongiorno a tutti", "Il locale è aperto questa sera?", "Grazie per le informazioni",
    "Conoscete un buon corso HACCP?", "A Torino oggi piove",
]


class CandidateClassificationTests(unittest.TestCase):
    def test_candidate_searches(self):
        for message in SEARCH_MESSAGES:
            with self.subTest(message=message):
                self.assertEqual(classify(message), "RICHIESTA")

    def test_employer_offers_are_not_candidate_searches(self):
        for message in EMPLOYER_MESSAGES:
            with self.subTest(message=message):
                self.assertEqual(classify(message), "OFFERTA")

    def test_generic_messages_are_left_alone(self):
        for message in GENERIC_MESSAGES:
            with self.subTest(message=message):
                self.assertNotEqual(classify(message), "RICHIESTA")

    def test_candidate_search_with_cv_link_is_still_a_request(self):
        self.assertEqual(
            bot.classify_group_text("Cerco lavoro, qui trovate il mio CV https://example.com/cv.pdf"),
            "RICHIESTA",
        )


class CandidateRedirectTests(unittest.IsolatedAsyncioTestCase):
    def make_update(self):
        message = SimpleNamespace(message_id=44, delete=AsyncMock())
        user = SimpleNamespace(id=123, first_name="Mario")
        chat = SimpleNamespace(id=-999, type="supergroup")
        return SimpleNamespace(message=message, effective_user=user, effective_chat=chat)

    async def test_unregistered_candidate_message_is_deleted_and_invited(self):
        update = self.make_update()
        telegram_bot = SimpleNamespace(send_message=AsyncMock(), get_me=AsyncMock())
        context = SimpleNamespace(bot=telegram_bot)
        with patch("bot.db.get_candidate_profile", return_value=None):
            await bot.redirect_candidate_search(update, context)

        update.message.delete.assert_awaited_once()
        telegram_bot.send_message.assert_awaited_once()
        call = telegram_bot.send_message.await_args
        self.assertEqual(call.kwargs["chat_id"], 123)
        self.assertIn("Registrati gratis", call.kwargs["reply_markup"].inline_keyboard[0][0].text)

    def test_base_candidate_gets_profile_and_premium_choices(self):
        with patch("bot.db.get_candidate_profile", return_value={"user_id": 123}), patch("bot.db.is_user_premium", return_value=False):
            text, keyboard, state = bot.candidate_search_invite(123)
        self.assertEqual(state, "base")
        self.assertIn("profilo candidato Base", text)
        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "candidate_profile")
        self.assertEqual(keyboard.inline_keyboard[1][0].callback_data, "candidate_premium")

    def test_premium_candidate_gets_profile_update_choice(self):
        with patch("bot.db.get_candidate_profile", return_value={"user_id": 123}), patch("bot.db.is_user_premium", return_value=True):
            text, keyboard, state = bot.candidate_search_invite(123)
        self.assertEqual(state, "premium")
        self.assertIn("Premium è già attivo", text)
        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "candidate_profile")

    async def test_private_failure_creates_and_deletes_temporary_fallback(self):
        update = self.make_update()
        temp_message = SimpleNamespace(delete=AsyncMock())
        telegram_bot = SimpleNamespace(
            send_message=AsyncMock(side_effect=[RuntimeError("private unavailable"), temp_message]),
            get_me=AsyncMock(return_value=SimpleNamespace(username="lavorotorinobot")),
        )
        context = SimpleNamespace(bot=telegram_bot)
        tasks = []

        async def no_wait(_seconds):
            return None

        def capture_task(coro):
            task = asyncio.get_running_loop().create_task(coro)
            tasks.append(task)
            return task

        with patch("bot.db.get_candidate_profile", return_value=None), patch("bot.asyncio.sleep", new=no_wait), patch("bot.asyncio.create_task", side_effect=capture_task):
            await bot.redirect_candidate_search(update, context)
            await asyncio.gather(*tasks)

        fallback = telegram_bot.send_message.await_args_list[1]
        button = fallback.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.url, "https://t.me/lavorotorinobot?start=registrati")
        temp_message.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
