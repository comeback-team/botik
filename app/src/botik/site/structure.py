"""Инструкция сайта, которую должна вернуть модель.

Это не вёрстка. Модель заполняет блоки, тексты и компоненты,
а HTML из этой структуры собирается отдельно.
"""
import logging
import re
from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from annotated_types import MaxLen
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)

_IMAGE_REF_RE = re.compile(
    r"^(<\d+>"                          # маска <1> — если реплейс вдруг не сделали
    r"|/media/[a-zA-Z0-9_.\-]{1,128}"   # наша сохранённая картинка
    r"|https?://[^\s\"'<>\\]{1,250})$"  # чистая ссылка — вставлена ТОЛЬКО нашим resolve
)

def _clean_image_url(value: str) -> str:
    """Модель не видит ссылок вовсе — она копирует только маски <N>.
    Реальные ссылки появляются в полях исключительно после нашего реплейса."""
    value = (value or "").strip()
    return value if _IMAGE_REF_RE.match(value) else ""


_COMPONENT_ID = r"^[a-z][a-z0-9_]{1,63}$"
_ENDPOINT = r"^/[A-Za-z0-9_\-/]{1,120}$"
_SUBMIT_ACTION = r"^[a-z][a-z0-9_]{1,79}$"
_HTML_TAG = re.compile(r"</?\s*[a-zA-Z][^>]*>")
_CURLY_BRACES = re.compile(r"\{[^}]*\}")  # {icon:clock}, {value:...} и т.д.


class ComponentType(StrEnum):
    TEXT_INPUT = "text_input"
    NUMBER_STEPPER = "number_stepper"
    SELECT_OPTIONS = "select_options"
    ACTION_BUTTON = "action_button"


class ActionType(StrEnum):
    SUBMIT = "submit"
    ADD_TO_CART = "add_to_cart"
    RESET = "reset"


class BlockType(StrEnum):
    HEADER = "header"
    HERO = "hero"
    TEXT = "text"
    FEATURES = "features"
    GALLERY = "gallery"
    INTERACTIVE = "interactive"
    FAQ = "faq"
    FOOTER = "footer"
    STATS = "stats"
    PRICING = "pricing"
    TESTIMONIALS = "testimonials"
    STEPS = "steps"
    CTA = "cta"
    CONTACTS = "contacts"
    TEAM = "team"
    MENU = "menu"


def _reject_html(value: str) -> str:
    if _HTML_TAG.search(value):
        raise ValueError(f"HTML запрещён в A2UI: {value!r}")
    # Чистим фигурные скобки — модель не должна генерить {icon}, {value}
    value = _CURLY_BRACES.sub("", value)
    return value.strip()


def _clip_words(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    cut = normalized[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:!?—–-«\"'(") or normalized[:limit].rstrip()


class A2UIComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: str
    id: str = Field(pattern=_COMPONENT_ID)
    label: str = Field(min_length=1, max_length=120)

    @field_validator("label")
    @classmethod
    def _label_clean(cls, value: str) -> str:
        return _reject_html(value)


class TextInput(A2UIComponent):
    type: Literal[ComponentType.TEXT_INPUT] = ComponentType.TEXT_INPUT
    placeholder: str = Field("", max_length=120)
    required: bool = False

    @field_validator("placeholder")
    @classmethod
    def _placeholder_clean(cls, value: str) -> str:
        return _reject_html(value)


class NumberStepper(A2UIComponent):
    type: Literal[ComponentType.NUMBER_STEPPER] = ComponentType.NUMBER_STEPPER
    min: int = Field(0, ge=0, le=1000)
    max: int = Field(10, ge=1, le=1000)
    step: int = Field(1, ge=1, le=100)
    initial_value: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _normalize(self) -> "NumberStepper":
        if self.max <= self.min:
            raise ValueError(f"min={self.min} >= max={self.max}")
        clamped = min(max(self.initial_value, self.min), self.max)
        steps = round((clamped - self.min) / self.step)
        self.initial_value = min(self.min + steps * self.step, self.max)
        return self


class SelectOptions(A2UIComponent):
    type: Literal[ComponentType.SELECT_OPTIONS] = ComponentType.SELECT_OPTIONS
    options: list[str] = Field(min_length=2, max_length=12)

    @field_validator("options")
    @classmethod
    def _clean_options(cls, value: list[str]) -> list[str]:
        options: list[str] = []
        for item in value:
            text = _reject_html(item)
            if not text or len(text) > 80:
                raise ValueError(f"Некорректный вариант: {item!r}")
            if text not in options:
                options.append(text)
        if len(options) < 2:
            raise ValueError("Нужно >= 2 различающихся варианта")
        return options


class ActionButton(A2UIComponent):
    type: Literal[ComponentType.ACTION_BUTTON] = ComponentType.ACTION_BUTTON
    action_type: ActionType = ActionType.SUBMIT
    target_endpoint: str = Field(pattern=_ENDPOINT)


A2UIComponentUnion = Annotated[
    Union[TextInput, NumberStepper, SelectOptions, ActionButton],
    Field(discriminator="type"),
]


class Colors(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    primary: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class BlockBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    variant: str = Field("default", pattern=r"^[a-z][a-z0-9_]{0,23}$")

    @model_validator(mode="before")
    @classmethod
    def _trim_long_texts(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        result = dict(data)
        for name, field in cls.model_fields.items():
            value = result.get(name)
            if not isinstance(value, str):
                continue
            limit = next((meta.max_length for meta in field.metadata if isinstance(meta, MaxLen)), None)
            if limit and len(value) > limit:
                result[name] = _clip_words(value, limit)
        return result


class HeaderBlock(BlockBase):
    type: Literal[BlockType.HEADER] = BlockType.HEADER
    logo_text: str = Field(min_length=1, max_length=60)
    menu: list[str] = Field(min_length=2, max_length=6)


class HeroBlock(BlockBase):
    type: Literal[BlockType.HERO] = BlockType.HERO
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field("", max_length=240)
    cta_text: str = Field("Оставить заявку", max_length=40)
    highlights: list[str] = Field(default_factory=list, max_length=3)


class TextBlock(BlockBase):
    type: Literal[BlockType.TEXT] = BlockType.TEXT
    title: str = Field(max_length=120)
    content: str = Field(min_length=1, max_length=1200)


class FeatureItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(max_length=80)
    description: str = Field("", max_length=240)


class FeaturesBlock(BlockBase):
    type: Literal[BlockType.FEATURES] = BlockType.FEATURES
    title: str = Field("Наши преимущества", max_length=120)
    items: list[FeatureItem] = Field(min_length=2, max_length=6)


class GalleryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    caption: str = Field(max_length=80)
    alt: str = Field("", max_length=120)


class GalleryBlock(BlockBase):
    type: Literal[BlockType.GALLERY] = BlockType.GALLERY
    title: str = Field("Галерея", max_length=120)
    items: list[GalleryItem] = Field(min_length=2, max_length=8)


class FaqItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(max_length=160)
    answer: str = Field(max_length=600)


class FaqBlock(BlockBase):
    type: Literal[BlockType.FAQ] = BlockType.FAQ
    title: str = Field("Частые вопросы", max_length=120)
    items: list[FaqItem] = Field(min_length=2, max_length=6)


class FooterBlock(BlockBase):
    type: Literal[BlockType.FOOTER] = BlockType.FOOTER
    email: str = Field("", max_length=120)
    phone: str = Field("", max_length=40)
    address: str = Field("", max_length=200)
    socials: list[str] = Field(default_factory=list, max_length=4)


class InteractiveBlock(BlockBase):
    type: Literal[BlockType.INTERACTIVE] = BlockType.INTERACTIVE
    title: str = Field("Оставьте заявку", min_length=1, max_length=120)
    submit_action: str = Field(pattern=_SUBMIT_ACTION)
    components: list[A2UIComponentUnion] = Field(min_length=1, max_length=10)

    @field_validator("title")
    @classmethod
    def _title_clean(cls, value: str) -> str:
        return _reject_html(value)

    @field_validator("submit_action", mode="before")
    @classmethod
    def _slug(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower().replace("-", "_").replace(" ", "_")
        return value

    @model_validator(mode="after")
    def _validate_components(self) -> "InteractiveBlock":
        seen: dict[str, int] = {}
        for component in self.components:
            stem = component.id[:56]
            if stem in seen:
                seen[stem] += 1
                component.id = f"{stem}_{seen[stem]}"
            else:
                seen[stem] = 1
                component.id = stem
        inputs = [component for component in self.components if not isinstance(component, ActionButton)]
        if not inputs:
            raise ValueError("interactive обязан содержать хотя бы одно поле ввода")
        buttons = [component for component in self.components if isinstance(component, ActionButton)]
        if not any(button.action_type == ActionType.SUBMIT for button in buttons):
            buttons.append(
                ActionButton(
                    id="submit_button",
                    label="Отправить",
                    action_type=ActionType.SUBMIT,
                    target_endpoint=buttons[0].target_endpoint if buttons else "/api/leads",
                )
            )
        self.components = inputs + buttons
        return self


class StatItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: str = Field(min_length=1, max_length=12)
    label: str = Field(min_length=1, max_length=60)


class StatsBlock(BlockBase):
    type: Literal[BlockType.STATS] = BlockType.STATS
    title: str = Field("", max_length=120)
    items: list[StatItem] = Field(min_length=2, max_length=4)


class PricingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=60)
    price: str = Field(min_length=1, max_length=40)
    period: str = Field("", max_length=30)
    features: list[str] = Field(min_length=1, max_length=6)
    highlighted: bool = False
    cta_text: str = Field("Выбрать", max_length=30)


class PricingBlock(BlockBase):
    type: Literal[BlockType.PRICING] = BlockType.PRICING
    title: str = Field("Тарифы", max_length=120)
    items: list[PricingPlan] = Field(min_length=2, max_length=4)


class TestimonialItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    author: str = Field(min_length=1, max_length=60)
    role: str = Field("", max_length=60)
    text: str = Field(min_length=1, max_length=400)
    rating: int = Field(5, ge=1, le=5)


class TestimonialsBlock(BlockBase):
    type: Literal[BlockType.TESTIMONIALS] = BlockType.TESTIMONIALS
    title: str = Field("Отзывы", max_length=120)
    items: list[TestimonialItem] = Field(min_length=2, max_length=4)


class StepItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=80)
    description: str = Field("", max_length=240)


class StepsBlock(BlockBase):
    type: Literal[BlockType.STEPS] = BlockType.STEPS
    title: str = Field("Как мы работаем", max_length=120)
    items: list[StepItem] = Field(min_length=3, max_length=5)


class CtaBlock(BlockBase):
    type: Literal[BlockType.CTA] = BlockType.CTA
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field("", max_length=240)
    button_text: str = Field("Оставить заявку", max_length=40)


class ContactsBlock(BlockBase):
    type: Literal[BlockType.CONTACTS] = BlockType.CONTACTS
    title: str = Field("Контакты", max_length=120)
    phone: str = Field("", max_length=40)
    email: str = Field("", max_length=120)
    address: str = Field("", max_length=200)
    hours: str = Field("", max_length=200)


class TeamMember(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=60)
    role: str = Field(min_length=1, max_length=60)
    bio: str = Field("", max_length=200)


class TeamBlock(BlockBase):
    type: Literal[BlockType.TEAM] = BlockType.TEAM
    title: str = Field("Команда", max_length=120)
    items: list[TeamMember] = Field(min_length=2, max_length=6)


class MenuItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    description: str = Field("", max_length=160)
    price: int = Field(ge=0, le=100000)


class MenuBlock(BlockBase):
    type: Literal[BlockType.MENU] = BlockType.MENU
    title: str = Field("Меню", max_length=120)
    currency: str = Field("₽", max_length=4)
    submit_action: str = Field("order_menu", pattern=_SUBMIT_ACTION)
    target_endpoint: str = Field("/api/orders/menu", pattern=_ENDPOINT)
    items: list[MenuItem] = Field(min_length=2, max_length=8)


BlockUnion = Annotated[
    Union[
        HeaderBlock,
        HeroBlock,
        TextBlock,
        FeaturesBlock,
        GalleryBlock,
        InteractiveBlock,
        FaqBlock,
        FooterBlock,
        StatsBlock,
        PricingBlock,
        TestimonialsBlock,
        StepsBlock,
        CtaBlock,
        ContactsBlock,
        TeamBlock,
        MenuBlock,
    ],
    Field(discriminator="type"),
]


class SiteStructure(BaseModel):
    business_type: str = Field(min_length=1, max_length=100)
    tone: str = Field(min_length=1, max_length=60)
    colors: Colors
    blocks: list[BlockUnion] = Field(min_length=3, max_length=20)

    @model_validator(mode="after")
    def _assemble(self) -> "SiteStructure":
        headers = [block for block in self.blocks if isinstance(block, HeaderBlock)]
        footers = [block for block in self.blocks if isinstance(block, FooterBlock)]
        middle = [block for block in self.blocks if not isinstance(block, (HeaderBlock, FooterBlock))]
        if not headers:
            headers = [
                HeaderBlock(
                    logo_text=self.business_type.capitalize(),
                    menu=["Главная", "Услуги", "Контакты"],
                )
            ]
        if not footers:
            footers = [FooterBlock()]
        self.blocks = headers[:1] + middle + footers[:1]
        if not any(isinstance(block, InteractiveBlock) for block in self.blocks):
            raise ValueError("Сайт обязан содержать блок interactive")
        used: set[str] = set()
        for block in self.blocks:
            if not isinstance(block, InteractiveBlock):
                continue
            for component in block.components:
                stem = component.id[:56]
                candidate = stem
                suffix = 2
                while candidate in used:
                    candidate = f"{stem}_{suffix}"
                    suffix += 1
                component.id = candidate
                used.add(candidate)
        return self

_COMPONENT_MODELS: dict[str, type[A2UIComponent]] = {
    ComponentType.TEXT_INPUT: TextInput,
    ComponentType.NUMBER_STEPPER: NumberStepper,
    ComponentType.SELECT_OPTIONS: SelectOptions,
    ComponentType.ACTION_BUTTON: ActionButton,
}

_BLOCK_MODELS: dict[str, type[BaseModel]] = {
    BlockType.HEADER: HeaderBlock,
    BlockType.HERO: HeroBlock,
    BlockType.TEXT: TextBlock,
    BlockType.FEATURES: FeaturesBlock,
    BlockType.GALLERY: GalleryBlock,
    BlockType.INTERACTIVE: InteractiveBlock,
    BlockType.FAQ: FaqBlock,
    BlockType.FOOTER: FooterBlock,
    BlockType.STATS: StatsBlock,
    BlockType.PRICING: PricingBlock,
    BlockType.TESTIMONIALS: TestimonialsBlock,
    BlockType.STEPS: StepsBlock,
    BlockType.CTA: CtaBlock,
    BlockType.CONTACTS: ContactsBlock,
    BlockType.TEAM: TeamBlock,
    BlockType.MENU: MenuBlock,
}


def _default_fill(block_type: str, business: str) -> dict[str, Any]:
    """Значения для полей, которые модель чаще всего забывает."""
    table: dict[str, dict[str, Any]] = {
        BlockType.HEADER: {
            "logo_text": business,
            "menu": ["Главная", "Услуги", "Контакты"],
        },
        BlockType.HERO: {
            "title": business,
            "subtitle": "",
            "cta_text": "Оставить заявку",
        },
        BlockType.TEXT: {
            "title": "О нас",
            "content": f"{business}: работаем для вас каждый день.",
        },
        BlockType.CTA: {
            "title": f"{business} — оставьте заявку прямо сейчас",
            "subtitle": "",
            "button_text": "Оставить заявку",
        },
        BlockType.INTERACTIVE: {
            "title": "Оставьте заявку",
            "submit_action": "send_lead",
            "components": [
                {
                    "type": "text_input",
                    "id": "phone_number",
                    "label": "Телефон",
                    "placeholder": "+7 900 000-00-00",
                    "required": True,
                }
            ],
        },
    }
    return table.get(block_type, {})


def _component_valid(component: Any) -> bool:
    """Проверить компонент интерактивного блока по его дискриминатору."""
    if not isinstance(component, dict):
        return False
    model = _COMPONENT_MODELS.get(str(component.get("type", "")).strip().lower())
    if model is None:
        return False
    try:
        model.model_validate(component)
    except ValidationError:
        return False
    return True

def _prune_block(block: dict[str, Any], model: type[BaseModel]) -> dict[str, Any]:
    """Выкинуть ключи, которых нет в модели блока."""
    allowed = set(model.model_fields.keys())
    return {key: value for key, value in block.items() if key in allowed}

def _repair_block(block: Any, business: str) -> dict[str, Any] | None:
    """Валидный блок вернуть как есть, дырявый подлатать, безнадёжный отбросить."""
    if not isinstance(block, dict):
        return None
    kind = block.get("type")
    if isinstance(kind, str):
        kind = kind.strip().lower()
    
    model = _BLOCK_MODELS.get(kind)
    if model is None:
        return None
        
    # Используем _prune_block, чтобы выкинуть поля вроде header.title
    patched = _prune_block(dict(block), model)
    patched["type"] = kind
    
    if kind == BlockType.INTERACTIVE and isinstance(patched.get("components"), list):
        # Чистим компоненты от мусора
        pruned: list[Any] = []
        for item in patched["components"]:
            if not isinstance(item, dict):
                continue
            ctype = str(item.get("type", "")).strip().lower()
            cmodel = _COMPONENT_MODELS.get(ctype)
            if cmodel is None:
                continue
            candidate = _prune_block(dict(item), cmodel)
            candidate["type"] = ctype
            try:
                cmodel.model_validate(candidate)
            except ValidationError:
                continue
            pruned.append(candidate)
        patched["components"] = pruned
        
    # Подставляем дефолты для отсутствующих полей
    for name, value in _default_fill(kind, business).items():
        if patched.get(name) in (None, "", []):
            patched[name] = value

    try:
        model.model_validate(patched)
    except ValidationError:
        # Если блок всё ещё невалиден, но он КРИТИЧЕСКИЙ — возвращаем "пустышку"
        if kind in (BlockType.HEADER, BlockType.HERO, BlockType.FOOTER, BlockType.INTERACTIVE):
            fallback = dict(_default_fill(kind, business))
            fallback["type"] = kind
            try:
                model.model_validate(fallback)
                return fallback
            except ValidationError:
                pass
        return None
    return patched


def _repair_colors(colors: Any) -> dict[str, str]:
    result = {"primary": "#2563EB", "secondary": "#F59E0B"}
    if isinstance(colors, dict):
        for key in ("primary", "secondary"):
            value = colors.get(key)
            if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value.strip()):
                result[key] = value.strip()
    return result


def repair_structure(data: Any) -> dict[str, Any]:
    """Подлатать сырой ответ модели так, чтобы SiteStructure его принял.

    GigaChat иногда присылает блоки без обязательных полей (header только
    с type и variant). Дыры закрываем значениями по умолчанию, безнадёжные
    блоки отбрасываем: лучше сайт без одного блока, чем падение генерации.
    """
    if not isinstance(data, dict):
        raise ValueError("Ожидался JSON-объект")
    fixed = dict(data)
    business = _clip_words(str(fixed.get("business_type") or "").strip() or "Наша компания", 100)
    raw_blocks = fixed.get("blocks")
    blocks = raw_blocks if isinstance(raw_blocks, list) else []
    fixed["business_type"] = business
    fixed["blocks"] = [item for item in (_repair_block(block, business) for block in blocks) if item is not None]
    if not str(fixed.get("tone") or "").strip():
        fixed["tone"] = "дружелюбный"
    fixed["colors"] = _repair_colors(fixed.get("colors"))
    return fixed


def parse_structure(data: Any) -> SiteStructure:
    """Разобрать ответ модели: сначала строго, при ошибке — с автопочинкой."""
    try:
        return SiteStructure.model_validate(data)
    except ValidationError as exc:
        logger.warning("Ответ модели с дефектами (%s шт.), чиним", exc.error_count())
        return SiteStructure.model_validate(repair_structure(data))
