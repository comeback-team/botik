"""Транскрипт подменяет голосовое до передачи сообщения дальше."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from botik.app.speech import message_from_speech, render_speech
from botik.domain.messages import Channel, InboundMessage


def _message() -> InboundMessage:
    return InboundMessage(
        channel=Channel.TELEGRAM,
        update_id="1",
        chat_id="2",
        message_id="3",
        user_id="4",
    )


class SpeechTest(unittest.TestCase):
    def test_transcript_replaces_voice_tag(self) -> None:
        message, tags = message_from_speech(_message(), ["<voice>", "<photo>"], " привет ")
        self.assertEqual(message.text, "привет")
        self.assertEqual(tags, ["<photo>"])

    def test_empty_transcript_keeps_the_voice(self) -> None:
        message, tags = message_from_speech(_message(), ["<voice>"], "  ")
        self.assertIsNone(message.text)
        self.assertEqual(tags, ["<voice>"])

    def test_file_is_removed_after_transcription(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        handle.close()
        path = Path(handle.name)

        class Fake:
            async def transcribe(self, audio: Path) -> str:
                self.audio = audio
                return "раз"

        message, tags = asyncio.run(render_speech(_message(), ["<voice>"], path, Fake()))
        self.assertEqual(message.text, "раз")
        self.assertEqual(tags, [])
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
