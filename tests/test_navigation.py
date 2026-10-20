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
        self.button = Node("NavButton_QMLTYPE_12")
        self.root = Node("Main_QMLTYPE_17", [Node("QQuickControl", [self.button])])
        self.api = types.SimpleNamespace(getForegroundObject=lambda: self.root)
        state = types.SimpleNamespace(UNAVAILABLE=1, INVISIBLE=2, OFFSCREEN=3)
        role = types.SimpleNamespace(EDITABLETEXT=8, BUTTON=9)
        modules = {
            "appModuleHandler": types.SimpleNamespace(AppModule=object),
            "api": self.api,
            "ui": types.SimpleNamespace(message=self.messages.append),
            "comtypes": types.SimpleNamespace(COMError=type("COMError", (Exception,), {})),
            "controlTypes": types.SimpleNamespace(Role=role, State=state),
            "logHandler": types.SimpleNamespace(log=types.SimpleNamespace(debugWarning=lambda *a: None)),
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
        self.app.processID = 42

    def run_command(self):
        self.app.script_navigation(None)

    def test_unique_native_action(self):
        self.run_command()
        self.assertEqual(self.button.invocations, 1)

    def test_locked_or_secure_desktop(self):
        self.locked = True
        self.run_command()
        self.locked = False
        self.secure = True
        self.run_command()
        self.assertEqual(self.button.invocations, 0)

    def test_foreign_process_and_dialog(self):
        self.root.processID = 99
        self.run_command()
        self.root.processID = 42
        self.root.UIAElement.currentClassName = "Dialog_QMLTYPE_1"
        self.run_command()
        self.assertEqual(self.button.invocations, 0)

    def test_duplicate_buttons(self):
        other = Node("NavButton_QMLTYPE_44")
        self.button.next = other
        self.run_command()
        self.assertEqual(self.button.invocations + other.invocations, 0)

    def test_focus_switch_during_lookup(self):
        foreground = iter([self.root, Node("Main_QMLTYPE_17")])
        self.api.getForegroundObject = lambda: next(foreground)
        self.run_command()
        self.assertEqual(self.button.invocations, 0)

    def test_unavailable_or_no_native_action(self):
        self.button.states = {1}
        self.run_command()
        self.button.states = set()
        self.button.UIAInvokePattern = None
        self.run_command()
        self.assertEqual(self.button.invocations, 0)

    def test_broken_sibling_cycle_is_bounded(self):
        self.button.next = self.button
        self.run_command()
        self.assertEqual(self.button.invocations, 0)


if __name__ == "__main__":
    unittest.main()
