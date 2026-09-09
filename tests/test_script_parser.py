import unittest

from src.script_parser import parse_structured_script


class StructuredScriptParserTests(unittest.TestCase):
    def test_demo_is_interleaved_by_appearance_order(self):
        text = """Diapositiva 3:
Diapo3.6: Antes del demo.

Inicio Demo/Diapositiva 3:
Esto es el demo.
Fin Demo/Diapositiva3.

Diapo3.7: Después del demo.
"""
        segments = parse_structured_script(text)

        self.assertEqual(
            [(s["order_index"], s["label"]) for s in segments],
            [(0, "3.6"), (1, "3-demo"), (2, "3.7")],
        )

    def test_real_demo_variants_are_accepted(self):
        text = """Diapositiva 6:
Introducción.
Demo/Diapositiva 6:
Contenido del demo.
Fin Demo/Diapositiva6

Diapositiva 11:
Demo-Diapositiva 11:
Contenido del segundo demo.
"""
        segments = parse_structured_script(text)

        self.assertEqual([s["label"] for s in segments], [
            "6-intro-1",
            "6-demo",
            "11-demo",
        ])

    def test_plain_script_returns_none_for_legacy_fallback(self):
        text = """Este es un guion plano.

No tiene etiquetas de diapositivas ni segmentos numerados.
"""
        self.assertIsNone(parse_structured_script(text))


if __name__ == "__main__":
    unittest.main()
