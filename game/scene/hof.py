"""명예의 전당 카드 (챔피언이 되면 한 번) 와 교환 장면 (game/scene 패키지)"""

import random

from .. import data as D
from .. import heroes as HR

from .base import (
    BOLD,
    FONT,
    H,
    INK,
    SMALL,
    SpriteGetter,
    TrainerGetter,
    W,
    _canvas,
    _finish,
    _hero,
    _put,
    _shrink,
    _sprite,
    _star,
    _text,
    _tw,
)

GOLD = (248, 208, 88)


def _night(d, top=(24, 20, 56), bottom=(72, 36, 96), seed: str = "hof"):
    """밤하늘 그라데이션 + 반짝이"""
    for y in range(H):
        t = (y // 4 * 4) / H
        d.line((0, y, W, y), fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    r = random.Random(seed)
    for _ in range(46):
        x, y = r.randrange(W), r.randrange(H)
        c = r.choice([(255, 244, 200), (200, 220, 255), (255, 255, 255)])
        d.point((x, y), fill=c)
        if r.random() < 0.25:
            d.line((x - 1, y, x + 1, y), fill=c)
            d.line((x, y - 1, x, y + 1), fill=c)


def hall_of_fame(run: dict, get_sprite: SpriteGetter | None = None, get_trainer: TrainerGetter | None = None,
                 region: str = "관동", count: int = 1, trainer: str = "", date: str = "") -> bytes:
    """명예의 전당: 주인공 + 파티 6마리 (이름·레벨·이로치 별)"""
    im, d = _canvas()
    _night(d, seed=f"{region}{count}")
    # 위: 제목 띠
    d.rectangle((0, 0, W, 22), fill=(40, 28, 16))
    d.line((0, 22, W, 22), fill=GOLD)
    title = "명예의 전당"
    _text(d, (8, 4), title, font=BOLD, fill=GOLD, shadow=(64, 40, 8))
    sub = f"{region} 포켓몬 리그 챔피언 · {count}번째 등록"
    _text(d, (W - _tw(sub, SMALL) - 8, 7), sub, font=SMALL, fill=(255, 240, 200))

    # 왼쪽: 주인공 (단상 위)
    d.ellipse((14, 150, 86, 166), fill=(96, 72, 24), outline=GOLD)
    hero = _hero(get_trainer, HR.of(run))
    if hero:
        _put(im, d, hero, 50, 158, 72, 120)
    if trainer:
        name, nf = _shrink(trainer, 84, (BOLD, FONT, SMALL))
        _text(d, (50 - _tw(name, nf) // 2, 168), name, font=nf, fill=(255, 255, 255), shadow=(16, 8, 32))

    # 오른쪽: 파티 3x2
    party = run["party"][:6]
    for i in range(6):
        cx, top = 132 + (i % 3) * 64, 28 + (i // 3) * 76
        box = (cx - 30, top, cx + 30, top + 72)
        d.rounded_rectangle(box, radius=5, fill=(48, 36, 80), outline=(152, 120, 56))
        if i >= len(party):
            continue
        m = party[i]
        d.ellipse((cx - 22, top + 44, cx + 22, top + 52), fill=(80, 64, 112))
        _put(im, d, _sprite(get_sprite, D.skey(m), False), cx, top + 50, 54, 44)
        name, nf = _shrink(D.name(m["sid"]), 56, (FONT, SMALL))
        _text(d, (cx - _tw(name, nf) // 2, top + 52), name, font=nf, fill=(255, 255, 255), shadow=(16, 8, 32))
        lv = f"Lv.{m['lv']}"
        _text(d, (cx - _tw(lv, SMALL) // 2, top + 62), lv, font=SMALL, fill=GOLD)
        if m.get("shiny"):
            _star(d, cx + 24, top + 6, 4)
    if date:
        _text(d, (8, H - 12), date, font=SMALL, fill=(200, 192, 232))
    return _finish(im, d)


def trade(left: tuple[str, dict], right: tuple[str, dict], get_sprite: SpriteGetter | None = None,
          done: bool = False) -> bytes:
    """교환 장면: (트레이너 이름, 포켓몬) 두 쪽. done이면 '교환 완료' (포켓몬이 서로 자리를 바꾼다)"""
    im, d = _canvas()
    _night(d, top=(16, 48, 88), bottom=(56, 112, 152), seed="trade")
    d.rectangle((0, 0, W, 22), fill=(16, 32, 56))
    _text(d, (8, 4), "포켓몬 교환" + (" 완료!" if done else ""), font=BOLD, fill=(255, 255, 255), shadow=(8, 16, 32))
    for side, (who, m) in enumerate((left, right)):
        cx = 80 if side == 0 else 240
        d.rounded_rectangle((cx - 66, 30, cx + 66, 166), radius=6, fill=(24, 40, 72), outline=(120, 168, 224))
        name, nf = _shrink(who, 124, (BOLD, FONT, SMALL))
        _text(d, (cx - _tw(name, nf) // 2, 34), name, font=nf, fill=(200, 224, 255))
        if m is None:
            _text(d, (cx - _tw("고르는 중...", FONT) // 2, 92), "고르는 중...", fill=(160, 184, 216))
            continue
        d.ellipse((cx - 40, 124, cx + 40, 138), fill=(56, 88, 136))
        _put(im, d, _sprite(get_sprite, D.skey(m), False), cx, 132, 96, 80)
        label = f"{D.name(m['sid'])} Lv.{m['lv']}"
        name, nf = _shrink(label, 124, (BOLD, FONT, SMALL))
        _text(d, (cx - _tw(name, nf) // 2, 144), name, font=nf, fill=(255, 255, 255), shadow=(8, 16, 32))
        if m.get("shiny"):
            _star(d, cx + 56, 50, 5)
    # 가운데 화살표
    ac = (255, 232, 120) if done else (200, 216, 240)
    d.polygon([(150, 84), (170, 84), (170, 78), (180, 90), (170, 102), (170, 96), (150, 96)], fill=ac, outline=INK)
    d.polygon([(170, 112), (150, 112), (150, 106), (140, 118), (150, 130), (150, 124), (170, 124)], fill=ac, outline=INK)
    return _finish(im, d)
