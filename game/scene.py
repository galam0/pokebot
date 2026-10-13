"""게임 화면처럼 보이는 그림 만들기 (Pillow).

배경·상자·바는 작은 캔버스(320x192)에 도트로 그린 뒤 3배로 키우고,
글자는 키운 뒤에 큰 그림 위에 따로 써서 깨지지 않게 한다 (나눔고딕, SIL OFL).
포켓몬 스프라이트는 밖에서 받아 넘겨준다 (get_sprite). 없으면 빈 실루엣 자리로 그린다.
"""

import io
import math
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import data as D
from . import adventure as A
from . import engine as E
from . import heroes as HR
from . import hoenn as HO
from . import johto as J
from . import kanto as K
from .text import josa

W, H = 320, 192
SCALE = 3
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# 글자는 3배 크기 그림에 쓰므로 실제 크기도 3배 (좌표는 작은 캔버스 기준)
FONT = ImageFont.truetype(str(_FONT_DIR / "NanumGothicBold.ttf"), 27)
BOLD = ImageFont.truetype(str(_FONT_DIR / "NanumGothicExtraBold.ttf"), 29)
SMALL = ImageFont.truetype(str(_FONT_DIR / "NanumGothicBold.ttf"), 22)
TITLE = ImageFont.truetype(str(_FONT_DIR / "NanumGothicExtraBold.ttf"), 52)

SpriteGetter = Callable[[int, bool], Image.Image | None]   # (종 번호, 뒷모습?) -> 이미지
TrainerGetter = Callable[[str], Image.Image | None]        # 주인공 키 -> 이미지

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


def _layer() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """투명한 위 칸 (배틀 GIF에서 스프라이트 위에 덮는 정보창·메시지 창)"""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.texts = []
    return im, d


def _enlarge(im: Image.Image, d: ImageDraw.ImageDraw) -> Image.Image:
    """3배로 키우고 모아 둔 글자를 쓴다"""
    big = im.resize((W * SCALE, H * SCALE), Image.NEAREST)
    bd = ImageDraw.Draw(big)
    for (x, y), s, font, fill, outline in d.texts:
        bd.text((x * SCALE, y * SCALE + 1), s, font=font, fill=fill,
                stroke_width=3 if outline else 0, stroke_fill=outline)
    return big


def _png(big: Image.Image) -> bytes:
    buf = io.BytesIO()
    big.save(buf, "PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _finish(im: Image.Image, d: ImageDraw.ImageDraw) -> bytes:
    return _png(_enlarge(im, d))


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
    ",": ["000", "000", "000", "000", "000", "011", "010"],
    "₽": ["11110", "10001", "10001", "11110", "11100", "10000", "10000"],
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


# ---------- 게임풍 HP / EXP 게이지 ----------
_GAUGE = {   # (위쪽 밝은 줄, 본색, 아래쪽 어두운 줄)
    "green": ((168, 248, 168), (88, 208, 96), (48, 144, 64)),
    "yellow": ((255, 236, 136), (240, 192, 40), (184, 136, 16)),
    "red": ((255, 160, 144), (232, 72, 64), (168, 32, 32)),
    "exp": ((152, 216, 255), (72, 160, 240), (40, 104, 192)),
}
_GAUGE_FRAME = (48, 48, 60)
_GAUGE_EMPTY = ((112, 112, 124), (84, 84, 96), (72, 72, 84))


def _gauge_rows(d, x0, x1, y, ratio, colors):
    """x0~x1 사이를 ratio만큼 3단 색으로 채운다 (y부터 5줄: 밝은 1 / 본색 3 / 어두운 1)"""
    fill_to = x0 - 1 + (0 if ratio <= 0 else max(1, round((x1 - x0 + 1) * min(1.0, ratio))))
    rows = [0, 1, 1, 1, 2]
    for i, k in enumerate(rows):
        d.line((x0, y + i, x1, y + i), fill=_GAUGE_EMPTY[k])
        if fill_to >= x0:
            d.line((x0, y + i, fill_to, y + i), fill=colors[k])


def _hp_gauge(d, x, y, w, ratio):
    """[HP|■■■■■□□] 캡슐 모양 HP 게이지 (높이 9)"""
    d.rounded_rectangle((x, y, x + w, y + 8), radius=2, fill=_GAUGE_FRAME)
    _pixel_text(d, x + 3, y + 1, "HP", (248, 200, 64), False, None)
    key = "green" if ratio > 0.5 else ("yellow" if ratio > 0.2 else "red")
    _gauge_rows(d, x + 16, x + w - 2, y + 2, ratio, _GAUGE[key])


def _exp_gauge(d, x, y, w, ratio):
    """얇은 EXP 게이지 (높이 4)"""
    d.rectangle((x, y, x + w, y + 3), fill=_GAUGE_FRAME)
    x0, x1 = x + 1, x + w - 1
    fill_to = x0 - 1 + (0 if ratio <= 0 else max(1, round((x1 - x0 + 1) * min(1.0, ratio))))
    d.line((x0, y + 1, x1, y + 1), fill=_GAUGE_EMPTY[1])
    d.line((x0, y + 2, x1, y + 2), fill=_GAUGE_EMPTY[2])
    if fill_to >= x0:
        d.line((x0, y + 1, fill_to, y + 1), fill=_GAUGE["exp"][0])
        d.line((x0, y + 2, fill_to, y + 2), fill=_GAUGE["exp"][2])


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
def _party_balls(d, x, y, run: dict):
    """파티 6칸을 작은 볼로 표시 (살아 있음 / 기절 / 빈칸)"""
    for i in range(E.MAX_PARTY):
        bx = x + i * 9
        if i < len(run["party"]):
            m = run["party"][i]
            top = (224, 64, 56) if m["hp"] > 0 else (128, 128, 136)
            d.ellipse((bx, y, bx + 6, y + 6), fill=(248, 248, 248), outline=(40, 40, 48))
            d.chord((bx, y, bx + 6, y + 6), 180, 360, fill=top, outline=(40, 40, 48))
            d.point((bx + 3, y + 3), fill=(40, 40, 48))
        else:
            d.ellipse((bx + 1, y + 1, bx + 5, y + 5), outline=(160, 160, 168))


def _mini_gauge(d, x, y, w, ratio):
    """이름 옆에 쓰는 얇은 HP 게이지 (높이 5)"""
    key = "green" if ratio > 0.5 else ("yellow" if ratio > 0.2 else "red")
    col = _GAUGE[key]
    d.rectangle((x, y, x + w, y + 4), fill=_GAUGE_FRAME)
    x0, x1 = x + 1, x + w - 1
    fill_to = x0 - 1 + (0 if ratio <= 0 else max(1, round((x1 - x0 + 1) * min(1.0, ratio))))
    for i, k in enumerate((0, 1, 2)):
        d.line((x0, y + 1 + i, x1, y + 1 + i), fill=_GAUGE_EMPTY[k])
        if fill_to >= x0:
            d.line((x0, y + 1 + i, fill_to, y + 1 + i), fill=col[k])


def _battle_layers(run: dict, message: list[str] | None):
    """배틀 화면을 (배경, 위 칸, 포켓몬 자리)로 나눠 그린다. 포켓몬은 그 사이에 붙인다 (GIF는 프레임마다)."""
    p, e, wave = E.lead(run), run["e"], run["wave"]
    adv = run.get("mode") == "adventure"
    biome = A.loc(run)["bg"] if adv else E.biome(wave)
    im, d = _canvas()
    _background(d, biome)
    _platform(d, 236, 86, 52, 12, biome)   # 상대 (오른쪽 위)
    _platform(d, 78, 146, 60, 14, biome)   # 나 (왼쪽 아래, 뒷모습)
    actors = []   # (종, 뒷모습?, 가운데 x, 발 y, 쓰러짐?)  — 작은 캔버스 좌표
    if e:
        actors.append((e["sid"], False, 236, 88, e["hp"] <= 0))
    actors.append((p["sid"], True, 78, 152, p["hp"] <= 0))

    ov, d = _layer()
    # 상대 정보창
    if e:
        _panel(d, (6, 8, 146, 48 if e.get("bars", 0) > 1 else 44))
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
        _hp_gauge(d, 12, 28, 128, r)
        bars = e.get("bars", 0)
        if bars > 1:   # 보스 보호막 칸: 게이지에 칸 나눔 + 남은 보호막 방패
            x0, x1 = 12 + 16, 12 + 128 - 2
            for k in range(1, bars):
                tx = x0 + round((x1 - x0) * k / bars)
                d.line((tx, 29, tx, 36), fill=(248, 248, 240))
            for k in range(e.get("bars_left", 1) - 1):
                sx = 14 + k * 9
                d.polygon([(sx, 38), (sx + 6, 38), (sx + 6, 41), (sx + 3, 44), (sx, 41)], fill=(96, 160, 232),
                          outline=(40, 64, 120))

    # 내 정보창 (+ 파티 볼)
    _panel(d, (172, 98, 314, 142))
    _party_balls(d, 258, 89, run)
    name = D.name(p["sid"])
    _text(d, (178, 102), name, font=BOLD)
    _status_tag(d, 178 + _tw(name, BOLD) + 4, 102, p.get("status"))
    lv = f"Lv.{p['lv']}"
    _text(d, (308 - _tw(lv), 102), lv)
    mh = E.max_hp(p)
    r = p["hp"] / mh
    _hp_gauge(d, 178, 115, 130, r)
    hp_txt = f"{p['hp']}/{mh}"
    _text(d, (308 - _tw(hp_txt), 123), hp_txt)
    need = E.exp_to_next(p)
    _text(d, (178, 131), "EXP", fill=(64, 128, 200))
    _exp_gauge(d, 198, 135, 110, (p["exp"] / need) if need else 1)

    # 웨이브 / 장소 표시 (오른쪽 위 작게)
    if adv:
        tag = A.loc(run)["n"]
        _text(d, (W - _tw(tag, SMALL) - 6, 2), tag, font=SMALL, fill=(255, 255, 255), shadow=(0, 0, 0))
        b = run.get("battle") or {}
        if b.get("total", 1) > 1 and e:   # 트레이너의 남은 포켓몬 (볼)
            left = len(b.get("queue", [])) + (1 if e["hp"] > 0 else 0)
            for i in range(b["total"]):
                bx = 12 + i * 9
                d.ellipse((bx, 49, bx + 6, 55), fill=(248, 248, 248), outline=(40, 40, 48))
                d.chord((bx, 49, bx + 6, 55), 180, 360, fill=(224, 64, 56) if i < left else (128, 128, 136),
                        outline=(40, 40, 48))
    else:
        tag = f"WAVE {wave}" + (" BOSS" if E.is_boss_wave(wave) else "")
        _text(d, (W - _tw(tag) - 6, 3), tag, fill=(255, 255, 255), shadow=(0, 0, 0))

    # 메시지 창
    _message_box(d, message if message is not None else _pick_lines(run))
    base = im.resize((W * SCALE, H * SCALE), Image.NEAREST)
    return base, _enlarge(ov, d), actors


def _fainted(img: Image.Image) -> Image.Image:
    """쓰러지면 흑백 + 반투명"""
    img = img.convert("LA").convert("RGBA")
    img.putalpha(img.getchannel("A").point(lambda a: a // 2))
    return img


def _actor_big(get_sprite, sid: int, back: bool, fainted: bool) -> Image.Image:
    """멈춘 스프라이트를 큰 그림 크기로 (뒷모습은 조금 크게)"""
    img = _sprite(get_sprite, sid, back)
    if fainted:
        img = _fainted(img)
    if back and img.height < 80:
        img = img.resize((int(img.width * 1.5), int(img.height * 1.5)), Image.NEAREST)
    return img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST)


def _paste_foot(canvas: Image.Image, img: Image.Image, cx: int, foot: int):
    """발(아래 가운데)을 (cx, foot) 큰 그림 좌표에 맞춰 붙인다"""
    canvas.paste(img, (cx - img.width // 2, foot - img.height), img)


def battle(run: dict, get_sprite: SpriteGetter | None = None, message: list[str] | None = None) -> bytes:
    base, over, actors = _battle_layers(run, message)
    for sid, back, cx, foot, fainted in actors:
        _paste_foot(base, _actor_big(get_sprite, sid, back, fainted), cx * SCALE, foot * SCALE)
    base.paste(over, (0, 0), over)
    return _png(base)


AnimGetter = Callable[[int, bool], list | None]   # (종 번호, 뒷모습?) -> [(그림, ms)] 또는 None
GIF_STEP = 60          # 프레임 간격 (ms)
GIF_MAX_MS = 2400      # 한 바퀴 최대 길이
GIF_IDLE_MS = 1200     # 움직이는 그림이 없을 때 숨쉬기 한 바퀴


def _anim_big(frames: list, still: Image.Image) -> list[tuple[Image.Image, int]]:
    """움직이는 스프라이트를 멈춘 그림과 비슷한 크기가 되도록 정수배로 키운다 (도트가 고르게)"""
    h = max(f.height for f, _ in frames)
    k = max(1, min(4, round(still.height / h))) if still.getbbox() else 2
    return [(f.resize((f.width * k, f.height * k), Image.NEAREST), ms) for f, ms in frames]


def _at(frames: list[tuple[Image.Image, int]], t: int) -> Image.Image:
    t %= sum(ms for _, ms in frames)
    for f, ms in frames:
        if t < ms:
            return f
        t -= ms
    return frames[-1][0]


def _breathe(img: Image.Image, phase: float) -> tuple[Image.Image, int]:
    """멈춘 그림에 숨쉬기 (살짝 늘었다 줄고 통통 뜀). (그림, 위로 뜬 높이)"""
    s = math.sin(phase * 2 * math.pi)
    w = max(1, round(img.width * (1 - 0.02 * s)))
    h = max(1, round(img.height * (1 + 0.04 * s)))
    lift = round(4 * max(0.0, math.sin(phase * 2 * math.pi + 0.6)))
    return img.resize((w, h), Image.NEAREST), lift


def battle_gif(run: dict, get_sprite: SpriteGetter | None = None, get_anim: AnimGetter | None = None,
               message: list[str] | None = None) -> bytes:
    """포켓몬이 움직이는 배틀 화면 GIF. 움직이는 스프라이트가 있으면 그걸, 없으면 멈춘 그림이 숨을 쉰다."""
    base, over, actors = _battle_layers(run, message)
    tracks = []   # (프레임 목록 또는 None, 멈춘 그림, cx, foot, 위상, 쓰러짐?)
    for i, (sid, back, cx, foot, fainted) in enumerate(actors):
        still = _actor_big(get_sprite, sid, back, fainted)
        frames = None
        if get_anim and not fainted:
            try:
                raw = get_anim(sid, back)
            except Exception:
                raw = None
            if raw:
                frames = _anim_big(raw, still)
        tracks.append((frames, still, cx * SCALE, foot * SCALE, 0.5 * i, fainted))
    loops = [sum(ms for _, ms in fr) for fr, *_ in tracks if fr]
    total = min(GIF_MAX_MS, max(loops)) if loops else GIF_IDLE_MS
    n = max(2, round(total / GIF_STEP))

    # 프레임마다 (그림, cx, 발 y)
    poses = []
    for frames, still, cx, foot, phase, fainted in tracks:
        row = []
        for j in range(n):
            t = j * GIF_STEP
            if frames:
                row.append((_at(frames, t), cx, foot))
            elif fainted:
                row.append((still, cx, foot))
            else:
                img, lift = _breathe(still, t / total + phase)
                row.append((img, cx, foot - lift))
        poses.append(row)

    # 배경 + 위 칸은 한 번만 합치고, 프레임마다 포켓몬이 지나가는 칸만 다시 그린다
    still_bg = base.copy()
    still_bg.paste(over, (0, 0), over)
    boxes = []
    for row in poses:
        xs0 = [cx - im.width // 2 for im, cx, _ in row]
        ys0 = [f - im.height for im, _, f in row]
        box = (max(0, min(xs0)), max(0, min(ys0)),
               min(base.width, max(x + im.width for x, (im, _, _) in zip(xs0, row))),
               min(base.height, max(f for _, _, f in row)))
        boxes.append((box, base.crop(box), over.crop(box)))
    rgb = []
    for j in range(n):
        fr = still_bg.copy()
        for row, (box, bg, ov) in zip(poses, boxes):
            img, cx, foot = row[j]
            part = bg.copy()
            part.paste(img, (cx - img.width // 2 - box[0], foot - img.height - box[1]), img)
            part.paste(ov, (0, 0), ov)
            fr.paste(part, box[:2])
        rgb.append(fr)
    return _gif(rgb, GIF_STEP)


def _gif(frames: list[Image.Image], step: int) -> bytes:
    """같은 팔레트로 줄이고, 앞 프레임과 같은 곳은 투명(255)으로 비워서 파일을 작게"""
    sample = Image.new("RGB", (frames[0].width, frames[0].height * 3))
    for k in range(3):
        sample.paste(frames[len(frames) * k // 3], (0, frames[0].height * k))
    pal = sample.quantize(255, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    out, prev = [], None
    for fr in frames:
        q = fr.quantize(palette=pal, dither=Image.Dither.NONE)
        if prev is not None:
            same = ImageChops.difference(fr, prev).convert("L").point(lambda v: 255 if v == 0 else 0)
            q.paste(255, mask=same)
        out.append(q)
        prev = fr
    buf = io.BytesIO()
    out[0].save(buf, "GIF", save_all=True, append_images=out[1:], duration=step, loop=0,
                transparency=255, disposal=1, optimize=False)
    return buf.getvalue()


def _pick_lines(run: dict) -> list[str]:
    import re
    lines = [re.sub(r"\*\*|[\u2190-\u21ff\u2600-\u27bf\u2b00-\u2bff\ufe0f\U0001f000-\U0001faff]", "", s).strip()
             for s in (run.get("log") or [])]
    lines = [s for s in lines if s]
    if run["phase"] == "reward":
        return (lines[-1:] if lines else []) + ["보상을 하나 고르세요!"]
    if run["phase"] == "field":
        return lines[-3:]
    if run["phase"] == "switch":
        return lines[-2:]
    if run["phase"] == "replace":
        return lines[-2:]
    if run["phase"] == "over":
        return lines[-1:] + [f"{run['wave'] - 1}웨이브 돌파! 게임이 끝났다."]
    if run["phase"] == "clear":
        return lines[-1:] + ["축하합니다! 모든 웨이브를 클리어했다!"]
    if run["phase"] == "battle" and len(lines) <= 2 and not any("데미지" in s for s in lines):
        return lines[-2:] + [f"{D.name(E.lead(run)['sid'])}은(는) 무엇을 할까?"]
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


def summary(run: dict, get_sprite: SpriteGetter | None = None, index: int | None = None) -> bytes:
    p = run["party"][run["active"] if index is None else index]
    im, d = _canvas((232, 232, 224))
    t0 = D.types(p["sid"])[0]
    head = TYPE_RGB[t0]
    d.rectangle((0, 0, W, 18), fill=head)
    _text(d, (6, 3), "포켓몬 정보", font=BOLD, fill=(255, 255, 255), shadow=tuple(max(0, c - 90) for c in head))
    dark = tuple(max(0, c - 90) for c in head)
    st = f"스타팅 {D.name(run['starter'])}"
    wv = f"배지 {len(run['badges'])}" if run.get("mode") == "adventure" else f"WAVE {run['wave']}"   # 관동+성도
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
    if p.get("held"):
        h = E.item_name(p["held"])
        _text(d, (108 - _tw(h), 28), h, fill=(120, 88, 24))

    # 오른쪽: 이름, HP, EXP, 능력치
    _panel(d, (116, 22, 314, 133))
    _text(d, (122, 27), D.name(p["sid"]), font=BOLD)
    _status_tag(d, 122 + _tw(D.name(p["sid"]), BOLD) + 4, 27, p.get("status"))
    mh = E.max_hp(p)
    r = p["hp"] / mh
    _hp_gauge(d, 122, 39, 130, r)
    _text(d, (258, 39), f"{p['hp']}/{mh}")
    need = E.exp_to_next(p)
    _text(d, (122, 50), "EXP", fill=(64, 128, 200))
    _exp_gauge(d, 144, 53, 108, (p["exp"] / need) if need else 1)
    _text(d, (256, 50), f"다음 {need - p['exp']}" if need else "MAX")
    d.line((122, 63, 308, 63), fill=(216, 216, 208))
    stats = E.stats_line(p)
    top = max(v for _, v in stats) or 1
    for i, (n, v) in enumerate(stats):
        y = 64 + i * 11
        _text(d, (122, y), n)
        col = STAT_RGB[i]
        d.rectangle((156, y + 2, 250, y + 8), fill=_GAUGE_FRAME)
        _gauge_rows(d, 157, 249, y + 3, v / top,
                    (tuple(min(255, c + 70) for c in col), col, tuple(max(0, c - 60) for c in col)))
        vt = str(v) + ("+" if p["vit"][i] else "")
        _text(d, (308 - _tw(vt), y), vt, font=BOLD if p["vit"][i] else FONT)

    # 아래: 기술 4칸
    for i, mid in enumerate(p["moves"][:4]):
        m = D.MOVES[mid]
        x0, y0 = 6 + (i % 2) * 155, 137 + (i // 2) * 27
        col = TYPE_RGB[m["t"]]
        _panel(d, (x0, y0, x0 + 152, y0 + 26), fill=tuple(min(255, c // 4 + 190) for c in col), edge=tuple(max(0, c - 60) for c in col))
        _text(d, (x0 + 5, y0 + 2), m["n"], font=BOLD)
        pp = f"PP {p['pp'][i]}/{E.max_pp(p, i)}"
        _text(d, (x0 + 148 - _tw(pp), y0 + 2), pp, fill=(200, 48, 48) if p["pp"][i] == 0 else INK)
        _type_pill(d, x0 + 5, y0 + 13, m["t"])
        info = f"{'물리' if m['c'] == 0 else '특수'} {m['p']}" + (f" 명중{m['a']}" if m["a"] and m["a"] < 100 else "")
        _text(d, (x0 + 148 - _tw(info), y0 + 14), info)
    return _finish(im, d)


# ---------- 보상 화면 ----------
ICON_FALLBACK = {"fairy-feather": "pixie-plate", "linking-cord": "up-grade"}   # 그림이 없는 아이템


def item_icon(item: str) -> str:
    return ICON_FALLBACK.get(item, item)


def reward_icon(key: str) -> str:
    return item_icon(E.reward_info(key)["icon"])


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
        nf = BOLD if _tw(name, BOLD) <= w - 6 else FONT   # 길면 조금 얇은 글꼴로
        while _tw(name, nf) > w - 6 and len(name) > 2:
            name = name[:-1]
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


def _party_strip(im, d, run: dict, get_sprite, x0: int, y0: int):
    """파티 6마리를 한 줄로 (스프라이트, Lv, 얇은 HP)"""
    _panel(d, (x0, y0, W - x0, y0 + 60), fill=(248, 248, 240))
    slot = (W - 2 * x0 - 4) // E.MAX_PARTY
    for i in range(E.MAX_PARTY):
        sx = x0 + 2 + i * slot
        if i >= len(run["party"]):
            d.rounded_rectangle((sx + 3, y0 + 5, sx + slot - 3, y0 + 55), radius=3, outline=(216, 216, 208))
            continue
        m = run["party"][i]
        if i == run["active"]:
            d.rounded_rectangle((sx + 1, y0 + 3, sx + slot - 1, y0 + 57), radius=3, fill=(255, 244, 208), outline=(216, 168, 72))
        sp = _sprite(get_sprite, m["sid"], False)
        sp.thumbnail((32, 32), Image.NEAREST)
        if m["hp"] <= 0:
            sp = sp.convert("LA").convert("RGBA")
        im.paste(sp, (sx + slot // 2 - sp.width // 2, y0 + 36 - sp.height), sp)
        lv = f"Lv.{m['lv']}"
        _text(d, (sx + slot // 2 - _tw(lv) // 2, y0 + 37), lv)
        _mini_gauge(d, sx + 5, y0 + 50, slot - 10, m["hp"] / E.max_hp(m))


# ---------- 모험: 필드 화면 ----------
BADGE_RGB = [(168, 168, 176), (88, 152, 240), (240, 160, 48), (120, 200, 96), (240, 120, 176), (232, 196, 64),
             (224, 72, 48), (72, 168, 104)]


def _badge(d, x, y, i: int, got: bool, palette=None):
    """배지 한 개 (13x13). 없으면 빈 자리"""
    if not got:
        d.ellipse((x + 1, y + 1, x + 11, y + 11), outline=(150, 150, 160))
        return
    col = (palette or BADGE_RGB)[i]
    dark = tuple(max(0, c - 90) for c in col)
    light = tuple(min(255, c + 80) for c in col)
    cx, cy = x + 6, y + 6
    shape = [
        [(cx - 3, y), (cx + 3, y), (x + 12, cy - 3), (x + 12, cy + 3), (cx + 3, y + 12), (cx - 3, y + 12),
         (x, cy + 3), (x, cy - 3)],                                                    # 회색: 팔각형 바위
        [(cx, y), (x + 11, cy + 2), (cx + 3, y + 12), (cx - 3, y + 12), (x + 1, cy + 2)],   # 블루: 물방울
        [(cx, y), (cx + 2, cy - 2), (x + 12, cy), (cx + 2, cy + 2), (cx, y + 12), (cx - 2, cy + 2), (x, cy),
         (cx - 2, cy - 2)],                                                            # 오렌지: 별
        [(cx, y), (x + 12, cy), (cx, y + 12), (x, cy)],                                # 무지개: 마름모
        [(cx, y + 3), (cx + 3, y), (x + 12, y + 3), (x + 12, cy), (cx, y + 12), (x, cy), (x, y + 3), (cx - 3, y)],   # 핑크: 하트
        None,                                                                          # 골드: 고리
        [(cx, y), (x + 11, y + 12), (x + 1, y + 12)],                                  # 진홍: 불꽃
        [(x + 1, y + 11), (x + 2, y + 3), (x + 11, y + 1), (x + 10, y + 9)],           # 그린: 잎
    ][i]
    if shape is None:
        d.ellipse((x, y, x + 12, y + 12), fill=col, outline=dark)
        d.ellipse((x + 4, y + 4, x + 8, y + 8), fill=dark)
    else:
        d.polygon(shape, fill=col, outline=dark)
    d.point((cx - 2, cy - 2), fill=light)
    d.point((cx - 1, cy - 3), fill=light)


def _badge_case(d, x, y, run: dict):
    """지금 있는 지방의 배지 8개"""
    mod = {"kanto": None, "johto": J, "hoenn": HO}[A.region_of(run["loc"])]
    order, palette = (mod.GYM_ORDER, mod.BADGE_RGB) if mod else (K.GYM_ORDER, BADGE_RGB)
    _panel(d, (x, y, x + 8 * 16 + 6, y + 18), fill=(56, 48, 72), edge=(24, 20, 32))
    for i, g in enumerate(order):
        _badge(d, x + 4 + i * 16, y + 3, i, g in run["badges"], palette)


def _facility_lines(run: dict) -> list[tuple[str, tuple]]:
    """필드 화면 오른쪽에 쓸 장소 정보 (글자, 색)"""
    L = A.loc(run)
    out = []
    if A.in_league(run):
        out.append((f"다음 상대: {run['chain'][0]['name']}", (176, 48, 48)))
    if L.get("home"):
        out.append(("집 · 쉬면 회복", (200, 64, 64)))
    if L.get("center"):
        out.append(("포켓몬센터", (216, 64, 72)))
    if L.get("mart"):
        out.append(("프렌들리숍" + (" · 백화점" if L.get("dept") else ""), (56, 112, 208)))
    gkey, ok, _ = A.gym_state(run)
    if gkey:
        g = A.GYMS[gkey]
        state = "배지 획득" if gkey in run["badges"] else ("도전 가능" if ok else "문이 잠김")
        out.append((f"체육관 · 관장 {g['leader']} ({state})", (160, 96, 24)))
    if L.get("league"):
        league, ok, _ = A.league_info(run)
        out.append((f"{A.REGIONS[league]['n']} 포켓몬 리그" + (" · 도전 가능" if ok else " · 배지 8개 필요"), (176, 136, 24)))
    if L.get("trainers"):
        left = len(A.trainers_left(run))
        out.append((f"트레이너 {left}명 남음" if left else "트레이너 모두 이김", (72, 72, 88)))
    if L.get("wild"):
        lo = min(w[1] for w in L["wild"])
        hi = max(w[2] for w in L["wild"])
        out.append((f"야생 포켓몬 Lv.{lo}~{hi}", (56, 136, 72)))
    if A.legend_available(run):
        out.append(("강한 기운이 느껴진다...", (136, 72, 168)))
    if A.gift_available(run) or A.gift_choices(run):
        out.append(("받을 수 있는 포켓몬이 있다", (200, 96, 152)))
    return out


def _hero(get_trainer: TrainerGetter | None, key: str) -> Image.Image | None:
    img = None
    if get_trainer:
        try:
            img = get_trainer(key)
        except Exception:
            img = None
    if img is None:
        return None
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def field(run: dict, get_sprite: SpriteGetter | None = None, get_trainer: TrainerGetter | None = None) -> bytes:
    L = A.loc(run)
    im, d = _canvas()
    _background(d, L["bg"])
    d.rectangle((0, 0, W, 20), fill=(40, 56, 88))
    _text(d, (8, 4), L["n"], font=BOLD, fill=(255, 232, 120), shadow=(16, 24, 40))
    money = f"₽{run.get('money', 0):,}"
    _text(d, (W - _tw(money) - 8, 6), money, fill=(255, 255, 255), shadow=(16, 24, 40))
    # 왼쪽: 주인공 + 맨 앞 포켓몬
    _platform(d, 56, 112, 44, 10, L["bg"])
    hero = _hero(get_trainer, HR.of(run))   # 도트가 깨지지 않게 줄이지 않고 원래 크기로
    hero_right = 0
    if hero:
        im.paste(hero, (6, 118 - hero.height), hero)
        hero_right = 6 + hero.width
    if run["party"]:
        sp = _sprite(get_sprite, E.lead(run)["sid"], False)
        cx = max(56, hero_right + sp.width // 2 - 6) if hero else 56
        im.paste(sp, (cx - sp.width // 2, 116 - sp.height), sp)
    cap = "없음" if A.level_cap(run) >= E.MAX_LEVEL else f"Lv.{A.level_cap(run)}"
    tag = f"레벨 제한 {cap}" + (f" · 박스 {len(run['box'])}" if run.get("box") else "")
    _text(d, (8, 24), tag, font=SMALL, fill=(255, 255, 255), shadow=(16, 24, 40))
    # 오른쪽: 배지 + 장소 정보
    _badge_case(d, 178, 24, run)
    lines = _facility_lines(run)[:6]
    _panel(d, (112, 46, 314, 46 + 6 + max(1, len(lines)) * 11), fill=(248, 248, 240))
    for i, (s, col) in enumerate(lines):
        _text(d, (118, 49 + i * 11), s, font=SMALL, fill=col)
    if not lines:
        _text(d, (118, 49), "조용한 곳이다.", font=SMALL, fill=(88, 88, 104))
    _party_strip(im, d, run, get_sprite, 8, 126)
    return _finish(im, d)


# ---------- 모험: 관동 지도 ----------
KIND_RGB = {"town": (232, 80, 72), "route": (248, 224, 152), "cave": (136, 104, 80), "building": (152, 120, 200),
            "water": (120, 184, 248)}


def kanto_map(run: dict) -> bytes:
    """지금 있는 지방(관동/성도)의 지도"""
    region = A.region_of(run["loc"])
    LOCS = {k: L for k, L in A.LOC.items() if L.get("region", "kanto") == region}
    im, d = _canvas((64, 128, 200))
    for y in range(0, H, 6):   # 바다 물결
        for x in range((y // 6 % 2) * 6, W, 12):
            d.line((x, y, x + 3, y), fill=(80, 144, 216))
    here = run["loc"]
    near = [k for k in A.LOC[here]["links"] if k in LOCS]
    seen = set()
    for k, L in LOCS.items():   # 길
        for nb in L["links"]:
            if (nb, k) in seen or nb not in LOCS:
                continue
            seen.add((k, nb))
            ok = A.can_enter(run, k)[0] and A.can_enter(run, nb)[0]
            a, b = L["pos"], LOCS[nb]["pos"]
            d.line((*a, *b), fill=(48, 64, 96), width=5)
            d.line((*a, *b), fill=(248, 232, 176) if ok else (120, 136, 168), width=3)
    for k, L in LOCS.items():   # 장소
        x, y = L["pos"]
        ok = A.can_enter(run, k)[0]
        col = KIND_RGB[L["kind"]] if ok else (112, 120, 144)
        edge = (40, 32, 48)
        if L["kind"] == "town":
            d.rectangle((x - 5, y - 5, x + 5, y + 5), fill=col, outline=edge)
            d.line((x - 4, y - 4, x + 4, y - 4), fill=tuple(min(255, c + 60) for c in col))
        else:
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=col, outline=edge)
        if k == here:
            d.rectangle((x - 8, y - 8, x + 8, y + 8), outline=(255, 255, 255))
            d.rectangle((x - 9, y - 9, x + 9, y + 9), outline=(232, 48, 48))
    # 이름표: 지금 장소와 바로 갈 수 있는 곳만 (서로 겹치지 않는 자리를 찾아서)
    taken = [(0, 0, W, 17)]
    for k in [here] + list(near):
        L = LOCS[k]
        x, y = L["pos"]
        ok = A.can_enter(run, k)[0]
        name = L["n"] if ok or k == here else L["n"] + " (잠김)"
        w, h = _tw(name, SMALL), 9
        spots = [(x - w // 2, y + 8), (x - w // 2, y - 8 - h), (x + 9, y - h // 2), (x - 9 - w, y - h // 2)]
        best = None
        for tx, ty in spots:
            tx = min(max(2, tx), W - w - 2)
            ty = min(max(18, ty), H - h - 2)
            box = (tx - 1, ty - 1, tx + w + 1, ty + h + 1)
            if not any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in taken):
                best = (tx, ty, box)
                break
        if best is None:
            tx, ty = min(max(2, x - w // 2), W - w - 2), min(max(18, y + 8), H - h - 2)
            best = (tx, ty, (tx, ty, tx + w, ty + h))
        taken.append(best[2])
        fill = (255, 232, 120) if k == here else ((255, 255, 255) if ok else (184, 192, 208))
        _text(d, (best[0], best[1] - 1), name, font=SMALL, fill=fill, shadow=(16, 24, 40))
    d.rectangle((0, 0, W, 15), fill=(40, 56, 88))
    _text(d, (6, 1), f"{A.REGIONS[region]['n']} 지도", font=BOLD, fill=(255, 232, 120), shadow=(16, 24, 40))
    info = f"{A.REGIONS[region]['n']} 배지 {len(A.region_badges(run, region))}/8"
    _text(d, (W - _tw(info, SMALL) - 6, 1), info, font=SMALL, fill=(255, 255, 255), shadow=(16, 24, 40))
    return _finish(im, d)


# ---------- 메뉴 카드 ----------
def _pokeball(d, cx, cy, r, top=(224, 64, 56)):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(248, 248, 248), outline=INK, width=2)
    d.chord((cx - r, cy - r, cx + r, cy + r), 180, 360, fill=top, outline=INK, width=2)
    d.line((cx - r, cy, cx + r, cy), fill=INK, width=2)
    d.ellipse((cx - r // 3, cy - r // 3, cx + r // 3, cy + r // 3), fill=(248, 248, 248), outline=INK, width=2)
    d.ellipse((cx - r + 3, cy - r + 4, cx - r + 7, cy - r + 8), fill=tuple(min(255, c + 70) for c in top))


def _menu_bg(d):
    for y in range(H):   # 남색 그라데이션 + 사선 무늬
        t = (y // 4 * 4) / H
        d.line((0, y, W, y), fill=(int(36 + 24 * t), int(48 + 30 * t), int(96 + 40 * t)))
    for x in range(-H, W, 16):
        d.line((x, H, x + H, 0), fill=(52, 68, 124), width=3)


def menu(info: dict, get_sprite: SpriteGetter | None = None) -> bytes:
    """메뉴 카드. info: {"name", "run"(모험 또는 None), "dex", "daily", "weekly", "public"}"""
    im, d = _canvas()
    _menu_bg(d)
    run, public = info.get("run"), info.get("public")
    # 제목
    _pokeball(d, 22, 20, 13)
    _text(d, (40, 4), "포켓몬 모험", font=TITLE, fill=(255, 220, 72), shadow=(40, 32, 96))
    sub = "관동 · 성도 · 호연"
    _text(d, (W - _tw(sub, SMALL) - 8, 10), sub, font=SMALL, fill=(208, 220, 255), shadow=(24, 32, 72))

    # 왼쪽: 트레이너 카드
    _panel(d, (8, 38, 166, 140), fill=(248, 244, 232), edge=(40, 40, 64))
    d.rectangle((9, 39, 165, 52), fill=(232, 88, 72))
    if public:
        _text(d, (14, 40), "트레이너 카드", font=BOLD, fill=(255, 255, 255), shadow=(150, 40, 32))
        lines = ["버튼을 눌러 시작해요!", "모험: 배지 8개 → 챔피언",
                 "관동 챔피언이 되면 성도로,", "성도 챔피언이 되면 호연으로"]
        for i, t in enumerate(lines):
            _text(d, (14, 58 + i * 13), t, font=SMALL, fill=INK)
    else:
        name = info.get("name", "트레이너")
        while _tw(name, BOLD) > 100 and len(name) > 2:
            name = name[:-1]
        _text(d, (14, 40), name, font=BOLD, fill=(255, 255, 255), shadow=(150, 40, 32))
        dex = f"도감 {info.get('dex', 0)}"
        _text(d, (160 - _tw(dex, SMALL), 41), dex, font=SMALL, fill=(255, 240, 220), shadow=(150, 40, 32))
        rows = [("관동", K.GYM_ORDER, BADGE_RGB, "hof"), ("성도", J.GYM_ORDER, J.BADGE_RGB, "hof2"),
                ("호연", HO.GYM_ORDER, HO.BADGE_RGB, "hof3")]
        for i, (rn, order, pal, hk) in enumerate(rows):
            y = 57 + i * 19
            _text(d, (14, y), rn, font=SMALL, fill=(88, 72, 64))
            for j, g in enumerate(order):
                _badge(d, 40 + j * 14, y - 1, j, bool(run) and g in run["badges"], pal)
            if run and run.get(hk):   # 챔피언: 금색 별
                cx, cy = 158, y + 6
                pts = []
                for k in range(10):
                    r = 6 if k % 2 == 0 else 3
                    ang = -1.5708 + k * 0.6283
                    pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
                d.polygon(pts, fill=(248, 200, 48), outline=(150, 100, 16))
        where = f"지금: {A.loc(run)['n']}" if run else "아직 모험을 시작하지 않았어요"
        _text(d, (14, 116), where, font=SMALL, fill=(64, 64, 88))
        if run:
            cap = A.level_cap(run)
            t = f"레벨 제한 {'없음' if cap >= E.MAX_LEVEL else cap} · 박스 {len(run.get('box', []))}"
            _text(d, (14, 127), t, font=SMALL, fill=(96, 96, 112))

    # 오른쪽: 파티 (없으면 스타팅 후보)
    _panel(d, (172, 38, 312, 140), fill=(232, 240, 248), edge=(40, 40, 64))
    d.rectangle((173, 39, 311, 52), fill=(72, 120, 200))
    party = run["party"] if run else []
    _text(d, (178, 40), "파티" if party else "함께 떠날 포켓몬", font=BOLD, fill=(255, 255, 255), shadow=(32, 56, 120))
    sids = [(m["sid"], m["lv"]) for m in party] or [(1, None), (4, None), (7, None), (252, None), (393, None), (906, None)]
    for i, (sid, lv) in enumerate(sids[:6]):
        cx, cy = 196 + (i % 3) * 45, 56 + (i // 3) * 42
        d.ellipse((cx - 16, cy + 26, cx + 16, cy + 32), fill=(200, 212, 228))
        sp = _sprite(get_sprite, sid, False)
        sp.thumbnail((40, 40), Image.NEAREST)
        im.paste(sp, (cx - sp.width // 2, cy + 30 - sp.height), sp)
        if lv:
            t = f"Lv{lv}"
            _text(d, (cx - _tw(t) // 2, cy + 31), t, fill=INK)

    # 아래: 모드 3칸
    tiles = [("모험", "이어서 하기" if run else "새로 시작", (64, 168, 96)),
             ("데일리", info.get("daily", "하루 한 번 도전"), (232, 152, 48)),
             ("주간 챌린지", info.get("weekly", "이번 주 규칙"), (176, 96, 208))]
    tw = (W - 16 - 8) // 3
    for i, (title, desc, col) in enumerate(tiles):
        x0 = 8 + i * (tw + 4)
        dark = tuple(max(0, c - 70) for c in col)
        d.rounded_rectangle((x0, 146, x0 + tw, 186), radius=4, fill=col, outline=dark, width=2)
        d.rectangle((x0 + 3, 149, x0 + tw - 3, 151), fill=tuple(min(255, c + 50) for c in col))
        _text(d, (x0 + 7, 152), title, font=BOLD, fill=(255, 255, 255), shadow=dark)
        while _tw(desc, SMALL) > tw - 12 and len(desc) > 2:
            desc = desc[:-1]
        _text(d, (x0 + 7, 170), desc, font=SMALL, fill=(255, 255, 240), shadow=dark)
    return _finish(im, d)


# ---------- 주인공 고르기 ----------
HERO_COLS, HERO_ZOOM = 5, 2
HERO_CELL_W, HERO_CELL_H = 188, 236


def heroes(selected: str, get_trainer: TrainerGetter | None = None) -> bytes:
    """역대 주인공을 원래 도트 그대로(정수배) 늘어놓고 이름을 붙인다. 고른 주인공은 노란 칸"""
    sel = HR.valid(selected)
    rows = (len(HR.HEROES) + HERO_COLS - 1) // HERO_COLS
    w, top = HERO_COLS * HERO_CELL_W + 20, 70
    h = top + rows * HERO_CELL_H + 10
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 4):   # 남색 그라데이션
        t = y / h
        d.rectangle((0, y, w, y + 3), fill=(int(36 + 24 * t), int(48 + 30 * t), int(96 + 40 * t)))
    _, name, gen, game = next(x for x in HR.HEROES if x[0] == sel)
    d.text((24, 10), "주인공 고르기", font=TITLE, fill=(255, 220, 72), stroke_width=3, stroke_fill=(40, 32, 96))
    info = f"지금: {name} · {gen}세대 {game}"
    d.text((w - 24 - BOLD.getlength(info), 24), info, font=BOLD, fill=(255, 255, 255), stroke_width=3,
           stroke_fill=(40, 32, 96))
    for i, (key, hname, hgen, hgame) in enumerate(HR.HEROES):
        r, c = divmod(i, HERO_COLS)
        x0, y0 = 10 + c * HERO_CELL_W, top + r * HERO_CELL_H
        box = (x0 + 4, y0 + 4, x0 + HERO_CELL_W - 4, y0 + HERO_CELL_H - 4)
        if key == sel:
            d.rounded_rectangle(box, radius=10, fill=(255, 236, 160), outline=(232, 168, 48), width=5)
        else:
            d.rounded_rectangle(box, radius=10, fill=(64, 84, 148), outline=(84, 104, 172), width=2)
        foot = y0 + HERO_CELL_H - 68
        img = _hero(get_trainer, key)
        if img is None:   # 아직 못 받은 그림: 실루엣 자리
            d.ellipse((x0 + 54, foot - 110, x0 + HERO_CELL_W - 54, foot - 20), fill=(48, 60, 112))
        else:
            k = HERO_ZOOM if max(img.width, img.height) * HERO_ZOOM <= HERO_CELL_W - 16 else 1
            img = img.resize((img.width * k, img.height * k), Image.NEAREST)
            im.paste(img, (x0 + HERO_CELL_W // 2 - img.width // 2, foot - img.height), img)
        ink, sub = (INK, (120, 96, 48)) if key == sel else ((255, 255, 255), (200, 212, 248))
        d.text((x0 + HERO_CELL_W // 2 - BOLD.getlength(hname) / 2, foot + 4), hname, font=BOLD, fill=ink)
        info = f"{hgen}세대 · {hgame}"
        d.text((x0 + HERO_CELL_W // 2 - SMALL.getlength(info) / 2, foot + 36), info, font=SMALL, fill=sub)
    return _png(im)


# ---------- 도감 ----------
GENS = [("관동", 1, 151), ("성도", 152, 251), ("호연", 252, 386), ("신오", 387, 493), ("하나", 494, 649),
        ("칼로스", 650, 721), ("알로라", 722, 809), ("가라르", 810, 905), ("팔데아", 906, 1025)]
DEX_COLS, DEX_ROWS = 6, 4
DEX_PAGE = DEX_COLS * DEX_ROWS


def dex_pages(gen: int) -> int:
    _, a, b = GENS[gen - 1]
    return (b - a + 1 + DEX_PAGE - 1) // DEX_PAGE


def dex_page_sids(gen: int, page: int) -> list[int]:
    _, a, b = GENS[gen - 1]
    start = a + page * DEX_PAGE
    return list(range(start, min(b, start + DEX_PAGE - 1) + 1))


def dex_page(gen: int, page: int, caught: dict[int, int], get_sprite: SpriteGetter | None = None,
             trainer: str = "") -> bytes:
    """세대별 도감 한 쪽 (6x4). 잡은 포켓몬은 그림과 이름, 못 잡은 포켓몬은 ?"""
    region, a, b = GENS[gen - 1]
    im, d = _canvas((200, 48, 48))
    # 도감 기계 느낌: 빨간 몸체 + 화면
    for y in range(0, H, 6):
        d.line((0, y, W, y), fill=(188, 40, 40))
    d.rectangle((0, 0, W, 19), fill=(152, 24, 32))
    d.ellipse((5, 3, 17, 15), fill=(120, 200, 248), outline=(255, 255, 255), width=2)
    d.ellipse((8, 5, 11, 8), fill=(220, 244, 255))
    for i, col in enumerate(((248, 88, 72), (248, 216, 72), (96, 200, 96))):
        d.ellipse((22 + i * 8, 6, 27 + i * 8, 11), fill=col, outline=(80, 16, 16))
    title = f"{gen}세대 {region} 도감"
    _text(d, (50, 3), title, font=BOLD, fill=(255, 255, 255), shadow=(96, 16, 24))
    got = sum(1 for sid in range(a, b + 1) if sid in caught)
    info = f"{got}/{b - a + 1}  {page + 1}/{dex_pages(gen)}쪽"
    _text(d, (W - _tw(info, SMALL) - 6, 5), info, font=SMALL, fill=(255, 236, 200), shadow=(96, 16, 24))
    # 화면
    d.rounded_rectangle((4, 22, W - 5, H - 5), radius=5, fill=(56, 64, 72), outline=(40, 16, 16), width=2)
    d.rectangle((8, 26, W - 9, H - 9), fill=(216, 232, 216))
    cw, ch = (W - 18) // DEX_COLS, (H - 36) // DEX_ROWS
    for i, sid in enumerate(dex_page_sids(gen, page)):
        cx0 = 9 + (i % DEX_COLS) * cw
        cy0 = 27 + (i // DEX_COLS) * ch
        own = sid in caught
        box = (cx0 + 1, cy0 + 1, cx0 + cw - 2, cy0 + ch - 2)
        d.rounded_rectangle(box, radius=3, fill=(248, 252, 240) if own else (184, 200, 184),
                            outline=(120, 144, 120))
        num = f"{sid:03d}" if sid < 1000 else str(sid)
        _text(d, (cx0 + 3, cy0 + 1), num, fill=(72, 96, 72) if own else (112, 128, 112))
        if own:
            sp = _sprite(get_sprite, sid, False)
            sp.thumbnail((30, 30), Image.NEAREST)
            im.paste(sp, (cx0 + cw // 2 - sp.width // 2, cy0 + ch - 11 - sp.height), sp)
            name = D.name(sid)
            while _tw(name, SMALL) > cw - 4 and len(name) > 1:
                name = name[:-1]
            _text(d, (cx0 + cw // 2 - _tw(name, SMALL) // 2, cy0 + ch - 12), name, font=SMALL, fill=INK)
            if caught[sid] > 1:
                c = f"x{caught[sid]}"
                _text(d, (cx0 + cw - 3 - _tw(c), cy0 + 1), c, fill=(200, 96, 48))
        else:
            mx, my = cx0 + cw // 2, cy0 + ch // 2 - 1
            d.ellipse((mx - 9, my - 9, mx + 9, my + 9), fill=(152, 168, 152), outline=(120, 140, 120))
            _text(d, (mx - _tw("?", BOLD) // 2, my - 7), "?", font=BOLD, fill=(240, 248, 240))
    return _finish(im, d)


# ---------- 파티 화면 ----------
def party(run: dict, get_sprite: SpriteGetter | None = None, title: str = "파티", mark: list[int] | None = None) -> bytes:
    """6칸 파티 화면. mark: 고를 수 있는 칸 (나머지는 흐리게)"""
    im, d = _canvas((56, 80, 120))
    for y in range(0, H, 8):   # 줄무늬 배경
        d.line((0, y, W, y), fill=(64, 88, 128))
    d.rectangle((0, 0, W, 18), fill=(40, 56, 88))
    _text(d, (6, 3), title, font=BOLD, fill=(255, 232, 120), shadow=(16, 24, 40))
    money = f"₽{run.get('money', 0):,}"
    _text(d, (W - _tw(money, BOLD) - 6, 3), money, font=BOLD, fill=(255, 255, 255), shadow=(16, 24, 40))
    for i in range(E.MAX_PARTY):
        x0, y0 = 6 + (i % 2) * 156, 23 + (i // 2) * 56
        box = (x0, y0, x0 + 152, y0 + 52)
        if i >= len(run["party"]):
            d.rounded_rectangle(box, radius=5, outline=(96, 120, 160))
            continue
        m = run["party"][i]
        dim = mark is not None and i not in mark
        fainted = m["hp"] <= 0
        fill = (200, 200, 200) if fainted else ((255, 244, 208) if i == run["active"] else (248, 248, 240))
        if dim:
            fill = tuple(int(c * 0.7) for c in fill)
        d.rounded_rectangle(box, radius=5, fill=fill, outline=(216, 168, 72) if i == run["active"] else PANEL_EDGE, width=2 if i == run["active"] else 1)
        _text(d, (x0 + 5, y0 + 3), f"{i + 1}", fill=(160, 120, 40))
        sp = _sprite(get_sprite, m["sid"], False)
        sp.thumbnail((44, 44), Image.NEAREST)
        if fainted or dim:
            sp = sp.convert("LA").convert("RGBA")
        im.paste(sp, (x0 + 30 - sp.width // 2, y0 + 49 - sp.height), sp)
        name = D.name(m["sid"])
        _text(d, (x0 + 56, y0 + 4), name, font=BOLD, fill=(96, 96, 104) if dim else INK)
        lv = f"Lv.{m['lv']}"
        _text(d, (x0 + 148 - _tw(lv), y0 + 4), lv)
        sx = x0 + 56
        if fainted:
            _text(d, (sx, y0 + 17), "기절", fill=(200, 48, 48))
        else:
            _status_tag(d, sx, y0 + 18, m.get("status"))
        mh = E.max_hp(m)
        _hp_gauge(d, sx, y0 + 30, 90, m["hp"] / mh)
        hp = f"{m['hp']}/{mh}"
        _text(d, (x0 + 148 - _tw(hp), y0 + 39), hp)
    return _finish(im, d)
