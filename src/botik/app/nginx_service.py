"""Единственный писатель состояния nginx.

Сначала сохраняем желаемое, потом сверяем диск. Если reload не прошёл,
в базе остаётся то, что хотели, и следующий commit применяет его снова.
"""

import asyncio
import logging

from botik.domain.nginx import ApplyReport, NginxChange, apply_change
from botik.ports.nginx import NginxManager
from botik.ports.repos import NginxStateRepository

logger = logging.getLogger(__name__)


class NginxService:
    def __init__(self, repo: NginxStateRepository, manager: NginxManager) -> None:
        self._repo = repo
        self._manager = manager
        self._lock = asyncio.Lock()

    async def commit(self, change: NginxChange) -> ApplyReport:
        async with self._lock:
            desired = apply_change(await self._repo.get(), change)
            await self._repo.save(desired)
            logger.info("nginx desired state saved, %d sites", len(desired.sites))
            return await self._manager.apply(desired)
