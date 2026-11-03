"""Один ход диалога. Доменных решений здесь нет: собрать, спросить, разобрать, выполнить."""

import logging
from pathlib import Path

from botik.app.execute import EffectExecutor
from botik.app.processor.context import TurnContext
from botik.app.processor.interpret import ResponseProcessor
from botik.app.prompt import build_prompt
from botik.domain.effects import Reply
from botik.domain.messages import InboundMessage
from botik.ports.llm import LlmClient
from botik.ports.repos import ConversationRepository, DeliveryLog
from botik.ports.transcriber import Transcriber

logger = logging.getLogger(__name__)

_FAILED = "Не получилось обработать сообщение."
_TEXT_ONLY = "Пока понимаю только текст."
_NO_SPEECH = "Речь не обнаружена."


class TurnService:
    def __init__(
        self,
        *,
        llm: LlmClient,
        conversations: ConversationRepository,
        deliveries: DeliveryLog,
        processor: ResponseProcessor,
        executor: EffectExecutor,
        transcriber: Transcriber,
    ) -> None:
        self._llm = llm
        self._conversations = conversations
        self._deliveries = deliveries
        self._processor = processor
        self._executor = executor
        self._transcriber = transcriber

    async def handle(self, message: InboundMessage) -> None:
        try:
            await self._handle(message)
        except Exception:
            logger.exception(
                "turn failed channel=%s chat=%s",
                message.channel.value,
                message.chat_id,
            )
            await self._tell(message, _FAILED)

    async def _handle(self, message: InboundMessage) -> None:
        if await self._deliveries.already_done(message.channel, message.update_id):
            return
        message = await self._ensure_text(message)
        if message is None:
            return
        conversation = await self._conversations.get(message.channel, message.chat_id)
        result = await self._llm.complete(
            build_prompt(conversation, message),
            self._processor.tool_specs(),
        )
        effects = await self._processor.run(
            TurnContext(incoming=message, conversation=conversation, llm=result)
        )
        await self._executor.run(message, effects)
        await self._deliveries.mark_done(message.channel, message.update_id)

    async def _ensure_text(self, message: InboundMessage) -> InboundMessage | None:
        if message.text:
            return message
        if message.voice_path is None:
            await self._finish(message, _TEXT_ONLY)
            return None
        recognized = (await self._transcriber.transcribe(Path(message.voice_path))).strip()
        if not recognized:
            await self._finish(message, _NO_SPEECH)
            return None
        return message.model_copy(update={"text": recognized})

    async def _finish(self, message: InboundMessage, text: str) -> None:
        await self._executor.run(message, [Reply(text=text)])
        await self._deliveries.mark_done(message.channel, message.update_id)

    async def _tell(self, message: InboundMessage, text: str) -> None:
        try:
            await self._executor.reply(message, text)
        except Exception:
            logger.exception("failed to send error reply")
