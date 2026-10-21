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
                                   parent=SimpleNamespace(location=rect(100, 80, 420, 140), firstChild=None),
                                   UIAElement=SimpleNamespace(currentName="Выкл", currentClassName="TextField"))
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
                                            SimpleNamespace(recogWidth=width * scale, recogHeight=height * scale,
                                                            convertXToScreen=lambda value: left + value / scale,
                                                            convertYToScreen=lambda value: top + value / scale,
                                                            convertWidthToScreen=lambda value: value / scale,
                                                            convertHeightToScreen=lambda value: value / scale)),
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
        self.module = module
        self.owner = SimpleNamespace(_terminated=False, processID=42)
        self.reader = module.SettingReader(self.owner, self.obj)
        self.result = SimpleNamespace(data=[[dict(text="Включить фрагментацию", x=20, y=60, width=250, height=30)]])

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

    def menu_reader(self):
        self.obj.UIAElement.currentClassName = "ImageButton"
        self.obj.UIAElement.currentName = ""
        self.obj.location = self.obj.location._replace(top=85, width=20, height=20)
        self.obj.parent.UIAElement = SimpleNamespace(currentClassName="StackView")
        self.obj.parent.firstChild = self.obj
        self.obj.next = SimpleNamespace(
            UIAElement=SimpleNamespace(currentClassName="SettingsPane"),
            location=self.obj.location._replace(left=110, top=120, width=400, height=50), next=None)
        self.reader = self.module.SettingReader(self.owner, self.obj)
        self.result.data = [[dict(text="Правила маршрутизации", x=20, y=20, width=300, height=20)]]

    def test_routing_menu_uses_verified_header_not_values(self):
        self.menu_reader()
        self.reader.start()
        self.capture.assert_called_once_with(110, 80, 290, 40)
        self.reader.finish(self.result)
        self.assertEqual(self.messages, ["Меню правил маршрутизации"])

    def test_unknown_menu_header_is_not_assigned_routing_name(self):
        self.menu_reader()
        self.result.data[0][0]["text"] = "Другие настройки"
        self.reader.start()
        self.reader.finish(self.result)
        self.assertEqual(self.messages, [])

    def test_ambiguous_menu_buttons_are_not_read(self):
        self.menu_reader()
        self.obj.next.next = SimpleNamespace(UIAElement=self.obj.UIAElement,
                                            location=self.obj.location, next=None)
        self.reader.start()
        self.capture.assert_not_called()

    def test_menu_without_settings_pane_is_not_read(self):
        self.menu_reader()
        self.obj.next = None
        self.reader.start()
        self.capture.assert_not_called()

    def test_menu_overlapping_parameter_is_not_read(self):
        self.menu_reader()
        self.obj.next.location = self.obj.next.location._replace(top=100)
        self.reader.start()
        self.capture.assert_not_called()

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

    def test_combobox_child_hit_is_accepted(self):
        self.hit = SimpleNamespace(processID=42, parent=self.obj)
        self.reader.start()
        self.recognizer.recognize.assert_called_once()

    def test_overlapping_sibling_is_not_accepted(self):
        self.hit = SimpleNamespace(processID=42, parent=SimpleNamespace(processID=42, parent=None))
        self.reader.start()
        self.capture.assert_not_called()

    def test_cyclic_provider_is_bounded(self):
        self.hit = SimpleNamespace(processID=42)
        self.hit.parent = self.hit
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
        self.reader.start()
        self.assertIsNone(self.context.setting_label_from_pane(self.result.data * 2, self.reader.info, self.obj.location))
        self.assertIsNone(self.context.setting_label_from_pane([], self.reader.info, self.obj.location))

    def test_clipped_and_neighboring_text_are_rejected(self):
        self.reader.start()
        for change in ({"x": -1}, {"width": 800}, {"y": 260}, {"height": 0}, {"y": 0, "height": 5}):
            with self.subTest(change=change):
                word = dict(self.result.data[0][0], **change)
                self.assertIsNone(self.context.setting_label_from_pane([[word]], self.reader.info, self.obj.location))

    def test_reading_order_and_colon(self):
        self.reader.start()
        words = [dict(text="IP:", x=100, y=60, width=40, height=30),
                 dict(text="Тип", x=10, y=60, width=60, height=30)]
        self.assertEqual(self.context.setting_label_from_pane([words], self.reader.info, self.obj.location), "Тип IP")

    def test_neighboring_rows_are_not_joined(self):
        self.reader.start()
        neighbor = [dict(text="Другая настройка", x=20, y=150, width=250, height=30)]
        self.reader.finish(SimpleNamespace(data=self.result.data + [neighbor]))
        self.assertEqual(self.messages, ["Включить фрагментацию: Выкл"])

    def test_capture_excludes_wider_sibling_values(self):
        sibling = SimpleNamespace(location=self.obj.location._replace(left=360), next=None,
                                  UIAElement=SimpleNamespace(currentClassName="ComboBox"))
        self.obj.parent.firstChild = sibling
        self.reader.start()
        self.capture.assert_called_once_with(100, 80, 260, 140)

    def test_hidden_sibling_detection_is_not_generic_occlusion(self):
        pane = SimpleNamespace(UIAElement=SimpleNamespace(currentClassName="SettingsPane"), processID=42, parent=None)
        self.obj.parent = pane
        visible = SimpleNamespace(processID=42, parent=pane,
                                  UIAElement=SimpleNamespace(currentClassName="Switch"))
        self.assertTrue(self.module.is_covered_setting(self.obj, visible))
        visible.parent = SimpleNamespace(processID=42, parent=None)
        self.assertFalse(self.module.is_covered_setting(self.obj, visible))

    def test_nested_control_does_not_hide_itself(self):
        hit = SimpleNamespace(processID=42, parent=self.obj)
        self.assertFalse(self.module.is_covered_setting(self.obj, hit))
