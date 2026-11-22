"""Прогон одного сообщения по графу. Канал здесь только адрес ответа."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from botik.ai_generator import complete, modify_site
from botik.app.publish import folder_name, publish_html, reserve_site, server_name
from botik.app.story import StoryMove, advance, wants_dns_check
from botik.domain.dialogue import Dialogue, DialogueStep
from botik.domain.messages import Channel, InboundMessage, OutboundMessage
from botik.ports.repos import DialogueRepository
from botik.site.request import build_site_request
from botik.site.structure import SiteStructure

logger = logging.getLogger(__name__)

RESTART_BUTTON = "Начать сначала"
_FAILED = "Не получилось собрать сайт. Опиши его ещё раз."
_UPDATED = "Если хотите поменять сайт, опишите, что изменить."

SiteBuilder = Callable[[str], dict]
SiteEditor = Callable[[dict, str], dict]
Sender = Callable[[Channel, OutboundMessage], Awaitable[None]]


class Graph:
    def __init__(
        self,
        dialogues: DialogueRepository,
        send: Sender,
        *,
        content_dir: Path,
        rules_dir: Path,
        public_ip: str | None,
        base_domain: str | None,
        generate: SiteBuilder | None = None,
        revise: SiteEditor | None = None,
    ) -> None:
        self._dialogues = dialogues
        self._send = send
        self._content_dir = content_dir
        self._rules_dir = rules_dir
        self._public_ip = public_ip
        self._base_domain = base_domain
        self._generate = generate or _generate
        self._revise = revise or _revise

    async def handle(self, message: InboundMessage) -> None:
        dialogue = await self._dialogues.ensure(message)
        dns_matches = None
        if self._public_ip and wants_dns_check(dialogue, message.text or ""):
            dns_matches = await asyncio.to_thread(_address_matches, dialogue.host or "", self._public_ip)
        move = advance(
            dialogue,
            message.text or "",
            image_url=message.image_url,
            dns_matches=dns_matches,
            public_ip=self._public_ip,
            base_domain=self._base_domain,
        )
        dialogue, replies = await self._apply(move)
        await self._dialogues.save(dialogue)
        labels = () if move.generate_brief or move.modify_instruction else move.buttons
        labels = labels + (RESTART_BUTTON,)
        last = len(replies) - 1
        for index, text in enumerate(replies):
            await self._send(
                message.channel,
                OutboundMessage(
                    chat_id=message.chat_id,
                    text=text,
                    reply_to=message.message_id,
                    buttons=labels if index == last else (),
                )
            )

    async def _apply(self, move: StoryMove) -> tuple[Dialogue, tuple[str, ...]]:
        dialogue = move.dialogue
        if move.reserve:
            _reserve(dialogue, self._content_dir, self._rules_dir, self._base_domain)
        if move.generate_brief:
            return await self._build(dialogue, move.generate_brief, move.replies)
        if move.modify_instruction:
            return await self._edit(dialogue, move.modify_instruction, move.replies)
        return dialogue, move.replies

    async def _build(
        self,
        dialogue: Dialogue,
        brief: str,
        replies: tuple[str, ...],
    ) -> tuple[Dialogue, tuple[str, ...]]:
        try:
            site = await asyncio.to_thread(self._generate, brief)
            _publish(dialogue, site, self._content_dir, self._rules_dir, self._base_domain)
        except Exception:
            logger.exception("site build failed chat=%s", dialogue.chat_id)
            return dialogue, replies + (_FAILED,)
        done = dialogue.model_copy(update={"site": site, "step": DialogueStep.EDITING})
        return done, replies + (_UPDATED,)

    async def _edit(
        self,
        dialogue: Dialogue,
        instruction: str,
        replies: tuple[str, ...],
    ) -> tuple[Dialogue, tuple[str, ...]]:
        current = dialogue.site or {}
        try:
            site = await asyncio.to_thread(self._revise, current, instruction)
            _publish(dialogue, site, self._content_dir, self._rules_dir, self._base_domain)
        except Exception:
            logger.exception("site edit failed chat=%s", dialogue.chat_id)
            return dialogue, replies + (_FAILED,)
        done = dialogue.model_copy(update={"site": site, "step": DialogueStep.EDITING, "image_url": None})
        return done, replies + (_UPDATED,)


def _address_matches(host: str, expected: str) -> bool:
    import socket

    try:
        found = socket.getaddrinfo(host, None, socket.AF_INET)
    except socket.gaierror:
        return False
    return any(item[4][0] == expected for item in found)


def _reserve(dialogue: Dialogue, content_dir: Path, rules_dir: Path, base_domain: str | None) -> None:
    folder = folder_name(dialogue.host, dialogue.slug)
    reserve_site(
        content_dir=content_dir,
        rules_dir=rules_dir,
        folder=folder,
        name=server_name(dialogue.host, dialogue.slug, base_domain),
    )


def _publish(
    dialogue: Dialogue,
    site: dict,
    content_dir: Path,
    rules_dir: Path,
    base_domain: str | None,
) -> None:
    folder = folder_name(dialogue.host, dialogue.slug)
    publish_html(site, content_dir=content_dir, folder=folder)
    reserve_site(
        content_dir=content_dir,
        rules_dir=rules_dir,
        folder=folder,
        name=server_name(dialogue.host, dialogue.slug, base_domain),
    )


def _generate(brief: str) -> dict:
    request = build_site_request(brief)
    answer = complete(request.system, request.user, response_format=request.response_format)
    return SiteStructure.model_validate(answer).model_dump()


def _revise(current: dict, instruction: str) -> dict:
    updated, info = modify_site(current, instruction)
    if info.get("status") != "ok":
        raise RuntimeError(str(info.get("error") or "modify failed"))
    return updated
