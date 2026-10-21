import api
import core
import gui
import ui
import wx
from comtypes import COMError
from controlTypes import State
from logHandler import log
from NVDAObjects import NVDAObject
from NVDAObjects.UIA import UIA

from .context import is_subscription_info, qml_type, subscription_header_label
from .servers import ServerMenu


def read_group(foreground, anchor):
    if (not isinstance(anchor, UIA) or anchor.processID != foreground.processID
            or qml_type(anchor.UIAElement.currentClassName) != "ImageButton"):
        return None
    container = anchor.parent
    if (not isinstance(container, UIA) or container.parent != foreground
            or qml_type(container.UIAElement.currentClassName) != "QQuickControl"):
        return None
    anchor_rect = anchor.location
    if anchor_rect is None:
        return None
    children = []
    records = []
    information = []
    snapshot = []
    child = container.firstChild
    for index in range(128):
        if child is None:
            break
        if not isinstance(child, UIA) or child.processID != foreground.processID:
            return None
        record = (child.UIAElement.currentClassName, child.UIAElement.currentName, child.location)
        children.append(child)
        records.append(record)
        snapshot.append((child, record))
        area = record[2]
        if (qml_type(record[0]) == "ServerItem" and area is not None
                and 0 <= area.top - anchor_rect.top - anchor_rect.height <= 2 * anchor_rect.height):
            parts = []
            part = child.firstChild
            for part_index in range(3):
                if part is None or not isinstance(part, UIA):
                    break
                part_record = (part.UIAElement.currentClassName, part.UIAElement.currentName, part.location)
                parts.append(part_record)
                snapshot.append((part, part_record))
                part = part.next
            if part is None and is_subscription_info(child.location, parts):
                information.append(child.location)
        child = child.next
    if child is not None or anchor not in children:
        return None
    if not subscription_header_label(anchor.location, records, information):
        return None
    actions = []
    for child, record in zip(children, records):
        rect = child.location
        if rect is None or rect.top != anchor.location.top:
            continue
        label = subscription_header_label(rect, records, information)
        if label and qml_type(record[0]) == "ImageButton" and not record[1]:
            actions.append((child, label, rect))
    actions.sort(key=lambda entry: entry[2].left)
    if [entry[1] for entry in actions] != ["Обновить подписку", "Пинг подписки", "Меню подписки"]:
        return None
    window = foreground.location
    if window is None:
        return None
    for child, label, rect in actions:
        if (child.states & {State.INVISIBLE, State.OFFSCREEN, State.UNAVAILABLE}
                or not (window.left <= rect.left and rect.left + rect.width <= window.left + window.width
                        and window.top <= rect.top and rect.top + rect.height <= window.top + window.height)):
            return None
    return actions, snapshot


class SubscriptionActions(ServerMenu):
    actionMessage = "Нажатие кнопки подписки отправлено. Проверьте результат в Happ"

    def start(self, foreground):
        self.foreground = foreground
        self.anchor = api.getFocusObject()
        self.selection = None
        self.actionTimer = None
        self.group = read_group(foreground, self.anchor)
        if self.group is None:
            self.cancel()
            ui.message("Перейдите клавишей Tab к кнопке Меню подписки нужной подписки и повторите команду")
            return
        self.rows = [entry[0] for entry in self.group[0]]
        self.rectangles = [entry[2] for entry in self.group[0]]
        wx.CallAfter(self.showActions)

    def unchanged(self):
        return (self.safe() and api.getForegroundObject() == self.foreground
                and self.foreground.processID == self.owner.processID
                and read_group(self.foreground, self.anchor) == self.group
                and all(NVDAObject.objectFromPoint(rect.left + rect.width // 2,
                                                  rect.top + rect.height // 2) == target
                        for target, rect in zip(self.rows, self.rectangles)))

    def showActions(self):
        try:
            if not self.unchanged():
                self.cancel()
                return
            selected = None
            gui.mainFrame.prePopup()
            try:
                labels = [entry[1] for entry in self.group[0]]
                self.dialog = wx.SingleChoiceDialog(
                    gui.mainFrame, "Действия подписки, на кнопке которой находился фокус. "
                    "Стрелки — выбор, Enter — продолжить, Escape — отмена. "
                    "Обновление и пинг требуют отдельного подтверждения.",
                    "Действия подписки Happ", labels,
                )
                self.dialog.SetSelection(2)
                if self.dialog.ShowModal() == wx.ID_OK:
                    selected = self.dialog.GetSelection()
                self.dialog.Destroy()
                self.dialog = None
                if selected in (0, 1) and self.safe():
                    text = ("Обновить выбранную подписку? Happ отправит сетевой запрос и может изменить список серверов."
                            if selected == 0 else "Запустить пинг выбранной подписки? Happ отправит сетевые запросы к её серверам.")
                    self.dialog = wx.MessageDialog(gui.mainFrame, text, labels[selected],
                                                   wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
                    if self.dialog.ShowModal() != wx.ID_YES:
                        selected = None
            finally:
                if self.dialog is not None:
                    self.dialog.Destroy()
                    self.dialog = None
                gui.mainFrame.postPopup()
            if selected is None or not self.safe():
                self.cancel()
                return
            self.selection = (selected, labels[selected])
            self.foreground.setFocus()
            self.actionTimer = core.callLater(200, self.activate)
        except (COMError, RuntimeError, OSError):
            self.cancel()
            log.debugWarning("Happ subscription actions unavailable")
            ui.message("Не удалось открыть действия подписки")
