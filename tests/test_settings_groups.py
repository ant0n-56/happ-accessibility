import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class SettingsGroupsTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "addon/appModules/happ"
        self.locked = False
        self.pending = []
        self.foreground = SimpleNamespace(processID=42)
        self.events = []
        self.cursor = (700, 800)
        self.held = False
        self.messages = []
        self.timer = Mock()
        self.pane = SimpleNamespace(location=(10, 20, 600, 200))
        self.hit = self.pane
        self.viewport = SimpleNamespace(location=SimpleNamespace(left=0, top=0, width=800, height=600))
        modules = {
            "api": SimpleNamespace(getForegroundObject=lambda: self.foreground),
            "core": SimpleNamespace(callLater=Mock(return_value=self.timer)),
            "gui": SimpleNamespace(mainFrame=Mock()),
            "screenBitmap": SimpleNamespace(),
            "ui": SimpleNamespace(message=self.messages.append),
            "wx": SimpleNamespace(CallAfter=lambda callback, *args: self.pending.append((callback, args)), ID_CANCEL=0),
            "mouseHandler": SimpleNamespace(executeMouseEvent=lambda *args: self.events.append(args)),
            "winUser": SimpleNamespace(getAsyncKeyState=lambda key: 0x8000 if self.held else 0,
                                       getCursorPos=lambda: self.cursor, setCursorPos=self.move,
                                       MOUSEEVENTF_LEFTDOWN=2, MOUSEEVENTF_LEFTUP=4),
            "comtypes": SimpleNamespace(COMError=type("COMError", (Exception,), {})),
            "contentRecog": SimpleNamespace(RecogImageInfo=object),
            "contentRecog.uwpOcr": SimpleNamespace(UwpOcr=object, getLanguages=lambda: []),
            "logHandler": SimpleNamespace(log=Mock()),
            "NVDAObjects": SimpleNamespace(NVDAObject=SimpleNamespace(objectFromPoint=lambda *args: self.hit)),
            "utils.security": SimpleNamespace(isRunningOnSecureDesktop=lambda: False),
            "winAPI.sessionTracking": SimpleNamespace(isLockScreenModeActive=lambda: self.locked),
        }
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        for name in ("panelLabels", "groupLabels", "panel", "settingsGroups"):
            fullname = "groups_test." + name
            spec = importlib.util.spec_from_file_location(fullname, root / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            self.addCleanup(lambda fullname=fullname: sys.modules.pop(fullname, None))
            spec.loader.exec_module(module)
        self.module = module
        self.menu = module.SettingsGroups(SimpleNamespace(_terminated=False, processID=42))
        self.menu.foreground = self.foreground
        self.menu.viewport = self.viewport
        self.menu.viewportRect = self.viewport.location
        self.menu.panes = [self.pane]
        self.menu.rectangles = [self.pane.location]
        self.menu.selection = (0, "Подписки", (30, 40, 100, 60))
        self.menu.actionTimer = None

    def move(self, *point):
        self.cursor = point

    def test_valid_click_restores_cursor(self):
        self.menu.click()
        self.assertEqual(self.events, [(2, 0, 0), (4, 0, 0)])
        self.assertEqual(self.cursor, (700, 800))
        self.assertTrue(self.menu.cancelled)

    def test_changed_foreground_blocks_click(self):
        self.foreground = object()
        self.menu.click()
        self.assertEqual(self.events, [])

    def test_changed_pane_blocks_click(self):
        self.pane.location = (20, 20, 600, 200)
        self.menu.click()
        self.assertEqual(self.events, [])

    def test_foreign_hit_blocks_click(self):
        self.hit = object()
        self.menu.click()
        self.assertEqual(self.events, [])

    def test_held_key_is_bounded(self):
        self.held = True
        self.menu.click(retries=0)
        self.assertEqual(self.events, [])
        self.assertTrue(self.menu.cancelled)

    def test_locked_session_blocks_click(self):
        self.locked = True
        self.menu.click()
        self.assertEqual(self.events, [])

    def test_cancellation_stops_scheduled_action(self):
        self.menu.actionTimer = self.timer
        self.menu.cancel()
        self.timer.Stop.assert_called_once()

    def test_late_callback_after_cancel_is_ignored(self):
        self.menu.receive(SimpleNamespace())
        self.menu.cancel()
        callback, args = self.pending.pop()
        callback(*args)
        self.assertEqual(self.events, [])

    def test_changed_recognition_never_clicks(self):
        with patch.object(self.module, "match_groups", return_value=[]):
            self.menu.info = object()
            self.menu.show(SimpleNamespace(data=[]))
        self.assertEqual(self.events, [])
        self.assertTrue(self.menu.cancelled)

    def test_repeated_recognition_must_match_full_entry(self):
        changed = (0, "Подписки", (30, 41, 100, 61))
        with patch.object(self.module, "match_groups", return_value=[changed]):
            self.menu.info = object()
            self.menu.show(SimpleNamespace(data=[]))
        self.assertEqual(self.events, [])

    def test_matching_recognition_permits_click(self):
        with patch.object(self.module, "match_groups", return_value=[self.menu.selection]):
            self.menu.info = object()
            self.menu.show(SimpleNamespace(data=[]))
        self.assertEqual(self.events, [(2, 0, 0), (4, 0, 0)])
