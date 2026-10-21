import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


path = Path(__file__).resolve().parents[1] / "addon/appModules/happ/groupLabels.py"
spec = importlib.util.spec_from_file_location("group_labels", path)
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)


class GroupLabelTests(unittest.TestCase):
    def setUp(self):
        self.info = SimpleNamespace(convertXToScreen=lambda value: value,
                                    convertYToScreen=lambda value: value,
                                    convertWidthToScreen=lambda value: value,
                                    convertHeightToScreen=lambda value: value)
        self.panes = [SimpleNamespace(left=100, top=100, width=800, height=150)]
        self.view = SimpleNamespace(left=80, top=80, width=850, height=400)

    def words(self, text="Настройки интерфейса", top=200, left=115):
        return [[dict(text=text, x=left, y=top, width=180, height=20)]]

    def match(self, lines):
        return labels.match_groups(lines, self.info, self.panes, self.view)

    def test_known_label_inside_pane(self):
        self.assertEqual(self.match(self.words()), [(0, "Настройки интерфейса", (115, 200, 295, 220))])

    def test_section_heading_outside_pane_is_not_action(self):
        self.assertEqual(self.match(self.words(top=85)), [])

    def test_setting_values_and_unknown_labels_are_not_actions(self):
        for text in ("Вкл", "Выкл", "Включить фрагментацию", "Удалить", "Настройкн интерфейса"):
            self.assertEqual(self.match(self.words(text)), [])

    def test_duplicate_label_is_rejected(self):
        self.assertEqual(self.match(self.words() + self.words(top=140)), [])

    def test_overlapping_panes_are_rejected(self):
        self.panes.append(self.panes[0])
        self.assertEqual(self.match(self.words()), [])

    def test_clipped_label_is_rejected(self):
        self.view.height = 130
        self.assertEqual(self.match(self.words()), [])

    def test_right_hand_value_is_not_action(self):
        self.assertEqual(self.match(self.words(left=600)), [])

    def test_words_are_joined_in_reading_order(self):
        words = [[dict(text="интерфейса", x=210, y=200, width=90, height=20),
                  dict(text="Настройки", x=115, y=200, width=90, height=20)]]
        self.assertEqual(self.match(words)[0][1], "Настройки интерфейса")
