import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "addon/appModules/happ/context.py"
spec = importlib.util.spec_from_file_location("settings_context", path)
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class SettingLabelsTests(unittest.TestCase):
    def setUp(self):
        self.language = (1710, 381, 140, 32)
        self.theme = (1710, 426, 140, 32)
        self.controls = [("ComboBox_QMLTYPE_10", "Русский", self.language),
                         ("ComboBox_QMLTYPE_10", "Системная", self.theme)]

    def test_verified_context_and_reverse_provider_order(self):
        self.assertEqual(context.interface_setting_label(self.language, self.controls), "Язык")
        self.assertEqual(context.interface_setting_label(self.theme, self.controls[::-1]), "Тема")

    def test_moved_and_scaled_window(self):
        controls = [(kind, name, tuple(value * 2 for value in rect)) for kind, name, rect in self.controls]
        self.assertEqual(context.interface_setting_label(controls[0][2], controls), "Язык")

    def test_unknown_values_and_extra_controls(self):
        self.assertIsNone(context.interface_setting_label(self.language, self.controls + self.controls[:1]))
        self.controls[1] = ("ComboBox", "Другое", self.theme)
        self.assertIsNone(context.interface_setting_label(self.language, self.controls))

    def test_unknown_or_overlapping_geometry(self):
        self.controls[1] = ("ComboBox", "Системная", self.language)
        self.assertIsNone(context.interface_setting_label(self.language, self.controls))
        self.controls[1] = ("ComboBox", "Системная", None)
        self.assertIsNone(context.interface_setting_label(self.language, self.controls))
