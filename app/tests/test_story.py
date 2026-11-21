"""Один граф ведёт диалог и для Telegram, и для MAX."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from botik.app.graph import RESTART_BUTTON, Graph
from botik.app.story import advance
from botik.domain.dialogue import Dialogue, DialogueStep
from botik.domain.messages import Channel, InboundMessage, OutboundMessage


def _dialogue(**update: object) -> Dialogue:
    dialogue = Dialogue(channel=Channel.TELEGRAM, chat_id="42", user_id="7")
    if update:
        return dialogue.model_copy(update=update)
    return dialogue


def _message(text: str, *, channel: Channel = Channel.MAX, image_url: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        update_id="1",
        chat_id="9",
        message_id="m",
        user_id="5",
        text=text,
        image_url=image_url,
    )


class StoryTest(unittest.TestCase):
    def test_greeting_asks_for_a_domain(self) -> None:
        move = advance(_dialogue(), "привет")
        self.assertEqual(move.dialogue.step, DialogueStep.ASK_DOMAIN)
        self.assertEqual(move.replies[0], "Привет. Я соберу сайт по твоему описанию.")

    def test_own_domain_waits_for_dns_then_opens_the_brief(self) -> None:
        asked = advance(_dialogue(step=DialogueStep.ASK_DOMAIN), "cafe.ru", public_ip="203.0.113.5")
        self.assertEqual(asked.dialogue.step, DialogueStep.OWN_DNS)
        self.assertEqual(asked.dialogue.host, "cafe.ru")
        self.assertIn("203.0.113.5", asked.replies[0])

        waiting = advance(asked.dialogue, "готово", dns_matches=False, public_ip="203.0.113.5")
        self.assertEqual(waiting.dialogue.step, DialogueStep.OWN_DNS)

        ready = advance(asked.dialogue, "готово", dns_matches=True, public_ip="203.0.113.5")
        self.assertEqual(ready.dialogue.step, DialogueStep.ASK_BRIEF)
        self.assertTrue(ready.reserve)

    def test_give_up_switches_to_our_slug(self) -> None:
        owned = _dialogue(step=DialogueStep.OWN_DNS, host="cafe.ru")
        move = advance(owned, "не разобрался")
        self.assertEqual(move.dialogue.step, DialogueStep.ASK_SLUG)
        self.assertIsNone(move.dialogue.host)

    def test_slug_then_restart_returns_to_the_domain_question(self) -> None:
        reserved = advance(_dialogue(step=DialogueStep.ASK_SLUG), "Coffee")
        self.assertEqual(reserved.dialogue.slug, "coffee")
        self.assertEqual(reserved.dialogue.step, DialogueStep.ASK_BRIEF)

        restarted = advance(reserved.dialogue, "Начать сначала")
        self.assertEqual(restarted.dialogue.step, DialogueStep.ASK_DOMAIN)
        self.assertIsNone(restarted.dialogue.slug)

    def test_picture_is_placed_by_the_next_text(self) -> None:
        editing = _dialogue(step=DialogueStep.EDITING, slug="coffee", site={"business_type": "кофе"})
        parked = advance(editing, "", image_url="https://cdn.example/cup.png")
        self.assertEqual(parked.dialogue.step, DialogueStep.ASK_IMAGE)
        placed = advance(parked.dialogue, "в первый экран")
        self.assertIn("https://cdn.example/cup.png", placed.modify_instruction or "")
        self.assertIn("в первый экран", placed.modify_instruction or "")


class GraphRunTest(unittest.TestCase):
    def test_max_message_follows_the_same_graph_and_shows_restart(self) -> None:
        sent: list[OutboundMessage] = []

        class Repo:
            def __init__(self) -> None:
                self.dialogue = Dialogue(channel=Channel.MAX, chat_id="9", user_id="5")

            async def ensure(self, message: InboundMessage) -> Dialogue:
                return self.dialogue

            async def save(self, dialogue: Dialogue) -> Dialogue:
                self.dialogue = dialogue
                return dialogue

        async def send(channel: Channel, message: OutboundMessage) -> None:
            self.assertEqual(channel, Channel.MAX)
            sent.append(message)

        graph = Graph(
            Repo(),
            send,
            content_dir=Path("."),
            rules_dir=Path("."),
            public_ip=None,
            base_domain=None,
        )
        asyncio.run(graph.handle(_message("привет")))
        self.assertEqual(sent[0].buttons, (RESTART_BUTTON,))
        self.assertIn("Привет", sent[0].text)

    def test_brief_publishes_html_for_the_saved_slug(self) -> None:
        site = {
            "business_type": "кофейня",
            "tone": "тёплый",
            "colors": {"primary": "#112233", "secondary": "#445566"},
            "blocks": [
                {"type": "header", "logo_text": "Зерно", "menu": ["Меню", "Контакты"]},
                {"type": "hero", "title": "Кофе"},
                {
                    "type": "interactive",
                    "title": "Заказ",
                    "submit_action": "send_lead",
                    "components": [
                        {"type": "text_input", "id": "phone_number", "label": "Телефон"},
                        {
                            "type": "action_button",
                            "id": "submit_order",
                            "label": "Отправить",
                            "action_type": "submit",
                            "target_endpoint": "/api/leads",
                        },
                    ],
                },
                {"type": "footer"},
            ],
        }

        class Repo:
            def __init__(self) -> None:
                self.dialogue = Dialogue(
                    channel=Channel.TELEGRAM,
                    chat_id="42",
                    user_id="7",
                    step=DialogueStep.ASK_BRIEF,
                    slug="coffee",
                )

            async def ensure(self, message: InboundMessage) -> Dialogue:
                return self.dialogue

            async def save(self, dialogue: Dialogue) -> Dialogue:
                self.dialogue = dialogue
                return dialogue

        sent: list[str] = []

        async def send(channel: Channel, message: OutboundMessage) -> None:
            del channel
            sent.append(message.text)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = Repo()
            graph = Graph(
                repo,
                send,
                content_dir=root / "content",
                rules_dir=root / "rules",
                public_ip=None,
                base_domain="example.com",
                generate=lambda brief: site,
            )
            asyncio.run(graph.handle(_message("кофейня у дома", channel=Channel.TELEGRAM)))
            html = (root / "content" / "coffee" / "index.html").read_text(encoding="utf-8")
            rule = (root / "rules" / "coffee.conf").read_text(encoding="utf-8")

        self.assertIn("Кофейня", html)
        self.assertIn("server_name coffee.example.com;", rule)
        self.assertEqual(repo.dialogue.step, DialogueStep.EDITING)
        self.assertIn("Собираю сайт.", sent)


if __name__ == "__main__":
    unittest.main()
