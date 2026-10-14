"""게임·도감·기록 저장 (Neon Postgres, asyncpg).

- DATABASE_URL이 없으면 메모리에만 저장한다 (로컬 테스트용, 재시작하면 사라짐).
- 진행 중인 게임, 도감, 이번 데일리·주간 결과는 시작할 때 메모리에 올려 두고,
  디스코드에 먼저 응답한 뒤 DB에 쓴다. (Neon 무료 플랜은 5분 쉬면 잠들어서 첫 쿼리가 느릴 수 있는데,
  디스코드는 3초 안에 응답해야 해서)
- Neon '-pooler' 주소(PgBouncer)에서는 prepared statement 캐시를 꺼야 한다.
- 게임은 (유저, 모드)마다 하나: adventure(관동 모험) / daily(데일리) / challenge(주간 챌린지)
"""

import asyncio
import json
import logging
import os
from urllib.parse import urlsplit, urlunsplit

import asyncpg

log = logging.getLogger("pokebot.db")

_pool: asyncpg.Pool | None = None
_runs: dict[tuple[int, str], dict | None] = {}          # (유저, 모드) -> 진행 중인 게임
_dex: dict[int, dict[int, int]] = {}                       # 유저 -> {종 번호: 잡은 횟수}
_results: dict[tuple[str, str], dict[int, dict]] = {}     # (모드, 기간) -> {유저: 결과}
_locks: dict[int, asyncio.Lock] = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    user_id BIGINT PRIMARY KEY,
    state JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS games (
    user_id BIGINT NOT NULL,
    mode TEXT NOT NULL,
    state JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, mode)
);
CREATE TABLE IF NOT EXISTS trainers (
    user_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    best_wave INT NOT NULL DEFAULT 0,
    best_starter INT,
    best_final INT,
    runs INT NOT NULL DEFAULT 0,
    clears INT NOT NULL DEFAULT 0,
    total_waves INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS dex (
    user_id BIGINT NOT NULL,
    species INT NOT NULL,
    caught INT NOT NULL DEFAULT 1,
    first_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, species)
);
CREATE TABLE IF NOT EXISTS results (
    mode TEXT NOT NULL,
    period TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    wave INT NOT NULL,
    starter INT,
    final INT,
    clear BOOLEAN NOT NULL DEFAULT FALSE,
    at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (mode, period, user_id)
);
"""


def lock(user_id: int) -> asyncio.Lock:
    """버튼 연타로 같은 게임이 동시에 진행되지 않게 유저마다 잠금"""
    return _locks.setdefault(user_id, asyncio.Lock())


def _dsn(raw: str) -> str:
    parts = urlsplit(raw)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))   # sslmode 등 libpq 전용 옵션 제거


async def init():
    global _pool
    url = os.getenv("DATABASE_URL")
    if not url:
        log.warning("DATABASE_URL이 없어요. 메모리에만 저장합니다 (재시작하면 사라져요).")
        return
    _pool = await asyncpg.create_pool(
        _dsn(url), ssl="require", min_size=1, max_size=4,
        statement_cache_size=0, max_inactive_connection_lifetime=120, command_timeout=15,
    )
    async with _pool.acquire() as con:
        await con.execute(SCHEMA)
        # 예전 runs 테이블(일반 게임) → games 로 옮기기 (원래 데이터는 남겨 둠)
        await con.execute("""INSERT INTO games(user_id, mode, state)
                             SELECT user_id, 'normal', state FROM runs ON CONFLICT DO NOTHING""")
        await con.execute("DELETE FROM runs")
        await con.execute("DELETE FROM games WHERE mode='normal'")   # 예전 로그라이크 일반 게임 (모험으로 바뀜)
        games = await con.fetch("SELECT user_id, mode, state FROM games")
        dex = await con.fetch("SELECT user_id, species, caught FROM dex")
        res = await con.fetch("SELECT * FROM results WHERE at > now() - interval '15 days'")
    for r in games:
        _runs[(r["user_id"], r["mode"])] = json.loads(r["state"])
    for r in dex:
        _dex.setdefault(r["user_id"], {})[r["species"]] = r["caught"]
    for r in res:
        _results.setdefault((r["mode"], r["period"]), {})[r["user_id"]] = dict(r)
    log.info("DB 연결 완료 (진행 중인 게임 %d개, 도감 %d명, 최근 결과 %d개)", len(games), len(_dex), len(res))


async def _retry(fn):
    """Neon이 잠들었다 깨면서 끊긴 연결이면 한 번 더 시도"""
    for attempt in range(2):
        try:
            async with _pool.acquire() as con:
                return await fn(con)
        except (asyncpg.PostgresConnectionError, ConnectionError, OSError) as e:
            if attempt:
                raise
            log.warning("DB 연결 재시도: %s", e)


# ---------- 게임 ----------
async def get_run(user_id: int, mode: str = "adventure") -> dict | None:
    # 시작할 때 진행 중인 게임을 모두 불러왔으니, 메모리에 없으면 게임이 없는 것 (DB를 기다리지 않음)
    return _runs.get((user_id, mode))


def cache_run(user_id: int, mode: str, run: dict | None):
    _runs[(user_id, mode)] = run


_dirty: set[tuple[int, str]] = set()     # DB에 아직 못 쓴 (유저, 모드)
_writing: set[tuple[int, str]] = set()   # 지금 쓰는 중인 (유저, 모드)


async def _flush(key: tuple[int, str]):
    """(유저, 모드)의 지금 상태를 DB에 쓴다. 저장은 응답 뒤 백그라운드로 여러 번 겹쳐 오는데,
    한 키에 한 번에 하나씩, 항상 '마지막 상태'로 쓴다 (늦게 끝난 옛 저장이 새 상태를 덮거나,
    끝난 게임을 되살리지 않게)."""
    if not _pool:
        return
    _dirty.add(key)
    if key in _writing:   # 쓰고 있는 쪽이 끝나고 한 번 더 쓴다
        return
    _writing.add(key)
    uid, mode = key
    try:
        while key in _dirty:
            _dirty.discard(key)
            run = _runs.get(key)
            try:
                if run is None:
                    await _retry(lambda con: con.execute("DELETE FROM games WHERE user_id=$1 AND mode=$2", uid, mode))
                else:
                    data = json.dumps(run, ensure_ascii=False)
                    await _retry(lambda con: con.execute(
                        "INSERT INTO games(user_id, mode, state, updated_at) VALUES($1, $2, $3::jsonb, now()) "
                        "ON CONFLICT (user_id, mode) DO UPDATE SET state=EXCLUDED.state, updated_at=now()",
                        uid, mode, data))
            except Exception:
                _dirty.add(key)   # 다음 저장 때 다시 쓴다
                raise
    finally:
        _writing.discard(key)


async def save_run(user_id: int, mode: str, run: dict):
    _runs[(user_id, mode)] = run
    await _flush((user_id, mode))


async def delete_run(user_id: int, mode: str):
    """모험 초기화"""
    _runs[(user_id, mode)] = None
    await _flush((user_id, mode))


def adventure_rows() -> list[tuple[int, dict, int]]:
    """모험 랭킹용: (유저, 모험 상태, 도감 수)"""
    return [(uid, run, len(_dex.get(uid, {}))) for (uid, mode), run in _runs.items() if mode == "adventure" and run]


async def finish_run(user_id: int, mode: str, name: str, run: dict, cleared_waves: int, clear: bool):
    """데일리·챌린지가 끝나면 게임을 지우고 기간 결과를 남긴다. (모험은 끝나지 않고 계속 저장)"""
    _runs[(user_id, mode)] = None
    party = run.get("party") or [run.get("p")]
    starter, final = run["starter"], max(party, key=lambda m: m["lv"])["sid"]   # 가장 레벨이 높은 포켓몬

    period = run.get("seed") or ""
    row = {"mode": mode, "period": period, "user_id": user_id, "name": name, "wave": cleared_waves,
           "starter": starter, "final": final, "clear": clear}
    _results.setdefault((mode, period), {})[user_id] = row
    await _flush((user_id, mode))   # 게임 지우기
    if _pool:
        await _retry(lambda con: con.execute(
            """INSERT INTO results(mode, period, user_id, name, wave, starter, final, clear)
               VALUES($1, $2, $3, $4, $5, $6, $7, $8)
               ON CONFLICT (mode, period, user_id) DO UPDATE SET
                 wave=GREATEST(results.wave, EXCLUDED.wave), name=EXCLUDED.name""",
            mode, period, user_id, name, cleared_waves, starter, final, clear))


def has_result(mode: str, period: str, user_id: int) -> dict | None:
    """이번 기간(오늘·이번 주)에 이미 끝낸 기록"""
    return _results.get((mode, period), {}).get(user_id)


def period_board(mode: str, period: str, limit: int = 10) -> list[dict]:
    rows = list(_results.get((mode, period), {}).values())
    return sorted(rows, key=lambda r: (-r["wave"], r["name"]))[:limit]


# ---------- 도감 ----------
def dex(user_id: int) -> dict[int, int]:
    return _dex.get(user_id, {})


async def add_dex(user_id: int, species: list[int]):
    if not species:
        return
    d = _dex.setdefault(user_id, {})
    for s in species:
        d[s] = d.get(s, 0) + 1
    if _pool:
        await _retry(lambda con: con.executemany(
            """INSERT INTO dex(user_id, species) VALUES($1, $2)
               ON CONFLICT (user_id, species) DO UPDATE SET caught = dex.caught + 1""",
            [(user_id, s) for s in species]))
