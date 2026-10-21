GROUP_LABELS = {label.casefold(): label for label in (
    "Настройки интерфейса", "Правила маршрутизации", "Дополнительные настройки",
    "Подписки", "Пинг",
)}


def match_settings_back(lines, info, viewport, window):
    matches = []
    for line in lines:
        words = sorted(line, key=lambda word: word["x"])
        if len(words) < 3 or words[0]["text"].strip().casefold() != "настройки":
            continue
        if words[1]["text"].strip() not in (">", "›"):
            continue
        suffix = " ".join(word["text"].strip() for word in words[2:]).casefold()
        if suffix not in GROUP_LABELS:
            continue
        if any(word["width"] <= 0 or word["height"] <= 0 for word in words):
            continue
        left = info.convertXToScreen(words[0]["x"])
        top = min(info.convertYToScreen(word["y"]) for word in words)
        right = max(info.convertXToScreen(word["x"]) + info.convertWidthToScreen(word["width"]) for word in words)
        bottom = max(info.convertYToScreen(word["y"]) + info.convertHeightToScreen(word["height"]) for word in words)
        if not (max(window.left, viewport.left) <= left < right <= min(window.left + window.width, viewport.left + viewport.width)
                and window.top <= top < bottom <= viewport.top
                and left - viewport.left <= 100):
            continue
        first = words[0]
        bounds = (left, info.convertYToScreen(first["y"]),
                  left + info.convertWidthToScreen(first["width"]),
                  info.convertYToScreen(first["y"]) + info.convertHeightToScreen(first["height"]))
        matches.append((-1, "Назад к настройкам", bounds))
    return matches if len(matches) == 1 else []


def match_groups(lines, info, rectangles, viewport):
    matches = []
    seen = set()
    for line in lines:
        if not line:
            continue
        words = sorted(line, key=lambda word: word["x"])
        label = GROUP_LABELS.get(" ".join(word["text"].strip() for word in words).casefold())
        if label is None:
            continue
        left = min(info.convertXToScreen(word["x"]) for word in words)
        top = min(info.convertYToScreen(word["y"]) for word in words)
        right = max(info.convertXToScreen(word["x"]) + info.convertWidthToScreen(word["width"]) for word in words)
        bottom = max(info.convertYToScreen(word["y"]) + info.convertHeightToScreen(word["height"]) for word in words)
        if not (viewport.left <= left < right <= viewport.left + viewport.width
                and viewport.top <= top < bottom <= viewport.top + viewport.height):
            continue
        targets = [index for index, rect in enumerate(rectangles)
                   if rect.left <= left < right <= rect.left + rect.width / 2
                   and left - rect.left <= max(60, 4 * (bottom - top))
                   and rect.top <= top < bottom <= rect.top + rect.height]
        if len(targets) != 1:
            continue
        if label in seen:
            return []
        seen.add(label)
        matches.append((targets[0], label, (left, top, right, bottom)))
    return sorted(matches, key=lambda entry: entry[2][1])
