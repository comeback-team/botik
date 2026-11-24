"""Запрос на создание сайта: промпт и structured output для GigaChat."""
from botik.site.brief_parser import BriefRegistry
from botik.site.request import SiteRequest, build_site_request
from botik.site.structure import SiteStructure

__all__ = ["BriefRegistry","SiteRequest","SiteStructure","build_site_request"]
