"""Запись наших site-файлов и перечитывание nginx.

apply получает готовый список сайтов. Дальше только файлы и две команды:
рендер sites-available/<name>.conf из шаблона, `nginx -t`, при успехе
symlink в sites-enabled и `nginx -s reload`. Пишем только файлы с slug-именем
сайта в каталогах из настроек. Команду выбирает этот класс, не модель.
"""

from pathlib import Path

from botik.domain.nginx import ApplyReport, NginxDesiredState


class SystemNginxManager:
    def __init__(self, sites_dir: Path, enabled_dir: Path) -> None:
        self._sites_dir = sites_dir
        self._enabled_dir = enabled_dir

    async def apply(self, state: NginxDesiredState) -> ApplyReport:
        del state
        raise NotImplementedError("nginx apply is not implemented")
