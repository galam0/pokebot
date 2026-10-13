"""게임 화면처럼 보이는 그림 만들기 (Pillow).

배경·상자·바는 작은 캔버스(320x192)에 도트로 그린 뒤 3배로 키우고,
글자는 키운 뒤에 큰 그림 위에 따로 써서 깨지지 않게 한다 (나눔고딕, SIL OFL).
포켓몬 스프라이트는 밖에서 받아 넘겨준다 (get_sprite). 없으면 빈 실루엣 자리로 그린다.
"""

import io
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from . import data as D
from . import engine as E
from .text import josa

W, H = 320, 192
SCALE = 3
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# 글자는 3배 크기 그림에 쓰므로 실제 크기도 3배 (좌표는 작은 캔버스 기준)
FONT = ImageFont.truetype(str(_FONT_DIR / "NanumGothicBold.ttf"), 27)
BOLD = ImageFont.truetype(str(_FONT_DIR / "NanumGothicExtraBold.ttf"), 29)

SpriteGetter = Callable[[int, bool], Image.Image | None]   # (종 번호, 뒷모습?) -> 이미지

TYPE_RGB = {
    1: (168, 167, 122), 2: (194, 46, 40), 3: (169, 143, 243), 4: (163, 62, 161), 5: (226, 191, 101),
    6: (182, 161, 54), 7: (166, 185, 26), 8: (115, 87, 151), 9: (183, 183, 206), 10: (238, 129, 48),
    11: (99, 144, 240), 12: (122, 199, 76), 13: (247, 208, 44), 14: (249, 85, 135), 15: (150, 217, 214),
    16: (111, 53, 252), 17: (112, 87, 70), 18: (214, 133, 173),
}
# 지역별 (하늘 위, 하늘 아래, 땅, 땅 무늬)
BIOME_RGB = {
    "풀숲": ((120, 200, 248), (200, 236, 248), (120, 192, 96), (96, 168, 72)),
    "동굴": ((56, 48, 48), (96, 80, 72), (128, 104, 88), (104, 84, 72)),
    "해변": ((88, 176, 248), (184, 228, 248), (240, 216, 152), (216, 192, 128)),
    "숲": ((64, 120, 88), (128, 176, 120), (72, 136, 64), (56, 112, 48)),
    "화산": ((136, 48, 40), (232, 120, 72), (96, 64, 56), (176, 72, 48)),
    "설원": ((168, 200, 232), (232, 240, 248), (232, 240, 248), (200, 216, 232)),
    "도시": ((136, 160, 200), (208, 216, 232), (152, 152, 160), (128, 128, 136)),
    "유적": ((200, 176, 120), (240, 224, 176), (192, 160, 104), (168, 136, 88)),
    "하늘탑": ((72, 64, 152), (168, 152, 232), (176, 176, 200), (144, 144, 176)),
    "챔피언로드": ((40, 40, 64), (112, 96, 136), (96, 88, 104), (72, 64, 88)),
}
INK = (40, 40, 48)
PANEL = (248, 248, 240)
PANEL_EDGE = (72, 72, 88)
MSG_BG = (40, 56, 88)
MSG_EDGE = (200, 168, 72)


# ---------- 기본 도구 ----------
def _canvas(color=(0, 0, 0)) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), color)
    d = ImageDraw.Draw(im)
    d.texts = []   # 글자는 모아 뒀다가 _finish에서 큰 그림에 쓴다
    return im, d


def _finish(im: Image.Image, d: ImageDraw.ImageDraw) -> bytes:
    big = im.resize((W * SCALE, H * SCALE), Image.NEAREST)
    bd = ImageDraw.Draw(big)
    for (x, y), s, font, fill, outline in d.texts:
        bd.text((x * SCALE, y * SCALE + 1), s, font=font, fill=fill,
                stroke_width=3 if outline else 0, stroke_fill=outline)
    buf = io.BytesIO()
    big.save(buf, "PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _panel(d: ImageDraw.ImageDraw, box, fill=PANEL, edge=PANEL_EDGE, r=4):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=edge, width=1)


# ---------- 도트 글꼴 (영문·숫자용, 5x7 직접 정의) ----------
# 한글은 나눔고딕으로 크게 쓰고, HP·Lv·숫자처럼 짧은 영문/숫자는 이 도트 글꼴로 캔버스에 바로 찍는다.
_GLYPHS = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "v": ["00000", "00000", "10001", "10001", "10001", "01010", "00100"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
}


def _is_pixel(s: str) -> bool:
    return bool(s) and all(c in _GLYPHS for c in s)


def _pixel_width(s: str, bold: bool) -> int:
    return sum(len(_GLYPHS[c][0]) + 1 + (1 if bold and c != " " else 0) for c in s) - 1


def _pixel_text(d, x: int, y: int, s: str, fill, bold: bool, shade):
    """도트 글자를 찍는다. shade: 오른쪽 아래 1칸 그림자 색 (게임 상태창 느낌)"""
    for c in s:
        rows = _GLYPHS[c]
        for dy, row in enumerate(rows):
            for dx, bit in enumerate(row):
                if bit == "1":
                    for bx in ((0, 1) if bold else (0,)):
                        if shade:
                            d.point((x + dx + bx + 1, y + dy + 1), fill=shade)
                        d.point((x + dx + bx, y + dy), fill=fill)
        if shade:   # 그림자가 다음 글자를 덮지 않게 본 글자를 한 번 더
            for dy, row in enumerate(rows):
                for dx, bit in enumerate(row):
                    if bit == "1":
                        for bx in ((0, 1) if bold else (0,)):
                            d.point((x + dx + bx, y + dy), fill=fill)
        x += len(rows[0]) + 1 + (1 if bold and c != " " else 0)


def _shade_of(fill, outline):
    if outline:   # 밝은 글자 → 진한 그림자
        return outline
    r, g, b = fill[:3]
    if r + g + b < 200:   # 진한 글자 → 옅은 회색 그림자
        return (200, 200, 192)
    return tuple(int(c * 0.35 + p * 0.65) for c, p in zip(fill[:3], PANEL))   # 색 글자 → 옅은 같은 색


def _text(d, xy, s, font=FONT, fill=INK, shadow=None):
    """영문·숫자만 있으면 도트로 바로 찍고, 한글이 섞이면 나중에 큰 그림에 쓴다.
    shadow: 밝은 글자의 테두리(도트일 땐 그림자) 색"""
    if _is_pixel(s):
        _pixel_text(d, xy[0], xy[1] + 2, s, fill, False, _shade_of(fill, shadow))
        return
    d.texts.append((xy, s, font, fill, shadow))


def _tw(s: str, font=FONT) -> int:
    """작은 캔버스 기준 글자 너비"""
    if _is_pixel(s):
        return _pixel_width(s, False) + 1
    return int(font.getlength(s) / SCALE + 0.99)


def _bar(d, x, y, w, h, ratio, fg, bg=(64, 64, 72), edge=INK):
    d.rectangle((x, y, x + w, y + h), fill=bg, outline=edge)
    fw = 0 if ratio <= 0 else max(1, int((w - 1) * min(1, ratio)))
    if fw:
        d.rectangle((x + 1, y + 1, x + fw, y + h - 1), fill=fg)


def _hp_color(ratio: float):
    return (88, 208, 96) if ratio > 0.5 else (240, 200, 48) if ratio > 0.2 else (232, 72, 64)


def _type_pill(d, x, y, t: int) -> int:
    label = D.TYPE_KO[t]
    w = _tw(label) + 8
    col = TYPE_RGB[t]
    d.rounded_rectangle((x, y, x + w, y + 12), radius=3, fill=col, outline=tuple(max(0, c - 70) for c in col))
    _text(d, (x + 4, y + 1), label, fill=(255, 255, 255), shadow=tuple(max(0, c - 90) for c in col))
    return w


def _status_tag(d, x, y, status: str | None) -> int:
    if not status:
        return 0
    col = {"par": (216, 176, 32), "brn": (224, 96, 48), "psn": (160, 64, 168), "frz": (96, 176, 224)}[status]
    label = E.STATUS_KO[status]
    w = _tw(label) + 6
    d.rectangle((x, y, x + w, y + 11), fill=col)
    _text(d, (x + 3, y), label, fill=(255, 255, 255))
    return w


def _placeholder(size=64) -> Image.Image:
    """스프라이트를 아직 못 받았을 때 쓰는 빈 실루엣 자리"""
    im = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    o = (96 - size) // 2
    d.ellipse((o, o + 8, o + size, o + size + 8), fill=(0, 0, 0, 60))
    return im


def _sprite(get_sprite: SpriteGetter | None, sid: int, back: bool) -> Image.Image:
    img = None
    if get_sprite:
        try:
            img = get_sprite(sid, back)
        except Exception:
            img = None
    if img is None:
        return _placeholder()
    img = img.convert("RGBA")
    bbox = img.getbbox()   # 투명 여백 잘라내기
    return img.crop(bbox) if bbox else img


def _background(d, biome: str):
    top, bottom, ground, mark = BIOME_RGB.get(biome, BIOME_RGB["풀숲"])
    horizon = 92
    for y in range(horizon):   # 하늘 그라데이션 (4줄씩 끊어서 도트 느낌)
        t = (y // 4 * 4) / horizon
        d.line((0, y, W, y), fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    d.rectangle((0, horizon, W, H), fill=ground)
    for i, y in enumerate(range(horizon + 6, H, 10)):   # 땅 무늬
        for x in range((i % 2) * 14, W, 28):
            d.line((x, y, x + 6, y), fill=mark)


def _platform(d, cx, cy, rx, ry, biome: str):
    _, _, ground, mark = BIOME_RGB.get(biome, BIOME_RGB["풀숲"])
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=mark, outline=tuple(max(0, c - 40) for c in mark))
    d.ellipse((cx - rx + 6, cy - ry + 3, cx + rx - 6, cy + ry - 4), fill=tuple(min(255, c + 16) for c in ground))


# ---------- 배틀 화면 ----------
def battle(run: dict, get_sprite: SpriteGetter | None = None, message: list[str] | None = None) -> bytes:
    p, e, wave = run["p"], run["e"], run["wave"]
    biome = E.biome(wave)
    im, d = _canvas()
    _background(d, biome)

    # 상대 (오른쪽 위)
    _platform(d, 236, 86, 52, 12, biome)
    if e:
        es = _sprite(get_sprite, e["sid"], False)
        if e["hp"] <= 0:
            es = es.convert("LA").convert("RGBA")   # 쓰러지면 흑백
            es.putalpha(es.getchannel("A").point(lambda a: a // 2))
        im.paste(es, (236 - es.width // 2, 88 - es.height), es)
    # 나 (왼쪽 아래, 뒷모습)
    _platform(d, 78, 146, 60, 14, biome)
    ps = _sprite(get_sprite, p["sid"], True)
    if ps.height < 80:   # 뒷모습은 조금 크게
        ps = ps.resize((int(ps.width * 1.5), int(ps.height * 1.5)), Image.NEAREST)
    im.paste(ps, (78 - ps.width // 2, 146 - ps.height + 6), ps)

    # 상대 정보창
    if e:
        _panel(d, (6, 8, 146, 44))
        name = D.name(e["sid"])
        _text(d, (12, 12), name, font=BOLD)
        x = 12 + _tw(name, BOLD) + 4
        if e.get("boss"):
            _text(d, (x, 12), "BOSS", font=BOLD, fill=(200, 48, 48))
            x += _tw("BOSS", BOLD) + 4
        _status_tag(d, x, 12, e.get("status"))
        lv = f"Lv.{e['lv']}"
        _text(d, (140 - _tw(lv), 12), lv)
        r = e["hp"] / E.max_hp(e)
        _text(d, (12, 28), "HP", font=BOLD, fill=(232, 160, 32))
        _bar(d, 28, 30, 110, 6, r, _hp_color(r))

    # 내 정보창
    _panel(d, (172, 98, 314, 142))
    name = D.name(p["sid"])
    _text(d, (178, 102), name, font=BOLD)
    _status_tag(d, 178 + _tw(name, BOLD) + 4, 102, p.get("status"))
    lv = f"Lv.{p['lv']}"
    _text(d, (308 - _tw(lv), 102), lv)
    mh = E.max_hp(p)
    r = p["hp"] / mh
    _text(d, (178, 116), "HP", font=BOLD, fill=(232, 160, 32))
    _bar(d, 194, 118, 114, 6, r, _hp_color(r))
    hp_txt = f"{p['hp']}/{mh}"
    _text(d, (308 - _tw(hp_txt), 125), hp_txt)
    need = E.exp_to_next(p)
    _bar(d, 178, 138, 130, 2, (p["exp"] / need) if need else 1, (64, 160, 240), bg=(200, 200, 208), edge=(200, 200, 208))
    _text(d, (178, 125), "EXP", fill=(64, 128, 200))

    # 웨이브 표시 (오른쪽 위 작게)
    tag = f"WAVE {wave}" + (" BOSS" if E.is_boss_wave(wave) else "")
    _text(d, (W - _tw(tag) - 6, 3), tag, fill=(255, 255, 255), shadow=(0, 0, 0))

    # 메시지 창
    _message_box(d, message if message is not None else _pick_lines(run))
    return _finish(im, d)


def _pick_lines(run: dict) -> list[str]:
    import re
    lines = [re.sub(r"\*\*|[⬆️✨🎁🗺️👑⚠️🏆🏳️→]", "", s).strip() for s in (run.get("log") or [])]
    lines = [s for s in lines if s]
    if run["phase"] == "reward":
        return (lines[-1:] if lines else []) + ["보상을 하나 고르세요!"]
    if run["phase"] == "over":
        return lines[-1:] + [f"{run['wave'] - 1}웨이브 돌파! 런이 끝났다."]
    if run["phase"] == "clear":
        return lines[-1:] + ["축하합니다! 모든 웨이브를 클리어했다!"]
    if run["phase"] == "battle" and len(lines) <= 2 and not any("데미지" in s for s in lines):
        return lines[-2:] + [f"{D.name(run['p']['sid'])}은(는) 무엇을 할까?"]
    return lines[-3:]


def _message_box(d, lines: list[str]):
    d.rectangle((0, 148, W, H), fill=MSG_EDGE)
    d.rounded_rectangle((3, 151, W - 4, H - 4), radius=3, fill=MSG_BG, outline=(24, 32, 56))
    y = 155
    for s in lines[-3:]:
        s = josa(s)
        while _tw(s) > W - 22:
            s = s[:-1]
        _text(d, (11, y), s, fill=(248, 248, 248), shadow=(16, 24, 40))
        y += 12


# ---------- 상태창 ----------
STAT_RGB = [(232, 72, 64), (240, 160, 48), (240, 208, 64), (96, 144, 240), (120, 200, 96), (240, 104, 168)]


def summary(run: dict, get_sprite: SpriteGetter | None = None) -> bytes:
    p = run["p"]
    im, d = _canvas((232, 232, 224))
    t0 = D.types(p["sid"])[0]
    head = TYPE_RGB[t0]
    d.rectangle((0, 0, W, 18), fill=head)
    _text(d, (6, 3), "포켓몬 정보", font=BOLD, fill=(255, 255, 255), shadow=tuple(max(0, c - 90) for c in head))
    dark = tuple(max(0, c - 90) for c in head)
    st = f"스타팅 {D.name(run['starter'])}"
    wv = f"WAVE {run['wave']}"
    _text(d, (W - _tw(st) - 6, 3), st, fill=(255, 255, 255), shadow=dark)
    _text(d, (W - _tw(st) - 12 - _tw(wv), 3), wv, fill=(255, 255, 255), shadow=dark)

    # 왼쪽: 스프라이트
    _panel(d, (6, 22, 110, 133), fill=(248, 248, 240))
    for y in range(23, 133, 6):
        d.line((7, y, 109, y), fill=(236, 236, 228))
    sp = _sprite(get_sprite, p["sid"], False)
    if sp.width <= 64:
        sp = sp.resize((sp.width * 2, sp.height * 2), Image.NEAREST)
    sp.thumbnail((96, 96), Image.NEAREST)
    im.paste(sp, (58 - sp.width // 2, 116 - sp.height), sp)
    _text(d, (12, 28), f"Lv.{p['lv']}", font=BOLD)
    x = 12
    for t in D.types(p["sid"]):
        x += _type_pill(d, x, 112, t) + 3

    # 오른쪽: 이름, HP, EXP, 능력치
    _panel(d, (116, 22, 314, 133))
    _text(d, (122, 27), D.name(p["sid"]), font=BOLD)
    _status_tag(d, 122 + _tw(D.name(p["sid"]), BOLD) + 4, 27, p.get("status"))
    mh = E.max_hp(p)
    r = p["hp"] / mh
    _text(d, (122, 39), "HP", font=BOLD, fill=(232, 160, 32))
    _bar(d, 140, 41, 110, 6, r, _hp_color(r))
    _text(d, (256, 39), f"{p['hp']}/{mh}")
    need = E.exp_to_next(p)
    _text(d, (122, 50), "EXP", fill=(64, 128, 200))
    _bar(d, 146, 53, 104, 4, (p["exp"] / need) if need else 1, (64, 160, 240), bg=(208, 208, 216))
    _text(d, (256, 50), f"다음 {need - p['exp']}" if need else "MAX")
    d.line((122, 63, 308, 63), fill=(216, 216, 208))
    stats = E.stats_line(p)
    top = max(v for _, v in stats) or 1
    for i, (n, v) in enumerate(stats):
        y = 64 + i * 11
        _text(d, (122, y), n)
        _bar(d, 156, y + 3, 92, 4, v / top, STAT_RGB[i], bg=(216, 216, 224), edge=(160, 160, 176))
        vt = str(v) + ("+" if p["vit"][i] else "")
        _text(d, (308 - _tw(vt), y), vt, font=BOLD if p["vit"][i] else FONT)

    # 아래: 기술 4칸
    for i, mid in enumerate(p["moves"][:4]):
        m = D.MOVES[mid]
        x0, y0 = 6 + (i % 2) * 155, 137 + (i // 2) * 27
        col = TYPE_RGB[m["t"]]
        _panel(d, (x0, y0, x0 + 152, y0 + 26), fill=tuple(min(255, c // 4 + 190) for c in col), edge=tuple(max(0, c - 60) for c in col))
        _text(d, (x0 + 5, y0 + 2), m["n"], font=BOLD)
        _type_pill(d, x0 + 5, y0 + 13, m["t"])
        info = f"{'물리' if m['c'] == 0 else '특수'} {m['p']}" + (f" 명중{m['a']}" if m["a"] and m["a"] < 100 else "")
        _text(d, (x0 + 148 - _tw(info), y0 + 14), info)
    return _finish(im, d)


# ---------- 보상 화면 ----------
REWARD_ICON = {   # 보상 → PokeAPI 아이템 스프라이트 이름
    "potion": "potion", "superpot": "super-potion", "fullrest": "full-restore", "fullheal": "full-heal",
    "candy": "rare-candy", "candy3": "rare-candy", "hpup": "hp-up", "protein": "protein", "iron": "iron",
    "calcium": "calcium", "zinc": "zinc", "carbos": "carbos", "expcharm": "exp-share",
}
ItemGetter = Callable[[str], Image.Image | None]


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


def rewards(run: dict, get_sprite: SpriteGetter | None = None, get_item: ItemGetter | None = None) -> bytes:
    im, d = _canvas()
    _background(d, E.biome(run["wave"]))
    d.rectangle((0, 0, W, 22), fill=(40, 56, 88))
    _text(d, (8, 5), f"WAVE {run['wave']} 클리어!  보상을 하나 고르세요", font=BOLD, fill=(255, 232, 120), shadow=(16, 24, 40))
    for i, key in enumerate(run["rewards"][:3]):
        r = E.REWARDS[key]
        x0 = 8 + i * 103
        _panel(d, (x0, 30, x0 + 98, 120), fill=(248, 248, 240))
        d.rectangle((x0 + 1, 31, x0 + 97, 42), fill=(232, 224, 200))
        _text(d, (x0 + 5, 31), f"{i + 1}", font=BOLD, fill=(160, 120, 40))
        icon = None
        if get_item:
            try:
                icon = get_item(REWARD_ICON[key])
            except Exception:
                icon = None
        if icon is not None:
            icon = icon.convert("RGBA")
            icon = icon.resize((icon.width * 2, icon.height * 2), Image.NEAREST)
            im.paste(icon, (x0 + 49 - icon.width // 2, 70 - icon.height // 2), icon)
        else:
            d.ellipse((x0 + 37, 50, x0 + 61, 74), fill=(232, 200, 120), outline=(160, 120, 40))
            _text(d, (x0 + 46, 56), "?", font=BOLD, fill=(120, 80, 24))
        name = r["n"]
        _text(d, (x0 + 49 - _tw(name, BOLD) // 2, 84), name, font=BOLD)
        desc = r["d"].replace(" (", "\n(").split("\n") if " (" in r["d"] else _wrap(r["d"], 90)
        for j, line in enumerate(desc[:2]):
            _text(d, (x0 + 49 - _tw(line) // 2, 97 + j * 11), line, fill=(88, 88, 104))
    # 아래: 내 포켓몬 상태
    p = run["p"]
    _panel(d, (8, 128, 312, 186), fill=(248, 248, 240))
    sp = _sprite(get_sprite, p["sid"], False)
    sp.thumbnail((48, 48), Image.NEAREST)
    im.paste(sp, (36 - sp.width // 2, 182 - sp.height), sp)
    _text(d, (66, 134), D.name(p["sid"]), font=BOLD)
    lv = f"Lv.{p['lv']}"
    _text(d, (304 - _tw(lv), 134), lv)
    mh = E.max_hp(p)
    r = p["hp"] / mh
    _text(d, (66, 150), "HP", font=BOLD, fill=(232, 160, 32))
    _bar(d, 84, 152, 160, 6, r, _hp_color(r))
    _text(d, (250, 150), f"{p['hp']}/{mh}")
    need = E.exp_to_next(p)
    _text(d, (66, 166), "EXP", fill=(64, 128, 200))
    _bar(d, 90, 169, 154, 4, (p["exp"] / need) if need else 1, (64, 160, 240), bg=(208, 208, 216))
    _text(d, (250, 166), f"다음 {need - p['exp']}" if need else "MAX")
    return _finish(im, d)
