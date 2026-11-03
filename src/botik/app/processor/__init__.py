"""Обработка ответа модели."""

from botik.app.processor.interpret import ResponseProcessor
from botik.app.processor.registry import handler_registry

__all__ = ["ResponseProcessor", "handler_registry"]
