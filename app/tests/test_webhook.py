"""Вебхуки Telegram и MAX приходят на один локальный порт."""

import asyncio
import unittest

from botik.adapters.max.client import MaxMessenger
from botik.adapters.telegram.client import TelegramMessenger
from botik.app.webhook import WebhookServer, webhook_url


class WebhookUrlTest(unittest.TestCase):
    def test_https_is_added_when_the_scheme_is_missing(self) -> None:
        self.assertEqual(webhook_url("example.com", "/telegram"), "https://example.com/telegram")
        self.assertEqual(webhook_url("https://example.com/", "/max"), "https://example.com/max")
        self.assertIsNone(webhook_url(None, "/telegram"))


class WebhookServerTest(unittest.TestCase):
    def test_post_reaches_the_telegram_path(self) -> None:
        seen: dict[str, bytes] = {}

        async def handler(headers: dict[str, str], body: bytes) -> int:
            seen["body"] = body
            seen["header"] = headers.get("x-test", "").encode()
            return 200

        async def once() -> bytes:
            server = WebhookServer("127.0.0.1", 0)
            server.add("/telegram", handler)
            task = asyncio.create_task(server.serve())
            await server.ready.wait()
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writer.write(
                b"POST /telegram HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n"
                b"X-Test: yes\r\n\r\n{}"
            )
            await writer.drain()
            raw = await reader.read()
            writer.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return raw

        raw = asyncio.run(once())
        self.assertTrue(raw.startswith(b"HTTP/1.1 200"))
        self.assertEqual(seen["body"], b"{}")
        self.assertEqual(seen["header"], b"yes")

    def test_unknown_path_is_not_found(self) -> None:
        async def once() -> bytes:
            server = WebhookServer("127.0.0.1", 0)
            task = asyncio.create_task(server.serve())
            await server.ready.wait()
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writer.write(b"POST /other HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            raw = await reader.read()
            writer.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return raw

        self.assertTrue(asyncio.run(once()).startswith(b"HTTP/1.1 404"))


class WebhookSecretTest(unittest.TestCase):
    def test_wrong_secret_is_rejected_before_the_update(self) -> None:
        telegram = TelegramMessenger("token", webhook_secret="secret")
        max_bot = MaxMessenger("token", webhook_secret="secret")

        async def both() -> tuple[int, int]:
            telegram_status = await telegram._receive({}, b"{}")
            max_status = await max_bot._receive({}, b"{}")
            return telegram_status, max_status

        self.assertEqual(asyncio.run(both()), (401, 401))


if __name__ == "__main__":
    unittest.main()
