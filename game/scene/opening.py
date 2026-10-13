"""모험 시작: 소개, 주인공 고르기, 스타팅 고르기 (game/scene 패키지)"""

from PIL import Image
from PIL import ImageDraw

from .. import data as D
from .. import heroes as HR

from .base import (
    BOLD,
    FONT,
    H,
    INK,
    MSG_BG,
    MSG_EDGE,
    PANEL,
    PANEL_EDGE,
    SMALL,
    STAT_RGB,
    SpriteGetter,
    TITLE,
    TYPE_RGB,
    TrainerGetter,
    W,
    _PEOPLE_DIR,
    _canvas,
    _finish,
    _hero,
    _menu_bg,
    _panel,
    _png,
    _sprite,
    _text,
    _tw,
    _type_pill,
)

# ---------- 주인공 고르기 ----------
HERO_COLS, HERO_ZOOM = 5, 2


HERO_CELL_W, HERO_CELL_H = 188, 236


INTRO_LINES = [
    "태초마을에서 출발해 관동의 도로와 동굴을 지나며 포켓몬을 잡고 키워요.",
    "체육관 8곳의 배지를 모아 석영고원에서 사천왕과 챔피언에게 도전해요.",
    "관동 챔피언이 되면 파티와 PC를 그대로 데리고 성도 지방으로 떠날 수 있어요.",
    "배지가 늘수록 더 높은 레벨까지 말을 들어요. 지면 마지막 포켓몬센터로 돌아가요.",
    "진행은 계속 저장되고, /초기화로 처음부터 다시 할 수 있어요.",
]


INTRO_DOT = [(232, 88, 72), (240, 176, 48), (88, 168, 96), (88, 144, 232), (176, 112, 208)]


def _wrap_px(s: str, font, width: float) -> list[str]:
    """큰 그림용: 글자 폭(픽셀)에 맞춰 띄어쓰기 단위로 줄바꿈"""
    lines, cur = [], ""
    for word in s.split(" "):
        t = f"{cur} {word}" if cur else word
        if font.getlength(t) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def _intro_text_w(w: int) -> int:
    return w - 180 - 72   # 안내 칸 안쪽 글자 폭


def _intro_height(w: int) -> int:
    n = sum(len(_wrap_px(t, FONT, _intro_text_w(w))) for t in INTRO_LINES)
    return 224 + n * 36 + len(INTRO_LINES) * 8 + 60


def _intro(im: Image.Image, d: ImageDraw.ImageDraw, w: int):
    """오박사 연구소 설명 (위쪽): 오박사 대사 창 + 모험 안내"""
    d.text((24, 10), "오박사 연구소", font=TITLE, fill=(255, 220, 72), stroke_width=3, stroke_fill=(40, 32, 96))
    # 오박사 (필드 도트를 6배)
    try:
        oak = Image.open(_PEOPLE_DIR / "prof_oak.png").convert("RGBA")
        oak = oak.resize((oak.width * 6, oak.height * 6), Image.NEAREST)
        im.paste(oak, (40, 84), oak)
    except FileNotFoundError:
        pass
    # 대사 창 (게임 메시지 창 모양)
    x0, y0, x1 = 160, 84, w - 20
    d.rounded_rectangle((x0, y0, x1, y0 + 120), radius=10, fill=MSG_EDGE)
    d.rounded_rectangle((x0 + 6, y0 + 6, x1 - 6, y0 + 114), radius=8, fill=MSG_BG, outline=(24, 32, 56), width=2)
    say = "오오, 왔구나! 함께 떠날 포켓몬을 골라 보거라. 먼 지방에서 온 포켓몬도 있단다."
    d.text((x0 + 24, y0 + 16), "오박사", font=BOLD, fill=(255, 220, 120))
    for k, line in enumerate(_wrap_px(say, FONT, x1 - x0 - 48)[:2]):
        d.text((x0 + 24, y0 + 50 + k * 32), line, font=FONT, fill=(248, 248, 248))
    # 안내 (색 점 + 글)
    y = y0 + 140
    wrapped = [_wrap_px(t, FONT, _intro_text_w(w)) for t in INTRO_LINES]
    d.rounded_rectangle((x0, y - 12, x1, y - 12 + sum(len(ls) * 36 + 8 for ls in wrapped) + 20),
                        radius=10, fill=PANEL, outline=PANEL_EDGE, width=2)
    for lines, col in zip(wrapped, INTRO_DOT):
        d.ellipse((x0 + 20, y + 10, x0 + 36, y + 26), fill=col, outline=INK, width=2)
        for line in lines:
            d.text((x0 + 50, y), line, font=FONT, fill=INK)
            y += 36
        y += 8
    tip = "다음으로 넘어가서 주인공과 함께 떠날 포켓몬을 골라요"
    d.text((x0 + 4, y + 18), tip, font=SMALL, fill=(208, 220, 255))


def _navy(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """큰 그림용 남색 그라데이션 바탕"""
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 4):
        t = y / h
        d.rectangle((0, y, w, y + 3), fill=(int(36 + 24 * t), int(48 + 30 * t), int(96 + 40 * t)))
    return im, d


def intro() -> bytes:
    """모험 시작 1단계 그림: 오박사 연구소 설명"""
    w = HERO_COLS * HERO_CELL_W + 20
    im, d = _navy(w, _intro_height(w))
    _intro(im, d, w)
    return _png(im)


def heroes(selected: str, get_trainer: TrainerGetter | None = None) -> bytes:
    """역대 주인공을 원래 도트 그대로(정수배) 늘어놓고 이름을 붙인다. 고른 주인공은 노란 칸"""
    sel = HR.valid(selected)
    rows = (len(HR.HEROES) + HERO_COLS - 1) // HERO_COLS
    w, top = HERO_COLS * HERO_CELL_W + 20, 70
    im, d = _navy(w, top + rows * HERO_CELL_H + 10)
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


# ---------- 스타팅 고르기 ----------
STAT_KO = ["HP", "공격", "방어", "특공", "특방", "스피드"]


def starters(region: str, sids: list[int], get_sprite: SpriteGetter | None = None) -> bytes:
    """스타팅 후보 3마리를 카드 한 장씩 (그림·이름·타입·종족값)"""
    im, d = _canvas()
    _menu_bg(d)
    _text(d, (8, 3), f"스타팅 고르기 · {region}", font=BOLD, fill=(255, 220, 72), shadow=(40, 32, 96))
    hint = "아래 버튼으로 골라요"
    _text(d, (W - _tw(hint, SMALL) - 8, 5), hint, font=SMALL, fill=(208, 220, 255), shadow=(24, 32, 72))
    cw = (W - 16) // 3
    for i, sid in enumerate(sids[:3]):
        x0, y0, x1, y1 = 6 + i * (cw + 2), 20, 6 + i * (cw + 2) + cw, H - 4
        t1 = D.types(sid)[0]
        _panel(d, (x0, y0, x1, y1), fill=(248, 244, 232), edge=(40, 40, 64))
        d.rectangle((x0 + 1, y0 + 1, x1 - 1, y0 + 4), fill=TYPE_RGB[t1])
        cx = (x0 + x1) // 2
        d.ellipse((cx - 30, 78, cx + 30, 88), fill=(220, 216, 200))
        sp = _sprite(get_sprite, sid, False)
        im.paste(sp, (cx - sp.width // 2, 84 - sp.height), sp)
        name = D.name(sid)
        _text(d, (cx - _tw(name, BOLD) // 2, 90), name, font=BOLD)
        types = D.types(sid)
        widths = [_tw(D.TYPE_KO[t]) + 8 for t in types]
        tx = cx - (sum(widths) + 3 * (len(types) - 1)) // 2
        for t, w in zip(types, widths):
            _type_pill(d, tx, 104, t)
            tx += w + 3
        st = D.SPECIES[sid]["s"]
        total = f"종족값 {sum(st)}"
        _text(d, (cx - _tw(total, SMALL) // 2, 118), total, font=SMALL, fill=(96, 88, 80))
        for k, (label, v) in enumerate(zip(STAT_KO, st)):
            y = 130 + k * 9
            _text(d, (x0 + 4, y - 2), label, font=SMALL, fill=(88, 80, 72))
            bx0, bx1 = x0 + 30, x1 - 22   # 숫자는 카드 오른쪽 끝에 맞춘다 (세 자리도 들어가게)
            d.rectangle((bx0, y + 1, bx1, y + 5), fill=(216, 212, 200))
            d.rectangle((bx0, y + 1, bx0 + max(1, round((bx1 - bx0) * min(1, v / 150))), y + 5), fill=STAT_RGB[k])
            _text(d, (x1 - 3 - _tw(str(v)), y - 1), str(v), fill=INK)
    return _finish(im, d)
