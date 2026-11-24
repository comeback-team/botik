"""Тест модификации сайта"""
import json
from botik.site.ai_generator import modify_site

# Пример текущей структуры
current_structure = {
    "business_type": "кофейня",
    "tone": "дружелюбный",
    "colors": {"primary": "#8B4513", "secondary": "#D2691E"},
    "blocks": [
        {"type": "header", "logo_text": "Кофейня", "menu": ["Главная", "Меню", "Контакты"]},
        {"type": "hero", "title": "Лучший кофе в городе", "subtitle": "Заходи к нам", "cta_text": "Посмотреть меню"},
        {"type": "text", "title": "О нас", "content": "Мы варим кофе с 2010 года"},
        {"type": "interactive", "title": "Заказать кофе", "submit_action": "order_coffee", "components": [
            {"type": "text_input", "id": "name", "label": "Ваше имя"},
            {"type": "action_button", "id": "submit", "label": "Заказать", "action_type": "submit", "target_endpoint": "/api/orders"}
        ]},
        {"type": "footer", "email": "info@coffee.ru", "phone": "+79001234567"}
    ],
}

instruction = "Добавь блок с галереей фотографий интерьера после блока 'О нас'. Также добавь блок FAQ с вопросами о доставке."

print("=" * 70)
print("ТЕКУЩАЯ СТРУКТУРА:")
print(json.dumps(current_structure, ensure_ascii=False, indent=2))
print("=" * 70)
print(f"\nИНСТРУКЦИЯ: {instruction}")
print("=" * 70)

new_structure = modify_site(current_structure, instruction)

print("\nНОВАЯ СТРУКТУРА:")
print(json.dumps(new_structure, ensure_ascii=False, indent=2))
