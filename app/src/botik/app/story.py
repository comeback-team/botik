"""Шаги диалога со схемой storytelling.

Функция не ходит в сеть и не пишет файлы. Оба мессенджера приносят уже
готовый текст: голос к этому моменту расшифрован.
"""

import re
from dataclasses import dataclass

from botik.domain.dialogue import Dialogue, DialogueStep
from botik.domain.nginx import site_slug

_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_URL = re.compile(r"^https?://\S+$")

_RESTART = {"начать сначала", "/start", "start", "сначала"}
_OWN = {"свой", "свой домен", "есть домен", "есть свой"}
_OURS = {"нет", "нет своего", "нету", "наш", "наш домен", "не свой"}
_GIVE_UP = ("не разобрался", "нет сисадмина", "не получается", "не выходит")
_CHECK = {"готово", "проверить", "проверил", "поставил", "сделал", "запись готова"}

_HELLO = "Привет. Я соберу сайт по твоему описанию."
_ASK_DOMAIN = "Какой у тебя будет домен?"
_ASK_HOST = "Домен, например cafe.ru."
_ASK_SLUG = "Короткое имя сайта латиницей, например coffee."
_ASK_BRIEF = "Какой сайт ты хочешь? Опиши его подробнее."
_WHERE = "Где разместить эту картинку?"
_AGAIN = "Не понял ответ. "
_OWN_BUTTON = "Свой домен"
_OURS_BUTTON = "Нет своего"
_READY_BUTTON = "Готово"
_GIVE_UP_BUTTON = "Не разобрался"
_DOMAIN_BUTTONS = (_OWN_BUTTON, _OURS_BUTTON)
_DNS_BUTTONS = (_READY_BUTTON, _GIVE_UP_BUTTON)


@dataclass(frozen=True, slots=True)
class StoryMove:
    dialogue: Dialogue
    replies: tuple[str, ...]
    generate_brief: str | None = None
    modify_instruction: str | None = None
    reserve: bool = False
    buttons: tuple[str, ...] = ()


def wants_dns_check(dialogue: Dialogue, text: str) -> bool:
    return (
        dialogue.step is DialogueStep.OWN_DNS
        and dialogue.host is not None
        and _norm(text) in _CHECK
    )


def advance(
    dialogue: Dialogue,
    text: str,
    *,
    image_url: str | None = None,
    dns_matches: bool | None = None,
    public_ip: str | None = None,
    base_domain: str | None = None,
) -> StoryMove:
    """Следующий шаг и реплики. dns_matches заполнен только на проверке A-записи."""

    normalized = _norm(text)
    if normalized in _RESTART and dialogue.step is not DialogueStep.GREET:
        return _domain_question(dialogue, (_ASK_DOMAIN,))
    if dialogue.step is DialogueStep.GREET:
        return _domain_question(dialogue, (_HELLO, _ASK_DOMAIN))
    if dialogue.step is DialogueStep.ASK_DOMAIN:
        return _from_domain(dialogue, normalized, public_ip)
    if dialogue.step is DialogueStep.OWN_DNS:
        return _from_dns(dialogue, normalized, dns_matches, public_ip)
    if dialogue.step is DialogueStep.ASK_SLUG:
        return _from_slug(dialogue, normalized, base_domain)
    if dialogue.step is DialogueStep.ASK_BRIEF:
        return _from_brief(dialogue, text.strip())
    if dialogue.step is DialogueStep.EDITING:
        return _from_editing(dialogue, text.strip(), image_url)
    return _from_image(dialogue, text.strip())


def _from_domain(dialogue: Dialogue, text: str, public_ip: str | None) -> StoryMove:
    if text in _OURS:
        return StoryMove(dialogue.model_copy(update={"step": DialogueStep.ASK_SLUG}), (_ASK_SLUG,))
    if text in _OWN:
        return StoryMove(
            dialogue.model_copy(update={"step": DialogueStep.OWN_DNS, "host": None}),
            (_ASK_HOST,),
        )
    if _HOST.fullmatch(text):
        return _own_host(dialogue, text, public_ip)
    return StoryMove(dialogue, (_AGAIN + _ASK_DOMAIN,), buttons=_DOMAIN_BUTTONS)


def _from_dns(
    dialogue: Dialogue,
    text: str,
    dns_matches: bool | None,
    public_ip: str | None,
) -> StoryMove:
    if any(phrase in text for phrase in _GIVE_UP) or text in _OURS:
        cleared = dialogue.model_copy(update={"host": None, "step": DialogueStep.ASK_SLUG})
        return StoryMove(cleared, ("Тогда возьмём наш адрес. " + _ASK_SLUG,))
    if dialogue.host is None and _HOST.fullmatch(text):
        return _own_host(dialogue, text, public_ip)
    if text in _CHECK:
        if not public_ip:
            return StoryMove(
                dialogue,
                ("Адрес сервера не задан, проверить A-запись не могу.",),
                buttons=_DNS_BUTTONS,
            )
        if dns_matches:
            moved = dialogue.model_copy(update={"step": DialogueStep.ASK_BRIEF})
            return StoryMove(moved, ("Запись домена отвечает. " + _ASK_BRIEF,), reserve=True)
        return StoryMove(
            dialogue,
            (f"A-запись {dialogue.host} ещё не указывает на {public_ip}.",),
            buttons=_DNS_BUTTONS,
        )
    if dialogue.host is None:
        return StoryMove(dialogue, (_ASK_HOST,))
    return StoryMove(dialogue, (_a_record(dialogue.host, public_ip),), buttons=_DNS_BUTTONS)


def _from_slug(dialogue: Dialogue, text: str, base_domain: str | None) -> StoryMove:
    try:
        slug = site_slug(text)
    except ValueError:
        return StoryMove(dialogue, ("Нужно короткое имя латиницей, цифрами и дефисом. " + _ASK_SLUG,))
    moved = dialogue.model_copy(update={"slug": slug, "step": DialogueStep.ASK_BRIEF})
    return StoryMove(moved, (f"Вашим доменом будет {_address(slug, base_domain)}. " + _ASK_BRIEF,), reserve=True)


def _from_brief(dialogue: Dialogue, text: str) -> StoryMove:
    if len(text) < 3:
        return StoryMove(dialogue, (_ASK_BRIEF,))
    return StoryMove(dialogue, ("Собираю сайт.",), generate_brief=text)


def _from_editing(dialogue: Dialogue, text: str, image_url: str | None) -> StoryMove:
    picture = image_url or (text if _URL.fullmatch(text) else None)
    if picture:
        waiting = dialogue.model_copy(update={"step": DialogueStep.ASK_IMAGE, "image_url": picture})
        return StoryMove(waiting, (_WHERE,))
    if dialogue.site is None:
        return StoryMove(
            dialogue.model_copy(update={"step": DialogueStep.ASK_BRIEF}),
            (_ASK_BRIEF,),
        )
    if len(text) < 3:
        return StoryMove(dialogue, ("Если хотите поменять сайт, опишите, что изменить.",))
    return StoryMove(dialogue, ("Обновляю сайт.",), modify_instruction=text)


def _from_image(dialogue: Dialogue, text: str) -> StoryMove:
    if dialogue.site is None or not dialogue.image_url:
        return StoryMove(
            dialogue.model_copy(update={"step": DialogueStep.ASK_BRIEF, "image_url": None}),
            (_ASK_BRIEF,),
        )
    if len(text) < 3:
        return StoryMove(dialogue, (_WHERE,))
    instruction = f"Поставь картинку {dialogue.image_url}. {text}"
    return StoryMove(dialogue, ("Обновляю сайт.",), modify_instruction=instruction)


def _own_host(dialogue: Dialogue, host: str, public_ip: str | None) -> StoryMove:
    moved = dialogue.model_copy(update={"step": DialogueStep.OWN_DNS, "host": host})
    return StoryMove(moved, (_a_record(host, public_ip),), buttons=_DNS_BUTTONS)


def _domain_question(dialogue: Dialogue, replies: tuple[str, ...]) -> StoryMove:
    cleared = dialogue.model_copy(
        update={
            "step": DialogueStep.ASK_DOMAIN,
            "host": None,
            "slug": None,
            "site": None,
            "image_url": None,
        }
    )
    return StoryMove(cleared, replies, buttons=_DOMAIN_BUTTONS)


def _a_record(host: str, public_ip: str | None) -> str:
    if public_ip:
        return f"Поставь A-запись {host} на {public_ip}."
    return (
        f"Поставь A-запись {host} на наш сервер. "
        "Адрес сервера не задан, поэтому проверить запись я не могу."
    )


def _address(slug: str, base_domain: str | None) -> str:
    domain = (base_domain or "").strip().strip(".")
    if domain:
        return f"{slug}.{domain}"
    return slug


def _norm(text: str) -> str:
    return " ".join(text.casefold().replace("ё", "е").split())
