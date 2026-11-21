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
from botik.app.intake import forward_to_model
from botik.app.router import ChannelRouter
from botik.app.turn import TurnService
from botik.config import Settings
from botik.domain.messages import InboundMessage, OutboundMessage
from botik.ports.repos import DialogueRepository


class App:
    def __init__(
        self,
        router: ChannelRouter,
        turns: TurnService,
        dialogues: DialogueRepository,
    ) -> None:
        self._router = router
        self._dialogues = dialogues
        # Полный ход с инструментами не подписан.
        # Живой маршрут — диалог в Mongo, затем текст входящего в модель.
        router.bind(self._on_message)
        self._turns = turns

    async def _on_message(self, message: InboundMessage) -> None:
        try:
            await self._dialogues.ensure(message)
        except Exception:
            logging.getLogger(__name__).exception(
                "dialogue ensure failed channel=%s chat=%s",
                message.channel.value,
                message.chat_id,
            )
        await forward_to_model(message, self._reply)

    async def _reply(self, message: InboundMessage, text: str) -> None:
        await self._router.send(
            message.channel,
            OutboundMessage(
                chat_id=message.chat_id,
                text=text,
                reply_to=message.message_id,
            ),
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
            TelegramMessenger(settings.telegram_token, transcriber),
            MaxMessenger(settings.max_token, transcriber),
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
    return App(router, turns, storage.dialogues)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    asyncio.run(build_app(settings).run())
