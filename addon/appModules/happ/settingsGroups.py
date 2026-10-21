import api
import core
import gui
import mouseHandler
import screenBitmap
import ui
import winUser
import wx
from comtypes import COMError
from contentRecog import RecogImageInfo
from contentRecog.uwpOcr import UwpOcr, getLanguages
from logHandler import log
from NVDAObjects import NVDAObject

from .groupLabels import match_groups
from .panel import PanelMenu


class SettingsGroups(PanelMenu):
    def start(self, foreground, viewport, panes):
        self.foreground = foreground
        self.viewport = viewport
        self.viewportRect = viewport.location
        self.panes = panes
        self.rectangles = [pane.location for pane in panes]
        self.selection = None
        self.actionTimer = None
        self.capture()

    def cancel(self):
        super().cancel()
        timer = getattr(self, "actionTimer", None)
        if timer is not None:
            timer.Stop()
            self.actionTimer = None

    def unchanged(self):
        return (self.safe() and api.getForegroundObject() == self.foreground
                and self.foreground.processID == self.owner.processID
                and self.viewport.location == self.viewportRect
                and all(pane.location == rect for pane, rect in zip(self.panes, self.rectangles)))

    def capture(self):
        self.actionTimer = None
        try:
            if not self.unchanged():
                self.cancel()
                return
            view = self.viewportRect
            window = self.foreground.location
            if not view or not window or any(not rect for rect in self.rectangles):
                self.cancel()
                return
            left = max(view.left, window.left, min(rect.left for rect in self.rectangles))
            right = min(view.left + view.width, window.left + window.width,
                        max(rect.left + min(rect.width // 2, 600) for rect in self.rectangles))
            top = max(view.top, window.top)
            bottom = min(view.top + view.height, window.top + window.height)
            if not (20 <= right - left <= 800 and 20 <= bottom - top <= 1200):
                self.cancel()
                return
            language = next((value for value in getLanguages() if value.lower().startswith("ru")), None)
            if language is None:
                self.cancel()
                ui.message("Для чтения групп нужен русский язык распознавания Windows")
                return
            self.info = RecogImageInfo(left, top, right - left, bottom - top, 2)
            bitmap = screenBitmap.ScreenBitmap(self.info.recogWidth, self.info.recogHeight)
            self.pixels = bitmap.captureImage(left, top, right - left, bottom - top)
            if not self.unchanged():
                self.cancel()
                return
            self.recognizer = UwpOcr(language)
            self.timeout = core.callLater(5000, self.expire)
            self.recognizer.recognize(self.pixels, self.info, self.receive)
        except (COMError, RuntimeError, OSError, ValueError, LookupError):
            self.cancel()
            log.debugWarning("Happ settings groups unavailable", exc_info=True)
            ui.message("Не удалось прочитать группы настроек")

    def restore(self):
        self.actionTimer = None
        try:
            if not self.safe() or api.getForegroundObject() != self.foreground:
                self.cancel()
                return
            self.viewportRect = self.viewport.location
            self.rectangles = [pane.location for pane in self.panes]
            self.capture()
        except (COMError, RuntimeError):
            self.cancel()
            log.debugWarning("Happ settings layout unavailable after dialog", exc_info=True)
            ui.message("Не удалось проверить расположение группы")

    def expire(self):
        announce = self.safe() and api.getForegroundObject() == self.foreground
        self.cancel()
        if announce:
            ui.message("Время чтения групп настроек истекло")

    def show(self, result):
        if self.timeout is not None:
            self.timeout.Stop()
            self.timeout = None
        try:
            if not self.unchanged():
                self.cancel()
                return
            if isinstance(result, Exception):
                self.cancel()
                ui.message("Не удалось распознать группы настроек")
                return
            entries = match_groups(result.data, self.info, self.rectangles, self.viewportRect)
            entries = [entry for entry in entries if self.hit(entry)]
            if self.selection is not None:
                matching = [entry for entry in entries if entry[:2] == self.selection[:2]]
                if len(matching) != 1:
                    self.cancel()
                    ui.message("Группа изменилась. Нажатие отменено")
                    return
                self.selection = matching[0]
                self.click()
                return
            if not entries:
                self.cancel()
                ui.message("Видимые заголовки групп не распознаны")
                return
            selected = None
            gui.mainFrame.prePopup()
            try:
                self.dialog = wx.SingleChoiceDialog(
                    gui.mainFrame,
                    "Выберите заголовок группы. Enter — нажать, Escape — отмена. "
                    "Показаны только видимые распознанные группы.",
                    "Группы настроек Happ", [entry[1] for entry in entries],
                )
                if self.dialog.ShowModal() == wx.ID_OK:
                    selected = entries[self.dialog.GetSelection()]
            finally:
                if self.dialog is not None:
                    self.dialog.Destroy()
                    self.dialog = None
                gui.mainFrame.postPopup()
            if selected is None or not self.safe():
                self.cancel()
                return
            self.selection = selected
            self.foreground.setFocus()
            self.actionTimer = core.callLater(200, self.restore)
        except (COMError, RuntimeError):
            self.cancel()
            log.debugWarning("Happ settings group changed", exc_info=True)
            ui.message("Группа настроек больше недоступна")

    def hit(self, entry):
        index, label, bounds = entry
        left, top, right, bottom = bounds
        return NVDAObject.objectFromPoint((left + right) // 2, (top + bottom) // 2) == self.panes[index]

    def click(self, retries=40):
        self.actionTimer = None
        try:
            if not self.unchanged() or self.selection is None or not self.hit(self.selection):
                self.cancel()
                return
            if any(winUser.getAsyncKeyState(key) & 0x8000 for key in range(1, 256)):
                if retries:
                    self.actionTimer = core.callLater(50, self.click, retries - 1)
                else:
                    self.cancel()
                    ui.message("Отпустите клавиши и повторите команду")
                return
            left, top, right, bottom = self.selection[2]
            point = ((left + right) // 2, (top + bottom) // 2)
            previous = winUser.getCursorPos()
            try:
                winUser.setCursorPos(*point)
                if not self.unchanged() or not self.hit(self.selection) or tuple(winUser.getCursorPos()) != point:
                    return
                try:
                    mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTDOWN, 0, 0)
                finally:
                    mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTUP, 0, 0)
                ui.message("Нажатие заголовка группы отправлено")
            finally:
                if tuple(winUser.getCursorPos()) == point:
                    winUser.setCursorPos(*previous)
                self.cancel()
        except (COMError, RuntimeError, OSError):
            self.cancel()
            log.debugWarning("Happ settings group click failed", exc_info=True)
            ui.message("Не удалось нажать заголовок группы")
