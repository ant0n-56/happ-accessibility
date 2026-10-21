"""Verify that ambiguous or changed UI never receives a navigation action."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class Node:
    def __init__(self, kind, children=(), process=42):
        self.UIAElement = types.SimpleNamespace(currentClassName=kind)
        self.processID = process
        self.firstChild = children[0] if children else None
        self.next = None
        self.states = set()
        self.location = types.SimpleNamespace(left=10, top=20, width=68, height=44)
        self.invocations = 0
        self.UIAInvokePattern = types.SimpleNamespace(Invoke=self.invoke)
        for before, after in zip(children, children[1:]):
            before.next = after

    def invoke(self):
        self.invocations += 1


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.locked = False
        self.secure = False
        self.mouse_events = []
        self.cursor = (300, 400)
        self.held = False
        self.timers = []
        self.button = Node("NavButton_QMLTYPE_12")
        self.root = Node("Main_QMLTYPE_17", [Node("QQuickControl", [self.button])])
        self.api = types.SimpleNamespace(getForegroundObject=lambda: self.root)
        state = types.SimpleNamespace(UNAVAILABLE=1, INVISIBLE=2, OFFSCREEN=3)
        role = types.SimpleNamespace(EDITABLETEXT=8, BUTTON=9, COMBOBOX=10)
        modules = {
            "appModuleHandler": types.SimpleNamespace(AppModule=type("Base", (), {"terminate": lambda self: None})),
            "core": types.SimpleNamespace(callLater=self.schedule),
            "mouseHandler": types.SimpleNamespace(executeMouseEvent=lambda *args: self.mouse_events.append(args)),
            "winUser": types.SimpleNamespace(
                getAsyncKeyState=lambda key: 0x8000 if self.held else 0,
                getCursorPos=lambda: self.cursor,
                setCursorPos=self.move_cursor,
                MOUSEEVENTF_LEFTDOWN=2, MOUSEEVENTF_LEFTUP=4,
            ),
            "NVDAObjects": types.SimpleNamespace(NVDAObject=types.SimpleNamespace(objectFromPoint=lambda *args: self.hit)),
            "api": self.api,
            "ui": types.SimpleNamespace(message=self.messages.append),
            "comtypes": types.SimpleNamespace(COMError=type("COMError", (Exception,), {})),
            "controlTypes": types.SimpleNamespace(Role=role, State=state),
            "logHandler": types.SimpleNamespace(log=types.SimpleNamespace(debugWarning=lambda *a, **kw: None)),
            "NVDAObjects.UIA": types.SimpleNamespace(UIA=Node),
            "scriptHandler": types.SimpleNamespace(script=lambda **kw: lambda func: func),
            "utils.security": types.SimpleNamespace(isRunningOnSecureDesktop=lambda: self.secure),
            "winAPI.sessionTracking": types.SimpleNamespace(isLockScreenModeActive=lambda: self.locked),
        }
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        path = Path(__file__).resolve().parents[1] / "addon/appModules/happ/__init__.py"
        spec = importlib.util.spec_from_file_location("happ_test_module", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(lambda: sys.modules.pop("happ_test_module.context", None))
        self.addCleanup(lambda: sys.modules.pop(spec.name, None))
        spec.loader.exec_module(module)
        self.app = module.AppModule()
        self.module = module
        self.app.processID = 42
        self.hit = self.button

    def setting(self):
        obj = self.module.ContextLabel("TextField")
        obj.parent = Node("SettingsPane")
        obj.name = None
        obj.UIAElement.currentName = ""
        self.api.getFocusObject = lambda: obj
        return obj

    def test_empty_native_name_does_not_skip_editor_recognition(self):
        from unittest.mock import Mock
        obj = self.setting()
        reader = Mock()
        factory = Mock(return_value=reader)
        with patch.dict(sys.modules, {"happ_test_module.settings": types.SimpleNamespace(SettingReader=factory)}):
            self.app.event_gainFocus(obj, Mock())
        factory.assert_called_once_with(self.app, obj)

    def test_tab_skips_confirmed_hidden_setting_without_speech(self):
        from unittest.mock import Mock
        obj = self.setting()
        gesture = Mock()
        self.app.script_settingsTab(gesture)
        handler = Mock()
        with patch.dict(sys.modules, {"happ_test_module.settings": types.SimpleNamespace(is_covered_setting=lambda *args: True)}):
            self.app.event_gainFocus(obj, handler)
        handler.assert_not_called()
        self.timers[-1].run()
        self.assertEqual(gesture.send.call_count, 2)

    def test_pending_tab_does_not_follow_user_to_another_window(self):
        from unittest.mock import Mock
        obj = self.setting()
        gesture = Mock()
        self.app.script_settingsTab(gesture)
        with patch.dict(sys.modules, {"happ_test_module.settings": types.SimpleNamespace(is_covered_setting=lambda *args: True)}):
            self.app.event_gainFocus(obj, Mock())
        self.root = Node("OtherWindow", process=99)
        self.timers[-1].run()
        self.assertEqual(gesture.send.call_count, 1)

    def test_tab_passes_through_outside_settings(self):
        from unittest.mock import Mock
        self.api.getFocusObject = lambda: self.button
        gesture = Mock()
        self.app.script_settingsTab(gesture)
        gesture.send.assert_called_once_with()
        self.assertIsNone(self.app._settingsTab)

    def test_expired_tab_never_sends_another_key(self):
        from unittest.mock import Mock
        obj = self.setting()
        gesture = Mock()
        self.app._settingsTab = (gesture, self.root, 0, 24)
        self.assertFalse(self.app._continueSettingsTab(obj))
        gesture.send.assert_not_called()

    def test_tab_skip_limit_is_enforced(self):
        from unittest.mock import Mock
        obj = self.setting()
        gesture = Mock()
        self.app.script_settingsTab(gesture)
        first, foreground, deadline, remaining = self.app._settingsTab
        self.app._settingsTab = (first, foreground, deadline, 0)
        self.assertFalse(self.app._continueSettingsTab(obj))
        self.assertEqual(gesture.send.call_count, 1)

    def test_new_tab_stops_previous_continuation(self):
        from unittest.mock import Mock
        obj = self.setting()
        gesture = Mock()
        self.app.script_settingsTab(gesture)
        with patch.dict(sys.modules, {"happ_test_module.settings": types.SimpleNamespace(is_covered_setting=lambda *args: True)}):
            self.app.event_gainFocus(obj, Mock())
        timer = self.timers[-1]
        self.app.script_settingsTab(gesture)
        self.assertTrue(timer.stopped)

    def test_setting_editor_and_spinbox_receive_label_overlay(self):
        for kind, role in (("TextField_QMLTYPE_9", 8), ("SpinBox_QMLTYPE_10", 8), ("Switch_QMLTYPE_11", 9)):
            with self.subTest(kind=kind):
                obj = Node(kind)
                obj.role = role
                classes = []
                self.app.chooseNVDAObjectOverlayClasses(obj, classes)
                self.assertEqual(len(classes), 1)
                self.assertTrue(any(base.__name__ == "SettingsRowLabel" for base in classes[0].__mro__))

    def test_focus_event_preserves_chain_and_cancels_reader(self):
        from unittest.mock import Mock
        reader = self.app._settingReader = Mock()
        next_handler = Mock()
        self.app.event_gainFocus(Node("Unrelated"), next_handler)
        next_handler.assert_called_once_with()
        reader.cancel.assert_called_once_with()
        self.assertIsNone(self.app._settingReader)

    def test_settings_groups_refuses_page_without_panes(self):
        self.app.script_settingsGroups(None)
        self.assertEqual(self.mouse_events, [])
        self.assertIn("Откройте главную страницу настроек Happ", self.messages)

    def test_navigation_cancels_settings_group_action(self):
        from unittest.mock import Mock
        groups = self.app._groupsMenu = Mock()
        self.app.script_navigation(None)
        groups.cancel.assert_called_once_with()
        self.assertIsNone(self.app._groupsMenu)

    def test_termination_cancels_settings_group_action(self):
        from unittest.mock import Mock
        groups = self.app._groupsMenu = Mock()
        self.app.terminate()
        groups.cancel.assert_called_once_with()

    def test_settings_groups_refuses_locked_session(self):
        self.locked = True
        self.app.script_settingsGroups(None)
        self.assertEqual(self.mouse_events, [])
        self.assertEqual(self.messages, [])

    def move_cursor(self, *point):
        self.cursor = point

    def schedule(self, delay, callback, *args):
        timer = types.SimpleNamespace(stopped=False)
        timer.Stop = lambda: setattr(timer, "stopped", True)
        timer.run = lambda: None if timer.stopped else callback(*args)
        self.timers.append(timer)
        return timer

    def run_command(self):
        self.app.script_navigation(None)
        if self.timers:
            self.timers[-1].run()

    def test_unique_button_click_and_cursor_restoration(self):
        self.run_command()
        self.assertEqual(self.mouse_events, [(2, 0, 0), (4, 0, 0)])
        self.assertEqual(self.cursor, (300, 400))
        self.assertEqual(self.button.invocations, 0)

    def test_locked_or_secure_desktop(self):
        self.locked = True
        self.run_command()
        self.locked = False
        self.secure = True
        self.run_command()
        self.assertEqual(self.button.invocations, 0)
        self.assertEqual(self.mouse_events, [])

    def test_foreign_process_and_dialog(self):
        self.root.processID = 99
        self.run_command()
        self.root.processID = 42
        self.root.UIAElement.currentClassName = "Dialog_QMLTYPE_1"
        self.run_command()
        self.assertEqual(self.button.invocations, 0)
        self.assertEqual(self.mouse_events, [])

    def test_duplicate_buttons(self):
        other = Node("NavButton_QMLTYPE_44")
        self.button.next = other
        self.run_command()
        self.assertEqual(self.button.invocations + other.invocations, 0)
        self.assertEqual(self.mouse_events, [])

    def test_focus_switch_during_lookup(self):
        foreground = iter([self.root, Node("Main_QMLTYPE_17")])
        self.api.getForegroundObject = lambda: next(foreground)
        self.run_command()
        self.assertEqual(self.button.invocations, 0)
        self.assertEqual(self.mouse_events, [])

    def test_unavailable_button(self):
        self.button.states = {1}
        self.run_command()
        self.assertEqual(self.mouse_events, [])

    def test_hit_test_rejects_occluded_button(self):
        self.hit = self.root
        self.run_command()
        self.assertEqual(self.mouse_events, [])
        self.assertEqual(self.cursor, (300, 400))

    def test_invalid_geometry(self):
        self.button.location.width = 0
        self.run_command()
        self.assertEqual(self.mouse_events, [])

    def test_wait_for_release_has_limit(self):
        self.held = True
        self.run_command()
        for attempt in range(40):
            self.timers[-1].run()
        self.assertEqual(len(self.timers), 41)
        self.assertEqual(self.mouse_events, [])
        self.assertIn("Отпустите клавиши и повторите команду", self.messages)

    def test_release_allows_click(self):
        self.held = True
        self.run_command()
        self.assertEqual(self.mouse_events, [])
        self.held = False
        self.timers[-1].run()
        self.assertEqual(len(self.mouse_events), 2)

    def test_lock_before_callback(self):
        self.app.script_navigation(None)
        self.locked = True
        self.timers[-1].run()
        self.assertEqual(self.mouse_events, [])

    def test_terminate_cancels_callback(self):
        self.app.script_navigation(None)
        self.app.terminate()
        self.timers[-1].run()
        self.assertTrue(self.timers[-1].stopped)
        self.assertEqual(self.mouse_events, [])

    def test_repeat_replaces_pending_click(self):
        self.app.script_navigation(None)
        first = self.timers[-1]
        self.app.script_navigation(None)
        first.run()
        self.timers[-1].run()
        self.assertTrue(first.stopped)
        self.assertEqual(len(self.mouse_events), 2)

    def test_broken_sibling_cycle_is_bounded(self):
        self.button.next = self.button
        self.run_command()
        self.assertEqual(self.button.invocations, 0)
        self.assertEqual(self.mouse_events, [])


if __name__ == "__main__":
    unittest.main()
