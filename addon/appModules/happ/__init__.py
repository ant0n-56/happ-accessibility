"""Happ accessibility corrections. Copyright 2026 Anton Chigarev."""

import appModuleHandler
import api
import ui
import core
import mouseHandler
import winUser
from NVDAObjects import NVDAObject
from comtypes import COMError
from controlTypes import Role, State
from logHandler import log
from NVDAObjects.UIA import UIA
from scriptHandler import script
from utils.security import isRunningOnSecureDesktop
from winAPI.sessionTracking import isLockScreenModeActive

from .context import is_search_menu, is_server_search, qml_type


class ContextLabel(UIA):
    def _get_name(self):
        native_name = super()._get_name()
        if native_name:
            return native_name
        try:
            parent = self.parent
            if parent is None or not isinstance(parent, UIA):
                return native_name
            if parent.UIAElement.currentClassName != "QQuickControl":
                return native_name
            controls = []
            child = parent.firstChild
            # A bounded walk also prevents a broken provider from looping forever.
            for _ in range(64):
                if child is None:
                    break
                if not isinstance(child, UIA):
                    return native_name
                element = child.UIAElement
                controls.append((element.currentClassName, element.currentName, child.location))
                child = child.next
            else:
                return native_name
            kind = qml_type(self.UIAElement.currentClassName)
            if kind == "TextField" and is_server_search([(c, n) for c, n, _ in controls]):
                return "Поиск серверов"
            if kind == "ImageButton" and is_search_menu(self.location, controls):
                return "Меню списка серверов"
        except (COMError, RuntimeError):
            # Closing a Qt window can invalidate its accessibility objects.
            log.debugWarning("Happ search context became unavailable")
        return native_name


class AppModule(appModuleHandler.AppModule):
    _clickTimer = None
    _terminated = False
    _panelMenu = None

    def terminate(self):
        self._terminated = True
        if self._panelMenu is not None:
            self._panelMenu.cancel()
        if self._clickTimer is not None:
            self._clickTimer.Stop()
            self._clickTimer = None
        super().terminate()

    def _clickNavigation(self, button, foreground, retries=40):
        self._clickTimer = None
        try:
            if (self._terminated or isRunningOnSecureDesktop() or isLockScreenModeActive()
                    or api.getForegroundObject() != foreground):
                return
            held = any(winUser.getAsyncKeyState(key) & 0x8000
                       for key in range(1, 256))
            if held:
                if retries:
                    self._clickTimer = core.callLater(50, self._clickNavigation, button, foreground, retries - 1)
                else:
                    ui.message("Отпустите клавиши и повторите команду")
                return
            rect = button.location
            if not rect or rect.width <= 0 or rect.height <= 0:
                ui.message("Не удалось определить границы кнопки панели")
                return
            point = (rect.left + rect.width // 2, rect.top + rect.height // 2)
            if (button.processID != self.processID
                    or qml_type(button.UIAElement.currentClassName) != "NavButton"
                    or button.states & {State.UNAVAILABLE, State.INVISIBLE, State.OFFSCREEN}
                    or NVDAObject.objectFromPoint(*point) != button):
                ui.message("Кнопка панели перекрыта или недоступна")
                return
            previous = winUser.getCursorPos()
            try:
                winUser.setCursorPos(*point)
                if (tuple(winUser.getCursorPos()) != point
                        or isRunningOnSecureDesktop() or isLockScreenModeActive()
                        or api.getForegroundObject() != foreground
                        or NVDAObject.objectFromPoint(*point) != button):
                    return
                try:
                    mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTDOWN, 0, 0)
                finally:
                    mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTUP, 0, 0)
                ui.message("Щелчок по кнопке панели отправлен")
            finally:
                if tuple(winUser.getCursorPos()) == point:
                    winUser.setCursorPos(*previous)
        except (COMError, RuntimeError, OSError):
            log.debugWarning("Happ navigation click failed", exc_info=True)
            ui.message("Не удалось нажать кнопку панели")

    @script(
        description="Раскрыть панель или выбрать распознанный раздел Happ",
        category="Happ",
        gesture="kb:NVDA+alt+n",
    )
    def script_navigation(self, gesture):
        if self._panelMenu is not None:
            self._panelMenu.cancel()
            self._panelMenu = None
        if self._clickTimer is not None:
            self._clickTimer.Stop()
            self._clickTimer = None
        if isRunningOnSecureDesktop() or isLockScreenModeActive():
            return
        try:
            foreground = api.getForegroundObject()
            if foreground.processID != self.processID:
                return
            if not isinstance(foreground, UIA):
                ui.message("Панель навигации Happ недоступна")
                return
            if qml_type(foreground.UIAElement.currentClassName) != "Main":
                ui.message("Сначала закройте диалог Happ")
                return
            pending = [(foreground, 0)]
            buttons = []
            visited = 0
            while pending and visited < 80:
                obj, depth = pending.pop()
                visited += 1
                if not isinstance(obj, UIA) or obj.processID != self.processID:
                    continue
                if qml_type(obj.UIAElement.currentClassName) == "NavButton":
                    buttons.append(obj)
                if depth < 2:
                    child = obj.firstChild
                    for _ in range(64):
                        if child is None:
                            break
                        pending.append((child, depth + 1))
                        child = child.next
                    else:
                        ui.message("Не удалось однозначно найти панель навигации")
                        return
            if not pending and len(buttons) == 6:
                from .panel import PanelMenu
                self._panelMenu = PanelMenu(self)
                self._panelMenu.start(foreground, buttons)
                return
            if pending or len(buttons) != 1:
                ui.message("Не удалось однозначно найти панель навигации")
                return
            button = buttons[0]
            if button.states & {State.UNAVAILABLE, State.INVISIBLE, State.OFFSCREEN}:
                ui.message("Панель навигации Happ недоступна")
                return
            if (isRunningOnSecureDesktop() or isLockScreenModeActive()
                    or api.getForegroundObject() != foreground):
                return
            self._clickTimer = core.callLater(50, self._clickNavigation, button, foreground)
        except (COMError, RuntimeError):
            log.debugWarning("Happ navigation provider became unavailable")
            ui.message("Не удалось открыть панель навигации Happ")

    def chooseNVDAObjectOverlayClasses(self, obj, clsList):
        if not isinstance(obj, UIA) or obj.role not in (Role.EDITABLETEXT, Role.BUTTON):
            return
        try:
            kind = qml_type(obj.UIAElement.currentClassName)
            if (kind, obj.role) in (("TextField", Role.EDITABLETEXT), ("ImageButton", Role.BUTTON)):
                clsList.insert(0, ContextLabel)
        except COMError:
            log.debugWarning("Happ control became unavailable during classification")
