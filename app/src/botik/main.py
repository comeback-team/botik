"""Сборка процесса. Единственное место, где адаптеры встречаются с приложением."""

import asyncio
import logging

from botik.adapters.max import MaxMessenger
from botik.adapters.mongo import MongoStorage
from botik.adapters.telegram import TelegramMessenger
from botik.adapters.whisper import WhisperTranscriber
from botik.app.graph import Graph
from botik.app.router import ChannelRouter
from botik.app.webhook import WebhookServer
from botik.config import Settings
from botik.domain.messages import InboundMessage


class App:
    def __init__(self, router: ChannelRouter, graph: Graph) -> None:
        self._router = router
        self._graph = graph
        router.bind(self._on_message)

    async def _on_message(self, message: InboundMessage) -> None:
        try:
            await self._graph.handle(message)
        except Exception:
            logging.getLogger(__name__).exception(
                "graph failed channel=%s chat=%s",
                message.channel.value,
                message.chat_id,
            )

    async def run(self) -> None:
        await self._router.run()


def build_app(settings: Settings) -> App:
    storage = MongoStorage(settings.mongo_uri)
    transcriber = WhisperTranscriber(
        model_size=settings.whisper_model,
        language=settings.whisper_language,
        denoise=settings.whisper_denoise,
    )
    webhooks = WebhookServer("0.0.0.0", settings.webhook_port)
    router = ChannelRouter(
        (
            TelegramMessenger(
                settings.telegram_token,
                transcriber,
                dialogues=storage.dialogues,
                content_dir=settings.content_dir,
                base_domain=settings.base_domain,
                webhooks=webhooks,
                webhook_secret=settings.webhook_secret,
            ),
            MaxMessenger(
                settings.max_token,
                transcriber,
                dialogues=storage.dialogues,
                content_dir=settings.content_dir,
                base_domain=settings.base_domain,
                webhooks=webhooks,
                webhook_secret=settings.webhook_secret,
            ),
        ),
        webhooks,
    )
    graph = Graph(
        storage.dialogues,
        router.send,
        content_dir=settings.content_dir,
        rules_dir=settings.nginx_rules_dir,
        public_ip=settings.public_ip,
        base_domain=settings.base_domain,
    )
    return App(router, graph)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    asyncio.run(build_app(settings).run())
