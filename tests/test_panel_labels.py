import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


path = Path(__file__).resolve().parents[1] / "addon/appModules/happ/panelLabels.py"
spec = importlib.util.spec_from_file_location("panel_labels_test", path)
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)


class PanelLabelsTests(unittest.TestCase):
    def setUp(self):
        self.info = SimpleNamespace(
            convertXToScreen=lambda value: 100 + value // 2,
            convertYToScreen=lambda value: 200 + value // 2,
            convertWidthToScreen=lambda value: value // 2,
            convertHeightToScreen=lambda value: value // 2,
        )
        self.rectangles = [SimpleNamespace(left=100, top=200, width=164, height=44),
                           SimpleNamespace(left=100, top=244, width=164, height=44)]

    def word(self, text, top=10):
        return {"text": text, "x": 100, "y": top, "width": 100, "height": 24}

    def test_exact_label_inside_button(self):
        self.assertEqual(labels.match_labels([[self.word("Настройки")]], self.info, self.rectangles),
                         [(0, "Настройки")])

    def test_icon_does_not_prevent_exact_word_match(self):
        words = [[self.word("□"), self.word("Логи")]]
        self.assertEqual(labels.match_labels(words, self.info, self.rectangles), [(0, "Логи")])

    def test_unknown_or_similar_text_is_not_guessed(self):
        words = [[self.word("Настройкн"), self.word("неизвестно")]]
        self.assertEqual(labels.match_labels(words, self.info, self.rectangles), [])

    def test_word_crossing_button_boundary_is_rejected(self):
        self.assertEqual(labels.match_labels([[self.word("Логи", 80)]], self.info, self.rectangles), [])

    def test_duplicate_label_rejects_result(self):
        words = [[self.word("Логи")], [self.word("Логи", 100)]]
        self.assertEqual(labels.match_labels(words, self.info, self.rectangles), [])

    def test_two_labels_on_one_button_reject_result(self):
        words = [[self.word("Логи"), self.word("Серверы")]]
        self.assertEqual(labels.match_labels(words, self.info, self.rectangles), [])

    def test_order_comes_from_geometry_not_provider(self):
        words = [[self.word("Логи", 100)], [self.word("Серверы")]]
        self.assertEqual(labels.match_labels(words, self.info, list(reversed(self.rectangles))),
                         [(1, "Серверы"), (0, "Логи")])

    def test_overlapping_buttons_reject_word(self):
        self.rectangles[1] = self.rectangles[0]
        self.assertEqual(labels.match_labels([[self.word("Логи")]], self.info, self.rectangles), [])
