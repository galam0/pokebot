"""배틀 화면(PNG·GIF), 배틀 결과, 트레이너 등장 (game/scene 패키지)"""

import io
import math
from PIL import Image
from PIL import ImageChops
from typing import Callable

from .. import adventure as A
from .. import data as D
from .. import engine as E
from .. import heroes as HR
from .. import trainer_pics as TP
from ..text import josa

from .base import (
    BOLD,
    FONT,
    H,
    INK,
    IconGetter,
    MSG_BG,
    MSG_EDGE,
    PANEL_EDGE,
    SCALE,
    SMALL,
    SpriteGetter,
    TINY,
    TrainerGetter,
    W,
    _asset,
    _background,
    _canvas,
    _enlarge,
    _exp_gauge,
    _finish,
    _hero,
    _hp_gauge,
    _icon,
    _layer,
    _panel,
    _party_balls,
    _platform,
    _png,
    _put,
    _shrink,
    _sprite,
    _status_tag,
    _text,
    _tw,
    _wrap_tw,
)

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
        e_bottom = 48 if e.get("bars", 0) > 1 else 44
        if e.get("status"):   # 상태이상은 HP 게이지 아래 오른쪽 (이름 줄을 넓게 쓰게)
            e_bottom = 52
        _panel(d, (6, 8, 146, e_bottom))
        lv = f"Lv.{e['lv']}"
        tags = _tw("BOSS", BOLD) + 4 if e.get("boss") else 0
        name, nf = _shrink(D.name(e["sid"]), 140 - _tw(lv) - 4 - 12 - tags, (BOLD, FONT, SMALL, TINY))
        _text(d, (12, 12 + (BOLD.size - nf.size) // 6), name, font=nf)
        if e.get("boss"):
            _text(d, (12 + _tw(name, nf) + 4, 12), "BOSS", font=BOLD, fill=(200, 48, 48))
        if e.get("status"):
            _status_tag(d, 140 - _tw(E.STATUS_KO[e["status"]]) - 6, 38, e["status"])
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
    lv = f"Lv.{p['lv']}"
    name, nf = _shrink(D.name(p["sid"]), 308 - _tw(lv) - 4 - 178, (BOLD, FONT, SMALL, TINY))
    _text(d, (178, 102 + (BOLD.size - nf.size) // 6), name, font=nf)
    _text(d, (308 - _tw(lv), 102), lv)
    mh = E.max_hp(p)
    r = p["hp"] / mh
    _hp_gauge(d, 178, 115, 130, r)
    hp_txt = f"{p['hp']}/{mh}"
    _text(d, (308 - _tw(hp_txt), 123), hp_txt)
    if p.get("status"):   # 상태이상은 HP 숫자 바로 왼쪽 (이름 줄을 넓게 쓰게)
        _status_tag(d, 308 - _tw(hp_txt) - _tw(E.STATUS_KO[p["status"]]) - 10, 122, p["status"])
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
            by = e_bottom + 5
            for i in range(b["total"]):
                bx = 12 + i * 9
                d.ellipse((bx, by, bx + 6, by + 6), fill=(248, 248, 248), outline=(40, 40, 48))
                d.chord((bx, by, bx + 6, by + 6), 180, 360, fill=(224, 64, 56) if i < left else (128, 128, 136),
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


BACK_ZOOM = 4   # 큰 그림 기준 (앞모습은 SCALE=3)


def _actor_big(get_sprite, sid: int, back: bool, fainted: bool) -> Image.Image:
    """멈춘 스프라이트를 큰 그림 크기로 (뒷모습은 조금 크게)"""
    img = _sprite(get_sprite, sid, back)
    if fainted:
        img = _fainted(img)
    k = BACK_ZOOM if back else SCALE   # 뒷모습은 모두 같은 배율로 조금 크게 (큰 그림 기준 정수배라 도트가 고르다)
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def _paste_foot(canvas: Image.Image, img: Image.Image, cx: int, foot: int):
    """발(아래 가운데)을 (cx, foot) 큰 그림 좌표에 맞춰 붙인다"""
    canvas.paste(img, (cx - img.width // 2, foot - img.height), img)


AnimGetter = Callable[[int, bool], list | None]   # (종 번호, 뒷모습?) -> [(그림, ms)] 또는 None


def _actor_frames(get_sprite, get_anim, sid: int, back: bool, fainted: bool):
    """(움직이는 프레임 또는 None, 멈춘 그림) — 큰 그림 크기. 쓰러지면 첫 프레임을 흑백으로 멈춘다"""
    still = _actor_big(get_sprite, sid, back, False)
    raw = None
    if get_anim:
        try:
            raw = get_anim(sid, back)
        except Exception:
            raw = None
    if not raw:
        return None, (_actor_big(get_sprite, sid, back, True) if fainted else still)
    frames = _anim_big(raw, still, back)
    if fainted:
        return None, _fainted(frames[0][0])
    return frames, frames[0][0]


def battle(run: dict, get_sprite: SpriteGetter | None = None, message: list[str] | None = None,
           get_anim: "AnimGetter | None" = None) -> bytes:
    """멈춘 배틀 화면. 움직이는 그림을 이미 받아 뒀으면 그 첫 프레임 (뒤에 오는 GIF와 같은 모습)"""
    base, over, actors = _battle_layers(run, message)
    for sid, back, cx, foot, fainted in actors:
        _paste_foot(base, _actor_frames(get_sprite, get_anim, sid, back, fainted)[1], cx * SCALE, foot * SCALE)
    base.paste(over, (0, 0), over)
    return _png(base)


GIF_STEP = 80          # 프레임 간격 (ms)


GIF_MAX_MS = 1600      # 한 바퀴 최대 길이 (프레임이 많으면 만들기·올리기가 느리다)


GIF_IDLE_MS = 1200     # 움직이는 그림이 없을 때 숨쉬기 한 바퀴


ANIM_MAX = {False: (164, 74), True: (150, 100)}   # 움직이는 그림 최대 (너비, 높이): 작은 캔버스 기준 (화면·정보창 밖으로 안 나가게)


def _anim_big(frames: list, still: Image.Image, back: bool = False) -> list[tuple[Image.Image, int]]:
    """움직이는 그림(쇼다운 3D)은 원래 크기 비율이 맞춰져 있어서 고정 배율 (앞 3배·뒤 4배, 멈춘 그림과 같은 배율).
    너무 크면(큰 포켓몬·날개 펄럭임) 칸에 맞게 줄인다"""
    h = max(f.height for f, _ in frames)
    w = max(f.width for f, _ in frames)
    k = BACK_ZOOM if back else SCALE
    mw, mh = (v * SCALE for v in ANIM_MAX[back])
    if w * k <= mw and h * k <= mh:
        return [(f.resize((f.width * k, f.height * k), Image.NEAREST), ms) for f, ms in frames]
    s = min(mw / w, mh / h)
    return [(f.resize((max(1, round(f.width * s)), max(1, round(f.height * s))),
                      Image.NEAREST if s >= 1 else Image.BOX), ms) for f, ms in frames]


def _at(frames: list[tuple[Image.Image, int]], t: int) -> Image.Image:
    t %= sum(ms for _, ms in frames)
    for f, ms in frames:
        if t < ms:
            return f
        t -= ms
    return frames[-1][0]


def _breathe(img: Image.Image, phase: float) -> tuple[Image.Image, int]:
    """멈춘 그림을 통통 뛰게 (그림 크기는 그대로라 도트가 깨지지 않는다). (그림, 위로 뜬 높이: 큰 그림 픽셀)"""
    return img, round(9 * max(0.0, math.sin(phase * 2 * math.pi)))


def battle_gif(run: dict, get_sprite: SpriteGetter | None = None, get_anim: AnimGetter | None = None,
               message: list[str] | None = None) -> bytes:
    """포켓몬이 움직이는 배틀 화면 GIF. 움직이는 스프라이트가 있으면 그걸, 없으면 멈춘 그림이 숨을 쉰다."""
    base, over, actors = _battle_layers(run, message)
    tracks = []   # (프레임 목록 또는 None, 멈춘 그림, cx, foot, 위상, 쓰러짐?)
    for i, (sid, back, cx, foot, fainted) in enumerate(actors):
        frames, still = _actor_frames(get_sprite, get_anim, sid, back, fainted)
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
    rows = [r for s in lines[-3:] for r in _wrap_tw(josa(s), W - 22)]
    for s in rows[-3:]:
        _text(d, (11, y), s, fill=(248, 248, 248), shadow=(16, 24, 40))
        y += 12


# ---------- 배틀 결과 ----------
def battle_result(run: dict, get_icon: "IconGetter | None" = None, get_sprite: SpriteGetter | None = None) -> bytes:
    """배틀이 끝난 뒤: 파티 포켓몬마다 얻은 경험치, 레벨 변화, 경험치 게이지"""
    res = run.get("result") or {}
    im, d = _canvas((48, 64, 104))
    for y in range(0, H, 6):
        d.line((0, y, W, y), fill=(56, 74, 116))
    d.rectangle((0, 0, W, 19), fill=(32, 44, 76))
    _text(d, (8, 3), "배틀 결과", font=BOLD, fill=(255, 220, 72), shadow=(16, 24, 40))
    kind, foe = res.get("kind", "wild"), res.get("name", "")
    if kind in ("wild", "legend"):
        head = f"{foe}을(를) 잡았다!" if res.get("caught") else f"{foe}을(를) 쓰러뜨렸다!"
    else:
        head = f"{foe}에게 이겼다! 상금 {res.get('prize', 0):,}"
    head, hf = _shrink(josa(head), W - 84, (SMALL, TINY))
    _text(d, (W - 8 - _tw(head, hf), 5), head, font=hf, fill=(255, 255, 255), shadow=(16, 24, 40))
    gains = res.get("gains", {})
    cw, chh = (W - 12) // 2, (H - 26) // 3
    for i in range(E.MAX_PARTY):
        c, r = i % 2, i // 2
        x0, y0 = 4 + c * (cw + 4), 23 + r * chh
        x1, y1 = x0 + cw - 2, y0 + chh - 3
        if i >= len(run["party"]):
            d.rounded_rectangle((x0, y0, x1, y1), radius=5, outline=(88, 104, 144))
            continue
        m, g = run["party"][i], gains.get(str(i))
        up = bool(g) and m["lv"] > g["lv0"]
        d.rounded_rectangle((x0, y0, x1, y1), radius=5, fill=(255, 248, 220) if up else (248, 248, 240),
                            outline=(216, 168, 72) if up else PANEL_EDGE, width=2 if up else 1)
        ic = _icon(get_icon, get_sprite, m["sid"])
        if m["hp"] <= 0:
            ic = ic.convert("LA").convert("RGBA")
        _put(im, d, ic, x0 + 20, y0 + 36, 34, 32)
        name, nf = _shrink(D.name(m["sid"]), cw - 90, (BOLD, FONT, SMALL))
        _text(d, (x0 + 40, y0 + 3 + (BOLD.size - nf.size) // 6), name, font=nf)
        lv = f"Lv.{g['lv0']} → {m['lv']}" if up else f"Lv.{m['lv']}"
        _text(d, (x1 - 5 - _tw(lv, SMALL if up else FONT), y0 + 4), lv, font=SMALL if up else FONT,
              fill=(40, 152, 72) if up else INK)
        if g and g["exp"]:
            gain, col = f"+{g['exp']:,} EXP" + (" (학습장치)" if g.get("share") and not g.get("fought") else ""), (40, 104, 200)
        elif m["hp"] <= 0:
            gain, col = "기절함", (176, 64, 64)
        elif g and not g.get("fought"):
            gain, col = "참여 안 함", (112, 112, 128)
        elif m["lv"] >= E.level_cap(m):
            gain, col = "레벨 제한 (말을 듣는 레벨)", (128, 96, 48)
        elif not g:
            gain, col = "이번 배틀 뒤에 들어왔어요", (112, 112, 128)
        else:
            gain, col = "+0 EXP", (112, 112, 128)
        gain, gf = _shrink(gain, cw - 46, (FONT, SMALL, TINY))
        _text(d, (x0 + 40, y0 + 17), gain, font=gf, fill=col)
        need = E.exp_to_next(m)
        _exp_gauge(d, x0 + 40, y0 + 31, cw - 48, (m["exp"] / need) if need else 1)
        if up:
            _text(d, (x0 + 4, y0 + 2), "▲", font=SMALL, fill=(40, 152, 72))
    return _finish(im, d)


# ---------- 트레이너 등장 ----------
def trainer_intro(run: dict, get_trainer: TrainerGetter | None = None) -> bytes:
    """포켓몬이 나오기 전: 상대 트레이너가 서 있고, 대사가 나온다 (주인공은 뒷모습)"""
    b = run.get("battle") or {}
    region = A.region_of(run["loc"])
    im, d = _canvas()
    biome = A.loc(run)["bg"]
    _background(d, biome)
    _platform(d, 236, 86, 52, 12, biome)
    _platform(d, 78, 146, 60, 14, biome)
    foe = _asset(f"battle/{TP.opponent(region, b)}.png") if TP.opponent(region, b) else None
    if foe:
        _put(im, d, foe, 236, 88, 96, 84)
    hero = HR.of(run)
    back = TP.player_back(hero)
    me = _asset(f"battle/{back}.png") if back else None
    if me:   # 원본 뒷모습
        _put(im, d, me, 78, 152, 120, 110, kmax=BACK_ZOOM)
    else:    # 뒷모습 원본이 없는 주인공: 진짜 앞모습 그림이 상대를 보고 선다
        front = _hero(get_trainer, hero)
        if front:
            _put(im, d, front.transpose(Image.FLIP_LEFT_RIGHT), 70, 150, 110, 100)
    # 양쪽 포켓몬 수 (볼)
    def balls(x0, y0, n, alive, right=False):
        d.rounded_rectangle((x0 - 4, y0 - 3, x0 + 6 * 9 + 2, y0 + 9), radius=3, fill=(40, 48, 64), outline=(248, 248, 240))
        for i in range(6):
            bx = x0 + (5 - i if right else i) * 9
            if i < n:
                top = (224, 64, 56) if i < alive else (128, 128, 136)
                d.ellipse((bx, y0, bx + 6, y0 + 6), fill=(248, 248, 248), outline=INK)
                d.chord((bx, y0, bx + 6, y0 + 6), 180, 360, fill=top, outline=INK)
            else:
                d.ellipse((bx + 1, y0 + 1, bx + 5, y0 + 5), outline=(120, 128, 144))
    balls(12, 20, b.get("total", 1), b.get("total", 1))
    balls(254, 118, len(run["party"]), len(E.alive(run)), right=True)
    name = b.get("name", "트레이너")
    lines = [f"{name}이(가) 승부를 걸어왔다!"]
    if b.get("line"):
        lines.append(f"\"{b['line']}\"")
    _message_box(d, lines)
    if run.get("loc"):
        tag = A.loc(run)["n"]
        _text(d, (W - _tw(tag, SMALL) - 6, 2), tag, font=SMALL, fill=(255, 255, 255), shadow=(0, 0, 0))
    return _finish(im, d)
