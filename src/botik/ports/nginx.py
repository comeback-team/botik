"""Применение желаемого состояния nginx к диску и процессу.

Вызов сериализует NginxService: параллельных reload быть не должно.
Порядок внутри адаптера: шаблон, nginx -t, подмена файлов, reload.
Предыдущие файлы остаются до успешного теста, чтобы было чем откатить.
"""

from typing import Protocol

from botik.domain.nginx import ApplyReport, NginxDesiredState


class NginxManager(Protocol):
    async def apply(self, state: NginxDesiredState) -> ApplyReport: ...
