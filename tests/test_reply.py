"""Ответ модели возвращается в чат человека, который написал сообщение."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from botik.adapters.max.client import MaxMessenger
from botik.adapters.telegram.client import TelegramMessenger
from botik.app.intake import forward_to_model
from botik.domain.messages import Channel, InboundMessage, OutboundMessage


def _incoming() -> InboundMessage:
    return InboundMessage(
        channel=Channel.TELEGRAM,
        update_id="u1",
        chat_id="42",
        message_id="3",
        user_id="7",
        text="привет",
    )


class ReplyDeliveryTest(unittest.TestCase):
    def test_model_text_is_sent_back_to_the_same_chat(self) -> None:
        sent: list[tuple[str, str]] = []

        async def send(message: InboundMessage, text: str) -> None:
            sent.append((message.chat_id, message.message_id, text))

        with patch("botik.app.intake.submit_site_request"):
            asyncio.run(forward_to_model(_incoming(), send))

        self.assertEqual(sent, [("42", "3", "all ok")])

    def test_user_text_is_saved_as_a_site_request(self) -> None:
        sent: list[tuple[str, str]] = []

        async def send(message: InboundMessage, text: str) -> None:
            sent.append((message.chat_id, message.message_id, text))

        with tempfile.TemporaryDirectory() as folder:
            with (
                patch("botik.app.intake.SITE_REQUESTS_DIR", Path(folder)),
                patch(
                    "botik.app.intake.complete",
                    return_value={"business_type": "кофейня"},
                ) as complete,
            ):
                asyncio.run(forward_to_model(_incoming(), send))
            request_path = Path(folder) / "telegram-42-3.json"
            reply_path = Path(folder) / "telegram-42-3.reply.json"
            payload = json.loads(request_path.read_text(encoding="utf-8"))
            reply = json.loads(reply_path.read_text(encoding="utf-8"))

        self.assertEqual(sent, [("42", "3", "all ok")])
        self.assertIn("привет", payload["user"])
        self.assertEqual(reply, {"business_type": "кофейня"})
        self.assertEqual(complete.call_args.kwargs["response_format"]["type"], "json_schema")

    def test_telegram_send_quotes_the_incoming_message(self) -> None:
        messenger = TelegramMessenger("token")
        calls: list[dict[str, object]] = []

        class Bot:
            async def send_message(self, **kwargs: object) -> None:
                calls.append(kwargs)

        messenger._bot = Bot()
        asyncio.run(
            messenger.send(OutboundMessage(chat_id="42", text="здравствуй", reply_to="3"))
        )

        self.assertEqual(calls[0]["chat_id"], "42")
        self.assertEqual(calls[0]["text"], "здравствуй")
        self.assertEqual(calls[0]["reply_parameters"].message_id, 3)

    def test_max_send_quotes_the_incoming_message(self) -> None:
        messenger = MaxMessenger("token")
        calls: list[tuple[str, dict[str, object], dict[str, object]]] = []

        class Response:
            def raise_for_status(self) -> None:
                return None

        class Client:
            async def post(
                self,
                path: str,
                *,
                params: dict[str, object],
                json: dict[str, object],
            ) -> Response:
                calls.append((path, params, json))
                return Response()

        messenger._http = Client()
        asyncio.run(
            messenger.send(OutboundMessage(chat_id="9", text="здравствуй", reply_to="mid1"))
        )

        self.assertEqual(
            calls,
            [
                (
                    "/messages",
                    {"chat_id": 9},
                    {"text": "здравствуй", "link": {"type": "reply", "mid": "mid1"}},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
