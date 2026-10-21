import api
import core
import screenBitmap
import ui
import wx
from types import SimpleNamespace
from comtypes import COMError
from contentRecog import RecogImageInfo
from contentRecog.uwpOcr import UwpOcr, getLanguages
from controlTypes import State
from logHandler import log
from NVDAObjects import NVDAObject
from utils.security import isRunningOnSecureDesktop
from winAPI.sessionTracking import isLockScreenModeActive

from .context import qml_type, setting_label_from_pane


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


def is_covered_setting(obj, hit):
    if qml_type(obj.UIAElement.currentClassName) not in ("Switch", "ComboBox", "TextField", "SpinBox"):
        return False
    if hit is None or hit.processID != obj.processID:
        return False
    parent = obj.parent
    if parent is None or qml_type(parent.UIAElement.currentClassName) != "SettingsPane":
        return False
    rect, pane = obj.location, getattr(parent, "location", None)
    if (rect and pane and rect.width > 0 and rect.height > 0 and pane.width > 0 and pane.height > 0
            and (rect.top >= pane.top + pane.height or rect.top + rect.height <= pane.top)):
        return True
    if belongs_to_control(hit, obj):
        return False
    for depth in range(4):
        if hit is None or hit.processID != obj.processID:
            return False
        if hit.parent == parent:
            return qml_type(hit.UIAElement.currentClassName) in ("Switch", "ComboBox", "TextField", "SpinBox")
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
        self.headingRect = None

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
            window = self.foreground.location
            if (not window or not 12 <= rect.height <= 120
                    or rect.top < pane.top or rect.top + rect.height > pane.top + pane.height
                    or rect.left + rect.width > pane.left + pane.width
                    or left < window.left or rect.top < window.top
                    or rect.left + rect.width > window.left + window.width
                    or rect.top + rect.height > window.top + window.height):
                return
            right = rect.left
            menu = qml_type(self.obj.UIAElement.currentClassName) == "ImageButton"
            children = []
            child = self.parent.firstChild
            for index in range(64):
                if child is None:
                    break
                child_rect = child.location
                element = getattr(child, "UIAElement", None)
                if element is None:
                    return
                children.append((qml_type(element.currentClassName), child_rect))
                if (child_rect and child_rect.width > 0 and child_rect.height > 0
                        and qml_type(element.currentClassName) in ("Switch", "TextField", "ComboBox", "SpinBox")
                        and left + 20 <= child_rect.left < right):
                    right = child_rect.left
                child = child.next
            else:
                return
            top = max(pane.top, window.top)
            bottom = min(pane.top + pane.height, window.top + window.height)
            if menu:
                if (qml_type(self.parent.UIAElement.currentClassName) != "StackView"
                        or any(kind not in ("ImageButton", "SettingsPane") for kind, area in children)
                        or sum(kind == "ImageButton" for kind, area in children) != 1):
                    return
                panes = [area for kind, area in children if kind == "SettingsPane"]
                if not panes or any(not area or area.width <= 0 or area.height <= 0 for area in panes):
                    return
                bottom = min(bottom, min(area.top for area in panes))
                left = max(left, min(area.left for area in panes))
                if rect.top + rect.height > bottom or rect.top - top > 2 * rect.height:
                    return
            width, height = min(right - left, 1200), bottom - top
            if (qml_type(self.obj.UIAElement.currentClassName) == "TextField"
                    and rect == pane and children == [("TextField", rect)]):
                container = self.parent.parent
                if (qml_type(self.parent.UIAElement.currentClassName) != "SettingsPane"
                        or container is None
                        or qml_type(container.UIAElement.currentClassName) != "StackView"
                        or not container.location):
                    return
                top = max(window.top, container.location.top, pane.top - rect.height)
                bottom = pane.top
                width, height = min(pane.width, 1200), bottom - top
                self.headingRect = SimpleNamespace(left=left + width, top=top, height=height)
                top = max(window.top, container.location.top, pane.top - 2 * rect.height)
                width, height = min(width, 600), bottom - top
            if not 20 <= width <= 1200 or not 12 <= height <= 1200:
                return
            if not belongs_to_control(
                    NVDAObject.objectFromPoint(rect.left + rect.width // 2, rect.top + rect.height // 2), self.obj):
                return
            for offset in (1, width // 2, width - 1):
                sample_y = top + height // 2 if self.headingRect else rect.top + rect.height // 2
                hit = NVDAObject.objectFromPoint(left + offset, sample_y)
                if hit is None or hit.processID != self.owner.processID:
                    return
            languages = getLanguages()
            language = next((value for value in languages if value.lower().startswith("en")), None) if self.headingRect else None
            language = language or next((value for value in languages if value.lower().startswith("ru")), None)
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
            label = setting_label_from_pane(result.data, self.info, self.headingRect or self.rect)
            if not label:
                return
            if self.headingRect:
                if label != "User agent":
                    return
                label = "Агент пользователя (User agent)"
            if qml_type(self.obj.UIAElement.currentClassName) == "ImageButton":
                if label != "Правила маршрутизации":
                    return
                label = "Меню правил маршрутизации"
            self.obj._happRowLabel = (label, self.rect)
            native = self.obj.UIAElement.currentName
            ui.message(f"{label}: {native}" if native else label)
        except (COMError, RuntimeError):
            log.debugWarning("Happ setting changed during recognition")
        finally:
            self.cancel()
