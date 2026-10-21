import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class PanelLifecycleTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "addon/appModules/happ"
        label_spec = importlib.util.spec_from_file_location("panel_test.panelLabels", root / "panelLabels.py")
        label_module = importlib.util.module_from_spec(label_spec)
        label_spec.loader.exec_module(label_module)
        self.pending = []
        self.popup = Mock(side_effect=AssertionError("Unexpected dialog"))
        self.foreground = object()
        self.locked = False
        modules = {
            "api": SimpleNamespace(getForegroundObject=lambda: self.foreground),
            "core": SimpleNamespace(),
            "gui": SimpleNamespace(mainFrame=SimpleNamespace(prePopup=self.popup)),
            "screenBitmap": SimpleNamespace(),
            "ui": SimpleNamespace(message=Mock()),
            "wx": SimpleNamespace(CallAfter=lambda function, *args: self.pending.append((function, args)), ID_CANCEL=0),
            "comtypes": SimpleNamespace(COMError=type("COMError", (Exception,), {})),
            "contentRecog": SimpleNamespace(RecogImageInfo=object),
            "contentRecog.uwpOcr": SimpleNamespace(UwpOcr=object, getLanguages=lambda: []),
            "logHandler": SimpleNamespace(log=Mock()),
            "NVDAObjects": SimpleNamespace(NVDAObject=object),
            "utils.security": SimpleNamespace(isRunningOnSecureDesktop=lambda: False),
            "winAPI.sessionTracking": SimpleNamespace(isLockScreenModeActive=lambda: self.locked),
            "panel_test.panelLabels": label_module,
        }
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        spec = importlib.util.spec_from_file_location("panel_test.panel", root / "panel.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.menu = module.PanelMenu(SimpleNamespace(_terminated=False))
        self.menu.foreground = self.foreground

    def test_result_is_deferred_to_gui_loop(self):
        self.menu.receive(SimpleNamespace())
        self.assertEqual(len(self.pending), 1)
        self.popup.assert_not_called()

    def test_cancelled_late_result_never_opens_dialog(self):
        self.menu.receive(SimpleNamespace())
        self.menu.cancel()
        function, args = self.pending.pop()
        function(*args)
        self.popup.assert_not_called()

    def test_lock_before_result_never_opens_dialog(self):
        self.menu.receive(SimpleNamespace())
        self.locked = True
        function, args = self.pending.pop()
        function(*args)
        self.popup.assert_not_called()

    def test_changed_foreground_discards_result(self):
        self.foreground = object()
        self.menu.show(SimpleNamespace())
        self.popup.assert_not_called()

    def test_cancel_stops_recognition_and_timeout(self):
        recognizer = self.menu.recognizer = Mock()
        timer = self.menu.timeout = Mock()
        self.menu.cancel()
        recognizer.cancel.assert_called_once_with()
        timer.Stop.assert_called_once_with()
