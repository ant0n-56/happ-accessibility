import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_servers as server_tests
from test_servers import Node, Rect


class SubscriptionActionTests(unittest.TestCase):
    move = server_tests.ServerTests.move

    def setUp(self):
        server_tests.ServerTests.setUp(self)
        path = Path(__file__).resolve().parents[1] / "addon/appModules/happ/subscriptionActions.py"
        name = "servers_test.subscriptionActions"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.addCleanup(lambda: sys.modules.pop(name, None))
        spec.loader.exec_module(module)
        self.module = module
        self.buttons = [Node("ImageButton", rect=Rect(left, 150, 20, 20)) for left in (814, 842, 870)]
        self.info = Node("ServerItem", rect=Rect(100, 186, 800, 24),
                         children=[Node("ProgressBar", rect=Rect(110, 190, 680, 16))])
        self.controls[0].location = Rect(100, 90, 750, 40)
        self.container = Node("QQuickControl", children=self.controls + self.buttons + [self.info])
        self.window.firstChild = self.container
        self.container.parent = self.window
        for button in self.buttons:
            button.parent = self.container
        self.anchor = self.buttons[-1]
        module.api.getFocusObject = lambda: self.anchor
        module.NVDAObject.objectFromPoint = self.hit_point
        self.menu = module.SubscriptionActions(SimpleNamespace(processID=42, _terminated=False))
        self.menu.foreground = self.window
        self.menu.anchor = self.anchor
        self.menu.group = module.read_group(self.window, self.anchor)
        self.menu.rows = self.buttons
        self.menu.rectangles = [button.location for button in self.buttons]
        self.menu.selection = (0, "Обновить подписку")
        self.menu.actionTimer = None
        module.wx.ID_YES = 2
        module.wx.YES_NO = 4
        module.wx.NO_DEFAULT = 8
        module.wx.ICON_QUESTION = 16
        self.dialog = Mock()
        self.confirm = Mock()
        self.dialog.ShowModal.return_value = module.wx.ID_OK
        self.dialog.GetSelection.return_value = 0
        self.confirm.ShowModal.return_value = module.wx.ID_YES
        module.wx.SingleChoiceDialog = Mock(return_value=self.dialog)
        module.wx.MessageDialog = Mock(return_value=self.confirm)
        self.window.setFocus = Mock()

    def hit_point(self, left, top):
        return next((button for button in self.buttons
                     if button.location.left <= left < button.location.left + button.location.width), None)

    def test_observed_group_has_three_actions(self):
        self.assertEqual([label for obj, label, rect in self.menu.group[0]],
                         ["Обновить подписку", "Пинг подписки", "Меню подписки"])

    def test_no_focused_subscription_button_rejects(self):
        self.assertIsNone(self.module.read_group(self.window, self.row))

    def test_other_page_rejects(self):
        self.controls[1].UIAElement.currentName = "Другое"
        self.assertIsNone(self.module.read_group(self.window, self.anchor))

    def test_missing_info_rejects(self):
        self.info.firstChild = None
        self.assertIsNone(self.module.read_group(self.window, self.anchor))

    def test_disabled_action_rejects(self):
        self.buttons[0].states.add(3)
        self.assertIsNone(self.module.read_group(self.window, self.anchor))

    def test_second_subscription_uses_focused_group_only(self):
        buttons = [Node("ImageButton", rect=Rect(left, 400, 20, 20)) for left in (814, 842, 870)]
        info = Node("ServerItem", rect=Rect(100, 436, 800, 24),
                    children=[Node("ProgressBar", rect=Rect(110, 440, 680, 16))])
        self.info.next = buttons[0]
        for before, after in zip(buttons, buttons[1:] + [info]):
            before.next = after
        for button in buttons:
            button.parent = self.container
        group = self.module.read_group(self.window, buttons[-1])
        self.assertEqual([entry[0] for entry in group[0]], buttons)
        first_group = self.module.read_group(self.window, self.anchor)
        self.assertEqual([entry[0] for entry in first_group[0]], self.buttons)

    def test_partly_hidden_group_rejects(self):
        self.window.location = Rect(0, 0, 880, 800)
        self.assertIsNone(self.module.read_group(self.window, self.anchor))

    def test_replaced_anchor_rejects(self):
        self.buttons[-2].next = Node("ImageButton", rect=self.anchor.location)
        self.assertIsNone(self.module.read_group(self.window, self.anchor))

    def test_cycle_is_bounded(self):
        self.info.next = self.container.firstChild
        self.assertIsNone(self.module.read_group(self.window, self.anchor))

    def test_open_only_queues_dialog(self):
        self.menu.start(self.window)
        self.assertEqual(len(self.pending), 1)
        self.mouse.assert_not_called()
        self.module.wx.SingleChoiceDialog.assert_not_called()

    def test_escape_never_clicks(self):
        self.dialog.ShowModal.return_value = self.module.wx.ID_CANCEL
        self.menu.showActions()
        self.mouse.assert_not_called()
        self.assertTrue(self.menu.cancelled)
        self.module.wx.MessageDialog.assert_not_called()

    def test_update_confirmation_defaults_to_no(self):
        self.confirm.ShowModal.return_value = self.module.wx.ID_CANCEL
        self.menu.showActions()
        self.mouse.assert_not_called()
        self.assertTrue(self.menu.cancelled)
        self.assertTrue(self.module.wx.MessageDialog.call_args.args[3] & self.module.wx.NO_DEFAULT)

    def test_ping_confirmation_is_required(self):
        self.dialog.GetSelection.return_value = 1
        self.confirm.ShowModal.return_value = self.module.wx.ID_CANCEL
        self.menu.showActions()
        self.module.wx.MessageDialog.assert_called_once()
        self.mouse.assert_not_called()

    def test_confirmation_only_schedules_action(self):
        self.menu.showActions()
        self.mouse.assert_not_called()
        self.module.core.callLater.assert_called_once()
        self.assertEqual(self.menu.selection[0], 0)

    def test_menu_action_has_no_network_confirmation(self):
        self.dialog.GetSelection.return_value = 2
        self.menu.showActions()
        self.module.wx.MessageDialog.assert_not_called()
        self.assertEqual(self.menu.selection[0], 2)
        self.dialog.SetSelection.assert_called_once_with(2)

    def test_single_click_and_cursor_restoration(self):
        self.menu.activate()
        self.menu.activate()
        self.assertEqual(self.mouse.call_count, 2)
        self.assertEqual(self.cursor, (20, 30))

    def test_structure_change_blocks_click(self):
        self.row.location = Rect(100, 201, 800, 48)
        self.menu.activate()
        self.mouse.assert_not_called()

    def test_occlusion_blocks_click(self):
        with patch.object(self.module.NVDAObject, "objectFromPoint", return_value=object()):
            self.menu.activate()
        self.mouse.assert_not_called()

    def test_lock_blocks_click(self):
        self.locked = True
        self.menu.activate()
        self.mouse.assert_not_called()

    def test_cancelled_queued_dialog_is_ignored(self):
        self.menu.start(self.window)
        self.menu.cancel()
        callback, args = self.pending.pop()
        callback(*args)
        self.module.wx.SingleChoiceDialog.assert_not_called()


if __name__ == "__main__":
    unittest.main()
