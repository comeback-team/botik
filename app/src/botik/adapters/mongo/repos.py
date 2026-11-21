"""MongoDB. Коллекции разделены по ролям, клиент у них общий.

Диалоги пишутся в Mongo. История реплик, доставки и nginx пока только
фиксируют контракт и не открывают свои коллекции.
"""

from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument

from botik.domain.dialogue import Dialogue, DialogueStep
from botik.domain.messages import Channel, ChatTurn, Conversation, InboundMessage
from botik.domain.nginx import NginxDesiredState

CONVERSATIONS = "conversations"
DELIVERIES = "deliveries"
NGINX_STATE = "nginx_state"
DIALOGUES = "dialogues"
_DIALOGUE_INDEX = "channel_chat"
_MISSING_URI = "MONGODB_URI is not set"


class MongoConversations:
    collection = CONVERSATIONS

    def __init__(self, uri: str | None) -> None:
        self._uri = uri

    async def get(self, channel: Channel, chat_id: str) -> Conversation:
        del channel, chat_id
        raise NotImplementedError("Mongo conversations are not implemented")

    async def append(
        self,
        channel: Channel,
        chat_id: str,
        turn: ChatTurn,
        *,
        key: str,
    ) -> None:
        del channel, chat_id, turn, key
        raise NotImplementedError("Mongo conversations are not implemented")


class MongoDeliveries:
    collection = DELIVERIES

    def __init__(self, uri: str | None) -> None:
        self._uri = uri

    async def already_done(self, channel: Channel, update_id: str) -> bool:
        del channel, update_id
        raise NotImplementedError("Mongo deliveries are not implemented")

    async def mark_done(self, channel: Channel, update_id: str) -> None:
        del channel, update_id
        raise NotImplementedError("Mongo deliveries are not implemented")


class MongoNginxState:
    collection = NGINX_STATE

    def __init__(self, uri: str | None) -> None:
        self._uri = uri

    async def get(self) -> NginxDesiredState:
        raise NotImplementedError("Mongo nginx state is not implemented")

    async def save(self, state: NginxDesiredState) -> None:
        del state
        raise NotImplementedError("Mongo nginx state is not implemented")


class MongoDialogues:
    """Диалог одного чата. Повторный ensure не сбрасывает шаг."""

    collection = DIALOGUES

    def __init__(self, collection: Any) -> None:
        self._collection = collection
        self._indexed = False

    async def get(self, channel: Channel, chat_id: str) -> Dialogue | None:
        await self._ready()
        found = await self._collection.find_one(_key(channel, chat_id))
        if found is None:
            return None
        return Dialogue.model_validate(found)

    async def ensure(self, message: InboundMessage) -> Dialogue:
        await self._ready()
        now = _now()
        found = await self._collection.find_one_and_update(
            _key(message.channel, message.chat_id),
            {
                "$set": {
                    "user_id": message.user_id,
                    "updated_at": now,
                },
                "$setOnInsert": {"step": DialogueStep.ASK_DOMAIN.value},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return Dialogue.model_validate(found)

    async def set_step(self, channel: Channel, chat_id: str, step: DialogueStep) -> Dialogue:
        await self._ready()
        found = await self._collection.find_one_and_update(
            _key(channel, chat_id),
            {"$set": {"step": step.value, "updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )
        if found is None:
            raise LookupError(f"Диалог не найден: {channel.value} {chat_id}")
        return Dialogue.model_validate(found)

    async def _ready(self) -> None:
        if self._collection is None:
            raise RuntimeError(_MISSING_URI)
        if self._indexed:
            return
        await self._collection.create_index(
            [("channel", 1), ("chat_id", 1)],
            unique=True,
            name=_DIALOGUE_INDEX,
        )
        self._indexed = True


class MongoStorage:
    """Репозитории на одном URI. Клиент Motor открывается, если URI задан."""

    def __init__(self, uri: str | None) -> None:
        self.conversations = MongoConversations(uri)
        self.deliveries = MongoDeliveries(uri)
        self.nginx_state = MongoNginxState(uri)
        collection = None
        if uri:
            from motor.motor_asyncio import AsyncIOMotorClient

            database = AsyncIOMotorClient(uri).get_default_database(default="botik")
            collection = database[DIALOGUES]
        self.dialogues = MongoDialogues(collection)


def _key(channel: Channel, chat_id: str) -> dict[str, str]:
    return {"channel": channel.value, "chat_id": chat_id}


def _now() -> datetime:
    return datetime.now(timezone.utc)
