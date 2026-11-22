"""Сборка процесса. Единственное место, где адаптеры встречаются с приложением."""

import asyncio
import logging

from botik.adapters.gigachat import GigaChatClient
from botik.adapters.max import MaxMessenger
from botik.adapters.mongo import MongoStorage
from botik.adapters.nginx import SystemNginxManager
from botik.adapters.telegram import TelegramMessenger
from botik.adapters.whisper import WhisperTranscriber
from botik.app.execute import EffectExecutor
from botik.app.nginx_service import NginxService
from botik.app.processor import ResponseProcessor, handler_registry
from botik.app.graph import Graph
from botik.app.router import ChannelRouter
from botik.app.turn import TurnService
from botik.config import Settings
from botik.domain.messages import InboundMessage


class App:
    def __init__(
        self,
        router: ChannelRouter,
        turns: TurnService,
        graph: Graph,
    ) -> None:
        self._router = router
        self._graph = graph
        # Полный ход с инструментами не подписан.
        # Живой маршрут — один граф для Telegram и MAX после транскрибации.
        router.bind(self._on_message)
        self._turns = turns

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
    router = ChannelRouter(
        (
            TelegramMessenger(
                settings.telegram_token,
                transcriber,
                dialogues=storage.dialogues,
                content_dir=settings.content_dir,
                base_domain=settings.base_domain,
            ),
            MaxMessenger(
                settings.max_token,
                transcriber,
                dialogues=storage.dialogues,
                content_dir=settings.content_dir,
                base_domain=settings.base_domain,
            ),
        )
    )
    executor = EffectExecutor(
        router=router,
        conversations=storage.conversations,
        nginx=NginxService(
            storage.nginx_state,
            SystemNginxManager(settings.nginx_sites_dir, settings.nginx_enabled_dir),
        ),
    )
    turns = TurnService(
        llm=GigaChatClient(settings.gigachat_credentials),
        conversations=storage.conversations,
        deliveries=storage.deliveries,
        processor=ResponseProcessor(handler_registry()),
        executor=executor,
        transcriber=transcriber,
    )
    graph = Graph(
        storage.dialogues,
        router.send,
        content_dir=settings.content_dir,
        rules_dir=settings.nginx_rules_dir,
        public_ip=settings.public_ip,
        base_domain=settings.base_domain,
    )
    return App(router, turns, graph)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    asyncio.run(build_app(settings).run())
