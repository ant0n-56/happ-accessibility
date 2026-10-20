"""Happ accessibility corrections. Copyright 2026 Anton Chigarev."""

import appModuleHandler
from comtypes import COMError
from controlTypes import Role
from logHandler import log
from NVDAObjects.UIA import UIA

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
    def chooseNVDAObjectOverlayClasses(self, obj, clsList):
        if not isinstance(obj, UIA) or obj.role not in (Role.EDITABLETEXT, Role.BUTTON):
            return
        try:
            kind = qml_type(obj.UIAElement.currentClassName)
            if (kind, obj.role) in (("TextField", Role.EDITABLETEXT), ("ImageButton", Role.BUTTON)):
                clsList.insert(0, ContextLabel)
        except COMError:
            log.debugWarning("Happ control became unavailable during classification")
