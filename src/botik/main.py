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
from botik.app.router import ChannelRouter
from botik.app.turn import TurnService
from botik.config import Settings


class App:
    def __init__(self, router: ChannelRouter, turns: TurnService) -> None:
        self._router = router
        # Ход собран, но не подписан на каналы: Mongo и LLM ещё заглушки
        # и уронили бы каждое входящее. Сейчас Telegram только пишет сообщения в лог.
        self._turns = turns

    async def run(self) -> None:
        await self._router.run()


def build_app(settings: Settings) -> App:
    storage = MongoStorage(settings.mongo_uri)
    router = ChannelRouter(
        (
            TelegramMessenger(settings.telegram_token),
            MaxMessenger(settings.max_token),
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
        transcriber=WhisperTranscriber(
            model_size=settings.whisper_model,
            language=settings.whisper_language,
            denoise=settings.whisper_denoise,
        ),
    )
    return App(router, turns)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    asyncio.run(build_app(settings).run())
