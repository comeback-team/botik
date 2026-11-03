"""Действия, которые процессор возвращает, а исполнитель выполняет.

Процессор не шлёт сообщения, не пишет в Mongo и не вызывает nginx.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from botik.domain.nginx import NginxChange


class Reply(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["reply"] = "reply"
    text: str


class PersistTurn(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["persist"] = "persist"
    role: Literal["user", "assistant"]
    content: str
    key: str


Effect = Reply | PersistTurn | NginxChange
