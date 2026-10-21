import api
import core
import gui
import screenBitmap
import ui
import wx
from comtypes import COMError
from contentRecog import RecogImageInfo
from contentRecog.uwpOcr import UwpOcr, getLanguages
from logHandler import log
from NVDAObjects import NVDAObject
from utils.security import isRunningOnSecureDesktop
from winAPI.sessionTracking import isLockScreenModeActive

from .panelLabels import match_labels


class PanelMenu:
    def __init__(self, owner):
        self.owner = owner
        self.recognizer = None
        self.timeout = None
        self.dialog = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if self.timeout is not None:
            self.timeout.Stop()
            self.timeout = None
        if self.recognizer is not None:
            self.recognizer.cancel()
        if self.dialog is not None:
            self.dialog.EndModal(wx.ID_CANCEL)

    def safe(self):
        return (not self.cancelled and not self.owner._terminated
                and not isRunningOnSecureDesktop() and not isLockScreenModeActive())

    def start(self, foreground, buttons):
        try:
            if not self.safe() or api.getForegroundObject() != foreground:
                return
            self.foreground = foreground
            self.buttons = buttons
            self.rectangles = [button.location for button in buttons]
            if any(not rect or rect.width <= 0 or rect.height <= 0 for rect in self.rectangles):
                ui.message("Границы панели недоступны")
                return
            left = min(rect.left for rect in self.rectangles)
            top = min(rect.top for rect in self.rectangles)
            right = max(rect.left + rect.width for rect in self.rectangles)
            bottom = max(rect.top + rect.height for rect in self.rectangles)
            if right - left > 800 or bottom - top > 1600:
                ui.message("Не удалось проверить расположение панели")
                return
            for button, rect in zip(buttons, self.rectangles):
                if NVDAObject.objectFromPoint(rect.left + rect.width // 2, rect.top + rect.height // 2) != button:
                    ui.message("Панель перекрыта другим окном")
                    return
            language = next((lang for lang in getLanguages() if lang.lower().startswith("ru")), None)
            if language is None:
                ui.message("Для чтения панели нужен русский язык распознавания Windows")
                return
            self.recognizer = UwpOcr(language)
            self.info = RecogImageInfo(left, top, right - left, bottom - top, 2)
            bitmap = screenBitmap.ScreenBitmap(self.info.recogWidth, self.info.recogHeight)
            self.pixels = bitmap.captureImage(left, top, right - left, bottom - top)
            if not self.safe() or api.getForegroundObject() != foreground:
                return
            ui.message("Чтение разделов панели")
            self.timeout = core.callLater(5000, self.expire)
            self.recognizer.recognize(self.pixels, self.info, self.receive)
        except (COMError, RuntimeError, OSError, ValueError, LookupError):
            self.cancel()
            log.debugWarning("Happ panel recognition unavailable", exc_info=True)
            ui.message("Не удалось прочитать разделы панели")

    def expire(self):
        self.timeout = None
        self.cancel()
        if not self.owner._terminated and not isRunningOnSecureDesktop() and not isLockScreenModeActive():
            ui.message("Время чтения панели истекло")

    def receive(self, result):
        wx.CallAfter(self.show, result)

    def show(self, result):
        if self.timeout is not None:
            self.timeout.Stop()
            self.timeout = None
        if not self.safe() or api.getForegroundObject() != self.foreground:
            return
        if isinstance(result, Exception):
            ui.message("Не удалось распознать разделы панели")
            return
        entries = match_labels(result.data, self.info, self.rectangles)
        if not entries:
            ui.message("Названия разделов не распознаны")
            return
        selection = None
        gui.mainFrame.prePopup()
        try:
            self.dialog = wx.SingleChoiceDialog(
                gui.mainFrame,
                "Выберите раздел стрелками и нажмите Enter. Escape — отмена. "
                "Показаны только распознанные пункты.",
                "Разделы Happ",
                [label for index, label in entries],
            )
            if self.dialog.ShowModal() == wx.ID_OK:
                selection = self.dialog.GetSelection()
        finally:
            if self.dialog is not None:
                self.dialog.Destroy()
                self.dialog = None
            gui.mainFrame.postPopup()
        if selection is None or not self.safe():
            return
        index, label = entries[selection]
        try:
            button = self.buttons[index]
            if button.location != self.rectangles[index]:
                ui.message("Положение панели изменилось. Повторите команду")
                return
            self.foreground.setFocus()
            self.owner._clickTimer = core.callLater(200, self.owner._clickNavigation, button, self.foreground)
        except (COMError, RuntimeError):
            ui.message("Окно Happ больше недоступно")
