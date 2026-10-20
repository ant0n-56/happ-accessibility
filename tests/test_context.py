import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "addon/appModules/happ/context.py"
spec = importlib.util.spec_from_file_location("happ_context", path)
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class SearchContextTests(unittest.TestCase):
    def setUp(self):
        self.controls = [
            ("TextField_QMLTYPE_48", ""),
            ("Button_QMLTYPE_46", "Тест пинга"),
            ("ToogleButton_QMLTYPE_58", "TUN"),
            ("ToogleButton_QMLTYPE_58", "Прокси"),
        ]

    def test_observed_page_with_no_subscriptions(self):
        self.assertTrue(context.is_server_search(self.controls))

    def test_qml_numbers_and_order_do_not_define_identity(self):
        changed = [(c.replace("48", "999"), n) for c, n in reversed(self.controls)]
        self.assertTrue(context.is_server_search(changed))

    def test_ambiguous_second_edit_is_not_named(self):
        self.assertFalse(context.is_server_search(self.controls + [("TextField_QMLTYPE_9", "")]))

    def test_other_pages_are_not_named(self):
        for index in range(len(self.controls)):
            with self.subTest(index=index):
                self.assertFalse(context.is_server_search(self.controls[:index] + self.controls[index + 1:]))

    def test_unknown_types_are_not_guessed(self):
        self.assertEqual(context.qml_type("TextField_QMLTYPE_12_QML_7"), "TextField")
        self.assertEqual(context.qml_type("OtherTextField_QMLTYPE_12"), "OtherTextField")
        self.assertFalse(context.is_server_search([("OtherTextField", "")] + self.controls[1:]))

    def menu_controls(self, scale=1, offset=0):
        rects = [(100, 100, 500, 40), (800, 500, 180, 32),
                 (800, 550, 50, 24), (860, 550, 50, 24),
                 (608, 110, 20, 20), (636, 110, 20, 20)]
        names = self.controls + [("ImageButton_QMLTYPE_33", "")] * 2
        return [(cls, name, (x * scale + offset, y * scale + offset, w * scale, h * scale))
                for (cls, name), (x, y, w, h) in zip(names, rects)]

    def test_menu_survives_move_scale_and_reordering(self):
        for scale, offset in [(1, 0), (1.5, -700), (2, 500)]:
            controls = self.menu_controls(scale, offset)
            self.assertTrue(context.is_search_menu(controls[-1][2], list(reversed(controls))))
            self.assertFalse(context.is_search_menu(controls[-2][2], controls))

    def test_other_toolbar_and_ambiguous_layout_not_named(self):
        controls = self.menu_controls()
        target = controls[-1][2]
        extra = ("ImageButton_QMLTYPE_33", "", (664, 110, 20, 20))
        self.assertFalse(context.is_search_menu(target, controls + [extra]))
        self.assertFalse(context.is_search_menu(target, controls[:-2] + controls[-1:]))
        self.assertFalse(context.is_search_menu((636, 200, 20, 20), controls))


if __name__ == "__main__":
    unittest.main()
