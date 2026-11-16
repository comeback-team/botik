"""Запрос на сайт: промпт, схема GigaChat и сборка SiteStructure."""

import json
import unittest

from botik.site.request import build_site_request
from botik.site.structure import SiteStructure


def _site() -> dict:
    return {
        "business_type": "кофейня",
        "tone": "тёплый",
        "colors": {"primary": "#112233", "secondary": "#445566"},
        "blocks": [
            {"type": "header", "logo_text": "Зерно", "menu": ["Меню", "Контакты"]},
            {"type": "hero", "title": "Кофе у дома"},
            {
                "type": "interactive",
                "title": "Заказ",
                "submit_action": "send_lead",
                "components": [
                    {"type": "text_input", "id": "phone_number", "label": "Телефон"},
                    {
                        "type": "action_button",
                        "id": "submit_order",
                        "label": "Отправить",
                        "action_type": "submit",
                        "target_endpoint": "/api/leads",
                    },
                ],
            },
        ],
    }


class SiteRequestTest(unittest.TestCase):
    def test_inline_schema_is_attached_as_response_format(self) -> None:
        request = build_site_request("Пиццерия с доставкой за 30 минут")

        self.assertIn("Ты НЕ пишешь HTML", request.system)
        self.assertIn("- hero: default, split", request.system)
        self.assertIn("Тональность и цвета выбери сам", request.system)
        self.assertNotIn("ТОНАЛЬНОСТЬ ТЕКСТОВ", request.system)
        self.assertIn("tone", request.response_format["schema"]["properties"])
        self.assertIn("Пиццерия с доставкой за 30 минут", request.user)
        self.assertEqual(request.response_format["type"], "json_schema")
        schema = json.dumps(request.response_format["schema"])
        self.assertNotIn("$ref", schema)
        self.assertNotIn("$defs", schema)
        self.assertNotIn("discriminator", schema)
        self.assertIn("business_type", request.response_format["schema"]["properties"])
        self.assertIs(request.output_model, SiteStructure)

    def test_prompt_mode_moves_schema_into_the_system_text(self) -> None:
        request = build_site_request("Барбершоп на Баумана", schema_mode="prompt")

        self.assertEqual(request.response_format, {"type": "json_object"})
        self.assertIn("JSON-СХЕМА:", request.system)
        self.assertIn('"business_type"', request.system)
        self.assertNotIn("$ref", request.system)

    def test_short_brief_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_site_request("  ок ")

    def test_structure_places_header_and_footer_around_blocks(self) -> None:
        site = SiteStructure.model_validate(_site())

        self.assertEqual([block.type for block in site.blocks], ["header", "hero", "interactive", "footer"])
        self.assertEqual(site.blocks[0].logo_text, "Зерно")


if __name__ == "__main__":
    unittest.main()
