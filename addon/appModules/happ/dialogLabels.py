def dialog_label(lines, info, popup, target, kind):
    rows = []
    for line in lines:
        if not line or any(word["width"] <= 0 or word["height"] <= 0 for word in line):
            continue
        words = sorted(line, key=lambda word: word["x"])
        left = min(info.convertXToScreen(word["x"]) for word in words)
        top = min(info.convertYToScreen(word["y"]) for word in words)
        right = max(info.convertXToScreen(word["x"]) + info.convertWidthToScreen(word["width"]) for word in words)
        bottom = max(info.convertYToScreen(word["y"]) + info.convertHeightToScreen(word["height"]) for word in words)
        if not (popup.left <= left < right <= popup.left + popup.width
                and popup.top <= top < bottom <= popup.top + popup.height):
            continue
        text = " ".join(word["text"].strip() for word in words).strip().rstrip(":")
        rows.append((text, left, top, right, bottom))
    titles = [row for row in rows if row[0] == "Добавить конфигурацию"
              and row[2] < popup.top + popup.height / 4 and row[1] < popup.left + popup.width / 4]
    if len(titles) != 1:
        return None
    title = titles[0]
    if kind == "ImageButton":
        if (0 < target.width <= 60 and 0 < target.height <= 60
                and target.left >= popup.left + popup.width * 0.8
                and target.top <= (title[2] + title[4]) / 2 <= target.top + target.height):
            return "Закрыть диалог добавления"
        return None
    allowed = {"ComboBox": {"Тип": "Тип конфигурации"},
               "TextField": {"Имя подписки": "Имя подписки", "URL подписки": "URL подписки",
                             "lJRL подписки": "URL подписки"},
               "Switch": {text: text for text in ("Скрыть настройки сервера", "Зашифрованная подписка",
                                                  "Разрешить небезопасное подключение")}}.get(kind, {})
    matches = []
    for text, left, top, right, bottom in rows:
        if text not in allowed:
            continue
        if kind == "Switch":
            aligned = (right <= target.left and target.top <= (top + bottom) / 2 <= target.top + target.height)
        else:
            aligned = (abs(left - target.left) <= target.height
                       and right <= target.left + target.width
                       and 0 <= target.top - bottom <= target.height)
        if aligned:
            matches.append(allowed[text])
    return matches[0] if len(matches) == 1 else None
