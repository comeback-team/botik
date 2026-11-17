"""Контракт каркаса: ход диалога, разбор намерений и сведение nginx."""

import asyncio
import unittest
from pathlib import Path

from botik.app.execute import EffectExecutor
from botik.app.nginx_service import NginxService
from botik.app.processor import ResponseProcessor, handler_registry
from botik.app.processor.context import TurnContext
from botik.app.router import ChannelRouter
from botik.app.turn import TurnService
from botik.config import Settings
from botik.domain.llm import Intent, LlmResult, ToolSpec
from botik.domain.messages import Channel, ChatTurn, Conversation, InboundMessage
from botik.domain.nginx import NginxChange, NginxDesiredState, NginxSite, apply_change
from botik.main import build_app
from botik.ports.messenger import MessageHandler


def _message(
    text: str | None = "привет",
    update_id: str = "u1",
    voice_path: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=Channel.TELEGRAM,
        update_id=update_id,
        chat_id="chat",
        message_id="m1",
        user_id="user",
        text=text,
        voice_path=voice_path,
    )


class FakeLlm:
    def __init__(self, result: LlmResult) -> None:
        self.result = result
        self.prompts: list[list[ChatTurn]] = []
        self.tools: list[tuple[ToolSpec, ...]] = []

    async def complete(self, messages, tools):
        self.prompts.append(list(messages))
        self.tools.append(tuple(tools))
        return self.result


class FakeConversations:
    def __init__(self, conversation: Conversation | None = None) -> None:
        self.conversation = conversation or Conversation(channel=Channel.TELEGRAM, chat_id="chat")
        self.appended: list[tuple[str, str]] = []

    async def get(self, channel: Channel, chat_id: str) -> Conversation:
        del channel, chat_id
        return self.conversation

    async def append(self, channel, chat_id, turn, *, key: str) -> None:
        del channel, chat_id
        self.appended.append((key, turn.content))


class FakeDeliveries:
    def __init__(self) -> None:
        self.done: set[tuple[Channel, str]] = set()

    async def already_done(self, channel: Channel, update_id: str) -> bool:
        return (channel, update_id) in self.done

    async def mark_done(self, channel: Channel, update_id: str) -> None:
        self.done.add((channel, update_id))


class FakeTranscriber:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.paths: list[Path] = []

    async def transcribe(self, path: Path) -> str:
        self.paths.append(path)
        return self.text


class FakeMessenger:
    def __init__(self, channel: Channel) -> None:
        self.channel = channel
        self.enabled = True
        self.sent: list[str] = []
        self.handler: MessageHandler | None = None

    def subscribe(self, handler: MessageHandler) -> None:
        self.handler = handler

    async def run(self) -> None:
        return None

    async def send(self, message) -> None:
        self.sent.append(message.text)


class FakeNginxRepo:
    def __init__(self) -> None:
        self.state = NginxDesiredState()
        self.saves = 0

    async def get(self) -> NginxDesiredState:
        return self.state

    async def save(self, state: NginxDesiredState) -> None:
        self.state = state
        self.saves += 1


class FakeNginx:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.applied: list[NginxDesiredState] = []

    async def apply(self, state: NginxDesiredState):
        self.applied.append(state)
        from botik.domain.nginx import ApplyReport

        return ApplyReport(ok=self.ok, detail="" if self.ok else "nginx -t failed")


def _service(
    llm: FakeLlm,
    nginx: FakeNginx | None = None,
    transcriber: FakeTranscriber | None = None,
) -> tuple[TurnService, FakeMessenger, FakeConversations, FakeDeliveries, FakeNginxRepo]:
    messenger = FakeMessenger(Channel.TELEGRAM)
    router = ChannelRouter((messenger,))
    conversations = FakeConversations()
    deliveries = FakeDeliveries()
    repo = FakeNginxRepo()
    manager = nginx or FakeNginx()
    executor = EffectExecutor(
        router=router,
        conversations=conversations,
        nginx=NginxService(repo, manager),
    )
    service = TurnService(
        llm=llm,
        conversations=conversations,
        deliveries=deliveries,
        processor=ResponseProcessor(handler_registry()),
        executor=executor,
        transcriber=transcriber or FakeTranscriber(),
    )
    return service, messenger, conversations, deliveries, repo


class ArchitectureTest(unittest.TestCase):
    def test_turn_prompts_persists_replies_and_marks_delivery(self) -> None:
        llm = FakeLlm(LlmResult(text="здравствуй"))
        service, messenger, conversations, deliveries, _repo = _service(llm)
        prior = Conversation(
            channel=Channel.TELEGRAM,
            chat_id="chat",
            summary="коротко",
            turns=(ChatTurn(role="user", content="раньше"),),
        )
        conversations.conversation = prior

        asyncio.run(service.handle(_message()))

        prompt = llm.prompts[0]
        self.assertEqual(prompt[0].role, "system")
        self.assertEqual(prompt[1].content, "коротко")
        self.assertEqual(prompt[-1].content, "привет")
        self.assertEqual([tool.name for tool in llm.tools[0]], ["nginx"])
        self.assertEqual(
            conversations.appended,
            [("m1", "привет"), ("m1:assistant", "здравствуй")],
        )
        self.assertEqual(messenger.sent, ["здравствуй"])
        self.assertIn((Channel.TELEGRAM, "u1"), deliveries.done)

    def test_duplicate_update_skips_the_model(self) -> None:
        llm = FakeLlm(LlmResult(text="ещё раз"))
        service, messenger, _conversations, deliveries, _repo = _service(llm)
        deliveries.done.add((Channel.TELEGRAM, "u1"))

        asyncio.run(service.handle(_message()))

        self.assertEqual(llm.prompts, [])
        self.assertEqual(messenger.sent, [])

    def test_nginx_intent_saves_desired_state_before_apply(self) -> None:
        llm = FakeLlm(
            LlmResult(
                text="добавил",
                intents=(
                    Intent(
                        name="nginx",
                        params={
                            "op": "upsert",
                            "name": "Blog",
                            "server_name": "blog.example",
                            "upstream": "127.0.0.1:8080",
                        },
                    ),
                ),
            )
        )
        manager = FakeNginx()
        service, messenger, _conversations, _deliveries, repo = _service(llm, manager)

        asyncio.run(service.handle(_message("подними блог")))

        self.assertEqual(repo.saves, 1)
        self.assertEqual(repo.state.sites[0].name, "blog")
        self.assertTrue(repo.state.sites[0].enabled)
        self.assertEqual(manager.applied, [repo.state])
        self.assertEqual(messenger.sent, ["добавил"])

    def test_broken_nginx_params_do_not_commit(self) -> None:
        llm = FakeLlm(
            LlmResult(intents=(Intent(name="nginx", params={"op": "upsert", "name": "../etc"}),))
        )
        service, messenger, _conversations, _deliveries, repo = _service(llm)

        asyncio.run(service.handle(_message()))

        self.assertEqual(repo.saves, 0)
        self.assertEqual(messenger.sent, ["Не разобрал параметры действия."])

    def test_failed_apply_is_a_separate_reply(self) -> None:
        llm = FakeLlm(
            LlmResult(
                text="готово",
                intents=(Intent(name="nginx", params={"op": "remove", "name": "blog"}),),
            )
        )
        service, messenger, _conversations, _deliveries, _repo = _service(llm, FakeNginx(ok=False))

        asyncio.run(service.handle(_message()))

        self.assertEqual(messenger.sent, ["Не получилось применить nginx.", "готово"])

    def test_attachment_does_not_call_the_model(self) -> None:
        llm = FakeLlm(LlmResult(text="не должен"))
        service, messenger, _conversations, deliveries, _repo = _service(llm)

        asyncio.run(service.handle(_message(text=None)))

        self.assertEqual(llm.prompts, [])
        self.assertEqual(messenger.sent, ["Пока понимаю только текст."])
        self.assertIn((Channel.TELEGRAM, "u1"), deliveries.done)

    def test_voice_is_transcribed_before_the_model(self) -> None:
        llm = FakeLlm(LlmResult(text="слышал"))
        transcriber = FakeTranscriber("распознано")
        service, messenger, conversations, _deliveries, _repo = _service(llm, transcriber=transcriber)

        asyncio.run(service.handle(_message(text=None, voice_path="/tmp/note.ogg")))

        self.assertEqual(transcriber.paths, [Path("/tmp/note.ogg")])
        self.assertEqual(llm.prompts[0][-1].content, "распознано")
        self.assertEqual(conversations.appended[0], ("m1", "распознано"))
        self.assertEqual(messenger.sent, ["слышал"])

    def test_silent_voice_skips_the_model(self) -> None:
        llm = FakeLlm(LlmResult(text="не должен"))
        service, messenger, _conversations, deliveries, _repo = _service(llm, transcriber=FakeTranscriber("  "))

        asyncio.run(service.handle(_message(text=None, voice_path="/tmp/note.ogg")))

        self.assertEqual(llm.prompts, [])
        self.assertEqual(messenger.sent, ["Речь не обнаружена."])
        self.assertIn((Channel.TELEGRAM, "u1"), deliveries.done)

    def test_apply_change_upsert_disable_remove(self) -> None:
        upsert = NginxChange(
            op="upsert",
            name="api",
            server_name="api.example",
            upstream="10.0.0.2:80",
        )
        state = apply_change(NginxDesiredState(), upsert)
        state = apply_change(state, NginxChange(op="disable", name="api"))
        self.assertFalse(state.sites[0].enabled)
        state = apply_change(state, NginxChange(op="remove", name="api"))
        self.assertEqual(state.sites, ())

    def test_site_rejects_raw_config(self) -> None:
        with self.assertRaises(ValueError):
            NginxSite(name="ok", server_name="example.com; include /tmp", upstream="127.0.0.1:80")

    def test_process_without_tokens_starts_and_returns(self) -> None:
        app = build_app(
            Settings(
                telegram_token=None,
                max_token=None,
                gigachat_credentials=None,
                mongo_uri=None,
                nginx_sites_dir=Path("/tmp/botik-sites"),
                nginx_enabled_dir=Path("/tmp/botik-enabled"),
            )
        )
        asyncio.run(app.run())

    def test_unknown_intent_becomes_a_reply(self) -> None:
        processor = ResponseProcessor(handler_registry())
        ctx = TurnContext(
            incoming=_message(),
            conversation=Conversation(channel=Channel.TELEGRAM, chat_id="chat"),
            llm=LlmResult(intents=(Intent(name="reboot-planet", params={}),)),
        )
        effects = asyncio.run(processor.run(ctx))
        texts = [effect.text for effect in effects if hasattr(effect, "text") and effect.kind == "reply"]
        self.assertEqual(texts, ["Неизвестное действие: reboot-planet"])


if __name__ == "__main__":
    unittest.main()
