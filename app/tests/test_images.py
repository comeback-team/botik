"""Картинка ложится в папку сайта до входа в граф."""

import asyncio
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from botik.adapters.content import remember_image
from botik.adapters.max.client import MaxMessenger
from botik.domain.dialogue import Dialogue
from botik.domain.messages import Channel, InboundMessage


def _message(**update: object) -> InboundMessage:
    message = InboundMessage(
        channel=Channel.MAX,
        update_id="1",
        chat_id="9",
        message_id="mid1",
        user_id="5",
        text="смотри",
    )
    if update:
        return message.model_copy(update=update)
    return message


class ImageStoreTest(unittest.TestCase):
    def test_file_lands_next_to_the_site(self) -> None:
        message = _message(channel=Channel.TELEGRAM, chat_id="42", message_id="3", user_id="7", text="вот")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            updated = remember_image(message, root, "example.com", b"png", ".png", folder="coffee")
            saved = root / "coffee" / "3.png"
            self.assertEqual(saved.read_bytes(), b"png")

        marker = "{{img:https://example.com/content/coffee/3.png}}"
        self.assertEqual(updated.text, f"вот\n{marker}")
        self.assertEqual(updated.image_url, "https://example.com/content/coffee/3.png")


class MaxImageStoreTest(unittest.TestCase):
    def test_image_is_linked_before_the_handler(self) -> None:
        seen: list[InboundMessage] = []

        class Dialogues:
            async def get(self, channel: Channel, chat_id: str) -> Dialogue:
                return Dialogue(
                    channel=channel,
                    chat_id=chat_id,
                    user_id="5",
                    slug="coffee",
                    host="coffee.example.com",
                )

        async def handler(message: InboundMessage) -> None:
            seen.append(message)

        async def download(url: str) -> tuple[bytes, str]:
            self.assertEqual(url, "https://cdn.example/cup.png")
            return b"png", "image/png"

        with tempfile.TemporaryDirectory() as folder:
            messenger = MaxMessenger(
                "token",
                dialogues=Dialogues(),
                content_dir=Path(folder),
                base_domain="example.com",
            )
            messenger.subscribe(handler)
            update = {
                "update_type": "message_created",
                "timestamp": 10,
                "message": {
                    "sender": {"user_id": 5, "username": "maxuser", "is_bot": False},
                    "recipient": {"chat_id": 9, "chat_type": "dialog", "user_id": 5},
                    "body": {
                        "mid": "mid1",
                        "text": "смотри",
                        "attachments": [{"type": "image", "payload": {"url": "https://cdn.example/cup.png"}}],
                    },
                },
            }
            with (
                patch("botik.adapters.max.client._download_image_bytes", download),
                self.assertLogs("botik.app.intake", level=logging.INFO),
            ):
                asyncio.run(messenger._on_update(update))
            saved = Path(folder) / "coffee.example.com" / "mid1.png"
            self.assertEqual(saved.read_bytes(), b"png")

        self.assertEqual(
            seen[0].text,
            "смотри\n{{img:https://example.com/content/coffee.example.com/mid1.png}}",
        )
        self.assertEqual(seen[0].image_url, "https://example.com/content/coffee.example.com/mid1.png")


if __name__ == "__main__":
    unittest.main()
