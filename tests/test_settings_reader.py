import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from collections import namedtuple
import unittest
from unittest.mock import Mock, patch


class SettingReaderTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "addon/appModules/happ"
        spec = importlib.util.spec_from_file_location("setting_test.context", root / "context.py")
        context = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(context)
        self.context = context
        rect = namedtuple("Rect", "left top width height")
        self.obj = SimpleNamespace(location=rect(400, 100, 95, 35), processID=42, states=set(),
                                   parent=SimpleNamespace(location=rect(100, 80, 420, 140)),
                                   UIAElement=SimpleNamespace(currentName="Выкл"))
        self.focus = self.obj
        self.foreground = SimpleNamespace(location=rect(0, 0, 800, 600), processID=42)
        self.locked = False
        self.secure = False
        self.pending = []
        self.messages = []
        self.recognizer = Mock()
        self.capture = Mock(return_value=b"pixels")
        self.timer = Mock()
        self.hit = self.obj
        modules = {
            "setting_test.context": context,
            "api": SimpleNamespace(getFocusObject=lambda: self.focus, getForegroundObject=lambda: self.foreground),
            "core": SimpleNamespace(callLater=lambda *args: self.timer),
            "screenBitmap": SimpleNamespace(ScreenBitmap=lambda *args: SimpleNamespace(captureImage=self.capture)),
            "ui": SimpleNamespace(message=self.messages.append),
            "wx": SimpleNamespace(CallAfter=lambda callback, *args: self.pending.append((callback, args))),
            "comtypes": SimpleNamespace(COMError=type("COMError", (Exception,), {})),
            "contentRecog": SimpleNamespace(RecogImageInfo=lambda left, top, width, height, scale:
                                            SimpleNamespace(recogWidth=width * scale, recogHeight=height * scale)),
            "contentRecog.uwpOcr": SimpleNamespace(UwpOcr=lambda language: self.recognizer, getLanguages=lambda: ["ru-RU"]),
            "controlTypes": SimpleNamespace(State=SimpleNamespace(INVISIBLE=1, OFFSCREEN=2, UNAVAILABLE=3)),
            "logHandler": SimpleNamespace(log=Mock()),
            "NVDAObjects": SimpleNamespace(NVDAObject=SimpleNamespace(objectFromPoint=lambda *args: self.hit)),
            "utils.security": SimpleNamespace(isRunningOnSecureDesktop=lambda: self.secure),
            "winAPI.sessionTracking": SimpleNamespace(isLockScreenModeActive=lambda: self.locked),
        }
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        spec = importlib.util.spec_from_file_location("setting_test.settings", root / "settings.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.owner = SimpleNamespace(_terminated=False, processID=42)
        self.reader = module.SettingReader(self.owner, self.obj)
        self.result = SimpleNamespace(data=[[dict(text="Включить фрагментацию", x=20, y=20, width=250, height=30)]])

    def test_reads_row_without_changing_value(self):
        self.reader.start()
        self.recognizer.recognize.assert_called_once()
        self.reader.receive(self.result)
        self.assertEqual(self.messages, [])
        callback, args = self.pending.pop()
        callback(*args)
        self.assertEqual(self.messages, ["Включить фрагментацию: Выкл"])
        self.assertEqual(self.obj.UIAElement.currentName, "Выкл")
        self.assertEqual(self.obj._happRowLabel[0], "Включить фрагментацию")

    def test_changed_focus_discards_result(self):
        self.reader.start()
        self.focus = object()
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])

    def test_moved_control_discards_result(self):
        self.reader.start()
        self.obj.location = self.obj.location._replace(top=140)
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])

    def test_locked_or_secure_session_does_not_capture(self):
        self.locked = True
        self.reader.start()
        self.locked = False
        self.secure = True
        self.reader.start()
        self.capture.assert_not_called()

    def test_timeout_or_cancel_discards_late_result(self):
        self.reader.start()
        self.reader.cancel()
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])
        self.recognizer.cancel.assert_called_once()
        self.timer.Stop.assert_called_once()

    def test_hidden_control_is_not_captured(self):
        self.obj.states = {2}
        self.reader.start()
        self.capture.assert_not_called()

    def test_occluded_control_is_not_captured(self):
        self.hit = SimpleNamespace(processID=77)
        self.reader.start()
        self.capture.assert_not_called()

    def test_value_is_read_at_completion(self):
        self.reader.start()
        self.obj.UIAElement.currentName = "Вкл"
        self.reader.finish(self.result)
        self.assertEqual(self.messages, ["Включить фрагментацию: Вкл"])

    def test_changed_foreground_discards_result(self):
        self.reader.start()
        self.foreground = object()
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])

    def test_terminated_owner_discards_result(self):
        self.reader.start()
        self.owner._terminated = True
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])

    def test_lock_after_capture_discards_result(self):
        self.reader.start()
        self.locked = True
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])

    def test_foreign_window_is_not_captured(self):
        self.foreground.processID = 77
        self.reader.start()
        self.capture.assert_not_called()

    def test_ambiguous_lines_are_rejected(self):
        self.assertIsNone(self.context.setting_row_label(self.result.data * 2, 600, 70))
        self.assertIsNone(self.context.setting_row_label([], 600, 70))

    def test_clipped_and_neighboring_text_are_rejected(self):
        for change in ({"x": -1}, {"width": 800}, {"y": 60}, {"height": 0}, {"y": 0, "height": 5}):
            with self.subTest(change=change):
                word = dict(self.result.data[0][0], **change)
                self.assertIsNone(self.context.setting_row_label([[word]], 600, 70))

    def test_reading_order_and_colon(self):
        words = [dict(text="IP:", x=100, y=20, width=40, height=30),
                 dict(text="Тип", x=10, y=20, width=60, height=30)]
        self.assertEqual(self.context.setting_row_label([words], 600, 70), "Тип IP")
