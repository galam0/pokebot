"""포켓몬·아이템 스프라이트 받아오기 (PokeAPI sprites, 메모리 캐시).

- 그림은 처음 한 번만 받고 메모리에 둔다 (한 장 1~3KB).
- 화면을 그릴 때는 ensure()로 잠깐만(기본 1초) 기다리고, 못 받으면 빈 자리로 그린다.
  → 디스코드 3초 제한을 넘지 않게.
- 보상을 고르는 동안 다음 상대 그림을 prefetch()로 미리 받아 둔다.
"""

import asyncio
import io
import logging

import aiohttp
from PIL import Image, ImageOps

log = logging.getLogger("pokebot.sprites")

BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites"
_cache: dict[str, Image.Image | None] = {}     # 키 -> 이미지 (None = 없는 그림)
_pending: dict[str, asyncio.Task] = {}
_session: aiohttp.ClientSession | None = None


def _key_url(kind: str, name) -> list[tuple[str, str]]:
    if kind == "front":
        return [(f"front:{name}", f"{BASE}/pokemon/{name}.png")]
    if kind == "back":
        return [(f"back:{name}", f"{BASE}/pokemon/back/{name}.png")]
    return [(f"item:{name}", f"{BASE}/items/{name}.png")]


async def _session_get() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6))
    return _session


async def _fetch(key: str, url: str):
    try:
        s = await _session_get()
        async with s.get(url) as resp:
            if resp.status != 200:
                _cache[key] = None
                return
            data = await resp.read()
        _cache[key] = Image.open(io.BytesIO(data)).convert("RGBA")
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


def prefetch(sids=(), backs=(), items=()):
    """기다리지 않고 미리 받기 시작"""
    for sid in sids:
        _start("front", sid)
    for sid in backs:
        _start("back", sid)
        _start("front", sid)   # 뒷모습이 없을 때 앞모습을 뒤집어 쓴다
    for name in items:
        _start("item", name)


async def ensure(sids=(), backs=(), items=(), timeout: float = 1.0):
    """필요한 그림을 최대 timeout초까지만 기다린다"""
    tasks = []
    for sid in sids:
        tasks += _start("front", sid)
    for sid in backs:
        tasks += _start("back", sid) + _start("front", sid)
    for name in items:
        tasks += _start("item", name)
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
