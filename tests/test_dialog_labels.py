import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("dialog_labels", Path(__file__).resolve().parents[1] / "addon/appModules/happ/dialogLabels.py")
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)


class DialogLabelsTests(unittest.TestCase):
    def setUp(self):
        self.info = SimpleNamespace(convertXToScreen=lambda value: value, convertYToScreen=lambda value: value,
                                    convertWidthToScreen=lambda value: value, convertHeightToScreen=lambda value: value)
        self.popup = SimpleNamespace(left=560, top=198, width=800, height=659)
        self.lines = [self.line("Добавить конфигурацию", 596, 244, 260, 24)]

    def line(self, text, left, top, width=200, height=14):
        return [dict(text=text, x=left, y=top, width=width, height=height)]

    def match(self, kind, left, top, width, height):
        return labels.dialog_label(self.lines, self.info, self.popup,
                                   SimpleNamespace(left=left, top=top, width=width, height=height), kind)

    def test_fields_and_type_match_top_labels(self):
        for kind, text, top, expected in (("TextField", "Имя подписки", 378, "Имя подписки"),
                                         ("TextField", "URL подписки", 448, "URL подписки"),
                                         ("ComboBox", "Тип", 309, "Тип конфигурации")):
            self.lines = self.lines[:1] + [self.line(text, 596, top - 25)]
            self.assertEqual(self.match(kind, 596, top, 728, 33), expected)

    def test_switch_ignores_explanatory_line(self):
        self.lines += [self.line("Скрыть настройки сервера", 596, 501, 250),
                       self.line("Неизвестное пояснение", 596, 525)]
        self.assertEqual(self.match("Switch", 1229, 501, 95, 35), "Скрыть настройки сервера")

    def test_close_requires_header_alignment(self):
        self.assertEqual(self.match("ImageButton", 1292, 234, 32, 32), "Закрыть диалог добавления")
        self.assertIsNone(self.match("ImageButton", 1292, 700, 32, 32))

    def test_other_popup_is_not_named(self):
        self.lines[0][0]["text"] = "Другой диалог"
        self.assertIsNone(self.match("ImageButton", 1292, 234, 32, 32))

    def test_duplicate_titles_are_rejected(self):
        self.lines *= 2
        self.assertIsNone(self.match("ImageButton", 1292, 234, 32, 32))

    def test_value_is_not_used_as_label(self):
        self.lines += [self.line("URL подписки", 596, 451)]
        self.assertIsNone(self.match("TextField", 596, 448, 728, 33))

    def test_duplicate_labels_are_rejected(self):
        self.lines += [self.line("Тип", 596, 284)] * 2
        self.assertIsNone(self.match("ComboBox", 596, 309, 728, 32))

    def test_observed_ocr_url_variant(self):
        self.lines += [self.line("lJRL подписки", 596, 425)]
        self.assertEqual(self.match("TextField", 596, 448, 728, 33), "URL подписки")
