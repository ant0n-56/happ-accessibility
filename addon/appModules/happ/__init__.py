"""Happ accessibility corrections. Copyright 2026 Anton Chigarev."""

import appModuleHandler
import api
import ui
import core
import mouseHandler
import winUser
from time import monotonic
from NVDAObjects import NVDAObject
from comtypes import COMError
from controlTypes import Role, State
from logHandler import log
from NVDAObjects.UIA import UIA
from scriptHandler import script
from utils.security import isRunningOnSecureDesktop
from winAPI.sessionTracking import isLockScreenModeActive

from .context import interface_setting_label, is_subscription_link, search_toolbar_label, is_server_search, qml_type


class SettingsRowLabel(UIA):
    def _get_name(self):
        native_name = super()._get_name()
        saved = getattr(self, "_happRowLabel", None)
        if (saved and not isRunningOnSecureDesktop() and not isLockScreenModeActive()
                and api.getFocusObject() == self and self.location == saved[1]):
            return f"{saved[0]}: {native_name}" if native_name else saved[0]
        return native_name


class InterfaceSettingLabel(SettingsRowLabel):
    def _get_name(self):
        native_name = super()._get_name()
        try:
            parent = self.parent
            if not isinstance(parent, UIA) or qml_type(parent.UIAElement.currentClassName) != "SettingsPane":
                return native_name
            controls = []
            child = parent.firstChild
            for index in range(3):
                if child is None:
                    break
                if not isinstance(child, UIA):
                    return native_name
                element = child.UIAElement
                controls.append((element.currentClassName, element.currentName, child.location))
                child = child.next
            if child is not None:
                return native_name
            label = interface_setting_label(self.location, controls)
            if label and native_name:
                return f"{label}: {native_name}"
        except (COMError, RuntimeError):
            log.debugWarning("Happ interface setting context unavailable")
        return native_name


class ContextLabel(SettingsRowLabel):
    def _get_name(self):
        native_name = super()._get_name()
        if native_name:
            return native_name
        try:
            parent = self.parent
            if parent is None or not isinstance(parent, UIA):
                return native_name
            parent_kind = qml_type(parent.UIAElement.currentClassName)
            if parent_kind not in ("QQuickControl", "ServerItem"):
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
            if parent_kind == "ServerItem":
                if kind != "ImageButton" or not is_subscription_link(self.location, parent.location, controls):
                    return native_name
                container = parent.parent
                if not isinstance(container, UIA) or container.UIAElement.currentClassName != "QQuickControl":
                    return native_name
                siblings = []
                child = container.firstChild
                for index in range(64):
                    if child is None:
                        break
                    if not isinstance(child, UIA):
                        return native_name
                    siblings.append((child.UIAElement.currentClassName, child.UIAElement.currentName))
                    child = child.next
                if child is None and is_server_search(siblings):
                    return "Ссылка подписки"
                return native_name
            if kind == "TextField" and is_server_search([(c, n) for c, n, _ in controls]):
                return "Поиск серверов"
            if kind == "ImageButton":
                return search_toolbar_label(self.location, controls) or native_name
        except (COMError, RuntimeError):
            # Closing a Qt window can invalidate its accessibility objects.
            log.debugWarning("Happ search context became unavailable")
        return native_name


class AppModule(appModuleHandler.AppModule):
    _settingsTab = None
    _tabTimer = None
    _groupsMenu = None
    _settingReader = None
    _clickTimer = None
    _terminated = False
    _panelMenu = None

    def terminate(self):
        self._terminated = True
        self._settingsTab = None
        if self._tabTimer is not None:
            self._tabTimer.Stop()
            self._tabTimer = None
        if self._groupsMenu is not None:
            self._groupsMenu.cancel()
        if self._settingReader is not None:
            self._settingReader.cancel()
        if self._panelMenu is not None:
            self._panelMenu.cancel()
        if self._clickTimer is not None:
            self._clickTimer.Stop()
            self._clickTimer = None
        super().terminate()

    def event_gainFocus(self, obj, nextHandler):
        if self._settingReader is not None:
            self._settingReader.cancel()
            self._settingReader = None
        if isinstance(obj, SettingsRowLabel):
            obj._happRowLabel = None
        if self._continueSettingsTab(obj):
            return
        nextHandler()
        if self._terminated or isRunningOnSecureDesktop() or isLockScreenModeActive():
            return
        try:
            if not isinstance(obj, SettingsRowLabel) or obj.processID != self.processID:
                return
            parent = obj.parent
            if not isinstance(parent, UIA):
                return
            parent_kind = qml_type(parent.UIAElement.currentClassName)
            popup = parent if parent_kind == "QQuickPopupItem" else parent.parent if parent_kind == "StackView" else None
            if (isinstance(popup, UIA) and qml_type(popup.UIAElement.currentClassName) == "QQuickPopupItem"
                    and qml_type(obj.UIAElement.currentClassName) in ("TextField", "ComboBox", "Switch", "ImageButton")):
                from .dialog import DialogReader
                self._settingReader = DialogReader(self, obj, popup)
                self._settingReader.timer = core.callLater(250, self._settingReader.start)
                return
            menu = (parent_kind == "StackView"
                    and qml_type(obj.UIAElement.currentClassName) == "ImageButton")
            if parent_kind != "SettingsPane" and not menu:
                return
            if obj.name and obj.name != (obj.UIAElement.currentName or ""):
                return
            from .settings import SettingReader
            self._settingReader = SettingReader(self, obj)
            self._settingReader.timer = core.callLater(250, self._settingReader.start)
        except (COMError, RuntimeError):
            log.debugWarning("Happ focused setting unavailable")

    @script(description="Перейти по Tab, пропуская перекрытые поля настроек Happ",
            category="Happ", gestures=["kb:tab", "kb:shift+tab"])
    def script_settingsTab(self, gesture):
        if self._tabTimer is not None:
            self._tabTimer.Stop()
            self._tabTimer = None
        self._settingsTab = None
        if not self._terminated and not isRunningOnSecureDesktop() and not isLockScreenModeActive():
            try:
                obj = api.getFocusObject()
                if (isinstance(obj, SettingsRowLabel) and obj.processID == self.processID
                        and isinstance(obj.parent, UIA)
                        and qml_type(obj.parent.UIAElement.currentClassName) == "SettingsPane"):
                    foreground = api.getForegroundObject()
                    if foreground.processID == self.processID:
                        self._settingsTab = (gesture, foreground, monotonic() + 2, 24)
            except (COMError, RuntimeError):
                log.debugWarning("Happ Tab context unavailable")
        gesture.send()

    def _continueSettingsTab(self, obj):
        pending = self._settingsTab
        self._settingsTab = None
        if pending is None or not isinstance(obj, SettingsRowLabel):
            return False
        gesture, foreground, deadline, remaining = pending
        try:
            if (self._terminated or isRunningOnSecureDesktop() or isLockScreenModeActive()
                    or monotonic() > deadline or not remaining
                    or api.getForegroundObject() != foreground or api.getFocusObject() != obj):
                return False
            rect = obj.location
            if not rect or rect.width <= 0 or rect.height <= 0:
                return False
            from .settings import is_covered_setting
            hit = NVDAObject.objectFromPoint(rect.left + rect.width // 2, rect.top + rect.height // 2)
            if not is_covered_setting(obj, hit):
                return False
            self._settingsTab = (gesture, foreground, deadline, remaining - 1)
            self._tabTimer = core.callLater(30, self._skipHiddenSetting, obj, self._settingsTab)
            return True
        except (COMError, RuntimeError):
            log.debugWarning("Happ Tab target unavailable")
            return False

    def _skipHiddenSetting(self, obj, pending):
        self._tabTimer = None
        if self._settingsTab is not pending:
            return
        gesture, foreground, deadline, remaining = pending
        try:
            if (self._terminated or isRunningOnSecureDesktop() or isLockScreenModeActive()
                    or monotonic() > deadline or api.getForegroundObject() != foreground
                    or api.getFocusObject() != obj):
                self._settingsTab = None
                return
            gesture.send()
        except (COMError, RuntimeError):
            self._settingsTab = None
            log.debugWarning("Happ Tab continuation unavailable")

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
        if self._groupsMenu is not None:
            self._groupsMenu.cancel()
            self._groupsMenu = None
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

    @script(description="Выбрать видимый заголовок группы настроек Happ", category="Happ")
    def script_settingsGroups(self, gesture):
        if self._groupsMenu is not None:
            self._groupsMenu.cancel()
            self._groupsMenu = None
        if self._panelMenu is not None:
            self._panelMenu.cancel()
            self._panelMenu = None
        if self._clickTimer is not None:
            self._clickTimer.Stop()
            self._clickTimer = None
        if self._terminated or isRunningOnSecureDesktop() or isLockScreenModeActive():
            return
        try:
            foreground = api.getForegroundObject()
            if (not isinstance(foreground, UIA) or foreground.processID != self.processID
                    or qml_type(foreground.UIAElement.currentClassName) != "Main"):
                return
            pending = [(foreground, 0)]
            groups = []
            visited = 0
            while pending and visited < 160:
                obj, depth = pending.pop()
                visited += 1
                if not isinstance(obj, UIA) or obj.processID != self.processID:
                    continue
                if qml_type(obj.UIAElement.currentClassName) == "SettingsPane":
                    groups.append(obj)
                    continue
                if depth < 3:
                    child = obj.firstChild
                    for index in range(64):
                        if child is None:
                            break
                        pending.append((child, depth + 1))
                        child = child.next
                    else:
                        ui.message("Структура настроек неоднозначна")
                        return
            if pending or not groups:
                ui.message("Откройте главную страницу настроек Happ")
                return
            viewport = groups[0].parent
            if (not isinstance(viewport, UIA) or qml_type(viewport.UIAElement.currentClassName) != "StackView"
                    or any(group.parent != viewport for group in groups)):
                ui.message("Не удалось определить область настроек")
                return
            from .settingsGroups import SettingsGroups
            self._groupsMenu = SettingsGroups(self)
            self._groupsMenu.start(foreground, viewport, groups)
        except (COMError, RuntimeError):
            log.debugWarning("Happ settings structure unavailable", exc_info=True)
            ui.message("Не удалось прочитать структуру настроек")

    def chooseNVDAObjectOverlayClasses(self, obj, clsList):
        if not isinstance(obj, UIA):
            return
        try:
            kind = qml_type(obj.UIAElement.currentClassName)
            if kind in ("Switch", "SpinBox"):
                clsList.insert(0, SettingsRowLabel)
                return
            if kind == "ComboBox" and obj.role == Role.COMBOBOX:
                clsList.insert(0, InterfaceSettingLabel)
                return
            if (kind, obj.role) in (("TextField", Role.EDITABLETEXT), ("ImageButton", Role.BUTTON)):
                clsList.insert(0, ContextLabel)
        except COMError:
            log.debugWarning("Happ control became unavailable during classification")
