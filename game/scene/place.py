"""모험 필드 화면: 파이어레드 맵 장면, 장소 정보, PC 박스, 관동 지도 (game/scene 패키지)"""

import json
from PIL import Image
from PIL import ImageDraw

from .. import adventure as A
from .. import engine as E
from .. import heroes as HR
from ..text import josa

from .badge import (_badge_case)
from .base import (
    BOLD,
    FONT,
    H,
    INK,
    IconGetter,
    SMALL,
    SpriteGetter,
    TrainerGetter,
    W,
    _ASSETS,
    _asset,
    _background,
    _canvas,
    _finish,
    _hero,
    _icon,
    _panel,
    _party_strip,
    _platform,
    _put,
    _shrink,
    _sprite,
    _text,
    _tw,
    _wrap_tw,
)

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


_places: dict | None = None


OVERWORLD = {"red": "red_normal", "leaf": "green_normal", "brendan": "brendan", "may": "may"}


DIALOG_BG, DIALOG_EDGE, DIALOG_INNER = (248, 248, 248), (88, 96, 112), (160, 200, 216)


def place_data(loc_key: str, kind: str = "field") -> dict | None:
    """장소의 맵 장면 정보 (assets/maps/places.json, tools/build_places.py로 만든다). 맵 그림이 없으면 None"""
    global _places
    if _places is None:
        f = _ASSETS / "maps" / "places.json"
        _places = json.loads(f.read_text()) if f.exists() else {}
    sc = (_places.get(loc_key) or {}).get(kind)
    if not sc or _asset(f"maps/{sc['map']}.png") is None:
        return None
    return sc


def _walker(name: str, face: str) -> Image.Image | None:
    """걷는 그림 세 칸 [아래, 위, 왼쪽] 중 하나 (오른쪽은 왼쪽을 뒤집는다)"""
    strip = _asset(f"people/{name}.png")
    if strip is None:
        return None
    fw = strip.width // 3
    i = {"down": 0, "up": 1, "left": 2, "right": 2}[face]
    fr = strip.crop((i * fw, 0, i * fw + fw, strip.height))
    return fr.transpose(Image.FLIP_LEFT_RIGHT) if face == "right" else fr


def _overworld(hero: str) -> str | None:
    """주인공의 필드 그림 (원본만): 파이어레드·에메랄드 넷, 플라티나·하트골드 넷. 없으면 None (팻말 옆 얼굴 그림)"""
    if hero in OVERWORLD:
        return OVERWORLD[hero]
    return f"hero_{hero}" if _asset(f"people/hero_{hero}.png") is not None else None


def _face(get_trainer: TrainerGetter | None, hero: str) -> Image.Image | None:
    """주인공 그림의 머리 부분 (위쪽 정사각형)"""
    img = _hero(get_trainer, hero)
    if img is None:
        return None
    return img.crop((0, 0, img.width, min(img.height, img.width)))


def _dialog(d, lines: list[tuple[str, tuple]]):
    """파이어레드풍 하얀 대화창 (3줄, 많으면 두 칸으로)"""
    d.rounded_rectangle((2, 146, W - 3, H - 3), radius=4, fill=DIALOG_BG, outline=DIALOG_EDGE, width=1)
    d.rounded_rectangle((4, 148, W - 5, H - 5), radius=3, outline=DIALOG_INNER, width=1)
    if len(lines) <= 3:   # 한 칸: 길면 다음 줄로
        rows = [(r, col) for s, col in lines for r in _wrap_tw(josa(s), W - 28)]
        if len(rows) <= 3:
            for r, (s, col) in enumerate(rows):
                _text(d, (12, 152 + r * 12), s, fill=col)
            return
    for i, (s, col) in enumerate(lines[:6]):   # 두 칸: 칸마다 글씨를 줄여서 맞춘다
        c, r = divmod(i, 3)
        s, f = _shrink(josa(s), W // 2 - 18)
        _text(d, (12 + c * (W // 2 - 4), 152 + r * 12), s, font=f, fill=col)


def map_scene(run: dict, kind: str = "field", lines: list[tuple[str, tuple]] | None = None,
              get_trainer: TrainerGetter | None = None) -> bytes | None:
    """파이어레드 원본 맵 위에 주인공·사람들을 세우고, 장소 팻말과 대화창을 얹는다. 맵이 없으면 None"""
    sc = place_data(run["loc"], kind)
    if sc is None:
        return None
    full = _asset(f"maps/{sc['map']}.png").copy()
    for name, x, y, face in sc["npcs"]:   # 사람들 (발이 칸 아래에 오게)
        img = _walker(name, face)
        if img:
            full.alpha_composite(img, (x * 16, y * 16 + 16 - img.height))
    px, py, face = sc["player"]
    walker = _overworld(HR.of(run))
    me = _walker(walker, face) if walker else None
    if me:   # 32칸짜리(4세대) 그림도 발이 칸 아래, 가운데에 오게
        full.alpha_composite(me, (px * 16 + 8 - me.width // 2, py * 16 + 16 - me.height + (4 if me.width > 16 else 0)))
    # 카메라: 주인공이 화면 가운데보다 조금 위에 (아래는 대화창)
    cx, cy = px * 16 + 8, py * 16 + 8 + 22
    x0 = (full.width - W) // 2 if full.width <= W else max(0, min(full.width - W, cx - W // 2))
    y0 = (full.height - H) // 2 if full.height <= H else max(0, min(full.height - H, cy - H // 2))
    im, d = _canvas()
    im.paste(full.crop((x0, y0, x0 + W, y0 + H)).convert("RGB"), (0, 0))
    if full.width < W or full.height < H:   # 작은 방: 바깥은 까맣게
        bx, by = max(0, -x0), max(0, -y0)
        mask = Image.new("L", (W, H), 255)
        ImageDraw.Draw(mask).rectangle((bx, by, bx + full.width - 1, by + full.height - 1), fill=0)
        im.paste((0, 0, 0), (0, 0), mask)
    # 장소 팻말
    L = A.loc(run)
    title = {"center": f"{L['n']} 포켓몬센터", "mart": f"{L['n']} " + ("백화점" if L.get("dept") else "프렌들리숍"),
             "gym": f"{L['n']} 체육관", "home": "우리 집"}.get(kind, L["n"])
    sx = 4
    if not me:   # 걷는 그림이 없는 주인공: 팻말 옆에 얼굴 그림
        face_img = _face(get_trainer, HR.of(run))
        if face_img:
            d.rounded_rectangle((4, 4, 30, 30), radius=4, fill=(248, 248, 240), outline=(72, 88, 120), width=1)
            _put(im, d, face_img, 17, 29, 24, 24)
            sx = 34
    title, tf = _shrink(title, W - 100 - (sx - 4), (BOLD, FONT, SMALL))
    tw = _tw(title, tf)
    d.rounded_rectangle((sx, 4, sx + 12 + tw, 22), radius=3, fill=(248, 248, 240), outline=(72, 88, 120), width=1)
    d.rectangle((sx + 2, 6, sx + 4, 20), fill=(232, 88, 72))
    _text(d, (sx + 7, 6 + (BOLD.size - tf.size) // 6), title, font=tf)
    # 오른쪽 위: 돈 · 배지
    region = A.region_of(run["loc"])
    info = f"₽{run.get('money', 0):,}"
    badges = f"배지 {len(A.region_badges(run, region))}/8"
    bw = max(_tw(info), _tw(badges, SMALL)) + 12
    d.rounded_rectangle((W - 4 - bw, 4, W - 4, 32), radius=3, fill=(248, 248, 240), outline=(72, 88, 120), width=1)
    _text(d, (W - 10 - _tw(info), 7), info)
    _text(d, (W - 10 - _tw(badges, SMALL), 18), badges, font=SMALL, fill=(96, 96, 112))
    _dialog(d, lines if lines is not None else (_facility_lines(run) or [("조용한 곳이다.", (88, 88, 104))]))
    return _finish(im, d)


PC_COLS, PC_ROWS = 5, 5


def pc(run: dict, page: int = 0, get_icon: IconGetter | None = None, get_sprite: SpriteGetter | None = None,
       per_page: int = 25) -> bytes:
    """PC 박스: 파이어레드 숲 배경지 위에 박스 포켓몬, 왼쪽에 지금 파티"""
    im, d = _canvas((88, 136, 200))
    for y in range(0, H, 8):   # 파란 줄무늬 바탕 (박스 화면 뒤쪽)
        d.rectangle((0, y, W, y + 3), fill=(104, 152, 216))
    box = run.get("box", [])
    pages = max(1, (len(box) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = box[page * per_page:(page + 1) * per_page]
    # 오른쪽: 박스 (배경지 160x144)
    bx, by = 152, 26
    wall = _asset("pc/forest.png")
    if wall:
        im.paste(wall, (bx, by), wall)
    else:
        d.rounded_rectangle((bx, by, bx + 159, by + 143), radius=4, fill=(136, 200, 96))
    label = f"박스 {page + 1}" + (f"/{pages}" if pages > 1 else "") + f" · {len(box)}마리"
    _text(d, (bx + 80 - _tw(label, BOLD) // 2, by + 5), label, font=BOLD, fill=(255, 255, 255), shadow=(40, 88, 40))
    sw, sh = 30, 22
    for i, m in enumerate(chunk):
        r, c = divmod(i, PC_COLS)
        x, y = bx + 6 + c * sw, by + 30 + r * sh
        _put(im, d, _icon(get_icon, get_sprite, m["sid"]), x + sw // 2, y + sh, sw, sh + 8)
    if not chunk:
        _text(d, (bx + 80 - _tw("비어 있어요", BOLD) // 2, by + 80), "비어 있어요", font=BOLD, fill=(40, 88, 40))
    # 왼쪽: 지금 파티 (2줄 x 3)
    d.rounded_rectangle((6, 26, 144, 170), radius=6, fill=(232, 96, 80), outline=(120, 40, 40), width=2)
    _text(d, (14, 30), "지금 파티", font=BOLD, fill=(255, 255, 255), shadow=(120, 40, 40))
    for i in range(E.MAX_PARTY):
        r, c = divmod(i, 2)
        x, y = 12 + c * 66, 46 + r * 40
        d.rounded_rectangle((x, y, x + 60, y + 36), radius=4, fill=(248, 232, 216) if i < len(run["party"]) else
                            (216, 128, 112), outline=(120, 40, 40))
        if i < len(run["party"]):
            m = run["party"][i]
            _put(im, d, _icon(get_icon, get_sprite, m["sid"]), x + 18, y + 32, 34, 30)
            lv = f"Lv.{m['lv']}"
            _text(d, (x + 58 - _tw(lv), y + 26), lv)
    # 제목
    d.rectangle((0, 0, W, 20), fill=(40, 56, 88))
    _text(d, (8, 4), f"{A.loc(run)['n']} PC · 포켓몬 맡기기·데려오기", font=BOLD, fill=(255, 232, 120), shadow=(16, 24, 40))
    _text(d, (8, 176), "맡긴 포켓몬은 회복되고, 지닌 물건은 가방으로 돌아와요.", font=SMALL, fill=(255, 255, 255),
          shadow=(24, 40, 80))
    return _finish(im, d)


def _log_lines(run: dict, n: int = 3) -> list[tuple[str, tuple]]:
    import re
    out = [re.sub(r"\*\*|[\u2190-\u21ff\u2600-\u27bf\u2b00-\u2bff\ufe0f\U0001f000-\U0001faff]", "", x).strip()
           for x in (run.get("log") or [])]
    return [(x, INK) for x in out if x][-n:]


def field(run: dict, get_sprite: SpriteGetter | None = None, get_trainer: TrainerGetter | None = None,
          place: str = "field") -> bytes:
    """모험 필드 화면. 관동은 파이어레드 맵 장면, 맵이 없는 곳(성도·호연 등)은 그린 배경"""
    if place in ("center", "home", "gym"):
        lines = _log_lines(run) or None
    elif place == "mart":
        lines = [("점원: \"어서 오세요! 무엇을 도와드릴까요?\"", INK)]
    else:
        lines = None
    try:
        png = map_scene(run, place, lines, get_trainer) or \
            (map_scene(run, "field", None, get_trainer) if place != "field" else None)
    except Exception:
        png = None
    if png:
        return png
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
