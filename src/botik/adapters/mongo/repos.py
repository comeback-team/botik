"""MongoDB. Коллекции разделены по ролям, клиент у них будет общий.

Пока методы только фиксируют контракт репозиториев и не открывают соединение.
"""

from botik.domain.messages import Channel, ChatTurn, Conversation
from botik.domain.nginx import NginxDesiredState

CONVERSATIONS = "conversations"
DELIVERIES = "deliveries"
NGINX_STATE = "nginx_state"


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


class MongoStorage:
    """Три репозитория на одном URI. Позже здесь появится один клиент Motor."""

    def __init__(self, uri: str | None) -> None:
        self.conversations = MongoConversations(uri)
        self.deliveries = MongoDeliveries(uri)
        self.nginx_state = MongoNginxState(uri)
