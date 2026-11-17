"""Приём Telegram-сообщения превращается в лог и внутреннее сообщение."""

import asyncio
import logging
import unittest
from datetime import datetime, timezone

from telegram import Chat, Message, Update, User, Voice

from botik.adapters.telegram.client import TelegramMessenger, inbound_message
from botik.domain.messages import InboundMessage


def _update(text: str | None = "привет", voice: Voice | None = None) -> Update:
    user = User(id=7, is_bot=False, first_name="Arman", username="arman")
    chat = Chat(id=42, type=Chat.PRIVATE)
    message = Message(
        message_id=3,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
        voice=voice,
    )
    return Update(update_id=11, message=message)


class TelegramInboundTest(unittest.TestCase):
    def test_text_becomes_inbound_message(self) -> None:
        inbound = inbound_message(_update("привет"))
        self.assertEqual(
            inbound,
            InboundMessage(
                channel="telegram",
                update_id="11",
                chat_id="42",
                message_id="3",
                user_id="7",
                text="привет",
            ),
        )

    def test_update_is_logged_and_forwarded(self) -> None:
        messenger = TelegramMessenger("token")
        seen: list[InboundMessage] = []

        async def handler(message: InboundMessage) -> None:
            seen.append(message)

        messenger.subscribe(handler)
        with self.assertLogs("botik.app.intake", level=logging.INFO) as logs:
            asyncio.run(messenger._on_update(_update("привет"), None))

        self.assertEqual([message.text for message in seen], ["привет"])
        self.assertIn("telegram chat=42 user=7 name=@arman message=3 привет", logs.output[0])

    def test_voice_is_logged_without_fake_text(self) -> None:
        voice = Voice(file_id="file", file_unique_id="uniq", duration=2)
        messenger = TelegramMessenger("token")
        update = _update(text=None, voice=voice)

        with self.assertLogs("botik.app.intake", level=logging.INFO) as logs:
            asyncio.run(messenger._on_update(update, None))

        self.assertIsNone(inbound_message(update).text)
        self.assertIn("telegram chat=42 user=7 name=@arman message=3 <voice>", logs.output[0])


if __name__ == "__main__":
    unittest.main()
