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

    def test_ping_toolbar_label_survives_scale_and_reordering(self):
        for scale, offset in [(1, 0), (1.5, -700), (2, 500)]:
            controls = self.menu_controls(scale, offset)
            self.assertEqual(context.search_toolbar_label(controls[-2][2], list(reversed(controls))),
                             "Пинг списка серверов")
            self.assertEqual(context.search_toolbar_label(controls[-1][2], controls), "Меню списка серверов")

    def test_subscription_link_observed_layout(self):
        for scale, offset in [(1, 0), (2, -500)]:
            transform = lambda rect: tuple(value * scale + (offset if index < 2 else 0) for index, value in enumerate(rect))
            parent = transform((188, 195, 822, 45))
            target = transform((966, 197, 32, 18))
            controls = [("ImageButton_QMLTYPE_12", "", target),
                        ("ProgressBar_QMLTYPE_13", "", transform((200, 198, 653, 16)))]
            self.assertTrue(context.is_subscription_link(target, parent, controls))
            self.assertFalse(context.is_subscription_link(target, parent, controls * 2))
            self.assertFalse(context.is_subscription_link(target, parent, controls[:1]))

    def test_subscription_link_outside_row_is_rejected(self):
        parent = (188, 195, 822, 45)
        target = (966, 250, 32, 18)
        controls = [("ImageButton", "", target), ("ProgressBar", "", (200, 198, 653, 16))]
        self.assertFalse(context.is_subscription_link(target, parent, controls))

    def header_controls(self, scale=1, offset=0):
        transform = lambda rect: tuple(value * scale + (offset if index < 2 else 0) for index, value in enumerate(rect))
        icons = [transform((left, 160, 20, 20)) for left in (584, 612, 640)]
        controls = self.menu_controls(scale, offset) + [("ImageButton_QMLTYPE_99", "", area) for area in icons]
        return controls, icons, [transform((100, 196, 570, 45))]

    def test_header_buttons_survive_scale_move_and_reordering(self):
        for scale, offset in ((1, 0), (2, -500), (1.5, 250)):
            controls, icons, rows = self.header_controls(scale, offset)
            for area, label in zip(icons, ("Обновить подписку", "Пинг подписки", "Меню подписки")):
                self.assertEqual(context.subscription_header_label(area, list(reversed(controls)), rows), label)

    def test_header_requires_unique_subscription_anchor(self):
        controls, icons, rows = self.header_controls()
        self.assertIsNone(context.subscription_header_label(icons[0], controls, []))
        self.assertIsNone(context.subscription_header_label(icons[0], controls, rows * 2))

    def test_header_rejects_extra_or_missing_icons(self):
        controls, icons, rows = self.header_controls()
        self.assertIsNone(context.subscription_header_label(icons[0], controls[:-1], rows))
        self.assertIsNone(context.subscription_header_label(icons[0], controls + [controls[-1]], rows))

    def test_header_does_not_name_search_toolbar(self):
        controls, icons, rows = self.header_controls()
        self.assertIsNone(context.subscription_header_label(controls[4][2], controls, rows))

    def test_header_requires_server_page(self):
        controls, icons, rows = self.header_controls()
        self.assertIsNone(context.subscription_header_label(icons[0], controls[1:], rows))

    def test_subscription_info_with_and_without_link(self):
        for scale, offset in ((1, 0), (1.5, -700), (2, 500)):
            transform = lambda rect: tuple(value * scale + (offset if index < 2 else 0)
                                          for index, value in enumerate(rect))
            for parent, parts in (
                ((188, 195, 822, 24), [("ProgressBar", "", (200, 199, 697, 16))]),
                ((188, 195, 822, 45), [("ProgressBar", "", (200, 198, 653, 16)),
                                         ("ImageButton", "", (966, 197, 32, 18))]),
            ):
                transformed = [(kind + "_QMLTYPE_42", name, transform(rect)) for kind, name, rect in parts]
                self.assertTrue(context.is_subscription_info(transform(parent), list(reversed(transformed))))

    def test_subscription_info_rejects_unknown_and_incomplete_rows(self):
        parent = (188, 195, 822, 24)
        bar = ("ProgressBar", "", (200, 199, 697, 16))
        for parts in ([], [bar, bar], [("Button", "", bar[2])],
                      [("ProgressBar", "", None)], [bar, ("ImageButton", "", (0, 0, 20, 20))]):
            self.assertFalse(context.is_subscription_info(parent, parts))
        self.assertFalse(context.is_subscription_info(None, [bar]))
        for rect in ((200, 250, 697, 16), (0, 199, 697, 16), (200, 199, 900, 16),
                     (200, 199, 697, 40), (200, 199, 30, 16), (200, 199, 697, 0)):
            self.assertFalse(context.is_subscription_info(parent, [("ProgressBar", "", rect)]))

    def test_new_subscription_without_link_names_all_header_buttons(self):
        controls = [(kind, name, rect) for (kind, name), rect in zip(self.controls,
                    [(188, 87, 756, 40), (1385, 916, 192, 32),
                     (1483, 976, 52, 24), (1427, 976, 52, 24)])]
        icons = [(left, 159, 20, 20) for left in (924, 952, 980)]
        controls += [("ImageButton", "", rect) for rect in icons]
        row = (188, 195, 822, 24)
        parts = [("ProgressBar", "", (200, 199, 697, 16))]
        rows = [row] if context.is_subscription_info(row, parts) else []
        for icon, label in zip(icons, ("Обновить подписку", "Пинг подписки", "Меню подписки")):
            self.assertEqual(context.subscription_header_label(icon, controls, rows), label)

    def test_multiple_subscription_headers_use_their_own_row(self):
        controls, icons, rows = self.header_controls()
        second_icons = [(left, top + 300, width, height) for left, top, width, height in icons]
        controls += [("ImageButton", "", rect) for rect in second_icons]
        left, top, width, height = rows[0]
        rows.append((left, top + 300, width, 24))
        for group in (icons, second_icons):
            for icon, label in zip(group, ("Обновить подписку", "Пинг подписки", "Меню подписки")):
                self.assertEqual(context.subscription_header_label(icon, controls, rows), label)


if __name__ == "__main__":
    unittest.main()
