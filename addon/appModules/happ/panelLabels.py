LABELS = {label.casefold(): label for label in (
    "Добавить", "Серверы", "Настройки", "Статистика", "Логи",
)}


def match_labels(lines, image_info, rectangles):
    matches = {}
    used = set()
    for line in lines:
        for word in line:
            label = LABELS.get(str(word["text"]).strip().casefold())
            if label is None:
                continue
            left = image_info.convertXToScreen(word["x"])
            top = image_info.convertYToScreen(word["y"])
            right = left + image_info.convertWidthToScreen(word["width"])
            bottom = top + image_info.convertHeightToScreen(word["height"])
            targets = [index for index, rect in enumerate(rectangles)
                       if rect.left <= left < right <= rect.left + rect.width
                       and rect.top <= top < bottom <= rect.top + rect.height]
            if len(targets) != 1:
                continue
            index = targets[0]
            if index in matches or label in used:
                return []
            matches[index] = label
            used.add(label)
    return sorted(matches.items(), key=lambda item: rectangles[item[0]].top)
