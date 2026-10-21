import api
import core
import screenBitmap
import ui
import wx
from comtypes import COMError
from contentRecog import RecogImageInfo
from contentRecog.uwpOcr import UwpOcr, getLanguages
from controlTypes import State
from logHandler import log
from NVDAObjects import NVDAObject
from utils.security import isRunningOnSecureDesktop
from winAPI.sessionTracking import isLockScreenModeActive

from .context import setting_row_label


def belongs_to_control(hit, control):
    for depth in range(4):
        if hit is None:
            return False
        if hit == control:
            return True
        if hit.processID != control.processID:
            return False
        hit = hit.parent
    return False


class SettingReader:
    def __init__(self, owner, obj):
        self.owner = owner
        self.obj = obj
        self.foreground = api.getForegroundObject()
        self.rect = obj.location
        self.parent = obj.parent
        self.parentRect = self.parent.location
        self.timer = None
        self.recognizer = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if self.timer is not None:
            self.timer.Stop()
            self.timer = None
        if self.recognizer is not None:
            self.recognizer.cancel()
            self.recognizer = None

    def safe(self):
        return (not self.cancelled and not self.owner._terminated
                and not isRunningOnSecureDesktop() and not isLockScreenModeActive()
                and api.getFocusObject() == self.obj
                and api.getForegroundObject() == self.foreground
                and self.foreground.processID == self.owner.processID
                and self.obj.location == self.rect and self.parent.location == self.parentRect
                and self.obj.processID == self.owner.processID
                and not self.obj.states & {State.INVISIBLE, State.OFFSCREEN, State.UNAVAILABLE})

    def start(self):
        self.timer = None
        try:
            if not self.safe() or not self.rect or not self.parentRect:
                return
            rect = self.rect
            pane = self.parentRect
            left = pane.left
            top = rect.top
            width = rect.left - left
            height = rect.height
            window = self.foreground.location
            if (not window or not 20 <= width <= 2000 or not 12 <= height <= 120
                    or top < pane.top or top + height > pane.top + pane.height
                    or rect.left + rect.width > pane.left + pane.width
                    or left < window.left or top < window.top
                    or rect.left + rect.width > window.left + window.width
                    or top + height > window.top + window.height):
                return
            if not belongs_to_control(
                    NVDAObject.objectFromPoint(rect.left + rect.width // 2, top + height // 2), self.obj):
                return
            for offset in (1, width // 2, width - 1):
                hit = NVDAObject.objectFromPoint(left + offset, top + height // 2)
                if hit is None or hit.processID != self.owner.processID:
                    return
            language = next((value for value in getLanguages() if value.lower().startswith("ru")), None)
            if language is None:
                return
            self.info = RecogImageInfo(left, top, width, height, 2)
            bitmap = screenBitmap.ScreenBitmap(self.info.recogWidth, self.info.recogHeight)
            self.pixels = bitmap.captureImage(left, top, width, height)
            if not self.safe():
                return
            self.recognizer = UwpOcr(language)
            self.timer = core.callLater(5000, self.cancel)
            self.recognizer.recognize(self.pixels, self.info, self.receive)
        except (COMError, RuntimeError, OSError, ValueError, LookupError):
            self.cancel()
            log.debugWarning("Happ setting label recognition unavailable", exc_info=True)

    def receive(self, result):
        wx.CallAfter(self.finish, result)

    def finish(self, result):
        try:
            if not self.safe() or isinstance(result, Exception):
                return
            label = setting_row_label(result.data, self.info.recogWidth, self.info.recogHeight)
            if not label:
                return
            self.obj._happRowLabel = (label, self.rect)
            native = self.obj.UIAElement.currentName
            ui.message(f"{label}: {native}" if native else label)
        except (COMError, RuntimeError):
            log.debugWarning("Happ setting changed during recognition")
        finally:
            self.cancel()
