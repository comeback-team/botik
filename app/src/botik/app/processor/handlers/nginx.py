"""Намерение nginx превращается в команду. До диска она здесь не доходит."""

from botik.app.processor.context import TurnContext
from botik.domain.effects import Effect
from botik.domain.llm import Intent, ToolSpec
from botik.domain.nginx import NginxChange

_PARAMETERS = {
    "type": "object",
    "additionalProperties": False,
    "required": ["op", "name"],
    "properties": {
        "op": {"type": "string", "enum": ["upsert", "disable", "remove"]},
        "name": {"type": "string"},
        "server_name": {"type": "string"},
        "upstream": {"type": "string", "description": "host:port, без путей и схемы"},
    },
}


class NginxIntentHandler:
    name = "nginx"

    def tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=(
                "Изменить сайт в nginx. "
                "upsert требует name, server_name и upstream (host:port). "
                "disable и remove требуют name. Сырой конфиг передавать нельзя."
            ),
            parameters=_PARAMETERS,
        )

    async def handle(self, ctx: TurnContext, intent: Intent) -> list[Effect]:
        del ctx
        return [NginxChange.model_validate(intent.params)]
