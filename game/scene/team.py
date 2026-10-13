"""파티 포켓몬 상태창과 파티 화면 (game/scene 패키지)"""

from .. import data as D
from .. import engine as E

from .base import (
    BOLD,
    FONT,
    H,
    INK,
    PANEL_EDGE,
    SCALE,
    SMALL,
    STAT_RGB,
    SpriteGetter,
    TINY,
    TYPE_RGB,
    W,
    _GAUGE_FRAME,
    _canvas,
    _exp_gauge,
    _finish,
    _gauge_rows,
    _hp_gauge,
    _panel,
    _put,
    _shrink,
    _sprite,
    _status_tag,
    _text,
    _tw,
    _type_pill,
)

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
    _put(im, d, sp, 58, 116, 100, 92, kmax=2 * SCALE)
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
        pp_w = _tw(f"PP {p['pp'][i]}/{E.max_pp(p, i)}") + 6
        mname, mf = _shrink(m["n"], 146 - pp_w, (BOLD, FONT, SMALL, TINY))
        _text(d, (x0 + 5, y0 + 2 + (BOLD.size - mf.size) // 6), mname, font=mf)
        pp = f"PP {p['pp'][i]}/{E.max_pp(p, i)}"
        _text(d, (x0 + 148 - _tw(pp), y0 + 2), pp, fill=(200, 48, 48) if p["pp"][i] == 0 else INK)
        _type_pill(d, x0 + 5, y0 + 13, m["t"])
        info = f"{'물리' if m['c'] == 0 else '특수'} {m['p']}" + (f" 명중{m['a']}" if m["a"] and m["a"] < 100 else "")
        _text(d, (x0 + 148 - _tw(info), y0 + 14), info)
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
        if fainted or dim:
            sp = sp.convert("LA").convert("RGBA")
        _put(im, d, sp, x0 + 30, y0 + 49, 48, 44)
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
