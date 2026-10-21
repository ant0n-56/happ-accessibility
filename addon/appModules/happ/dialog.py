import core
import screenBitmap
import ui
from comtypes import COMError
from contentRecog import RecogImageInfo
from contentRecog.uwpOcr import UwpOcr, getLanguages
from logHandler import log
from NVDAObjects import NVDAObject

from .context import qml_type
from .dialogLabels import dialog_label
from .settings import SettingReader, belongs_to_control


class DialogReader(SettingReader):
    def __init__(self, owner, obj, popup):
        super().__init__(owner, obj)
        self.popup = popup
        self.popupRect = popup.location

    def safe(self):
        return (super().safe() and self.popup.location == self.popupRect
                and belongs_to_control(self.obj, self.popup))

    def start(self):
        self.timer = None
        try:
            if not self.safe() or not self.rect or not self.popupRect:
                return
            area = self.popupRect
            window = self.foreground.location
            if (not window or not 100 <= area.width <= 1200 or not 100 <= area.height <= 1200
                    or area.left < window.left or area.top < window.top
                    or area.left + area.width > window.left + window.width
                    or area.top + area.height > window.top + window.height):
                return
            rect = self.rect
            if (rect.width <= 0 or rect.height <= 0
                    or not belongs_to_control(NVDAObject.objectFromPoint(
                        rect.left + rect.width // 2, rect.top + rect.height // 2), self.obj)):
                return
            for horizontal in (0.1, 0.5, 0.9):
                for vertical in (0.1, 0.5, 0.9):
                    hit = NVDAObject.objectFromPoint(int(area.left + area.width * horizontal),
                                                    int(area.top + area.height * vertical))
                    if not belongs_to_control(hit, self.popup):
                        return
            language = next((value for value in getLanguages() if value.lower().startswith("ru")), None)
            if language is None:
                return
            self.info = RecogImageInfo(area.left, area.top, area.width, area.height, 2)
            bitmap = screenBitmap.ScreenBitmap(self.info.recogWidth, self.info.recogHeight)
            self.pixels = bitmap.captureImage(area.left, area.top, area.width, area.height)
            if not self.safe():
                return
            self.recognizer = UwpOcr(language)
            self.timer = core.callLater(5000, self.cancel)
            self.recognizer.recognize(self.pixels, self.info, self.receive)
        except (COMError, RuntimeError, OSError, ValueError, LookupError):
            self.cancel()
            log.debugWarning("Happ dialog recognition unavailable", exc_info=True)

    def finish(self, result):
        try:
            if not self.safe() or isinstance(result, Exception):
                return
            label = dialog_label(result.data, self.info, self.popupRect, self.rect,
                                 qml_type(self.obj.UIAElement.currentClassName))
            if label:
                self.obj._happRowLabel = (label, self.rect)
                native = self.obj.UIAElement.currentName
                ui.message(f"{label}: {native}" if native else label)
        except (COMError, RuntimeError):
            log.debugWarning("Happ dialog changed during recognition")
        finally:
            self.cancel()
