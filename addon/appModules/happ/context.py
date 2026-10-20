"""Conservative recognition of the Happ server-search context."""

import re


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
    """Identify the observed menu beside search without absolute coordinates.

    Qt gives both toolbar icons the same ID. Accept only the verified layout:
    one search field and exactly two small icons directly to its right.
    Each record is (class name, native name, (left, top, width, height)).
    """
    if not is_server_search([(cls, name) for cls, name, _ in controls]):
        return False
    search = next(rect for cls, _, rect in controls if qml_type(cls) == "TextField")
    if search is None or target_rect is None:
        return False
    left, top, width, height = search
    if width <= 0 or height <= 0:
        return False
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
        return False
    first, last = sorted(icons, key=lambda rect: rect[0])
    return first[0] + first[2] <= last[0] and target_rect == last
