"""보상 선택 화면 (game/scene 패키지)"""

from PIL import Image

from .. import engine as E

from .base import (
    BOLD,
    FONT,
    ItemGetter,
    SMALL,
    SpriteGetter,
    TINY,
    W,
    _background,
    _canvas,
    _finish,
    _panel,
    _party_strip,
    _shrink,
    _text,
    _tw,
)

# ---------- 보상 화면 ----------
ICON_FALLBACK = {"fairy-feather": "pixie-plate", "linking-cord": "up-grade"}   # 그림이 없는 아이템


def item_icon(item: str) -> str:
    return ICON_FALLBACK.get(item, item)


def reward_icon(key: str) -> str:
    return item_icon(E.reward_info(key)["icon"])


def _wrap(s: str, width: int) -> list[str]:
    out, cur = [], ""
    for word in s.split(" "):
        test = (cur + " " + word).strip()
        if _tw(test) <= width:
            cur = test
        else:
            if cur:
                out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


def _cards(im, d, entries: list[dict], y0: int = 30, y1: int = 120):
    """카드 여러 장 (보상·갈림길). entry: {"n": 이름, "d": 설명, "icon": 이미지|None, "draw": 그리기 함수|None}"""
    n = max(1, len(entries))
    gap = 5
    w = (W - 16 - gap * (n - 1)) // n
    for i, en in enumerate(entries):
        x0 = 8 + i * (w + gap)
        cx = x0 + w // 2
        _panel(d, (x0, y0, x0 + w, y1), fill=(248, 248, 240))
        d.rectangle((x0 + 1, y0 + 1, x0 + w - 1, y0 + 12), fill=(232, 224, 200))
        _text(d, (x0 + 5, y0 + 1), f"{i + 1}", font=BOLD, fill=(160, 120, 40))
        icon = en.get("icon")
        if en.get("pix") is not None:
            pix = en["pix"]
            im.paste(pix, (cx - pix.width // 2, y0 + 33 - pix.height // 2), pix)
        elif icon is not None:
            icon = icon.convert("RGBA")
            icon = icon.resize((icon.width * 2, icon.height * 2), Image.NEAREST)
            im.paste(icon, (cx - icon.width // 2, y0 + 40 - icon.height // 2), icon)
        elif en.get("draw"):
            en["draw"](d, cx, y0 + 40)
        else:
            d.ellipse((cx - 12, y0 + 20, cx + 12, y0 + 44), fill=(232, 200, 120), outline=(160, 120, 40))
            _text(d, (cx - 3, y0 + 26), "?", font=BOLD, fill=(120, 80, 24))
        name = en["n"]
        name, nf = _shrink(name, w - 6, (BOLD, FONT, SMALL, TINY))   # 길면 글씨를 줄여서
        _text(d, (cx - _tw(name, nf) // 2, y0 + 54), name, font=nf)
        text = en["d"]
        if ". " in text and _tw(text) > 2 * (w - 8):   # 카드에 안 들어가면 앞의 꾸밈말은 빼고
            text = text.split(". ", 1)[1]
        desc = _wrap(text, w - 8)
        if len(desc) > 2:
            desc = desc[:2]
            while _tw(desc[1] + "…") > w - 6 and len(desc[1]) > 1:
                desc[1] = desc[1][:-1]
            desc[1] = desc[1].rstrip() + "…"
        for j, line in enumerate(desc):
            while _tw(line) > w - 6 and len(line) > 2:
                line = line[:-1]
            _text(d, (cx - _tw(line) // 2, y0 + 67 + j * 11), line, fill=(88, 88, 104))


def rewards(run: dict, get_sprite: SpriteGetter | None = None, get_item: ItemGetter | None = None) -> bytes:
    im, d = _canvas()
    _background(d, E.biome(run["wave"]))
    d.rectangle((0, 0, W, 22), fill=(40, 56, 88))
    title = f"WAVE {run['wave']} 클리어!  " + "보상을 하나 고르세요"
    _text(d, (8, 5), title, font=BOLD, fill=(255, 232, 120), shadow=(16, 24, 40))
    money = f"₽{run.get('money', 0):,}"
    _text(d, (W - _tw(money, BOLD) - 8, 5), money, font=BOLD, fill=(255, 255, 255), shadow=(16, 24, 40))
    entries = []
    for key in run["rewards"][:4]:
        r = E.reward_info(key, run)
        icon = None
        if get_item:
            try:
                icon = get_item(reward_icon(key))
            except Exception:
                icon = None
        entries.append({"n": r["n"], "d": r["d"], "icon": icon})
    _cards(im, d, entries)
    # 아래: 파티 6칸
    _party_strip(im, d, run, get_sprite, 8, 126)
    return _finish(im, d)
