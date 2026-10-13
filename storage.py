"""런·트레이너 기록 저장 (Neon Postgres, asyncpg).

- DATABASE_URL이 없으면 메모리에만 저장한다 (로컬 테스트용, 재시작하면 사라짐).
- 진행 중인 런은 메모리에 캐시하고, 디스코드에 먼저 응답한 뒤 DB에 쓴다.
  (Neon 무료 플랜은 5분 쉬면 잠들어서 첫 쿼리가 느릴 수 있는데, 디스코드는 3초 안에 응답해야 해서)
- Neon '-pooler' 주소(PgBouncer)에서는 prepared statement 캐시를 꺼야 한다.
"""

import asyncio
import json
import logging
import os
from urllib.parse import urlsplit, urlunsplit

import asyncpg

log = logging.getLogger("pokebot.db")

_pool: asyncpg.Pool | None = None
_runs: dict[int, dict | None] = {}          # user_id -> 진행 중인 런 (None = 없음 확인됨)
_memory_trainers: dict[int, dict] = {}       # DB 없을 때만 사용
_locks: dict[int, asyncio.Lock] = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    user_id BIGINT PRIMARY KEY,
    state JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
"""


def lock(user_id: int) -> asyncio.Lock:
    """버튼 연타로 같은 런이 동시에 진행되지 않게 유저마다 잠금"""
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
        rows = await con.fetch("SELECT user_id, state FROM runs")
    # 진행 중인 런을 미리 메모리에 올려두면 버튼을 누를 때 DB를 기다리지 않아요
    for r in rows:
        _runs[r["user_id"]] = json.loads(r["state"])
    log.info("DB 연결 완료 (진행 중인 런 %d개 불러옴)", len(rows))


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


# ---------- 런 ----------
async def get_run(user_id: int) -> dict | None:
    # 시작할 때 진행 중인 런을 모두 불러왔으니, 메모리에 없으면 런이 없는 것 (DB를 기다리지 않음)
    if user_id in _runs or _pool:
        return _runs.get(user_id)
    run = None
    if _pool:
        row = await _retry(lambda con: con.fetchrow("SELECT state FROM runs WHERE user_id=$1", user_id))
        if row:
            run = json.loads(row["state"])
    _runs[user_id] = run
    return run


def cache_run(user_id: int, run: dict | None):
    _runs[user_id] = run


async def save_run(user_id: int, run: dict):
    _runs[user_id] = run
    if _pool:
        await _retry(lambda con: con.execute(
            "INSERT INTO runs(user_id, state, updated_at) VALUES($1, $2::jsonb, now()) "
            "ON CONFLICT (user_id) DO UPDATE SET state=EXCLUDED.state, updated_at=now()",
            user_id, json.dumps(run, ensure_ascii=False)))


async def finish_run(user_id: int, name: str, run: dict, cleared_waves: int, clear: bool):
    """런이 끝나면 런을 지우고 트레이너 기록을 갱신한다."""
    _runs[user_id] = None
    starter, final = run["starter"], run["p"]["sid"]
    if not _pool:
        t = _memory_trainers.setdefault(user_id, {"user_id": user_id, "name": name, "best_wave": 0, "runs": 0, "clears": 0,
                                                  "total_waves": 0, "best_starter": None, "best_final": None})
        t["name"], t["runs"], t["clears"] = name, t["runs"] + 1, t["clears"] + int(clear)
        t["total_waves"] += cleared_waves
        if cleared_waves > t["best_wave"]:
            t.update(best_wave=cleared_waves, best_starter=starter, best_final=final)
        return

    async def q(con):
        async with con.transaction():
            await con.execute("DELETE FROM runs WHERE user_id=$1", user_id)
            await con.execute(
                """INSERT INTO trainers(user_id, name, best_wave, best_starter, best_final, runs, clears, total_waves)
                   VALUES($1, $2, $3, $4, $5, 1, $6, $3)
                   ON CONFLICT (user_id) DO UPDATE SET
                     name=EXCLUDED.name,
                     runs=trainers.runs + 1,
                     clears=trainers.clears + EXCLUDED.clears,
                     total_waves=trainers.total_waves + EXCLUDED.total_waves,
                     best_starter=CASE WHEN EXCLUDED.best_wave > trainers.best_wave THEN EXCLUDED.best_starter ELSE trainers.best_starter END,
                     best_final=CASE WHEN EXCLUDED.best_wave > trainers.best_wave THEN EXCLUDED.best_final ELSE trainers.best_final END,
                     best_wave=GREATEST(trainers.best_wave, EXCLUDED.best_wave),
                     updated_at=now()""",
                user_id, name, cleared_waves, starter, final, int(clear))
    await _retry(q)


async def delete_run(user_id: int):
    _runs[user_id] = None
    if _pool:
        await _retry(lambda con: con.execute("DELETE FROM runs WHERE user_id=$1", user_id))


# ---------- 기록 ----------
async def get_trainer(user_id: int) -> dict | None:
    if not _pool:
        return _memory_trainers.get(user_id)
    row = await _retry(lambda con: con.fetchrow("SELECT * FROM trainers WHERE user_id=$1", user_id))
    return dict(row) if row else None


async def leaderboard(limit: int = 10) -> list[dict]:
    if not _pool:
        return sorted(_memory_trainers.values(), key=lambda t: -t["best_wave"])[:limit]
    rows = await _retry(lambda con: con.fetch(
        "SELECT * FROM trainers WHERE best_wave > 0 ORDER BY best_wave DESC, updated_at ASC LIMIT $1", limit))
    return [dict(r) for r in rows]
