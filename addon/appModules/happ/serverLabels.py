def match_servers(lines, info, rectangles):
    matches = []
    for index, rect in enumerate(rectangles):
        candidates = []
        for line in lines:
            line = [word for word in line
                    if info.convertXToScreen(word["x"]) + info.convertWidthToScreen(word["width"])
                    > rect.left + rect.height * 0.75]
            if not line or any(word["width"] <= 0 or word["height"] <= 0
                               or word["x"] < 0 or word["y"] < 0
                               or word["x"] + word["width"] >= info.recogWidth - 2
                               or word["y"] + word["height"] > info.recogHeight for word in line):
                continue
            words = sorted(line, key=lambda word: word["x"])
            left = min(info.convertXToScreen(word["x"]) for word in words)
            right = max(info.convertXToScreen(word["x"]) + info.convertWidthToScreen(word["width"])
                        for word in words)
            top = min(info.convertYToScreen(word["y"]) for word in words)
            bottom = max(info.convertYToScreen(word["y"]) + info.convertHeightToScreen(word["height"])
                         for word in words)
            if not (rect.left + rect.height * 0.75 <= left <= rect.left + 2 * rect.height
                    and left < right <= rect.left + rect.width - rect.height / 2
                    and rect.top <= top < bottom <= rect.top + rect.height * 0.65):
                continue
            label = " ".join(word["text"].strip() for word in words).strip()
            if (label and len(label) <= 160 and any(character.isalpha() for character in label)
                    and not any(ord(character) < 32 for character in label)):
                candidates.append(label)
        if len(candidates) == 1:
            matches.append((index, candidates[0]))
    return matches
