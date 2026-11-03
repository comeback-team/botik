"""Приём MAX попадает в тот же лог, что и Telegram."""

import asyncio
import logging
import unittest

from botik.adapters.max.client import MaxMessenger, parse_update
from botik.domain.messages import Channel, InboundMessage


def _update(text: str | None, attachments: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "update_type": "message_created",
        "timestamp": 10,
        "message": {
            "sender": {
                "user_id": 5,
                "username": "maxuser",
                "is_bot": False,
                "first_name": "Max",
            },
            "recipient": {"chat_id": 9, "chat_type": "dialog", "user_id": 5},
            "body": {"mid": "mid1", "text": text, "attachments": attachments or []},
        },
    }


class MaxInboundTest(unittest.TestCase):
    def test_text_and_photo_share_the_intake_log(self) -> None:
        messenger = MaxMessenger("token")
        seen: list[InboundMessage] = []

        async def handler(message: InboundMessage) -> None:
            seen.append(message)

        messenger.subscribe(handler)
        update = _update("смотри", [{"type": "image", "payload": {"url": "https://example"}}])
        with self.assertLogs("botik.app.intake", level=logging.INFO) as logs:
            asyncio.run(messenger._on_update(update))

        self.assertEqual(seen[0].channel, Channel.MAX)
        self.assertEqual(seen[0].text, "смотри")
        self.assertIn("max chat=9 user=5 name=@maxuser message=mid1 смотри <photo>", logs.output[0])

    def test_voice_is_logged_without_fake_text(self) -> None:
        update = _update(None, [{"type": "audio", "payload": {"token": "secret"}}])
        parsed = parse_update(update)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        inbound, _name, shown = parsed
        self.assertIsNone(inbound.text)
        self.assertEqual(shown, "<voice>")
        self.assertNotIn("secret", shown)

    def test_voice_without_message_body_is_logged(self) -> None:
        messenger = MaxMessenger("token")
        update = {"update_type": "message_created", "timestamp": 1784114462472, "user_locale": "ru"}

        with self.assertLogs("botik.adapters.max.client", level=logging.INFO) as logs:
            asyncio.run(messenger._on_update(update))

        self.assertIn("max message_created timestamp=1784114462472", logs.output[0])
        self.assertIn("<no message body>", logs.output[0])

    def test_bot_message_is_ignored(self) -> None:
        update = _update("сам себе")
        message = update["message"]
        assert isinstance(message, dict)
        sender = message["sender"]
        assert isinstance(sender, dict)
        sender["is_bot"] = True
        self.assertIsNone(parse_update(update))


if __name__ == "__main__":
    unittest.main()
