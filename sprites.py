"""포켓몬·아이템 스프라이트 받아오기 (포켓몬은 smogon/sprites 블랙·화이트 스타일, 아이템은 PokeAPI, 메모리 캐시).

- 그림은 처음 한 번만 받고 메모리에 둔다 (한 장 1~3KB).
- 화면을 그릴 때는 ensure()로 잠깐만(기본 1초) 기다리고, 못 받으면 빈 자리로 그린다.
  → 디스코드 3초 제한을 넘지 않게.
- 보상을 고르는 동안 다음 상대 그림을 prefetch()로 미리 받아 둔다.
- 배틀 GIF용 움직이는 스프라이트(1~5세대 블랙·화이트 GIF)는 프레임 목록 [(그림, ms)]으로 둔다.
- 주인공 그림은 assets/trainers에 있으면 그걸 쓰고, 없으면(6·8·9세대) 쇼다운에서 받는다.
"""

import asyncio
import io
import json
import logging
from collections import deque
from pathlib import Path

import aiohttp
from PIL import Image, ImageOps, ImageSequence

log = logging.getLogger("pokebot.sprites")

BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites"   # 아이템
SMOGON = "https://raw.githubusercontent.com/smogon/sprites/master/src"     # 포켓몬 (블랙·화이트 스타일)
SHOWDOWN = "https://play.pokemonshowdown.com/sprites"
TRAINER_BASE = "https://play.pokemonshowdown.com/sprites/trainers"
TRAINER_DIR = Path(__file__).resolve().parent / "assets" / "trainers"
TRAINER_REMOTE = {"florian": "florian-s", "juliana": "juliana-s"}   # 쇼다운 파일 이름이 다른 주인공
_cache: dict[str, Image.Image | list | None] = {}     # 키 -> 이미지 또는 GIF 프레임 목록 (None = 없는 그림)
_pending: dict[str, asyncio.Task] = {}
_anim_keys: deque[str] = deque()   # GIF 프레임은 크니까 최근 것만 들고 있는다
ANIM_KEEP = 16
_session: aiohttp.ClientSession | None = None
_sprite_names: dict | None = None


def _names(sid) -> list:
    """[앞모습, 뒷모습, 아이콘] 파일 이름 (game/sprite_names.json, tools/build_sprite_names.py로 만든다)"""
    global _sprite_names
    if _sprite_names is None:
        f = Path(__file__).resolve().parent / "game" / "sprite_names.json"
        _sprite_names = json.loads(f.read_text()) if f.exists() else {}
    return _sprite_names.get(str(sid)) or [None, None, None]


def _mon_url(sid, back: bool) -> str | None:
    """모든 세대를 같은 블랙·화이트 도트 스타일로: smogon/sprites gen5 (없으면 쇼다운 gen5)"""
    name = _names(sid)[1 if back else 0]
    if not name:
        return None
    if name.startswith("sd:"):
        return f"{SHOWDOWN}/{'gen5-back' if back else 'gen5'}/{name[3:]}.png"
    return f"{SMOGON}/sprites/gen5/{name}"


def _key_url(kind: str, name) -> list[tuple[str, str | None]]:
    if kind in ("front", "back"):
        return [(f"{kind}:{name}", _mon_url(name, kind == "back"))]
    if kind in ("anim", "animback"):   # 배틀 GIF는 쇼다운 3D 움직이는 그림 (1~9세대 모두). 없으면 멈춘 그림이 통통 뛴다
        return [(f"{kind}:{name}", f"{BASE}/pokemon/other/showdown/{'back/' if kind == 'animback' else ''}{name}.gif")]
    if kind == "icon":
        icon = _names(name)[2]
        return [(f"icon:{name}", f"{SMOGON}/minisprites/pokemon/gen6/{icon}" if icon else None)]
    if kind == "trainer":
        return [(f"trainer:{name}", f"{TRAINER_BASE}/{TRAINER_REMOTE.get(name, name)}.png")]
    return [(f"item:{name}", f"{BASE}/items/{name}.png")]


async def _session_get() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6))
    return _session


def _frames(img: Image.Image) -> list[tuple[Image.Image, int]]:
    """GIF → [(RGBA 프레임, ms)], 모든 프레임에 공통인 투명 여백은 잘라 둔다 (발 위치가 흔들리지 않게)"""
    frames = [(f.convert("RGBA"), max(20, f.info.get("duration") or 50)) for f in ImageSequence.Iterator(img)]
    boxes = [b for f, _ in frames if (b := f.getbbox())]
    if not boxes:
        return frames
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    frames = [(f.crop(box), ms) for f, ms in frames]
    # 3D 그림은 프레임이 100개 넘는 것도 있다: 배틀 GIF 간격(80ms)·최대 길이(1.6초)로 미리 줄여 메모리를 아낀다
    step, total = 80, min(1600, sum(ms for _, ms in frames))
    out, t, i, acc = [], 0, 0, frames[0][1]
    while t < total:
        while t >= acc and i < len(frames) - 1:
            i += 1
            acc += frames[i][1]
        out.append((frames[i][0], step))
        t += step
    return out or frames[:1]


async def _fetch(key: str, url: str):
    try:
        s = await _session_get()
        async with s.get(url) as resp:
            if resp.status != 200:
                _cache[key] = None
                return
            data = await resp.read()
        img = Image.open(io.BytesIO(data))
        if key.startswith("anim"):
            _cache[key] = _frames(img)
            _anim_keys.append(key)
            while len(_anim_keys) > ANIM_KEEP:
                _cache.pop(_anim_keys.popleft(), None)
        else:
            _cache[key] = img.convert("RGBA")
    except Exception as e:
        log.debug("스프라이트 실패 %s: %s", url, e)   # 다음에 다시 시도
    finally:
        _pending.pop(key, None)


def _start(kind: str, name) -> list[asyncio.Task]:
    tasks = []
    for key, url in _key_url(kind, name):
        if key in _cache:
            continue
        if url is None:   # 그림이 없는 것
            _cache[key] = None
            continue
        if key not in _pending:
            _pending[key] = asyncio.create_task(_fetch(key, url))
        tasks.append(_pending[key])
    return tasks


def _starts(sids=(), backs=(), items=(), anims=(), anim_backs=(), trainers=(), icons=()) -> list[asyncio.Task]:
    tasks = []
    for sid in icons:
        tasks += _start("icon", sid) + _start("front", sid)   # 아이콘을 못 받으면 앞모습으로
    for sid in sids:
        tasks += _start("front", sid)
    for sid in backs:
        tasks += _start("back", sid) + _start("front", sid)   # 뒷모습이 없을 때 앞모습을 뒤집어 쓴다
    for name in items:
        tasks += _start("item", name)
    for sid in anims:
        tasks += _start("anim", sid)
    for sid in anim_backs:
        tasks += _start("animback", sid) + _start("anim", sid)
    for key in trainers:
        if not (TRAINER_DIR / f"{key}.png").exists():
            tasks += _start("trainer", key)
    return tasks


def prefetch(sids=(), backs=(), items=(), anims=(), anim_backs=(), trainers=(), icons=()):
    """기다리지 않고 미리 받기 시작"""
    _starts(sids, backs, items, anims, anim_backs, trainers, icons)


async def ensure(sids=(), backs=(), items=(), anims=(), anim_backs=(), trainers=(), icons=(), timeout: float = 1.0):
    """필요한 그림을 최대 timeout초까지만 기다린다"""
    tasks = _starts(sids, backs, items, anims, anim_backs, trainers, icons)
    if tasks:
        await asyncio.wait(tasks, timeout=timeout)


def get_sprite(sid: int, back: bool) -> Image.Image | None:
    if back:
        img = _cache.get(f"back:{sid}")
        if img is not None:
            return img
        front = _cache.get(f"front:{sid}")
        return ImageOps.mirror(front) if front is not None else None
    return _cache.get(f"front:{sid}")


def get_item(name: str) -> Image.Image | None:
    return _cache.get(f"item:{name}")


def get_anim(sid: int, back: bool) -> list[tuple[Image.Image, int]] | None:
    """움직이는 스프라이트 프레임 [(그림, ms)]. 뒷모습이 없으면 앞모습을 뒤집어 쓴다."""
    if back:
        frames = _cache.get(f"animback:{sid}")
        if frames is not None:
            return frames
        front = _cache.get(f"anim:{sid}")
        return [(ImageOps.mirror(f), ms) for f, ms in front] if front is not None else None
    return _cache.get(f"anim:{sid}")


def get_trainer(key: str) -> Image.Image | None:
    """주인공 그림 (assets/trainers 먼저, 없으면 받아 둔 쇼다운 그림)"""
    k = f"trainer:{key}"
    if k not in _cache:
        f = TRAINER_DIR / f"{key}.png"
        if not f.exists():
            return None
        _cache[k] = Image.open(f).convert("RGBA")
    return _cache.get(k)


def get_icon(sid: int) -> Image.Image | None:
    """PC·도감용 작은 아이콘 (smogon 메뉴 아이콘, 모든 세대 같은 스타일)"""
    return _cache.get(f"icon:{sid}")
