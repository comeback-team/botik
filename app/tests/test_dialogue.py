"""Диалог в Mongo: первый заход создаёт шаг, повторный его не сбрасывает."""

import asyncio
import unittest

from botik.adapters.mongo.repos import MongoDialogues
from botik.domain.dialogue import DialogueStep
from botik.domain.messages import Channel, InboundMessage


class MemoryCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.indexes: list[tuple] = []

    async def create_index(self, keys, unique: bool = False, name: str | None = None) -> None:
        self.indexes.append((tuple(keys), unique, name))

    async def find_one(self, query: dict) -> dict | None:
        found = self._find(query)
        return None if found is None else dict(found)

    async def find_one_and_update(
        self,
        query: dict,
        update: dict,
        upsert: bool = False,
        return_document=None,
    ) -> dict | None:
        del return_document
        found = self._find(query)
        if found is None:
            if not upsert:
                return None
            found = dict(query)
            found.update(update.get("$setOnInsert", {}))
            self.docs.append(found)
        found.update(update.get("$set", {}))
        return dict(found)

    def _find(self, query: dict) -> dict | None:
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None


def _message(user_id: str = "7") -> InboundMessage:
    return InboundMessage(
        channel=Channel.TELEGRAM,
        update_id="1",
        chat_id="42",
        message_id="3",
        user_id=user_id,
        text="привет",
    )


class DialogueRepositoryTest(unittest.TestCase):
    def test_ensure_creates_dialogue_and_keeps_step(self) -> None:
        collection = MemoryCollection()
        repo = MongoDialogues(collection)

        created = asyncio.run(repo.ensure(_message()))
        self.assertEqual(created.step, DialogueStep.GREET)
        self.assertEqual(created.user_id, "7")
        self.assertEqual(created.chat_id, "42")
        self.assertEqual(collection.indexes[0][2], "channel_chat")

        moved = asyncio.run(repo.set_step(Channel.TELEGRAM, "42", DialogueStep.ASK_BRIEF))
        self.assertEqual(moved.step, DialogueStep.ASK_BRIEF)

        again = asyncio.run(repo.ensure(_message(user_id="8")))
        self.assertEqual(again.step, DialogueStep.ASK_BRIEF)
        self.assertEqual(again.user_id, "8")
        self.assertEqual(len(collection.docs), 1)

        loaded = asyncio.run(repo.get(Channel.TELEGRAM, "42"))
        assert loaded is not None
        self.assertEqual(loaded.step, DialogueStep.ASK_BRIEF)

    def test_set_step_requires_an_existing_dialogue(self) -> None:
        repo = MongoDialogues(MemoryCollection())
        with self.assertRaises(LookupError):
            asyncio.run(repo.set_step(Channel.MAX, "9", DialogueStep.ASK_SLUG))

    def test_missing_uri_does_not_open_a_client(self) -> None:
        repo = MongoDialogues(None)
        with self.assertRaises(RuntimeError):
            asyncio.run(repo.get(Channel.MAX, "9"))


if __name__ == "__main__":
    unittest.main()
