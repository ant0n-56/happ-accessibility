import importlib.util
from collections import namedtuple
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("serverLabels", Path(__file__).resolve().parents[1]
                                            / "addon/appModules/happ/serverLabels.py")
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)
Rect = namedtuple("Rect", "left top width height")


class Info:
    recogWidth = 1600
    recogHeight = 200

    def convertXToScreen(self, value):
        return 188 + value / 2

    def convertYToScreen(self, value):
        return 219 + value / 2

    def convertWidthToScreen(self, value):
        return value / 2

    convertHeightToScreen = convertWidthToScreen


def word(text, left=88, top=12, width=200, height=28):
    return dict(text=text, x=left, y=top, width=width, height=height)


class ServerLabelTests(unittest.TestCase):
    def setUp(self):
        self.rows = [Rect(188, 219, 822, 48), Rect(188, 267, 822, 48)]

    def test_names_exclude_lower_protocol_line(self):
        lines = [[word("Латвия")], [word("VLESS", top=62, height=16)],
                 [word("Другой сервер", top=108)]]
        self.assertEqual(labels.match_servers(lines, Info(), self.rows), [(0, "Латвия"), (1, "Другой сервер")])

    def test_duplicate_names_preserve_row_identity(self):
        lines = [[word("Латвия")], [word("Латвия", top=108)]]
        self.assertEqual(labels.match_servers(lines, Info(), self.rows), [(0, "Латвия"), (1, "Латвия")])

    def test_ambiguous_lines_are_not_chosen(self):
        self.assertEqual(labels.match_servers([[word("First")], [word("Second")]], Info(), self.rows), [])

    def test_invalid_and_clipped_text_rejected(self):
        for value in (word("123"), word("X\nY"), word("Long" * 50), word("Cut", left=1500),
                      word("Outside", top=-2), word("Empty", width=0), word("Icon", left=0)):
            self.assertEqual(labels.match_servers([[value]], Info(), self.rows), [])

    def test_words_are_read_left_to_right(self):
        line = [word("два", left=320), word("один")]
        self.assertEqual(labels.match_servers([line], Info(), self.rows), [(0, "один два")])

    def test_icon_and_separate_latency_are_not_part_of_name(self):
        lines = [[word("@", left=28, top=32, width=32, height=32),
                  word("Latvia", left=90, top=20, width=302, height=30)],
                 [word("632ms", left=1512, top=42, width=56, height=14)]]
        self.assertEqual(labels.match_servers(lines, Info(), self.rows), [(0, "Latvia")])


if __name__ == "__main__":
    unittest.main()
