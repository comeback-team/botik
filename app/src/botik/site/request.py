"""Сборка запроса на сайт для GigaChat.

Модель получает бриф и схему SiteStructure. В ответ она отдаёт JSON
с блоками, а не HTML.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from botik.site.schema import gigachat_schema
from botik.site.structure import SiteStructure
from botik.site.brief_parser import BriefRegistry

SchemaMode = Literal["inline", "prompt"]

# Варианты шаблонов из каталога blocks1. В промпт попадают имена, не файлы.
BLOCK_VARIANTS: dict[str, tuple[str, ...]] = {
    "contacts": ("default",),
    "cta": ("default",),
    "faq": ("default",),
    "features": ("default",),
    "footer": ("default",),
    "gallery": ("default",),
    "header": ("default",),
    "hero": ("default", "split"),
    "interactive": ("default",),
    "menu": ("default",),
    "pricing": ("default",),
    "stats": ("default",),
    "steps": ("default",),
    "team": ("default",),
    "testimonials": ("default",),
    "text": ("default",),
}

_SYSTEM = (
    "Ты — генератор декларативного сайта в парадигме A2UI. Ты НЕ пишешь HTML, CSS и JS. "
    "Только JSON по схеме: блоки, тексты, компоненты, действия.\n"
    "ПРАВИЛА:\n"
    "1. Доступно 16 типов блоков: header, hero, text, features, gallery, interactive, "
    "faq, footer, stats, pricing, testimonials, steps, cta, contacts, team, menu. "
    "header первый, footer последний, ровно один interactive обязателен.\n"
    "2. Подбирай блоки под бизнес: еда/товары → menu; пакеты услуг → pricing; "
    "доверие → stats и testimonials; процесс → steps; люди → team; "
    "адрес и часы → contacts; перед footer ставь cta. Всего 6-12 блоков.\n"
    "3. Компоненты interactive только: text_input, number_stepper, select_options, "
    "action_button. Сначала поля ввода, последними кнопки.\n"
    "4. id компонентов — семантический snake_case, уникальны. target_endpoint — /api/...\n"
    "5. submit_action — snake_case: book_table, order_pizza, send_lead, order_menu.\n"
    "6. Форматы полей: stats.items = {value (до 12 симв), label}; "
    "pricing.items = {name, price (строка), period, features[], highlighted, cta_text}; "
    "testimonials.items = {author, role, text, rating 1-5}; "
    "steps.items = {title, description} (3-5); team.items = {name, role, bio}; "
    "menu.items = {name, description, price (целое число)}, menu.currency — символ валюты.\n"
    "7. Тексты по-русски, продающие, конкретные, под бизнес из брифа. "
    "Тональность и цвета выбери сам под этот бизнес. Цвета — HEX #RRGGBB.\n"
    "8. Не выдумывай телефоны, адреса и URL картинок: пустые строки, если не даны.\n"
    "8а. ЗАПРЕЩЕНО использовать фигурные скобки { } в любом тексте. "
    "Никаких {icon}, {value}, {placeholder} — это ломает рендер. "
    "Пиши обычный текст без спец-символов.\n"
    "9. variant — визуальный вариант из каталога. Не уверен — default.\n"
    "ПРИМЕР interactive:\n"
    '{"type":"interactive","title":"Соберите пиццу","submit_action":"order_pizza",'
    '"components":[{"type":"select_options","id":"pizza_size","label":"Размер",'
    '"options":["25 см","30 см","35 см"]},{"type":"number_stepper","id":"pizza_count",'
    '"label":"Количество","min":1,"max":10,"step":1,"initial_value":1},'
    '{"type":"text_input","id":"phone_number","label":"Телефон",'
    '"placeholder":"+7 900 000-00-00","required":true},'
    '{"type":"action_button","id":"submit_order","label":"Заказать",'
    '"action_type":"submit","target_endpoint":"/api/orders/pizza"}]}\n'
    "Ответ — строго JSON без markdown и пояснений."
)


@dataclass(slots=True)
class SiteRequest:
    """Промпт и схема, которые уходят в chat/completions."""
    system: str
    user: str
    response_format: dict[str, Any]
    output_model: type[BaseModel]
    brief_registry: BriefRegistry      # ← новое
    masked_brief: str                  # ← новое


def build_site_request(brief: str, *, schema_mode: SchemaMode = "inline") -> SiteRequest:
    """Собрать запрос: системный промпт, бриф и structured output.

    schema_mode inline кладёт плоскую JSON Schema в response_format.
    schema_mode prompt дописывает ту же схему текстом в системный промпт
    и просит обычный json_object: так GigaChat отвечает, если json_schema
    он отклонил.
    """
    
    text = brief.strip()
    if len(text) < 3:
        raise ValueError("Описание бизнеса слишком короткое")
    if schema_mode not in {"inline", "prompt"}:
        raise ValueError(f"Неизвестный schema_mode: {schema_mode}")

    schema = gigachat_schema(SiteStructure)
    system = _system_prompt()
    if schema_mode == "prompt":
        system += "\nJSON-СХЕМА:\n" + json.dumps(schema, ensure_ascii=False)
        response_format: dict[str, Any] = {"type": "json_object"}
    else:
        response_format = {"type": "json_schema", "schema": schema}

    # Маскируем чувствительные данные
    registry = BriefRegistry()
    masked_brief = registry.mask(text)

    return SiteRequest(
        system=system,
        user=_user_prompt(masked_brief),   # ← передаём маскированный
        response_format=response_format,
        output_model=SiteStructure,
        brief_registry=registry,           # ← новое
        masked_brief=masked_brief,         # ← новое
    )


def _system_prompt() -> str:
    variants = "\n".join(
        f"- {name}: {', '.join(options)}" for name, options in BLOCK_VARIANTS.items()
    )
    token_rules = (
        "\n10. Чувствительные данные пользователя (ссылки на изображения, телефоны, "
        "email, адреса) замаскированы в брифе короткими метками <1>, <2>, <3>. "
        "Скопируй метку В ТОЧНОСТИ (одним словом, без изменений) в соответствующее "
        "поле: image_url, phone, email, address. "
        "НИКОГДА не вставляй в JSON реальные ссылки и контакты — их у тебя нет. "
        "Нет метки для поля — пустая строка. "
        'Пример: {"type":"hero","title":"...","image_url":"<1>"}.'
    )
    return (
        f"{_SYSTEM}\n"
        f"{token_rules}\n"
        f"КАТАЛОГ ВАРИАНТОВ (выбирай только из него):\n{variants}"
        "\nЗаполняй все блоки конкретикой из брифа, без пустых заглушек."
    )


def _user_prompt(brief: str) -> str:
    return (
        f'Описание бизнеса:\n"""{brief}"""\n'
        "Собери сайт из 6-12 блоков, заполненных конкретикой этого бизнеса. "
        "Обязательно interactive с главным сценарием."
    )

def build_modify_request(
    current_structure: dict[str, Any],
    instruction: str,
    *,
    schema_mode: SchemaMode = "inline",
    registry: BriefRegistry | None = None,   # ← новое
) -> SiteRequest:
    text = instruction.strip()
    if len(text) < 3:
        raise ValueError("Инструкция слишком короткая")

    schema = gigachat_schema(SiteStructure)
    system = _system_prompt()
    if schema_mode == "prompt":
        system += "\nJSON-СХЕМА:\n" + json.dumps(schema, ensure_ascii=False)
        response_format: dict[str, Any] = {"type": "json_object"}
    else:
        response_format = {"type": "json_schema", "schema": schema}

    system += (
        "\nЗАДАЧА: модифицировать существующую структуру сайта по инструкции пользователя. "
        "Сохрани все блоки, которые не нужно менять. "
        "Верни полную обновлённую структуру в формате JSON."
    )

    # Маскируем инструкцию (если там есть новые {{img:...}} и т.п.)
    reg = registry if registry is not None else BriefRegistry()
    masked_instruction = reg.mask(text)

    user = _modify_user_prompt(current_structure, masked_instruction)

    return SiteRequest(
        system=system,
        user=user,
        response_format=response_format,
        output_model=SiteStructure,
        brief_registry=reg,
        masked_brief=masked_instruction,
    )

def _modify_user_prompt(current_structure: dict[str, Any], instruction: str) -> str:
    """Сформировать пользовательский промпт для модификации."""
    return (
        f"Текущая структура сайта:\n```json\n"
        f"{json.dumps(current_structure, ensure_ascii=False, indent=2)}\n```\n\n"
        f"Инструкция пользователя:\n\"\"\"{instruction}\"\"\"\n\n"
        "Измени структуру сайта согласно инструкции. "
        "Сохрани все блоки, которые не нужно менять. "
        "Верни полную обновлённую структуру в формате JSON."
    )
