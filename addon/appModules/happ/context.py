"""Conservative recognition of the Happ server-search context."""

import re


def setting_label_from_pane(lines, info, target_rect):
    candidates = []
    for line in lines:
        if not line:
            continue
        words = sorted(line, key=lambda word: word["x"])
        if any(word["width"] <= 0 or word["height"] <= 0
               or word["x"] < 0 or word["y"] < 0
               or word["x"] + word["width"] > info.recogWidth
               or word["y"] + word["height"] > info.recogHeight for word in words):
            continue
        top = min(info.convertYToScreen(word["y"]) for word in words)
        bottom = max(info.convertYToScreen(word["y"]) + info.convertHeightToScreen(word["height"]) for word in words)
        center = (top + bottom) / 2
        if not target_rect.top <= center <= target_rect.top + target_rect.height:
            continue
        if any(info.convertXToScreen(word["x"]) + info.convertWidthToScreen(word["width"]) > target_rect.left
               for word in words):
            continue
        text = " ".join(word["text"].strip() for word in words).strip().rstrip(":")
        if (text and len(text) <= 100 and any(character.isalpha() for character in text)
                and not any(ord(character) < 32 for character in text)):
            candidates.append(text)
    return candidates[0] if len(candidates) == 1 else None


def interface_setting_label(target_rect, controls):
    if len(controls) != 2 or target_rect is None:
        return None
    if any(qml_type(kind) != "ComboBox" or rect is None for kind, name, rect in controls):
        return None
    by_name = {name: rect for kind, name, rect in controls}
    if set(by_name) != {"Русский", "Системная"}:
        return None
    language = by_name["Русский"]
    theme = by_name["Системная"]
    left, top, width, height = language
    theme_left, theme_top, theme_width, theme_height = theme
    if (width <= 0 or height <= 0 or theme_height <= 0
            or left != theme_left or width != theme_width
            or not top + height <= theme_top <= top + 3 * height):
        return None
    if target_rect == language:
        return "Язык"
    if target_rect == theme:
        return "Тема"
    return None


def qml_type(class_name):
    """Remove runtime-generated Qt suffixes, not arbitrary class-name text."""
    return re.sub(r"_QMLTYPE_\d+(?:_QML_\d+)?$", "", class_name or "")


def is_server_search(classes_and_names):
    """Require the observed server page signature and one search field.

    Duplicate UIA automation IDs and numeric QML suffixes are not identities.
    Unknown layouts deliberately receive no inferred label.
    """
    controls = [(qml_type(cls), name or "") for cls, name in classes_and_names]
    return (
        sum(cls == "TextField" for cls, _ in controls) == 1
        and any(cls == "Button" and name == "Тест пинга" for cls, name in controls)
        and {name for cls, name in controls if cls == "ToogleButton"}
        >= {"TUN", "Прокси"}
    )


def is_search_menu(target_rect, controls):
    return search_toolbar_label(target_rect, controls) == "Меню списка серверов"


def search_toolbar_label(target_rect, controls):
    """Identify the observed menu beside search without absolute coordinates.

    Qt gives both toolbar icons the same ID. Accept only the verified layout:
    one search field and exactly two small icons directly to its right.
    Each record is (class name, native name, (left, top, width, height)).
    """
    if not is_server_search([(cls, name) for cls, name, _ in controls]):
        return None
    search = next(rect for cls, _, rect in controls if qml_type(cls) == "TextField")
    if search is None or target_rect is None:
        return None
    left, top, width, height = search
    if width <= 0 or height <= 0:
        return None
    icons = []
    for cls, name, rect in controls:
        if qml_type(cls) != "ImageButton" or name or rect is None:
            continue
        x, y, w, h = rect
        if (0 < w <= height and 0 < h <= height
                and left + width <= x <= left + width + 3 * height
                and top <= y and y + h <= top + height):
            icons.append(rect)
    if len(icons) != 2 or icons[0][0] == icons[1][0]:
        return None
    first, last = sorted(icons, key=lambda rect: rect[0])
    if first[0] + first[2] > last[0]:
        return None
    if target_rect == last:
        return "Меню списка серверов"
    if target_rect == first:
        return "Пинг списка серверов"
    return None


def is_subscription_link(target_rect, parent_rect, controls):
    if target_rect is None or parent_rect is None or len(controls) != 2:
        return False
    icons = [rect for kind, name, rect in controls if qml_type(kind) == "ImageButton" and not name]
    bars = [rect for kind, name, rect in controls if qml_type(kind) == "ProgressBar"]
    if icons != [target_rect] or len(bars) != 1 or bars[0] is None:
        return False
    left, top, width, height = target_rect
    parent_left, parent_top, parent_width, parent_height = parent_rect
    bar_left, bar_top, bar_width, bar_height = bars[0]
    return (0 < width <= parent_height and 0 < height <= parent_height
            and 0 < bar_width and 0 < bar_height <= parent_height
            and parent_left <= bar_left < bar_left + bar_width <= left
            and left + width <= parent_left + parent_width
            and left >= parent_left + parent_width * 0.85
            and parent_top <= top <= bar_top + bar_height / 2 <= top + height <= parent_top + parent_height
            and parent_top <= bar_top < bar_top + bar_height <= parent_top + parent_height)


def is_subscription_info(parent_rect, controls):
    if parent_rect is None:
        return False
    if len(controls) == 2:
        icons = [rect for kind, name, rect in controls if qml_type(kind) == "ImageButton"]
        return len(icons) == 1 and is_subscription_link(icons[0], parent_rect, controls)
    if len(controls) != 1:
        return False
    kind, name, rect = controls[0]
    if qml_type(kind) != "ProgressBar" or rect is None:
        return False
    left, top, width, height = parent_rect
    bar_left, bar_top, bar_width, bar_height = rect
    return (width > 0 and height > 0 and width / 2 <= bar_width <= width
            and 0 < bar_height <= height
            and left <= bar_left < bar_left + bar_width <= left + width
            and top <= bar_top < bar_top + bar_height <= top + height)


def subscription_header_label(target_rect, controls, rows):
    if target_rect is None or not is_server_search([(kind, name) for kind, name, rect in controls]):
        return None
    left, top, width, height = target_rect
    if width <= 0 or height <= 0:
        return None
    search = next(rect for kind, name, rect in controls if qml_type(kind) == "TextField")
    if search is None or top < search[1] + search[3]:
        return None
    icons = sorted([rect for kind, name, rect in controls
                    if qml_type(kind) == "ImageButton" and not name and rect is not None
                    and rect[1:] == (top, width, height)], key=lambda rect: rect[0])
    if len(icons) != 3 or target_rect not in icons:
        return None
    if any(not 0 <= after[0] - before[0] - width <= width
           for before, after in zip(icons, icons[1:])):
        return None
    anchors = [row for row in rows if row is not None
               and row[2] > 0 and row[3] > 0 and row[0] <= icons[0][0]
               and 0 <= row[1] - top - height <= 2 * height
               and 0 <= row[0] + row[2] - icons[-1][0] - width <= width]
    if len(anchors) != 1:
        return None
    return ("Обновить подписку", "Пинг подписки", "Меню подписки")[icons.index(target_rect)]
