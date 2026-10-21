import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_settings_reader as settings_tests


class DialogReaderTests(unittest.TestCase):
    def setUp(self):
        settings_tests.SettingReaderTests.setUp(self)
        root = Path(__file__).resolve().parents[1] / "addon/appModules/happ"
        spec = importlib.util.spec_from_file_location("setting_test.dialogLabels", root / "dialogLabels.py")
        labels = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(labels)
        modules = patch.dict(sys.modules, {"setting_test.settings": self.module, "setting_test.dialogLabels": labels})
        modules.start()
        self.addCleanup(modules.stop)
        spec = importlib.util.spec_from_file_location("setting_test.dialog", root / "dialog.py")
        self.dialog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.dialog)
        self.popup = SimpleNamespace(location=self.obj.location._replace(left=100, top=80, width=420, height=400),
                                     processID=42, parent=None)
        self.obj.parent = self.popup
        self.reader = self.dialog.DialogReader(self.owner, self.obj, self.popup)

    def test_capture_is_bounded_by_popup(self):
        self.reader.start()
        self.capture.assert_called_once_with(100, 80, 420, 400)
        self.recognizer.recognize.assert_called_once()

    def test_foreign_window_over_popup_blocks_capture(self):
        self.hit = SimpleNamespace(processID=99, parent=None)
        self.reader.start()
        self.capture.assert_not_called()

    def test_moved_popup_discards_result(self):
        self.reader.start()
        self.popup.location = self.popup.location._replace(left=200)
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])

    def test_cancelled_recognition_cannot_speak(self):
        self.reader.start()
        self.reader.cancel()
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])

    def test_focus_change_discards_result(self):
        self.reader.start()
        self.focus = object()
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])
