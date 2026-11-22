"""Один граф ведёт диалог и для Telegram, и для MAX."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from botik.app.graph import RESTART_BUTTON, Graph
from botik.app.publish import owner_line, reserve_site
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
        self.assertEqual(move.buttons, ("Свой домен", "Нет своего"))
        self.assertNotIn("напиши", " ".join(move.replies).casefold())

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
        reserved = advance(_dialogue(step=DialogueStep.ASK_SLUG), "Coffee", base_domain="example.com")
        self.assertEqual(reserved.dialogue.slug, "coffee")
        self.assertEqual(reserved.dialogue.host, "coffee.example.com")
        self.assertIn("Вашим доменом будет http://coffee.example.com.", reserved.replies[0])
        self.assertEqual(reserved.dialogue.step, DialogueStep.ASK_BRIEF)
        self.assertTrue(reserved.reserve)

        restarted = advance(reserved.dialogue, "Начать сначала")
        self.assertEqual(restarted.dialogue.step, DialogueStep.ASK_DOMAIN)
        self.assertIsNone(restarted.dialogue.slug)
        self.assertIsNone(restarted.dialogue.host)
        self.assertEqual(restarted.release_host, "coffee.example.com")

    def test_picture_is_placed_by_the_next_text(self) -> None:
        editing = _dialogue(step=DialogueStep.EDITING, slug="coffee", site={"business_type": "кофе"})
        parked = advance(editing, "", image_url="https://cdn.example/cup.png")
        self.assertEqual(parked.dialogue.step, DialogueStep.ASK_IMAGE)
        placed = advance(parked.dialogue, "в первый экран")
        self.assertIn("https://cdn.example/cup.png", placed.modify_instruction or "")
        self.assertIn("в первый экран", placed.modify_instruction or "")

    def test_address_is_only_the_host_and_our_zone_is_refused(self) -> None:
        pasted = advance(
            _dialogue(step=DialogueStep.ASK_DOMAIN),
            "https://Cafe.RU/menu",
            public_ip="203.0.113.5",
            base_domain="example.com",
        )
        self.assertEqual(pasted.dialogue.host, "cafe.ru")
        self.assertFalse(pasted.reserve)

        ours = advance(
            _dialogue(step=DialogueStep.ASK_DOMAIN),
            "coffee.example.com",
            base_domain="https://example.com",
        )
        self.assertEqual(ours.dialogue.step, DialogueStep.ASK_DOMAIN)
        self.assertIsNone(ours.dialogue.host)
        self.assertIn("Это наш домен", ours.replies[0])

    def test_slug_without_base_domain_does_not_reserve(self) -> None:
        move = advance(_dialogue(step=DialogueStep.ASK_SLUG), "coffee", base_domain=None)
        self.assertEqual(move.dialogue.step, DialogueStep.ASK_SLUG)
        self.assertFalse(move.reserve)
        self.assertIn("не задан", move.replies[0])


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
        self.assertEqual(sent[-1].buttons, ("Свой домен", "Нет своего", RESTART_BUTTON))
        self.assertIn("Привет", sent[0].text)
        self.assertNotIn("напиши", sent[-1].text.casefold())

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
                    host="coffee.example.com",
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
            html = (root / "content" / "coffee.example.com" / "index.html").read_text(encoding="utf-8")
            rule = (root / "rules" / "coffee.example.com.conf").read_text(encoding="utf-8")

        self.assertIn("Кофейня", html)
        self.assertIn("server_name coffee.example.com;", rule)
        self.assertEqual(repo.dialogue.step, DialogueStep.EDITING)
        self.assertIn("Собираю сайт.", sent)


class _Repo:
    def __init__(self, dialogue: Dialogue) -> None:
        self.dialogue = dialogue

    async def ensure(self, message: InboundMessage) -> Dialogue:
        del message
        return self.dialogue

    async def save(self, dialogue: Dialogue) -> Dialogue:
        self.dialogue = dialogue
        return dialogue


class DomainFilesTest(unittest.TestCase):
    def _graph(self, root: Path, dialogue: Dialogue, public_ip: str | None = "203.0.113.5") -> tuple[Graph, _Repo, list[str]]:
        sent: list[str] = []
        repo = _Repo(dialogue)

        async def send(channel: Channel, message: OutboundMessage) -> None:
            del channel
            sent.append(message.text)

        graph = Graph(
            repo,
            send,
            content_dir=root / "content",
            rules_dir=root / "rules",
            public_ip=public_ip,
            base_domain="example.com",
        )
        return graph, repo, sent

    def test_own_domain_is_written_after_the_address_matches(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            graph, repo, sent = self._graph(
                root,
                Dialogue(channel=Channel.MAX, chat_id="9", user_id="5", step=DialogueStep.ASK_DOMAIN),
            )
            asyncio.run(graph.handle(_message("https://Cafe.RU/menu")))
            self.assertEqual(repo.dialogue.host, "cafe.ru")
            self.assertFalse((root / "content" / "cafe.ru").exists())

            with patch("botik.app.graph._address_matches", return_value=True):
                asyncio.run(graph.handle(_message("готово")))
            rule = (root / "rules" / "cafe.ru.conf").read_text(encoding="utf-8")
            self.assertTrue((root / "content" / "cafe.ru" / "index.html").is_file())

        self.assertIn("server_name cafe.ru;", rule)
        self.assertIn("root /var/www/content/cafe.ru;", rule)
        self.assertEqual(repo.dialogue.step, DialogueStep.ASK_BRIEF)
        self.assertIn("Запись домена отвечает", sent[-1])

    def test_taken_name_stays_on_the_same_step(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "rules").mkdir()
            (root / "rules" / "old.conf").write_text(
                "server {\n    server_name coffee.example.com;\n}\n",
                encoding="utf-8",
            )
            graph, repo, sent = self._graph(
                root,
                Dialogue(channel=Channel.MAX, chat_id="9", user_id="5", step=DialogueStep.ASK_SLUG),
                public_ip=None,
            )
            asyncio.run(graph.handle(_message("coffee")))
            self.assertFalse((root / "rules" / "coffee.example.com.conf").exists())

        self.assertEqual(repo.dialogue.step, DialogueStep.ASK_SLUG)
        self.assertIn("уже занят", sent[-1])

    def test_restart_removes_the_site_files(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            graph, repo, _sent = self._graph(
                root,
                Dialogue(channel=Channel.MAX, chat_id="9", user_id="5", step=DialogueStep.ASK_SLUG),
                public_ip=None,
            )
            asyncio.run(graph.handle(_message("coffee")))
            self.assertTrue((root / "rules" / "coffee.example.com.conf").is_file())
            asyncio.run(graph.handle(_message("Начать сначала")))
            self.assertFalse((root / "rules" / "coffee.example.com.conf").exists())
            self.assertFalse((root / "content" / "coffee.example.com").exists())

        self.assertEqual(repo.dialogue.step, DialogueStep.ASK_DOMAIN)
        self.assertIsNone(repo.dialogue.host)

    def test_ready_index_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dialogue = Dialogue(
                channel=Channel.MAX,
                chat_id="9",
                user_id="5",
                step=DialogueStep.OWN_DNS,
                host="cafe.ru",
            )
            reserve_site(
                content_dir=root / "content",
                rules_dir=root / "rules",
                folder="cafe.ru",
                name="cafe.ru",
                owner=owner_line(dialogue.channel.value, dialogue.chat_id),
            )
            index = root / "content" / "cafe.ru" / "index.html"
            index.write_text("готовый", encoding="utf-8")
            graph, _repo, _sent = self._graph(root, dialogue)
            with patch("botik.app.graph._address_matches", return_value=True):
                asyncio.run(graph.handle(_message("готово")))
            self.assertEqual(index.read_text(encoding="utf-8"), "готовый")


if __name__ == "__main__":
    unittest.main()
