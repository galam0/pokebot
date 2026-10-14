"""공통 도구: 캔버스·글자·도트 글꼴·게이지·스프라이트 붙이기·배경·그림 파일 읽기 (game/scene 패키지)"""

import io
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from pathlib import Path
from typing import Callable

from .. import data as D
from .. import engine as E


W, H = 320, 192


SCALE = 3


_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"


# 글자는 3배 크기 그림에 쓰므로 실제 크기도 3배 (좌표는 작은 캔버스 기준)
FONT = ImageFont.truetype(str(_FONT_DIR / "NanumGothicBold.ttf"), 27)


BOLD = ImageFont.truetype(str(_FONT_DIR / "NanumGothicExtraBold.ttf"), 29)


SMALL = ImageFont.truetype(str(_FONT_DIR / "NanumGothicBold.ttf"), 22)


TITLE = ImageFont.truetype(str(_FONT_DIR / "NanumGothicExtraBold.ttf"), 52)


TINY = ImageFont.truetype(str(_FONT_DIR / "NanumGothicBold.ttf"), 18)


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
    d.bigs = []    # 1·2배로 붙일 도트 그림 (작은 캔버스의 3배와 안 맞으니 큰 그림에 바로)
    return im, d


def _layer() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """투명한 위 칸 (배틀 GIF에서 스프라이트 위에 덮는 정보창·메시지 창)"""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.texts = []
    d.bigs = []
    return im, d


def _enlarge(im: Image.Image, d: ImageDraw.ImageDraw) -> Image.Image:
    """3배로 키우고 모아 둔 글자를 쓴다"""
    big = im.resize((W * SCALE, H * SCALE), Image.NEAREST)
    for img, xy in getattr(d, "bigs", []):
        big.paste(img, xy, img)
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


def _shrink(s: str, max_w: int, fonts=None) -> tuple[str, ImageFont.FreeTypeFont]:
    """칸 폭에 맞게: 글꼴을 차례로 줄여 보고, 가장 작은 글꼴로도 넘치면 끝을 …로"""
    fonts = fonts or (FONT, SMALL, TINY)
    for f in fonts:
        if _tw(s, f) <= max_w:
            return s, f
    f = fonts[-1]
    while _tw(s + "…", f) > max_w and len(s) > 1:
        s = s[:-1]
    return s + "…", f


def _wrap_tw(s: str, max_w: int, font=None) -> list[str]:
    """작은 캔버스 폭(max_w)에 맞춰 줄바꿈 (띄어쓰기 단위, 긴 낱말은 글자 단위)"""
    font = font or FONT
    lines, cur = [], ""
    for word in s.split(" "):
        t = f"{cur} {word}" if cur else word
        if _tw(t, font) <= max_w:
            cur = t
            continue
        if cur:
            lines.append(cur)
        cur = word
        while _tw(cur, font) > max_w and len(cur) > 1:   # 띄어쓰기 없이 긴 낱말
            k = len(cur)
            while k > 1 and _tw(cur[:k], font) > max_w:
                k -= 1
            lines.append(cur[:k])
            cur = cur[k:]
    return lines + ([cur] if cur else [])


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


def _put(im: Image.Image, d, img: Image.Image, cx: int, foot: int, w: int, h: int, kmax: int = SCALE):
    """도트 그림을 칸(w x h, 작은 캔버스 기준)에 맞는 가장 큰 정수배로 붙인다. 발(아래 가운데)이 (cx, foot).
    큰 그림 기준 1·2·3·…배라 흐려지거나 도트가 빠지지 않는다. 3의 배수면 작은 캔버스에, 아니면 큰 그림에 바로."""
    k = next((k for k in range(kmax, 0, -1) if img.width * k <= w * SCALE and img.height * k <= h * SCALE), 1)
    if k % SCALE == 0:
        m = k // SCALE
        img = img.resize((img.width * m, img.height * m), Image.NEAREST) if m > 1 else img
        im.paste(img, (cx - img.width // 2, foot - img.height), img)
        return
    big = img.resize((img.width * k, img.height * k), Image.NEAREST)
    d.bigs.append((big, (cx * SCALE - big.width // 2, foot * SCALE - big.height)))


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


# ---------- 상태창 ----------
STAT_RGB = [(232, 72, 64), (240, 160, 48), (240, 208, 64), (96, 144, 240), (120, 200, 96), (240, 104, 168)]


ItemGetter = Callable[[str], Image.Image | None]


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
        if m["hp"] <= 0:
            sp = sp.convert("LA").convert("RGBA")
        _put(im, d, sp, sx + slot // 2, y0 + 36, slot - 6, 32)
        lv = f"Lv.{m['lv']}"
        _text(d, (sx + slot // 2 - _tw(lv) // 2, y0 + 37), lv)
        _mini_gauge(d, sx + 5, y0 + 50, slot - 10, m["hp"] / E.max_hp(m))


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


# ---------- 모험: 파이어레드 맵 장면 ----------
_ASSETS = Path(__file__).resolve().parents[2] / "assets"


_img_cache: dict[str, Image.Image | None] = {}


_MAP_KEEP = 10   # 맵 그림은 크다 (다 풀면 190MB+): 최근 것만 들고 있는다 (무료 서버 메모리 512MB)
_map_keys: list[str] = []


def _asset(rel: str) -> Image.Image | None:
    if rel not in _img_cache:
        f = _ASSETS / rel
        _img_cache[rel] = Image.open(f).convert("RGBA") if f.exists() else None
    if rel.startswith("maps/") and _img_cache[rel] is not None:
        if rel in _map_keys:
            _map_keys.remove(rel)
        _map_keys.append(rel)
        while len(_map_keys) > _MAP_KEEP:
            _img_cache.pop(_map_keys.pop(0), None)
    return _img_cache[rel]


# ---------- PC 박스 ----------
IconGetter = Callable[[int], Image.Image | None]


def _icon(get_icon: IconGetter | None, get_sprite: SpriteGetter | None, sid: int) -> Image.Image:
    img = None
    if get_icon:
        try:
            img = get_icon(sid)
        except Exception:
            img = None
    if img is not None:
        img = img.convert("RGBA")
        bbox = img.getbbox()
        img = img.crop(bbox) if bbox else img
    else:
        img = _sprite(get_sprite, sid, False)
    return img


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


_PEOPLE_DIR = Path(__file__).resolve().parents[2] / "assets" / "people"
