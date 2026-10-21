import importlib.util
from collections import namedtuple
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


Rect = namedtuple("Rect", "left top width height")


class Node:
    def __init__(self, kind, name="", rect=Rect(0, 0, 1000, 800), children=()):
        self.UIAElement = SimpleNamespace(currentClassName=kind, currentName=name)
        self.processID = 42
        self.location = rect
        self.states = set()
        self.firstChild = children[0] if children else None
        self.next = None
        self.UIAInvokePattern = Mock()
        for before, after in zip(children, children[1:]):
            before.next = after


class ServerTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "addon/appModules/happ"
        self.locked = False
        self.messages = []
        self.pending = []
        self.cursor = (20, 30)
        self.held = False
        self.mouse = Mock()
        self.row = Node("ServerItem", rect=Rect(100, 200, 800, 48))
        self.controls = [Node("TextField"), Node("Button", "Тест пинга"),
                         Node("ToogleButton", "TUN"), Node("ToogleButton", "Прокси"), self.row]
        self.container = Node("QQuickControl", children=self.controls)
        self.window = Node("Main", children=[Node(""), self.container])
        self.foreground = self.window
        self.hit = self.row
        modules = {
            "api": SimpleNamespace(getForegroundObject=lambda: self.foreground),
            "core": SimpleNamespace(callLater=Mock()),
            "mouseHandler": SimpleNamespace(executeMouseEvent=self.mouse),
            "winUser": SimpleNamespace(getAsyncKeyState=lambda key: 0x8000 if self.held else 0,
                                       getCursorPos=lambda: self.cursor, setCursorPos=self.move,
                                       MOUSEEVENTF_LEFTDOWN=2, MOUSEEVENTF_LEFTUP=4),
            "gui": SimpleNamespace(mainFrame=Mock()),
            "screenBitmap": SimpleNamespace(),
            "ui": SimpleNamespace(message=self.messages.append),
            "wx": SimpleNamespace(CallAfter=lambda callback, *args: self.pending.append((callback, args)),
                                  ID_CANCEL=0, ID_OK=1),
            "comtypes": SimpleNamespace(COMError=type("COMError", (Exception,), {})),
            "contentRecog": SimpleNamespace(RecogImageInfo=object),
            "contentRecog.uwpOcr": SimpleNamespace(UwpOcr=object, getLanguages=lambda: []),
            "controlTypes": SimpleNamespace(State=SimpleNamespace(INVISIBLE=1, OFFSCREEN=2, UNAVAILABLE=3)),
            "logHandler": SimpleNamespace(log=Mock()),
            "NVDAObjects": SimpleNamespace(NVDAObject=SimpleNamespace(objectFromPoint=lambda *args: self.hit)),
            "NVDAObjects.UIA": SimpleNamespace(UIA=Node),
            "utils.security": SimpleNamespace(isRunningOnSecureDesktop=lambda: False),
            "winAPI.sessionTracking": SimpleNamespace(isLockScreenModeActive=lambda: self.locked),
        }
        mocked = patch.dict(sys.modules, modules)
        mocked.start()
        self.addCleanup(mocked.stop)
        for name in ("context", "panelLabels", "panel", "serverLabels", "servers"):
            fullname = "servers_test." + name
            spec = importlib.util.spec_from_file_location(fullname, root / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            self.addCleanup(lambda fullname=fullname: sys.modules.pop(fullname, None))
            spec.loader.exec_module(module)
        self.module = module
        self.menu = module.ServerMenu(SimpleNamespace(_terminated=False, processID=42))
        self.menu.foreground = self.window
        self.menu.rows = [self.row]
        self.menu.rectangles = [self.row.location]
        self.menu.selection = (0, "Латвия")
        self.menu.actionTimer = None
        self.menu.info = object()
        self.menu.secondaryLanguage = None
        self.menu.firstEntries = None
        matching = patch.object(module, "match_servers", return_value=[(0, "Латвия")])
        self.match = matching.start()
        self.addCleanup(matching.stop)

    def move(self, *point):
        self.cursor = point

    def test_title_bar_before_content_is_not_a_server_container(self):
        self.assertEqual(self.module.find_rows(self.window), [self.row])

    def test_information_row_is_excluded(self):
        self.row.firstChild = Node("ProgressBar")
        self.assertEqual(self.module.find_rows(self.window), [])

    def test_duplicate_container_is_rejected(self):
        self.container.next = Node("QQuickControl")
        self.assertEqual(self.module.find_rows(self.window), [])

    def test_incomplete_provider_is_bounded(self):
        self.row.next = self.row
        self.assertEqual(self.module.find_rows(self.window), [])

    def test_foreign_page_is_rejected(self):
        self.controls[1].UIAElement.currentName = "Другое"
        self.assertEqual(self.module.find_rows(self.window), [])

    def test_hidden_rows_are_excluded(self):
        self.row.states.add(2)
        self.assertEqual(self.module.find_rows(self.window), [])

    def test_confirmed_row_invoked_once(self):
        self.menu.show(SimpleNamespace(data=[]))
        self.menu.show(SimpleNamespace(data=[]))
        self.assertEqual(self.mouse.call_count, 2)
        self.assertEqual(self.cursor, (20, 30))
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.assertTrue(self.menu.cancelled)

    def test_secondary_language_finishes_before_action(self):
        self.menu.secondaryLanguage = "en-US"
        self.menu.pixels = object()
        recognizer = Mock()
        self.match.return_value = []
        with patch.object(self.module, "UwpOcr", return_value=recognizer):
            self.menu.show(SimpleNamespace(data=[]))
        recognizer.recognize.assert_called_once()
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.match.return_value = [(0, "Латвия")]
        self.menu.show(SimpleNamespace(data=[]))
        self.assertEqual(self.mouse.call_count, 2)

    def test_cancel_between_languages_prevents_action(self):
        self.menu.secondaryLanguage = "en-US"
        self.menu.pixels = object()
        with patch.object(self.module, "UwpOcr", return_value=Mock()):
            self.menu.show(SimpleNamespace(data=[]))
        self.menu.cancel()
        self.menu.show(SimpleNamespace(data=[]))
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.mouse.assert_not_called()

    def test_changed_label_is_not_invoked(self):
        self.match.return_value = [(0, "Другой сервер")]
        self.menu.show(SimpleNamespace(data=[]))
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.mouse.assert_not_called()

    def test_moved_row_is_not_invoked(self):
        self.row.location = Rect(100, 201, 800, 48)
        self.menu.show(SimpleNamespace(data=[]))
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.mouse.assert_not_called()

    def test_locked_session_is_not_invoked(self):
        self.locked = True
        self.menu.show(SimpleNamespace(data=[]))
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.mouse.assert_not_called()

    def test_changed_focus_is_not_invoked(self):
        self.foreground = object()
        self.menu.show(SimpleNamespace(data=[]))
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.mouse.assert_not_called()

    def test_occluded_row_is_not_invoked(self):
        self.hit = object()
        self.menu.show(SimpleNamespace(data=[]))
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.mouse.assert_not_called()

    def test_click_failure_has_no_retry(self):
        self.mouse.side_effect = RuntimeError()
        self.menu.show(SimpleNamespace(data=[]))
        self.menu.show(SimpleNamespace(data=[]))
        self.assertEqual(self.mouse.call_count, 2)
        self.assertIn("Повторное нажатие не отправлено", self.messages[-1])

    def test_held_key_wait_has_limit(self):
        self.held = True
        self.menu.activate(retries=0)
        self.mouse.assert_not_called()
        self.assertTrue(self.menu.cancelled)

    def test_focus_change_during_cursor_move_prevents_click(self):
        def move_and_obscure(*point):
            self.cursor = point
            self.hit = object()
        with patch.object(self.module.winUser, "setCursorPos", move_and_obscure):
            self.menu.activate()
        self.mouse.assert_not_called()
        self.assertEqual(self.cursor, (20, 30))

    def test_cancel_stops_timer_and_late_callback(self):
        timer = self.menu.actionTimer = Mock()
        self.menu.receive(SimpleNamespace(data=[]))
        self.menu.cancel()
        callback, args = self.pending.pop()
        callback(*args)
        timer.Stop.assert_called_once()
        self.row.UIAInvokePattern.Invoke.assert_not_called()
        self.mouse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
