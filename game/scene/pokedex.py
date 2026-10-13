"""그림 도감 (game/scene 패키지)"""

from .. import data as D

from .base import (
    BOLD,
    H,
    INK,
    IconGetter,
    SMALL,
    SpriteGetter,
    TINY,
    W,
    _canvas,
    _finish,
    _icon,
    _put,
    _shrink,
    _text,
    _tw,
)

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
             trainer: str = "", get_icon: "IconGetter | None" = None) -> bytes:
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
        if own:   # 번호는 아이콘 위에 (글자는 그림을 다 붙인 뒤에 쓰므로 가려지지 않는다)
            d.texts.append(((cx0 + 3, cy0), num, TINY, (72, 96, 72), (248, 252, 240)))
        else:
            _text(d, (cx0 + 3, cy0 + 1), num, fill=(112, 128, 112))
        if own:
            sp = _icon(get_icon, get_sprite, sid)   # 작은 칸에는 메뉴 아이콘 (2배로 선명하게)
            _put(im, d, sp, cx0 + cw // 2, cy0 + ch - 11, cw - 4, ch - 12)
            name, nf = _shrink(D.name(sid), cw - 4, (SMALL, TINY))
            _text(d, (cx0 + cw // 2 - _tw(name, nf) // 2, cy0 + ch - 12), name, font=nf, fill=INK)
            if caught[sid] > 1:
                c = f"x{caught[sid]}"
                _text(d, (cx0 + cw - 3 - _tw(c), cy0 + 1), c, fill=(200, 96, 48))
        else:
            mx, my = cx0 + cw // 2, cy0 + ch // 2 - 1
            d.ellipse((mx - 9, my - 9, mx + 9, my + 9), fill=(152, 168, 152), outline=(120, 140, 120))
            _text(d, (mx - _tw("?", BOLD) // 2, my - 7), "?", font=BOLD, fill=(240, 248, 240))
    return _finish(im, d)
