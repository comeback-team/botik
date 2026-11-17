"""Реестр намерений. Новое поведение добавляется сюда, оркестратор не растёт."""

from botik.app.processor.handler import IntentHandler
from botik.app.processor.handlers.nginx import NginxIntentHandler


def handler_registry() -> dict[str, IntentHandler]:
    handlers: tuple[IntentHandler, ...] = (NginxIntentHandler(),)
    return {handler.name: handler for handler in handlers}
