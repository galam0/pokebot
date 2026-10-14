"""메뉴 카드 (game/scene 패키지)"""

import math

from .. import adventure as A
from .. import data as D
from .. import engine as E
from .. import hoenn as HO
from .. import johto as J
from .. import kanto as K

from .badge import (BADGE_RGB, _badge)
from .base import (
    BOLD,
    FONT,
    INK,
    SMALL,
    SpriteGetter,
    TINY,
    TITLE,
    W,
    _canvas,
    _finish,
    _menu_bg,
    _panel,
    _pokeball,
    _put,
    _shrink,
    _sprite,
    _text,
    _tw,
)

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
        name, nf = _shrink(info.get("name", "트레이너"), 100, (BOLD, FONT, SMALL, TINY))
        _text(d, (14, 40 + (BOLD.size - nf.size) // 6), name, font=nf, fill=(255, 255, 255), shadow=(150, 40, 32))
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
    sids = [(D.skey(m), m["lv"]) for m in party] or [(1, None), (4, None), (7, None), (252, None), (393, None), (906, None)]
    for i, (sid, lv) in enumerate(sids[:6]):
        cx, cy = 196 + (i % 3) * 45, 56 + (i // 3) * 42
        d.ellipse((cx - 16, cy + 26, cx + 16, cy + 32), fill=(200, 212, 228))
        sp = _sprite(get_sprite, sid, False)
        _put(im, d, sp, cx, cy + 30, 42, 31)
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
        desc, df = _shrink(desc, tw - 12, (SMALL, TINY))
        _text(d, (x0 + 7, 170), desc, font=df, fill=(255, 255, 240), shadow=dark)
    return _finish(im, d)
