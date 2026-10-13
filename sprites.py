"""포켓몬·아이템 스프라이트 받아오기 (PokeAPI sprites, 메모리 캐시).

- 그림은 처음 한 번만 받고 메모리에 둔다 (한 장 1~3KB).
- 화면을 그릴 때는 ensure()로 잠깐만(기본 1초) 기다리고, 못 받으면 빈 자리로 그린다.
  → 디스코드 3초 제한을 넘지 않게.
- 보상을 고르는 동안 다음 상대 그림을 prefetch()로 미리 받아 둔다.
- 배틀 GIF용 움직이는 스프라이트(쇼다운 GIF)는 프레임 목록 [(그림, ms)]으로 둔다.
- 주인공 그림은 assets/trainers에 있으면 그걸 쓰고, 없으면(6·8·9세대) 쇼다운에서 받는다.
"""

import asyncio
import io
import logging
from collections import deque
from pathlib import Path

import aiohttp
from PIL import Image, ImageOps, ImageSequence

log = logging.getLogger("pokebot.sprites")

BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites"
TRAINER_BASE = "https://play.pokemonshowdown.com/sprites/trainers"
TRAINER_DIR = Path(__file__).resolve().parent / "assets" / "trainers"
TRAINER_REMOTE = {"florian": "florian-s", "juliana": "juliana-s"}   # 쇼다운 파일 이름이 다른 주인공
_cache: dict[str, Image.Image | list | None] = {}     # 키 -> 이미지 또는 GIF 프레임 목록 (None = 없는 그림)
_pending: dict[str, asyncio.Task] = {}
_anim_keys: deque[str] = deque()   # GIF 프레임은 크니까 최근 것만 들고 있는다
ANIM_KEEP = 24
ICON_MAX = 898   # 메뉴 아이콘(8세대)이 있는 마지막 번호. 그 뒤는 앞모습을 줄여 쓴다
_session: aiohttp.ClientSession | None = None


def _key_url(kind: str, name) -> list[tuple[str, str]]:
    if kind == "front":
        return [(f"front:{name}", f"{BASE}/pokemon/{name}.png")]
    if kind == "back":
        return [(f"back:{name}", f"{BASE}/pokemon/back/{name}.png")]
    if kind == "anim":
        return [(f"anim:{name}", f"{BASE}/pokemon/other/showdown/{name}.gif")]
    if kind == "animback":
        return [(f"animback:{name}", f"{BASE}/pokemon/other/showdown/back/{name}.gif")]
    if kind == "icon":
        return [(f"icon:{name}", f"{BASE}/pokemon/versions/generation-viii/icons/{name}.png")]
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
    return [(f.crop(box), ms) for f, ms in frames]


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
        if key not in _pending:
            _pending[key] = asyncio.create_task(_fetch(key, url))
        tasks.append(_pending[key])
    return tasks


def _starts(sids=(), backs=(), items=(), anims=(), anim_backs=(), trainers=(), icons=()) -> list[asyncio.Task]:
    tasks = []
    for sid in icons:
        tasks += _start("icon", sid) + ([] if sid <= ICON_MAX else _start("front", sid))
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
    """PC·목록용 작은 아이콘 (8세대 메뉴 아이콘)"""
    return _cache.get(f"icon:{sid}")
