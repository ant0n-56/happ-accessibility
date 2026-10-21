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
from controlTypes import State
from logHandler import log
from NVDAObjects import NVDAObject
from NVDAObjects.UIA import UIA

from .context import is_server_search, qml_type
from .panel import PanelMenu
from .serverLabels import match_servers


def find_rows(foreground):
    candidates = []
    child = foreground.firstChild
    for index in range(8):
        if child is None:
            break
        if (isinstance(child, UIA) and child.processID == foreground.processID
                and qml_type(child.UIAElement.currentClassName) == "QQuickControl"):
            candidates.append(child)
        child = child.next
    if child is not None or len(candidates) != 1:
        return []
    container = candidates[0]
    records = []
    rows = []
    child = container.firstChild
    for index in range(128):
        if child is None:
            break
        if not isinstance(child, UIA) or child.processID != foreground.processID:
            return []
        kind = qml_type(child.UIAElement.currentClassName)
        records.append((kind, child.UIAElement.currentName))
        if kind == "ServerItem" and child.firstChild is None:
            rows.append(child)
        child = child.next
    if child is not None or not is_server_search(records):
        return []
    window = foreground.location
    if window is None:
        return []
    visible = []
    for row in rows:
        rect = row.location
        if (rect and rect.width > 2 * rect.height > 0
                and not row.states & {State.INVISIBLE, State.OFFSCREEN, State.UNAVAILABLE}
                and window.left <= rect.left and rect.left + rect.width <= window.left + window.width
                and window.top <= rect.top and rect.top + rect.height <= window.top + window.height):
            visible.append(row)
    visible.sort(key=lambda row: row.location.top)
    if any(before.location.top + before.location.height > after.location.top
           or before.location.left != after.location.left
           or before.location.width != after.location.width for before, after in zip(visible, visible[1:])):
        return []
    return visible


class ServerMenu(PanelMenu):
    def start(self, foreground):
        self.foreground = foreground
        self.selection = None
        self.actionTimer = None
        self.rows = find_rows(foreground)
        if not self.rows:
            ui.message("Откройте раздел Серверы и разверните подписку. Видимые строки серверов не найдены")
            return
        self.rectangles = [row.location for row in self.rows]
        self.capture()

    def cancel(self):
        super().cancel()
        if getattr(self, "actionTimer", None) is not None:
            self.actionTimer.Stop()
            self.actionTimer = None

    def unchanged(self):
        return (self.safe() and api.getForegroundObject() == self.foreground
                and self.foreground.processID == self.owner.processID
                and find_rows(self.foreground) == self.rows
                and [row.location for row in self.rows] == self.rectangles
                and all(NVDAObject.objectFromPoint(rect.left + rect.width // 2,
                                                  rect.top + rect.height // 2) == row
                        for row, rect in zip(self.rows, self.rectangles)))

    def capture(self):
        self.actionTimer = None
        try:
            if not self.unchanged():
                self.cancel()
                ui.message("Список серверов изменился или перекрыт. Повторите команду")
                return
            left = min(rect.left for rect in self.rectangles)
            right = min(left + 800, max(rect.left + rect.width for rect in self.rectangles))
            top = self.rectangles[0].top
            bottom = self.rectangles[-1].top + self.rectangles[-1].height
            if not (20 <= right - left <= 800 and 20 <= bottom - top <= 1200):
                self.cancel()
                ui.message("Область серверов слишком велика для чтения")
                return
            available = getLanguages()
            language = next((value for value in available if value.lower().startswith("ru")), None)
            if language is None:
                self.cancel()
                ui.message("Для чтения серверов нужен русский язык распознавания Windows")
                return
            self.info = RecogImageInfo(left, top, right - left, bottom - top, 2)
            bitmap = screenBitmap.ScreenBitmap(self.info.recogWidth, self.info.recogHeight)
            self.pixels = bitmap.captureImage(left, top, right - left, bottom - top)
            if not self.unchanged():
                self.cancel()
                return
            self.recognizer = UwpOcr(language)
            self.secondaryLanguage = next((value for value in available if value.lower().startswith("en")), None)
            self.firstEntries = None
            self.timeout = core.callLater(5000, self.expire)
            self.recognizer.recognize(self.pixels, self.info, self.receive)
        except (COMError, RuntimeError, OSError, ValueError, LookupError):
            self.cancel()
            log.debugWarning("Happ server recognition unavailable")
            ui.message("Не удалось прочитать список серверов")

    def expire(self):
        announce = self.safe() and api.getForegroundObject() == self.foreground
        self.cancel()
        if announce:
            ui.message("Время чтения серверов истекло")

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
                ui.message("Не удалось распознать серверы")
                return
            entries = match_servers(result.data, self.info, self.rectangles)
            if self.secondaryLanguage is not None:
                self.firstEntries = entries
                language = self.secondaryLanguage
                self.secondaryLanguage = None
                self.recognizer = UwpOcr(language)
                self.timeout = core.callLater(5000, self.expire)
                self.recognizer.recognize(self.pixels, self.info, self.receive)
                return
            if self.firstEntries is not None:
                combined = dict(entries)
                combined.update(self.firstEntries)
                entries = sorted(combined.items())
            self.present(entries)
        except (COMError, RuntimeError, OSError, ValueError, LookupError):
            self.cancel()
            log.debugWarning("Happ server recognition result unavailable")
            ui.message("Не удалось распознать серверы")

    def present(self, entries):
        try:
            if not self.unchanged():
                self.cancel()
                return
            if self.selection is not None:
                selected = self.selection
                if entries.count(selected) != 1:
                    self.cancel()
                    ui.message("Название сервера изменилось. Выбор отменён")
                    return
                self.activate()
                return
            if not entries:
                self.cancel()
                ui.message("Названия видимых серверов не распознаны")
                return
            selected = None
            gui.mainFrame.prePopup()
            try:
                self.dialog = wx.SingleChoiceDialog(
                    gui.mainFrame,
                    "Стрелки — выбрать строку, Enter — активировать её в Happ. "
                    "Это может изменить подключение. Escape — отмена. "
                    "Показаны только распознанные видимые серверы; названия могут содержать ошибки OCR.",
                    "Серверы Happ", [f"{index + 1}. {label}" for index, label in entries],
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
            self.actionTimer = core.callLater(200, self.capture)
        except (COMError, RuntimeError, OSError, NotImplementedError):
            self.cancel()
            log.debugWarning("Happ server action unavailable")
            ui.message("Не удалось подтвердить выбор сервера. Повторное нажатие не отправлено")

    def activate(self, retries=40):
        self.actionTimer = None
        try:
            if not self.unchanged() or self.selection is None:
                self.cancel()
                return
            if any(winUser.getAsyncKeyState(key) & 0x8000 for key in range(1, 256)):
                if retries:
                    self.actionTimer = core.callLater(50, self.activate, retries - 1)
                else:
                    self.cancel()
                    ui.message("Отпустите клавиши и повторите команду")
                return
            rect = self.rectangles[self.selection[0]]
            target = self.rows[self.selection[0]]
            point = (rect.left + rect.width // 2, rect.top + rect.height // 2)
            previous = winUser.getCursorPos()
            try:
                winUser.setCursorPos(*point)
                if (not self.unchanged() or tuple(winUser.getCursorPos()) != point
                        or NVDAObject.objectFromPoint(*point) != target):
                    return
                self.selection = None
                try:
                    mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTDOWN, 0, 0)
                finally:
                    mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTUP, 0, 0)
                ui.message("Нажатие строки сервера отправлено. Проверьте результат в Happ")
            finally:
                if tuple(winUser.getCursorPos()) == point:
                    winUser.setCursorPos(*previous)
                self.cancel()
        except (COMError, RuntimeError, OSError):
            self.cancel()
            log.debugWarning("Happ server row click failed")
            ui.message("Не удалось подтвердить выбор сервера. Повторное нажатие не отправлено")
