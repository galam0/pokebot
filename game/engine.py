"""PokeRogue식 게임 배틀 엔진 (디스코드와 무관한 순수 파이썬).

게임 상태는 JSON으로 저장할 수 있는 dict 하나예요.

run = {
  "wave": 1,
  "phase": "battle" | "switch"(기절 후 교체) | "reward" | "replace"(파티 가득) | "learn"(기술 잊기) | "over" | "clear",
  "party": [포켓몬 최대 6], "active": 앞에 나온 번호, "e": 상대 포켓몬, "log": [최근 메시지],
  "rewards": [보상 키], "money": 돈, "bag": {아이템: 개수}, "rerolls": 이번 웨이브 다시 뽑기 횟수,
  "exp_mult": 1.0, "starter": 종 번호, "best_hit": 최고 데미지, "caught": 잡은 수, "turn": 이번 배틀 턴 수,
  "next_e": 다음 웨이브 상대(미리 정함), "pending": 파티가 가득 찼을 때 잡은 포켓몬,
  "after_learn": 기술 잊기가 끝나면 갈 곳 ("reward" | "next_wave"),
}
포켓몬 = {"sid", "lv", "exp"(현재 레벨에서 모은 양), "hp", "iv"[6], "moves"[기술 id], "pp"[남은 PP], "ppx"[포인트업 단계],
         "stg"[공 방 특공 특방 스피드 랭크], "crit"(급소 랭크), "status", "rc"(다음 턴 쉬기), "vit"[6], "boss",
         "held"(지닌 물건), "lock"(구애 아이템으로 묶인 기술 번호), "sash"(이번 웨이브 기합의띠 사용), "pend"[배울 기술 대기]}
아이템·보상 키는 PokeAPI 아이템 이름(identifier)을 그대로 쓴다 (그림 이름과 같다).
"""

import math
import random

from . import data as D

MAX_LEVEL = 100
FINAL_WAVE = 100
BIOME_SIZE = 10         # 10웨이브마다 보스 + 새 지역(전체 회복)
WAVE_EXP = 1.5       # 웨이브 게임은 싸운 포켓몬만 받는 대신 경험치를 조금 더
WIN_HEAL = 0.15         # 이길 때마다 살아 있는 파티 포켓몬 HP 15% 회복
LEVEL_PER_WAVE = 0.85   # 웨이브당 상대 레벨 증가
MONEY_BASE = 100        # 웨이브 보상 돈 = MONEY_BASE + 웨이브 × MONEY_PER_WAVE (보스 2.5배)
MONEY_PER_WAVE = 25
EXP_BASE = 1.55          # 기본 경험치 배율 (PokeRogue처럼 넉넉하게)
OTHER_EVO_LEVEL = 25    # 친밀도·시간 등으로 진화하는 포켓몬은 이 레벨에서 진화
MAX_PARTY = 6

STATUS_KO = {"par": "마비", "brn": "화상", "psn": "독", "frz": "얼음"}
AILMENT = {1: "par", 3: "frz", 4: "brn", 5: "psn"}
STATUS_IMMUNE = {"par": {13}, "brn": {10}, "psn": {4, 9}, "frz": {15}}

BIOMES = ["풀숲", "동굴", "해변", "숲", "화산", "설원", "도시", "유적", "하늘탑", "챔피언로드"]

# ---------- 모드 (일반 / 데일리 / 주간 챌린지) ----------
# 데일리·챌린지는 run["seed"]로 상대·보상·갈림길을 정해서 모두 같은 게임을 한다 (배틀 중 운은 각자 다름).
RULES = {
    "mono":     "단일 타입: 정해진 타입의 포켓몬만 쓰고 잡을 수 있어요",
    "noitems":  "아이템 금지: 볼 말고는 가방 아이템과 상점을 쓸 수 없어요",
    "hardcore": "하드코어: 이겨도 회복되지 않고, 새 지역에서도 회복되지 않아요",
    "lv50":     "레벨 제한: 레벨이 50에서 멈춰요",
}
WEEKLY_ROTATION = ["mono", "noitems", "hardcore", "lv50"]
STARTER_POOL = [1, 4, 7, 152, 155, 158, 252, 255, 258, 387, 390, 393, 495, 498, 501,
                650, 653, 656, 722, 725, 728, 810, 813, 816, 906, 909, 912]


def seeded(seed: str, *tags) -> random.Random:
    return random.Random(":".join(map(str, (seed,) + tags)))


def _srng(run: dict, rng: random.Random, *tags) -> random.Random:
    """데일리·챌린지면 시드로 정해진 난수, 아니면 그냥 난수"""
    return seeded(run["seed"], *tags) if run.get("seed") else rng


def daily_starters(seed: str) -> list[int]:
    return seeded(seed, "starters").sample(STARTER_POOL, 3)


def weekly_rules(seed: str) -> tuple[str, int | None]:
    """(규칙, 단일 타입이면 타입 번호)"""
    r = seeded(seed, "rule")
    rule = WEEKLY_ROTATION[int(seed.split("-W")[-1]) % len(WEEKLY_ROTATION)] if "-W" in seed else r.choice(WEEKLY_ROTATION)
    return rule, (r.randint(1, 18) if rule == "mono" else None)


def challenge_starters(seed: str) -> list[int]:
    rule, mono = weekly_rules(seed)
    r = seeded(seed, "starters")
    if mono:
        pool = [s for s in _base_species() if mono in D.types(s) and 300 <= D.bst(s) <= 450]
        return r.sample(pool, min(3, len(pool)))
    return r.sample(STARTER_POOL, 3)


def _base_species() -> list[int]:
    return [sid for sid, s in D.SPECIES.items() if not s["from"] and not s["leg"]]


def root_species(sid: int) -> int:
    """진화 전 첫 단계 (도감 해금용)"""
    while D.SPECIES[sid]["from"]:
        sid = D.SPECIES[sid]["from"]
    return sid


def allowed(run: dict, sid: int) -> bool:
    """단일 타입 챌린지에서 쓸 수 있는 포켓몬인지"""
    mono = run.get("mono")
    return not mono or mono in D.types(sid)


STRUGGLE = {"n": "발버둥", "t": 0, "p": 50, "a": None, "c": 0, "pr": 0, "pp": 1}   # PP가 모두 떨어지면


# ---------- 지닌 물건 ----------
HELD = {
    "leftovers":     "매 턴 HP가 조금씩 회복된다",
    "shell-bell":    "공격하면 준 데미지만큼 조금 회복된다",
    "focus-sash":    "HP가 가득할 땐 한 방을 버텨 낸다",
    "life-orb":      "기술이 세지지만 쓸 때마다 HP가 깎인다",
    "choice-band":   "공격이 오르지만 한 기술만 쓸 수 있다",
    "choice-specs":  "특공이 오르지만 한 기술만 쓸 수 있다",
    "choice-scarf":  "스피드가 오르지만 한 기술만 쓸 수 있다",
    "lucky-egg":     "배틀에서 얻는 경험치가 늘어난다",
    "scope-lens":    "기술이 급소에 맞기 쉬워진다",
}
TYPE_BOOST = {   # 타입 강화 아이템 → 타입 (위력 1.2배)
    "silk-scarf": 1, "black-belt": 2, "sharp-beak": 3, "poison-barb": 4, "soft-sand": 5, "hard-stone": 6,
    "silver-powder": 7, "spell-tag": 8, "metal-coat": 9, "charcoal": 10, "mystic-water": 11, "miracle-seed": 12,
    "magnet": 13, "twisted-spoon": 14, "never-melt-ice": 15, "dragon-fang": 16, "black-glasses": 17,
    "fairy-feather": 18,
}
for _k, _t in TYPE_BOOST.items():
    HELD[_k] = f"{D.TYPE_KO[_t]} 타입 기술이 강해진다"
CHOICE = {"choice-band": 1, "choice-specs": 3, "choice-scarf": 5}


def held(mon: dict) -> str | None:
    return mon.get("held")


# ---------- 능력치 ----------
def max_hp(mon: dict) -> int:
    b = D.SPECIES[mon["sid"]]["s"][0]
    if b == 1:  # 껍질몬 같은 HP 1 고정 포켓몬
        return 1
    hp = (2 * b + mon["iv"][0]) * mon["lv"] // 100 + mon["lv"] + 10
    hp = int(hp * (1 + 0.1 * mon.get("vit", [0] * 6)[0]))
    return int(hp * 1.3) if mon.get("boss") else hp


def stat(mon: dict, i: int) -> int:
    """i: 1 공격, 2 방어, 3 특공, 4 특방, 5 스피드 (랭크·비타민·상태이상·지닌 물건 반영)"""
    b = D.SPECIES[mon["sid"]]["s"][i]
    v = (2 * b + mon["iv"][i]) * mon["lv"] // 100 + 5
    v *= 1 + 0.1 * mon.get("vit", [0] * 6)[i]
    s = mon["stg"][i - 1]
    v *= (2 + s) / 2 if s >= 0 else 2 / (2 - s)
    if CHOICE.get(held(mon)) == i:
        v *= 1.5
    if i == 5 and mon.get("status") == "par":
        v *= 0.5
    return max(1, int(v))


def stats_line(mon: dict) -> list[tuple[str, int]]:
    return [("HP", max_hp(mon))] + [(D.STAT_KO[i], stat(mon, i)) for i in range(1, 6)]


def level_cap(mon: dict) -> int:
    return mon.get("cap") or MAX_LEVEL


def exp_to_next(mon: dict) -> int:
    if mon["lv"] >= level_cap(mon):
        return 0
    g = D.SPECIES[mon["sid"]]["g"]
    return D.total_exp(g, mon["lv"] + 1) - D.total_exp(g, mon["lv"])


# ---------- 기술·PP ----------
def move(mid: int) -> dict:
    return STRUGGLE if mid == -1 else D.MOVES[mid]


def max_pp(mon: dict, i: int) -> int:
    base = D.MOVES[mon["moves"][i]]["pp"]
    return int(base * (1 + 0.2 * mon.get("ppx", [0] * 4)[i]))


def fix_pp(mon: dict):
    """기술 목록에 맞춰 PP 칸을 맞춘다 (예전 저장 데이터·새 기술)"""
    n = len(mon["moves"])
    ppx = (mon.get("ppx") or [])[:n]
    mon["ppx"] = ppx + [0] * (n - len(ppx))
    pp = (mon.get("pp") or [])[:n]
    mon["pp"] = pp + [max_pp(mon, i) for i in range(len(pp), n)]


def restore_pp(mon: dict, i: int | None = None, amount: int | None = None):
    for j in ([i] if i is not None else range(len(mon["moves"]))):
        top = max_pp(mon, j)
        mon["pp"][j] = top if amount is None else min(top, mon["pp"][j] + amount)


def usable_moves(mon: dict) -> list[int]:
    """지금 쓸 수 있는 기술 번호 (PP 남음, 구애 아이템 묶임 반영)"""
    idx = [i for i in range(len(mon["moves"])) if mon["pp"][i] > 0]
    lock = mon.get("lock")
    if lock is not None and lock in idx:
        return [lock]
    return idx


def learnset_upto(sid: int, lv: int) -> list[int]:
    return [m for l, m in D.SPECIES[sid]["ls"] if l <= lv]


def pick_moves(sid: int, lv: int) -> list[int]:
    """야생/새 포켓몬: 그 레벨까지 배운 기술 중 최근 것 4개 (본가 야생 포켓몬 방식)"""
    moves: list[int] = []
    for m in learnset_upto(sid, lv):
        if m in moves:
            continue
        moves.append(m)
        if len(moves) > 4:
            moves.pop(0)
    return moves or [D.TACKLE]


def learn(mon: dict, move_id: int) -> str | None:
    """새 기술. 4개 미만이면 바로 배우고, 4개면 '배울 기술 대기(pend)'에 넣어 플레이어가 고르게 한다."""
    if move_id in mon["moves"] or move_id in mon.get("pend", []):
        return None
    name = D.name(mon["sid"])
    new = D.MOVES[move_id]
    if len(mon["moves"]) < 4:
        mon["moves"].append(move_id)
        mon["ppx"].append(0)
        mon["pp"].append(max_pp(mon, len(mon["moves"]) - 1))
        return f"{name}은(는) **{new['n']}**을(를) 배웠다!"
    mon.setdefault("pend", []).append(move_id)
    return f"{name}은(는) **{new['n']}**을(를) 배우고 싶어 한다!"


def _move_value(mon: dict, mid: int) -> float:
    m = D.MOVES[mid]
    v = m["p"] * (m["a"] or 100) / 100
    if m.get("h"):
        v *= sum(m["h"]) / 2 if m["h"][0] != m["h"][1] else m["h"][0]
    if m["t"] in D.types(mon["sid"]):
        v *= 1.5
    atk = D.SPECIES[mon["sid"]]["s"][1 if m["c"] == 0 else 3]
    v *= atk / 100
    if m.get("rc"):
        v *= 0.55
    return v


# ---------- 포켓몬 만들기 ----------
def new_mon(sid: int, lv: int, rng: random.Random, boss: bool = False) -> dict:
    mon = {
        "sid": sid, "lv": lv, "exp": 0, "iv": [rng.randint(0, 31) for _ in range(6)],
        "moves": pick_moves(sid, lv), "stg": [0] * 5, "crit": 0, "status": None, "rc": 0,
        "vit": [0] * 6, "boss": boss, "held": None, "lock": None, "sash": 0, "pend": [],
    }
    fix_pp(mon)
    mon["hp"] = max_hp(mon)
    return mon


START_MONEY = 1000
START_BAG = {"poke-ball": 5, "potion": 2}
_OLD_ITEM = {"pokeball": "poke-ball", "greatball": "great-ball", "ultraball": "ultra-ball",
             "masterball": "master-ball", "superpot": "super-potion", "fullrest": "full-restore",
             "fullheal": "full-heal"}


def new_run(starter: int, rng: random.Random | None = None, mode: str = "normal", seed: str | None = None) -> dict:
    """mode: normal / daily(seed=날짜) / challenge(seed=주)"""
    rng = rng or random.Random()
    p = new_mon(starter, 5, seeded(seed, "starter-iv") if seed else rng)
    p["iv"] = [max(iv, 20) for iv in p["iv"]]   # 스타팅은 개체값 최소 20 보장
    run = {"wave": 0, "phase": "battle", "party": [p], "active": 0, "e": None, "log": [],
           "rewards": [], "money": START_MONEY, "bag": dict(START_BAG), "rerolls": 0, "turn": 0,
           "exp_mult": 1.0, "starter": starter, "best_hit": 0, "caught": 0, "caught_list": [starter],
           "mode": mode, "seed": seed, "rule": None, "mono": None}
    if mode == "challenge" and seed:
        run["rule"], run["mono"] = weekly_rules(seed)
        if run["rule"] == "lv50":
            p["cap"] = 50
        if run["rule"] == "noitems":
            run["bag"] = {"poke-ball": 5}
        if run["rule"] == "mono":
            run["bag"]["poke-ball"] = 10   # 같은 타입 동료를 빨리 모을 수 있게
    p["hp"] = max_hp(p)
    start_wave(run, rng)
    return run


def normalize(run: dict) -> dict:
    """예전 저장 형식을 지금 형식으로 바꾼다."""
    if "party" not in run:
        run["party"] = [run.pop("p")]
        run["active"] = 0
    run.setdefault("money", START_MONEY)
    run.setdefault("bag", dict(START_BAG))
    run["bag"] = {_OLD_ITEM.get(k, k): v for k, v in run["bag"].items()}
    run.setdefault("rerolls", 0)
    run.setdefault("caught", 0)
    run.setdefault("turn", 0)
    run.setdefault("mode", "normal")
    run.setdefault("seed", None)
    run.setdefault("rule", None)
    run.setdefault("mono", None)
    run.setdefault("caught_list", [])
    old_rewards = run.get("rewards", [])
    run["rewards"] = [k for k in old_rewards if _valid_reward(k)] or (["balls"] if old_rewards else [])
    for m in run["party"] + ([run["e"]] if run.get("e") else []):
        m.setdefault("crit", 0)
        m.setdefault("held", None)
        m.setdefault("lock", None)
        m.setdefault("sash", 0)
        m.setdefault("pend", [])
        fix_pp(m)
    if run.get("phase") == "learn" and learner(run) is None:   # 예전 버그로 멈춘 게임 풀기
        run["phase"] = "field" if run.get("mode") == "adventure" else "reward"
    return run


# ---------- 파티 ----------
def lead(run: dict) -> dict:
    return run["party"][run["active"]]


def alive(run: dict) -> list[int]:
    return [i for i, m in enumerate(run["party"]) if m["hp"] > 0]


def heal_full(mon: dict):
    mon["hp"] = max_hp(mon)
    mon["status"] = None
    restore_pp(mon)


def heal_party(run: dict):
    for m in run["party"]:
        heal_full(m)


def _reset_battle_state(mon: dict):
    mon["stg"] = [0] * 5
    mon["crit"] = 0
    mon["rc"] = 0
    mon["lock"] = None


# ---------- 웨이브 ----------
def is_boss_wave(wave: int) -> bool:
    return wave % BIOME_SIZE == 0


def biome(wave: int) -> str:
    return BIOMES[((wave - 1) // BIOME_SIZE) % len(BIOMES)]


def enemy_level(wave: int, rng: random.Random) -> int:
    jitter = rng.choice([-2, -1, -1, 0]) if wave <= 10 else rng.choice([-1, 0, 0, 1])
    lv = 1.5 + wave * LEVEL_PER_WAVE + jitter
    if is_boss_wave(wave) and wave >= 30:
        lv += 2
    return max(2, min(MAX_LEVEL, round(lv)))


_BASE_POOL = [sid for sid, s in D.SPECIES.items() if not s["from"] and not s["leg"]]
EARLY_SAFE_WAVES = 8
EARLY_EXCLUDE_TYPES = {8, 9, 16}   # 고스트, 강철, 드래곤
_LEGEND_POOL = [sid for sid, s in D.SPECIES.items() if s["leg"] and not s["from"] and D.bst(sid) >= 580]


def _wild_evo_ok(how: str, val, lv: int) -> bool:
    if how == "lv":
        return val <= lv
    return lv >= (32 if how in ("item", "trade") else OTHER_EVO_LEVEL)


def _evolve_for_level(sid: int, lv: int, rng: random.Random) -> int:
    while True:
        options = [c for c, how, val in D.SPECIES[sid]["evo"] if _wild_evo_ok(how, val, lv)]
        if not options:
            return sid
        sid = rng.choice(options)


def wild_species(wave: int, lv: int, rng: random.Random) -> int:
    if wave == FINAL_WAVE:
        return rng.choice(_LEGEND_POOL)
    # 초반엔 약한 포켓몬, 뒤로 갈수록 강한 포켓몬 (진화 전 기준 종족값)
    cap = 280 + wave * 6
    if is_boss_wave(wave):
        cap += 120
    pool = [s for s in _BASE_POOL if D.bst(s) <= cap] or _BASE_POOL
    if wave <= EARLY_SAFE_WAVES:   # 초반에는 노말 기술이 안 듣거나 잘 안 듣는 타입을 빼서 스타팅이 막히지 않게
        pool = [s for s in pool if not set(D.types(s)) & EARLY_EXCLUDE_TYPES] or pool
    sid = _evolve_for_level(rng.choice(pool), lv, rng)
    if is_boss_wave(wave):   # 보스는 한 단계 더 진화 (30웨이브부터는 최종 진화형)
        sid = _evolve_for_level(sid, MAX_LEVEL if wave >= 30 else lv + 8, rng)
    return sid


def boss_bars(wave: int) -> int:
    """보스 HP 칸 수 (칸이 깨질 때마다 보스가 강해진다)"""
    if wave >= FINAL_WAVE:
        return 5
    return 2 if wave < 30 else (3 if wave < 60 else 4)


def roll_enemy(wave: int, rng: random.Random, mono: int | None = None) -> dict:
    lv = enemy_level(wave, rng)
    sid = wild_species(wave, lv, rng)
    if mono and wave <= EARLY_SAFE_WAVES:   # 단일 타입 챌린지 초반: 그 타입의 약점을 찌르는 상대는 다시 뽑기
        weak = {t for t in range(1, 19) if D.effectiveness(t, [mono]) > 1}
        for _ in range(10):
            if not set(D.types(sid)) & weak:
                break
            sid = wild_species(wave, lv, rng)
    if mono and not is_boss_wave(wave) and rng.random() < 0.6:   # 단일 타입 챌린지: 잡을 수 있는 상대를 자주
        pool = [s for s in _base_species() if mono in D.types(s) and D.bst(s) <= 280 + wave * 6]
        if pool:
            sid = _evolve_for_level(rng.choice(pool), lv, rng)
    mon = new_mon(sid, lv, rng, boss=is_boss_wave(wave))
    if mon["boss"]:
        mon["bars"] = mon["bars_left"] = boss_bars(wave)
    return mon


def next_enemy(run: dict, wave: int, rng: random.Random) -> dict:
    return roll_enemy(wave, _srng(run, rng, "enemy", wave), run.get("mono"))


def start_wave(run: dict, rng: random.Random) -> list[str]:
    run["wave"] += 1
    wave = run["wave"]
    msgs = []
    if wave > 1 and (wave - 1) % BIOME_SIZE == 0:
        if run.get("rule") == "hardcore":
            msgs.append(f"🗺️ 새 지역 **{biome(wave)}**에 도착했다! (하드코어: 회복 없음)")
        else:
            heal_party(run)
            msgs.append(f"🗺️ 새 지역 **{biome(wave)}**에 도착했다! 파티의 HP와 PP가 모두 회복됐다.")
    nxt = run.pop("next_e", None)
    if nxt and nxt.get("wave") == wave:   # 보상 고르는 동안 미리 정해 둔 상대 (그림을 미리 받아 두려고)
        run["e"] = nxt["mon"]
        run["seen"] = [run["active"]]
    else:
        run["e"] = next_enemy(run, wave, rng)
        run["seen"] = [run["active"]]
    sid, lv, boss = run["e"]["sid"], run["e"]["lv"], run["e"]["boss"]
    for m in run["party"]:
        _reset_battle_state(m)
        m["sash"] = 0
    if lead(run)["hp"] <= 0:
        run["active"] = alive(run)[0]
    run["rerolls"] = 0
    run["turn"] = 0
    lv = run["e"]["lv"]
    tag = "⚠️ 마지막 보스 " if wave == FINAL_WAVE else ("👑 보스 " if boss else "야생의 ")
    msgs.append(f"{tag}**{D.name(sid)}** Lv.{lv}이(가) 나타났다!")
    if boss:
        msgs.append(f"보스는 HP 보호막이 {run['e']['bars']}칸 있다! 칸이 깨질 때마다 더 강해진다.")
    run["phase"] = "battle"
    run["log"] = msgs
    return msgs


# ---------- 배틀 ----------
def _hit_count(m: dict, rng: random.Random) -> int:
    if not m.get("h"):
        return 1
    lo, hi = m["h"]
    if lo == hi:
        return lo
    if (lo, hi) == (2, 5):
        return rng.choices([2, 3, 4, 5], weights=[35, 35, 15, 15])[0]
    return rng.randint(lo, hi)


def damage(att: dict, dfn: dict, m: dict, rng: random.Random, crit: bool) -> tuple[int, float]:
    a_i, d_i = (1, 2) if m["c"] == 0 else (3, 4)
    a, d = stat(att, a_i), stat(dfn, d_i)
    if crit:   # 급소는 내 능력 하락·상대 능력 상승 무시
        if att["stg"][a_i - 1] < 0:
            a = stat({**att, "stg": [0] * 5}, a_i)
        if dfn["stg"][d_i - 1] > 0:
            d = stat({**dfn, "stg": [0] * 5}, d_i)
    base = (2 * att["lv"] // 5 + 2) * m["p"] * a // d // 50 + 2
    eff = D.effectiveness(m["t"], D.types(dfn["sid"]))
    mult = rng.uniform(0.85, 1.0) * eff
    if m["t"] in D.types(att["sid"]):
        mult *= 1.5
    if crit:
        mult *= 1.5
    if m["c"] == 0 and att.get("status") == "brn":
        mult *= 0.5
    h = held(att)
    if h == "life-orb":
        mult *= 1.3
    if TYPE_BOOST.get(h) == m["t"]:
        mult *= 1.2
    return (max(1, int(base * mult)) if eff > 0 else 0), eff


def _expected(att: dict, dfn: dict, mid: int) -> float:
    m = move(mid)
    a_i, d_i = (1, 2) if m["c"] == 0 else (3, 4)
    base = (2 * att["lv"] / 5 + 2) * m["p"] * stat(att, a_i) / stat(dfn, d_i) / 50 + 2
    base *= D.effectiveness(m["t"], D.types(dfn["sid"])) * 0.925
    if m["t"] in D.types(att["sid"]):
        base *= 1.5
    base *= (m["a"] or 100) / 100
    if m.get("h"):
        base *= 3 if m["h"] == [2, 5] else sum(m["h"]) / 2
    if m.get("rc"):
        base *= 0.55
    return base


def ai_move(att: dict, dfn: dict, rng: random.Random) -> int:
    if rng.random() < 0.2:
        return rng.choice(att["moves"])
    return max(att["moves"], key=lambda mid: _expected(att, dfn, mid))


def best_move_index(att: dict, dfn: dict) -> int:
    """시뮬레이션용: 지금 쓸 수 있는 기술 중 기대 데미지가 가장 큰 기술 (-1 = 발버둥)"""
    idx = usable_moves(att)
    if not idx:
        return -1
    return max(idx, key=lambda i: _expected(att, dfn, att["moves"][i]))


def _crit_chance(user: dict, m: dict) -> float:
    stage = m.get("cr", 0) + user.get("crit", 0) + (1 if held(user) == "scope-lens" else 0)
    return (1 / 24, 1 / 8, 1 / 2, 1.0)[min(3, stage)]


def _act(user: dict, target: dict, mid: int, uname: str, tname: str, rng: random.Random, log: list, run: dict,
         is_player: bool):
    if user["rc"]:
        user["rc"] = 0
        log.append(f"{uname}은(는) 반동으로 움직일 수 없다!")
        return
    st = user.get("status")
    if st == "frz":
        if rng.random() < 0.2:
            user["status"] = None
            log.append(f"{uname}의 얼음이 녹았다!")
        else:
            log.append(f"{uname}은(는) 얼어붙어서 움직일 수 없다!")
            return
    if st == "par" and rng.random() < 0.25:
        log.append(f"{uname}은(는) 몸이 저려서 움직일 수 없다!")
        return

    m = move(mid)
    if mid == -1:
        log.append(f"{uname}은(는) 쓸 수 있는 기술이 없다!")
    log.append(f"{uname}의 **{m['n']}**!")
    if m["a"] is not None and rng.random() * 100 >= m["a"]:
        log.append("그러나 공격이 빗나갔다!")
        return
    if m.get("rc"):
        user["rc"] = 1

    eff = D.effectiveness(m["t"], D.types(target["sid"]))
    if eff == 0:
        log.append(f"{tname}에게는 효과가 없는 것 같다...")
        return

    total, hits, crit_any, endured, broke = 0, _hit_count(m, rng), False, False, []
    for _ in range(hits):
        crit = rng.random() < _crit_chance(user, m)
        crit_any |= crit
        dmg, _ = damage(user, target, m, rng, crit)
        if (dmg >= target["hp"] and target["hp"] == max_hp(target) and held(target) == "focus-sash"
                and not target.get("sash") and target["hp"] > 1):
            dmg = target["hp"] - 1
            target["sash"] = 1
            endured = True
        if target.get("bars_left", 0) > 1:   # 보스 보호막: 이번 칸 아래로는 한 번에 못 내려감
            line = math.ceil(max_hp(target) * (target["bars_left"] - 1) / target["bars"])
            if target["hp"] - dmg < line:
                dmg = target["hp"] - line
                target["bars_left"] -= 1
                stat_i = rng.randrange(5)
                broke.append(stat_i)
        dmg = min(dmg, target["hp"])
        target["hp"] -= dmg
        total += dmg
        if target["hp"] <= 0:
            break
    if is_player:
        run["best_hit"] = max(run.get("best_hit", 0), total)
    if crit_any:
        log.append("급소에 맞았다!")
    if eff > 1:
        log.append("효과가 굉장했다!")
    elif eff < 1:
        log.append("효과가 별로인 듯하다...")
    if hits > 1:
        log.append(f"{hits}번 맞았다!")
    log.append(f"→ {tname}에게 **{total}** 데미지")
    if endured:
        log.append(f"{tname}은(는) 기합의띠로 버텼다!")
    for stat_i in broke:
        log.append(f"🛡️ {tname}의 보호막이 깨졌다! (남은 보호막 {target['bars_left'] - 1}칸)")
        _change_stage(target, tname, stat_i, 1, log)

    if m.get("dr") and total:
        amt = max(1, abs(total * m["dr"]) // 100)
        if m["dr"] > 0:
            user["hp"] = min(max_hp(user), user["hp"] + amt)
            log.append(f"{tname}의 체력을 흡수했다!")
        else:
            user["hp"] = max(0, user["hp"] - amt)
            log.append(f"{uname}은(는) 반동 데미지를 입었다!")
    if mid == -1:
        user["hp"] = max(0, user["hp"] - max(1, max_hp(user) // 4))
        log.append(f"{uname}은(는) 반동 데미지를 입었다!")
    if total and user["hp"] > 0:
        if held(user) == "shell-bell":
            user["hp"] = min(max_hp(user), user["hp"] + max(1, total // 8))
            log.append(f"{uname}은(는) 조개껍질방울로 HP를 회복했다.")
        if held(user) == "life-orb":
            user["hp"] = max(0, user["hp"] - max(1, max_hp(user) // 10))
            log.append(f"{uname}은(는) 생명의구슬 때문에 HP가 줄었다!")

    if target["hp"] > 0 and m.get("ai"):
        ail, chance = m["ai"]
        status = AILMENT[ail]
        if (not target.get("status") and rng.random() * 100 < chance
                and not (STATUS_IMMUNE[status] & set(D.types(target["sid"])))):
            target["status"] = status
            log.append(f"{tname}은(는) **{STATUS_KO[status]}** 상태가 됐다!")

    sc = m.get("sc")
    if sc and rng.random() * 100 < sc["ch"]:
        who, wname = (user, uname) if sc["self"] else (target, tname)
        if who["hp"] > 0:
            for s_id, ch in sc["s"]:
                _change_stage(who, wname, s_id - 2, ch, log)


def _change_stage(who: dict, wname: str, i: int, ch: int, log: list):
    before = who["stg"][i]
    who["stg"][i] = max(-6, min(6, before + ch))
    if who["stg"][i] != before:
        word = "올라갔다" if ch > 0 else "떨어졌다"
        if abs(ch) >= 2:
            word = "크게 " + word
        log.append(f"{wname}의 {D.STAT_KO[i + 1]}이(가) {word}!")
    else:
        log.append(f"{wname}의 {D.STAT_KO[i + 1]}은(는) 더 이상 {'오르지' if ch > 0 else '떨어지지'} 않는다!")


def _end_of_turn(mon: dict, name: str, log: list):
    if mon["hp"] <= 0:
        return
    if mon.get("status") == "brn":
        mon["hp"] = max(0, mon["hp"] - max(1, max_hp(mon) // 16))
        log.append(f"{name}은(는) 화상 데미지를 입었다!")
    elif mon.get("status") == "psn":
        mon["hp"] = max(0, mon["hp"] - max(1, max_hp(mon) // 8))
        log.append(f"{name}은(는) 독 데미지를 입었다!")
    if mon["hp"] > 0 and held(mon) == "leftovers" and mon["hp"] < max_hp(mon):
        mon["hp"] = min(max_hp(mon), mon["hp"] + max(1, max_hp(mon) // 16))
        log.append(f"{name}은(는) 먹다남은음식으로 HP를 조금 회복했다.")


def _ename(run: dict) -> str:
    return "상대 " + D.name(run["e"]["sid"])


def _after_enemy_action(run: dict, log: list, rng: random.Random) -> str:
    """턴 끝 처리와 기절 판정. 결과: 'continue' | 'win' | 'switch' | 'lose' (+ 'learn')"""
    p, e = lead(run), run["e"]
    _end_of_turn(p, D.name(p["sid"]), log)
    _end_of_turn(e, _ename(run), log)
    run["turn"] = run.get("turn", 0) + 1
    run["log"] = log
    if e["hp"] <= 0:
        log.append(f"{_ename(run)}은(는) 쓰러졌다!")
        if not alive(run):   # 같은 턴에 내 마지막 포켓몬도 쓰러짐 → 패배
            log.append(f"{D.name(p['sid'])}도 쓰러졌다...")
            return _on_lead_fainted(run, log)
        log.extend(win(run, rng))
        return "learn" if run["phase"] == "learn" else "win"
    if p["hp"] <= 0:
        log.append(f"{D.name(p['sid'])}은(는) 쓰러졌다...")
        return _on_lead_fainted(run, log)
    return "continue"


def _on_lead_fainted(run: dict, log: list) -> str:
    _reset_battle_state(lead(run))
    if alive(run):
        run["phase"] = "switch"
        log.append("다음 포켓몬을 골라 주세요!")
        return "switch"
    if run.get("mode") == "adventure":
        from . import adventure
        return adventure.blackout(run, log)
    run["phase"] = "over"
    log.append("눈앞이 캄캄해졌다...")
    return "lose"


def _enemy_turn(run: dict, log: list, rng: random.Random):
    p, e = lead(run), run["e"]
    if e["hp"] > 0 and p["hp"] > 0:
        _act(e, p, ai_move(e, p, rng), _ename(run), D.name(p["sid"]), rng, log, run, False)


def take_turn(run: dict, move_index: int, rng: random.Random | None = None) -> str:
    """앞에 나온 포켓몬이 기술을 쓴다 (-1 = 발버둥). 결과: 'continue' | 'win' | 'learn' | 'switch' | 'lose'"""
    rng = rng or random.Random()
    p, e = lead(run), run["e"]
    if p["rc"]:
        pmove = p["moves"][0]
    else:
        usable = usable_moves(p)
        if move_index == -1:
            if usable:
                raise ValueError("struggle only when no PP")
            pmove = -1
        else:
            if move_index not in usable:
                raise ValueError("move not usable")
            pmove = p["moves"][move_index]
            p["pp"][move_index] -= 1
            if p["held"] in CHOICE:
                p["lock"] = move_index
    pname, ename = D.name(p["sid"]), _ename(run)
    log: list[str] = []
    emove = ai_move(e, p, rng)

    def order_key(mon, mid):
        return (move(mid)["pr"] if not mon["rc"] else 0, stat(mon, 5), rng.random())

    turns = [(p, e, pmove, pname, ename, True), (e, p, emove, ename, pname, False)]
    if order_key(p, pmove) < order_key(e, emove):
        turns.reverse()
    for user, target, mid, un, tn, is_p in turns:
        if user["hp"] <= 0 or target["hp"] <= 0:
            continue
        _act(user, target, mid, un, tn, rng, log, run, is_p)
    return _after_enemy_action(run, log, rng)


# ---------- 교체 ----------
def switch(run: dict, index: int, rng: random.Random | None = None) -> str:
    """포켓몬 교체. 배틀 중이면 턴을 쓰고(상대가 공격), 기절 후 교체면 바로 나온다."""
    rng = rng or random.Random()
    if not 0 <= index < len(run["party"]) or run["party"][index]["hp"] <= 0 or index == run["active"]:
        raise ValueError("bad switch")
    forced = run["phase"] == "switch"
    old = lead(run)
    _reset_battle_state(old)
    run["active"] = index
    seen = run["battle"] if isinstance(run.get("battle"), dict) else run   # 지금 상대와 싸운 포켓몬으로 센다 (경험치)
    seen.setdefault("seen", []).append(index)
    new = lead(run)
    log = [] if forced else [f"돌아와, {D.name(old['sid'])}!"]
    log.append(f"가랏, **{D.name(new['sid'])}**!")
    run["phase"] = "battle"
    if forced:
        run["log"] = log
        return "continue"
    _enemy_turn(run, log, rng)
    return _after_enemy_action(run, log, rng)


# ---------- 가방 아이템 ----------
# cat: ball(볼) heal(회복) status(상태이상) revive(기절) pp(PP) ppup(최대 PP) battle(배틀용) evo(진화) held(지닌 물건)
ITEMS: dict[str, dict] = {
    "poke-ball":    {"cat": "ball", "ball": 1.0, "price": 200, "d": "야생 포켓몬에게 던져서 잡는 볼"},
    "great-ball":   {"cat": "ball", "ball": 1.5, "price": 600, "d": "몬스터볼보다 잘 잡히는 볼"},
    "ultra-ball":   {"cat": "ball", "ball": 2.0, "price": 1200, "d": "슈퍼볼보다 더 잘 잡히는 볼"},
    "quick-ball":   {"cat": "ball", "ball": "quick", "price": 1000, "d": "배틀을 시작하자마자 던지면 잘 잡힌다"},
    "timer-ball":   {"cat": "ball", "ball": "timer", "price": 1000, "d": "배틀이 길어질수록 잘 잡힌다"},
    "net-ball":     {"cat": "ball", "ball": "net", "price": 1000, "d": "물이나 벌레 타입이 잘 잡힌다"},
    "heal-ball":    {"cat": "ball", "ball": "heal", "price": 300, "d": "잡은 포켓몬의 HP가 가득 찬다"},
    "master-ball":  {"cat": "ball", "ball": 255.0, "price": 0, "d": "어떤 포켓몬이든 반드시 잡힌다"},
    "potion":       {"cat": "heal", "heal": 0.25, "price": 300, "d": "HP를 25% 회복한다"},
    "super-potion": {"cat": "heal", "heal": 0.5, "price": 700, "d": "HP를 50% 회복한다"},
    "hyper-potion": {"cat": "heal", "heal": 0.75, "price": 1200, "d": "HP를 75% 회복한다"},
    "max-potion":   {"cat": "heal", "heal": 1.0, "price": 2500, "d": "HP를 전부 회복한다"},
    "full-restore": {"cat": "heal", "heal": 1.0, "cure": "all", "price": 3000, "d": "HP와 상태이상을 전부 회복한다"},
    "fresh-water":  {"cat": "heal", "heal": 0.3, "price": 0, "d": "시원한 물. HP를 30% 회복한다"},
    "soda-pop":     {"cat": "heal", "heal": 0.4, "price": 0, "d": "톡 쏘는 사이다. HP를 40% 회복한다"},
    "lemonade":     {"cat": "heal", "heal": 0.5, "price": 0, "d": "달콤한 음료. HP를 50% 회복한다"},
    "moomoo-milk":  {"cat": "heal", "heal": 0.6, "price": 0, "d": "고소한 우유. HP를 60% 회복한다"},
    "antidote":     {"cat": "status", "cure": "psn", "price": 100, "d": "독을 치료한다"},
    "paralyze-heal": {"cat": "status", "cure": "par", "price": 200, "d": "마비를 풀어 준다"},
    "burn-heal":    {"cat": "status", "cure": "brn", "price": 200, "d": "화상을 치료한다"},
    "ice-heal":     {"cat": "status", "cure": "frz", "price": 200, "d": "얼어붙은 몸을 녹인다"},
    "full-heal":    {"cat": "status", "cure": "all", "price": 400, "d": "상태이상을 전부 치료한다"},
    "revive":       {"cat": "revive", "revive": 0.5, "price": 1500, "d": "기절한 포켓몬을 HP 절반으로 깨운다"},
    "max-revive":   {"cat": "revive", "revive": 1.0, "price": 4000, "d": "기절한 포켓몬을 완전히 깨운다"},
    "sacred-ash":   {"cat": "revive", "revive": 1.0, "all": True, "price": 0, "d": "기절한 파티 포켓몬을 모두 되살린다"},
    "ether":        {"cat": "pp", "pp": 10, "one": True, "price": 1200, "d": "기술 하나의 PP를 10 회복한다"},
    "max-ether":    {"cat": "pp", "pp": None, "one": True, "price": 2000, "d": "기술 하나의 PP를 전부 회복한다"},
    "elixir":       {"cat": "pp", "pp": 10, "one": False, "price": 3000, "d": "모든 기술의 PP를 10씩 회복한다"},
    "max-elixir":   {"cat": "pp", "pp": None, "one": False, "price": 4500, "d": "모든 기술의 PP를 전부 회복한다"},
    "pp-up":        {"cat": "ppup", "ppx": 1, "price": 0, "d": "기술 하나의 최대 PP가 늘어난다"},
    "pp-max":       {"cat": "ppup", "ppx": 3, "price": 0, "d": "기술 하나의 최대 PP를 끝까지 늘린다"},
    "x-attack":     {"cat": "battle", "stage": 0, "price": 500, "d": "배틀 동안 공격이 크게 오른다"},
    "x-defense":    {"cat": "battle", "stage": 1, "price": 550, "d": "배틀 동안 방어가 크게 오른다"},
    "x-sp-atk":     {"cat": "battle", "stage": 2, "price": 600, "d": "배틀 동안 특공이 크게 오른다"},
    "x-sp-def":     {"cat": "battle", "stage": 3, "price": 550, "d": "배틀 동안 특방이 크게 오른다"},
    "x-speed":      {"cat": "battle", "stage": 4, "price": 700, "d": "배틀 동안 스피드가 크게 오른다"},
    "dire-hit":     {"cat": "battle", "crit": 2, "price": 650, "d": "배틀 동안 급소에 훨씬 잘 맞는다"},
    "linking-cord": {"cat": "evo", "price": 0, "d": "교환해야 진화하는 포켓몬을 진화시킨다"},
    "exp-share": {"cat": "key", "price": 3000, "d": "가지고 있으면 배틀에 안 나온 파티 포켓몬도 경험치를 절반 받는다"},
}
for _h, _d in HELD.items():
    ITEMS[_h] = {"cat": "held", "price": 0, "d": _d}
for _sp in D.SPECIES.values():   # 진화의 돌 등 진화 아이템
    for _c, _how, _val in _sp["evo"]:
        if _how == "item" and _val not in ITEMS:
            ITEMS[_val] = {"cat": "evo", "price": 0, "d": "쓰면 진화하는 포켓몬이 있다"}
VIT_ITEMS = ["hp-up", "protein", "iron", "calcium", "zinc", "carbos"]   # 맥스업 타우린 사포닌 리보플라빈 키토산 알칼로이드
for _i, _k in enumerate(VIT_ITEMS):
    ITEMS[_k] = {"cat": "vit", "vit": _i, "price": 9800, "d": f"{D.STAT_KO[_i]} 능력치가 오른다"}
ITEMS["rare-candy"] = {"cat": "candy", "price": 4800, "d": "레벨이 1 오른다"}
for _mid, _m in D.MOVES.items():   # 기술머신 (몇 번이고 쓸 수 있다)
    ITEMS[f"tm{_mid}"] = {"cat": "tm", "mid": _mid, "price": 3000 if _m["p"] <= 80 else 7500,
                          "d": f"{D.TYPE_KO[_m['t']]} {'물리' if _m['c'] == 0 else '특수'} 위력 {_m['p']} · 몇 번이고 쓸 수 있다"}
CAT_ORDER = ["ball", "heal", "status", "revive", "pp", "ppup", "battle", "vit", "candy", "tm", "evo", "held", "key"]
CAT_KO = {"ball": "볼", "heal": "회복", "status": "상태이상", "revive": "기절 회복", "pp": "PP 회복",
          "ppup": "PP 늘리기", "battle": "배틀용", "vit": "영양제", "candy": "이상한사탕", "tm": "기술머신",
          "evo": "진화", "held": "지닌 물건", "key": "중요한 물건"}
OUT_OF_BATTLE = ("reward", "field")   # 배틀 밖 (로그라이크 보상 고르기 / 모험 필드)
SHOP = ["poke-ball", "great-ball", "ultra-ball", "quick-ball", "timer-ball", "net-ball", "heal-ball",
        "potion", "super-potion", "hyper-potion", "max-potion", "full-restore",
        "antidote", "paralyze-heal", "burn-heal", "ice-heal", "full-heal",
        "revive", "max-revive", "ether", "max-ether", "elixir", "max-elixir",
        "x-attack", "x-defense", "x-sp-atk", "x-sp-def", "x-speed", "dire-hit"]


def item_name(item: str) -> str:
    if item.startswith("tm") and item[2:].isdigit():
        return f"기술머신 {D.MOVES[int(item[2:])]['n']}"
    return D.item_name(item)


def is_ball(item: str) -> bool:
    return ITEMS[item]["cat"] == "ball"


def evo_child(mon: dict, item: str) -> int | None:
    """이 아이템으로 진화할 수 있으면 진화 후 종 번호"""
    for c, how, val in D.SPECIES[mon["sid"]]["evo"]:
        if (how == "item" and val == item) or (how == "trade" and item == "linking-cord"):
            return c
    return None


def item_usable_now(run: dict, item: str) -> bool:
    cat = ITEMS[item]["cat"]
    if run.get("rule") == "noitems" and cat != "ball":
        return False
    if cat == "key":   # 중요한 물건은 가지고만 있으면 된다
        return False
    if cat in ("ball", "battle"):
        return run["phase"] == "battle"
    if cat in ("evo", "held", "ppup", "vit", "candy", "tm"):
        return run["phase"] in OUT_OF_BATTLE   # 배틀 밖에서만
    return run["phase"] == "battle" or run["phase"] in OUT_OF_BATTLE


def item_targets(run: dict, item: str) -> list[int]:
    """그 아이템을 쓸 수 있는 파티 번호"""
    it = ITEMS[item]
    cat = it["cat"]
    out = []
    for i, m in enumerate(run["party"]):
        if cat == "revive":
            ok = m["hp"] <= 0
        elif cat == "battle":
            ok = run["phase"] == "battle" and i == run["active"]
        elif cat == "evo":
            ok = evo_child(m, item) is not None
        elif cat == "held":
            ok = m.get("held") != item
        elif cat == "vit":
            ok = m["vit"][it["vit"]] < MAX_VITAMIN
        elif cat == "candy":
            ok = m["lv"] < level_cap(m)
        elif cat == "tm":
            ok = (it["mid"] in D.SPECIES[m["sid"]]["tm"] and it["mid"] not in m["moves"]
                  and it["mid"] not in m.get("pend", []))
        elif m["hp"] <= 0:
            ok = False
        elif cat == "heal":
            ok = m["hp"] < max_hp(m) or (it.get("cure") and m.get("status"))
        elif cat == "status":
            ok = bool(m.get("status")) and it["cure"] in ("all", m["status"])
        elif cat == "pp":
            ok = any(m["pp"][j] < max_pp(m, j) for j in range(len(m["moves"])))
        elif cat == "ppup":
            ok = any(m["ppx"][j] < 3 for j in range(len(m["moves"])))
        else:
            ok = False
        if ok:
            out.append(i)
    return out


def item_moves(run: dict, item: str, target: int) -> list[int]:
    """기술 하나에 쓰는 아이템(PP에이드, 포인트업)이면 고를 수 있는 기술 번호, 아니면 []"""
    it, m = ITEMS[item], run["party"][target]
    if it["cat"] == "pp" and it["one"]:
        return [j for j in range(len(m["moves"])) if m["pp"][j] < max_pp(m, j)]
    if it["cat"] == "ppup":
        return [j for j in range(len(m["moves"])) if m["ppx"][j] < 3]
    return []


def _take(run: dict, item: str):
    if run["bag"].get(item, 0) <= 0:
        raise ValueError("no item")
    run["bag"][item] -= 1
    if run["bag"][item] <= 0:
        del run["bag"][item]


def add_item(run: dict, item: str, count: int = 1):
    run["bag"][item] = run["bag"].get(item, 0) + count


def use_item(run: dict, item: str, target: int, rng: random.Random | None = None, move_index: int | None = None) -> str:
    """가방 아이템 사용 (볼 제외). 배틀 중이면 턴을 쓴다(상대가 공격). 보상 고르는 중이면 바로 쓴다."""
    rng = rng or random.Random()
    if is_ball(item) or not item_usable_now(run, item) or target not in item_targets(run, item):
        raise ValueError("bad item use")
    it = ITEMS[item]
    if item_moves(run, item, target) and move_index not in item_moves(run, item, target):
        raise ValueError("need move")
    cat, m = it["cat"], run["party"][target]
    if cat == "tm":   # 기술머신은 없어지지 않는다
        if run["bag"].get(item, 0) <= 0:
            raise ValueError("no item")
    else:
        _take(run, item)
    name = D.name(m["sid"])
    log = [f"🎒 {item_name(item)}을(를) 썼다!"]
    if cat == "revive":
        for x in (run["party"] if it.get("all") else [m]):
            if x["hp"] <= 0:
                x["hp"] = max(1, int(max_hp(x) * it["revive"]))
                x["status"] = None
                log.append(f"{D.name(x['sid'])}이(가) 기운을 되찾았다!")
    elif cat in ("heal", "status"):
        if it.get("heal"):
            before = m["hp"]
            m["hp"] = min(max_hp(m), m["hp"] + max(1, int(max_hp(m) * it["heal"])))
            if m["hp"] > before:
                log.append(f"{name}의 HP가 {m['hp'] - before} 회복됐다.")
        if it.get("cure") and m.get("status") and it["cure"] in ("all", m["status"]):
            log.append(f"{name}의 {STATUS_KO[m['status']]} 상태가 나았다.")
            m["status"] = None
    elif cat == "pp":
        if it["one"]:
            restore_pp(m, move_index, it["pp"])
            log.append(f"{name}의 {D.MOVES[m['moves'][move_index]]['n']} PP가 회복됐다.")
        else:
            restore_pp(m, None, it["pp"])
            log.append(f"{name}의 모든 기술 PP가 회복됐다.")
    elif cat == "ppup":
        j = move_index
        before = max_pp(m, j)
        m["ppx"][j] = min(3, m["ppx"][j] + it["ppx"])
        m["pp"][j] += max_pp(m, j) - before
        log.append(f"{name}의 {D.MOVES[m['moves'][j]]['n']} 최대 PP가 {max_pp(m, j)}(으)로 늘었다!")
    elif cat == "battle":
        if "stage" in it:
            _change_stage(m, name, it["stage"], 2, log)
        else:
            m["crit"] = min(3, m.get("crit", 0) + it["crit"])
            log.append(f"{name}은(는) 의욕이 넘친다! (급소율 업)")
    elif cat == "evo":
        log.extend(evolve(m, evo_child(m, item)))
    elif cat == "vit":
        i = it["vit"]
        old_max = max_hp(m)
        m["vit"][i] += 1
        if i == 0 and m["hp"] > 0:
            m["hp"] += max_hp(m) - old_max
        log.append(f"{name}의 {D.STAT_KO[i]}이(가) 올랐다! ({m['vit'][i]}/{MAX_VITAMIN})")
    elif cat == "candy":
        m["exp"] = 0
        log.extend(level_up(m))
    elif cat == "tm":
        log.append(learn(m, it["mid"]) or "")
    elif cat == "held":
        old = m.get("held")
        m["held"] = item
        m["lock"] = None
        log.append(f"{name}에게 {item_name(item)}을(를) 지니게 했다.")
        if old:
            add_item(run, old)
            log.append(f"원래 지니고 있던 {item_name(old)}은(는) 가방에 넣었다.")
    if run["phase"] != "battle":
        run["log"] = [x for x in log if x]
        _maybe_learn(run, run["phase"])
        return "continue"
    _enemy_turn(run, log, rng)
    return _after_enemy_action(run, log, rng)


# ---------- 포획 ----------
def _ball_mult(run: dict, item: str) -> float:
    b = ITEMS[item]["ball"]
    if isinstance(b, float):
        return b
    if b == "quick":
        return 5.0 if run.get("turn", 0) == 0 else 1.0
    if b == "timer":
        return min(4.0, 1.0 + run.get("turn", 0) * 0.3)
    if b == "net":
        return 3.5 if {7, 11} & set(D.types(run["e"]["sid"])) else 1.0
    return 1.0


def catch_chance(run: dict, item: str) -> float:
    """한 번 던졌을 때 잡힐 확률 (3세대 공식)"""
    e = run["e"]
    ball = _ball_mult(run, item)
    if ball >= 255:
        return 1.0
    rate = D.SPECIES[e["sid"]]["cap"] or 45
    if (run.get("battle") or {}).get("kind") == "legend":   # 모험의 전설: 너무 안 잡히지 않게
        rate = max(rate, 45)
    if e.get("boss"):
        rate /= 3
    mh = max_hp(e)
    a = (3 * mh - 2 * e["hp"]) * rate * ball / (3 * mh)
    a *= {"frz": 2.0, "par": 1.5, "brn": 1.5, "psn": 1.5}.get(e.get("status"), 1.0)
    if a >= 255:
        return 1.0
    b = 1048560 / math.sqrt(math.sqrt(16711680 / max(a, 0.1)))
    return (b / 65536) ** 4


def can_catch(run: dict) -> bool:
    """트레이너의 포켓몬은 잡을 수 없다 (모험)"""
    return (run.get("battle") or {}).get("kind", "wild") in ("wild", "legend")


def throw_ball(run: dict, item: str, rng: random.Random | None = None) -> str:
    """볼 던지기. 결과: 'caught' | 'replace'(파티가 가득) | 'learn' | 'continue' | 'switch' | 'lose' | 'win'"""
    rng = rng or random.Random()
    if not is_ball(item) or run["phase"] != "battle":
        raise ValueError("not a ball")
    if not allowed(run, run["e"]["sid"]):
        raise ValueError("mono rule")
    if not can_catch(run):
        raise ValueError("trainer pokemon")
    chance = catch_chance(run, item)
    _take(run, item)
    e = run["e"]
    ename = D.name(e["sid"])
    log = [f"🎒 {item_name(item)}을(를) 던졌다!"]
    p_shake = chance ** 0.25
    shakes = 0
    while shakes < 4 and rng.random() < p_shake:
        shakes += 1
    if shakes >= 4:
        log.append("흔들... 흔들... 흔들... 딸깍!")
        log.append(f"✨ 신난다! **{ename}**을(를) 잡았다!")
        mon = dict(e)
        mon.update(boss=False, stg=[0] * 5, crit=0, rc=0, lock=None, vit=[0] * 6, exp=0, held=None, sash=0, pend=[])
        mon["hp"] = max(1, min(max_hp(mon), mon["hp"]))
        if ITEMS[item]["ball"] == "heal":
            heal_full(mon)
            log.append(f"{ename}의 HP와 PP가 모두 회복됐다!")
        run["caught"] = run.get("caught", 0) + 1
        run.setdefault("caught_list", []).append(e["sid"])
        if e.get("shiny"):   # 도감에 ✨ 표시
            run.setdefault("shiny_list", []).append(e["sid"])
        if run.get("rule") == "lv50":
            mon["cap"] = 50
        log.extend(win(run, rng, caught=True))
        if run.get("mode") == "adventure":
            from . import adventure
            log.extend(adventure.add_caught(run, mon))
            run["log"] = log
            return "learn" if run["phase"] == "learn" else "caught"
        if len(run["party"]) < MAX_PARTY:
            run["party"].append(mon)
            log.append(f"{ename}이(가) 파티에 들어왔다! ({len(run['party'])}/{MAX_PARTY})")
            run["log"] = log
            return "learn" if run["phase"] == "learn" else "caught"
        run["pending"] = {"mon": mon, "then": run["phase"]}
        run["phase"] = "replace"
        log.append("파티가 가득 찼다! 놓아줄 포켓몬을 골라 주세요.")
        run["log"] = log
        return "replace"
    log.append(["앗! 볼에서 나와 버렸다!", "아깝다! 조금만 더였는데!", "아아! 거의 잡았는데!", "으악! 잡은 줄 알았는데!"][shakes])
    _enemy_turn(run, log, rng)
    return _after_enemy_action(run, log, rng)


def resolve_replace(run: dict, release: int | None, rng: random.Random | None = None) -> list[str]:
    """파티가 가득 찼을 때: release 번호의 포켓몬을 놓아주고 새 포켓몬을 넣는다. None이면 새 포켓몬을 놓아준다."""
    pend = run.pop("pending")
    new = pend["mon"]
    if release is None:
        msgs = [f"{D.name(new['sid'])}을(를) 놓아주었다."]
    else:
        old = run["party"][release]
        run["party"][release] = new
        msgs = [f"{D.name(old['sid'])}을(를) 놓아주고 **{D.name(new['sid'])}**을(를) 파티에 넣었다."]
        if old.get("held"):
            add_item(run, old["held"])
            msgs.append(f"{D.name(old['sid'])}이(가) 지니고 있던 {item_name(old['held'])}은(는) 가방에 넣었다.")
        if run["active"] == release and new["hp"] <= 0:
            run["active"] = alive(run)[0]
    run["phase"] = pend["then"]
    if run["phase"] == "learn" and learner(run) is None:   # 기술을 배우려던 포켓몬을 놓아준 경우
        run["phase"] = "reward"
        if run.pop("after_learn", "reward") == "next_wave":
            msgs.extend(advance(run, rng or random.Random()))
    run["log"] = msgs
    return msgs


# ---------- 기술 잊기 (기술이 4개일 때 새 기술) ----------
def learner(run: dict) -> int | None:
    """기술을 배우려고 기다리는 파티 포켓몬 번호"""
    for i, m in enumerate(run["party"]):
        if m.get("pend"):
            return i
    return None


def _maybe_learn(run: dict, after: str):
    """배울 기술이 기다리고 있으면 기술 잊기 화면(learn)으로. after: 끝나고 갈 단계 ('reward' | 'field' | 'battle') 또는 'next_wave'"""
    if learner(run) is not None:
        run["phase"] = "learn"
        run["after_learn"] = after


def resolve_learn(run: dict, forget: int | None, rng: random.Random | None = None) -> list[str]:
    """forget: 잊을 기술 번호 (None = 새 기술을 배우지 않음)"""
    rng = rng or random.Random()
    i = learner(run)
    if run["phase"] != "learn" or i is None:
        raise ValueError("nothing to learn")
    m = run["party"][i]
    new = m["pend"].pop(0)
    name = D.name(m["sid"])
    if forget is None:
        msgs = [f"{name}은(는) {D.MOVES[new]['n']}을(를) 배우지 않았다."]
    else:
        if not 0 <= forget < len(m["moves"]):
            m["pend"].insert(0, new)
            raise ValueError("bad forget")
        old = m["moves"][forget]
        m["moves"][forget] = new
        m["ppx"][forget] = 0
        m["pp"][forget] = max_pp(m, forget)
        if m.get("lock") == forget:
            m["lock"] = None
        msgs = [f"1, 2, 3... 짠! {name}은(는) {D.MOVES[old]['n']}을(를) 깨끗이 잊었다!",
                f"그리고 **{D.MOVES[new]['n']}**을(를) 배웠다!"]
    if learner(run) is None:
        after = run.pop("after_learn", "reward")
        if after == "next_wave":
            run["phase"] = "reward"
            msgs.extend(advance(run, rng))
        else:
            run["phase"] = after   # 원래 하던 곳으로 (보상 / 필드 / 배틀)
    run["log"] = msgs
    return msgs


# ---------- 승리, 경험치, 진화 ----------
def exp_gain(p: dict, e: dict, mult: float) -> int:
    b, le, lp = D.SPECIES[e["sid"]]["x"], e["lv"], p["lv"]
    exp = (b * le / 5) * ((2 * le + 10) / (le + lp + 10)) ** 2.5 + 1
    if e.get("boss"):
        exp *= 1.5
    if held(p) == "lucky-egg":
        exp *= 1.5
    return max(1, int(exp * mult * EXP_BASE))


def gain_exp(p: dict, amount: int) -> list[str]:
    msgs = []
    cap = level_cap(p)
    if p["lv"] >= cap:
        return msgs
    p["exp"] += amount
    while p["lv"] < cap and p["exp"] >= exp_to_next(p):
        p["exp"] -= exp_to_next(p)
        msgs.extend(level_up(p))
    if p["lv"] >= cap:
        p["exp"] = 0
    return msgs


def level_up(p: dict) -> list[str]:
    old_max = max_hp(p)
    p["lv"] += 1
    if p["hp"] > 0:
        p["hp"] = min(max_hp(p), p["hp"] + max_hp(p) - old_max)
    msgs = [f"⬆️ {D.name(p['sid'])}은(는) **Lv.{p['lv']}**(으)로 올랐다!"]
    for l, mid in D.SPECIES[p["sid"]]["ls"]:
        if l == p["lv"]:
            if (msg := learn(p, mid)):
                msgs.append(msg)
    msgs.extend(try_evolve(p))
    return msgs


def try_evolve(p: dict) -> list[str]:
    """레벨로 진화 (친밀도·시간 등 '기타' 진화는 OTHER_EVO_LEVEL에서)"""
    for c, how, val in D.SPECIES[p["sid"]]["evo"]:
        if (how == "lv" and val <= p["lv"]) or (how == "other" and p["lv"] >= OTHER_EVO_LEVEL):
            return evolve(p, c)
    return []


def evolve(p: dict, child: int) -> list[str]:
    before = D.name(p["sid"])
    old_max = max_hp(p)
    p["sid"] = child
    if p["hp"] > 0:
        p["hp"] = min(max_hp(p), p["hp"] + max_hp(p) - old_max)
    p.setdefault("evolved", []).append(child)   # 도감 기록용 (봇이 저장 후 비움)
    msgs = [f"✨ 축하합니다! **{before}**은(는) **{D.name(child)}**(으)로 진화했다!"]
    for l, mid in D.SPECIES[child]["ls"]:
        if l in (1, p["lv"]) and mid not in p["moves"]:
            if (msg := learn(p, mid)):
                msgs.append(msg)
    msgs.extend(try_evolve(p))   # 한 번에 두 단계 (예: 레벨이 이미 높을 때)
    return msgs


def wave_money(wave: int, boss: bool) -> int:
    return int((MONEY_BASE + wave * MONEY_PER_WAVE) * (2.5 if boss else 1))


def win(run: dict, rng: random.Random, caught: bool = False) -> list[str]:
    """상대를 쓰러뜨리거나 잡았을 때: 파티 전원 경험치, 돈, 보상"""
    if run.get("mode") == "adventure":
        from . import adventure
        return adventure.after_ko(run, rng, caught)
    e = run["e"]
    msgs = []
    fought = set(run.get("seen", [])) | {run["active"]}   # 이 상대와 싸운 포켓몬만 경험치
    for i, m in enumerate(run["party"]):
        if m["hp"] <= 0:
            continue
        amount = exp_gain(m, e, run.get("exp_mult", 1.0) * WAVE_EXP)
        if i not in fought:   # 웨이브 게임은 학습장치가 늘 켜져 있다: 안 나온 포켓몬은 절반
            amount = max(1, amount // 2)
        if m["lv"] < level_cap(m):
            msgs.append(f"{D.name(m['sid'])}은(는) 경험치 **{amount}**을(를) 얻었다!")
        msgs.extend(gain_exp(m, amount))
        _reset_battle_state(m)
        if WIN_HEAL and run.get("rule") != "hardcore" and m["hp"] < max_hp(m):
            m["hp"] = min(max_hp(m), m["hp"] + int(max_hp(m) * WIN_HEAL))
    money = wave_money(run["wave"], e.get("boss", False))
    run["money"] = run.get("money", 0) + money
    msgs.append(f"💰 **₽{money:,}**을(를) 얻었다! (소지금 ₽{run['money']:,})")
    if lead(run)["hp"] <= 0 and alive(run):
        run["active"] = alive(run)[0]
    if run["wave"] >= FINAL_WAVE:
        run["phase"] = "clear"
        msgs.append(f"🏆 **{FINAL_WAVE}웨이브 클리어!** 전설을 {'잡았다' if caught else '쓰러뜨렸다'}!")
        return msgs
    run["phase"] = "reward"
    run["rewards"] = roll_rewards(run, rng)
    run["next_e"] = {"wave": run["wave"] + 1, "mon": next_enemy(run, run["wave"] + 1, rng)}
    _maybe_learn(run, "reward")
    return msgs


# ---------- 보상 (웨이브마다 하나 무료) ----------
# 고정 보상. kind: bag(가방에 넣기) / target(포켓몬 하나) / run(이번 게임 전체) / money
# 동적 보상 키: "tm:<기술>" 기술머신, "held:<아이템>" 지닌 물건, "evo:<아이템>" 진화 아이템
REWARDS = {
    "balls":    {"kind": "bag", "item": ("poke-ball", 5), "w": 12},
    "great":    {"kind": "bag", "item": ("great-ball", 3), "w": 7},
    "ultra":    {"kind": "bag", "item": ("ultra-ball", 2), "w": 3},
    "quick":    {"kind": "bag", "item": ("quick-ball", 2), "w": 2},
    "timer":    {"kind": "bag", "item": ("timer-ball", 2), "w": 2},
    "net":      {"kind": "bag", "item": ("net-ball", 2), "w": 2},
    "healball": {"kind": "bag", "item": ("heal-ball", 3), "w": 2},
    "master":   {"kind": "bag", "item": ("master-ball", 1), "w": 0.4},
    "potion":   {"kind": "bag", "item": ("potion", 3), "w": 10},
    "superpot": {"kind": "bag", "item": ("super-potion", 2), "w": 7},
    "hyperpot": {"kind": "bag", "item": ("hyper-potion", 2), "w": 4},
    "maxpot":   {"kind": "bag", "item": ("max-potion", 1), "w": 2},
    "fullrest": {"kind": "bag", "item": ("full-restore", 1), "w": 2},
    "drinks":   {"kind": "bag", "item": ("fresh-water", 3), "w": 3},
    "soda":     {"kind": "bag", "item": ("soda-pop", 3), "w": 2},
    "lemonade": {"kind": "bag", "item": ("lemonade", 2), "w": 2},
    "milk":     {"kind": "bag", "item": ("moomoo-milk", 2), "w": 2},
    "fullheal": {"kind": "bag", "item": ("full-heal", 2), "w": 2},
    "revive":   {"kind": "bag", "item": ("revive", 2), "w": 5},
    "maxrevive": {"kind": "bag", "item": ("max-revive", 1), "w": 1.5},
    "sacred":   {"kind": "bag", "item": ("sacred-ash", 1), "w": 0.5},
    "ether":    {"kind": "bag", "item": ("ether", 2), "w": 3},
    "maxether": {"kind": "bag", "item": ("max-ether", 1), "w": 1.5},
    "elixir":   {"kind": "bag", "item": ("elixir", 1), "w": 2},
    "maxelixir": {"kind": "bag", "item": ("max-elixir", 1), "w": 1},
    "ppup":     {"kind": "bag", "item": ("pp-up", 1), "w": 2},
    "ppmax":    {"kind": "bag", "item": ("pp-max", 1), "w": 0.6},
    "xattack":  {"kind": "bag", "item": ("x-attack", 2), "w": 1.5},
    "xspatk":   {"kind": "bag", "item": ("x-sp-atk", 2), "w": 1.5},
    "xspeed":   {"kind": "bag", "item": ("x-speed", 2), "w": 1.5},
    "xdefense": {"kind": "bag", "item": ("x-defense", 2), "w": 1},
    "xspdef":   {"kind": "bag", "item": ("x-sp-def", 2), "w": 1},
    "direhit":  {"kind": "bag", "item": ("dire-hit", 2), "w": 1},
    "candy":    {"kind": "target", "n": "이상한사탕", "d": "레벨이 1 오른다", "icon": "rare-candy", "w": 10},
    "candy3":   {"kind": "target", "n": "이상한사탕 x3", "d": "레벨이 3 오른다", "icon": "rare-candy", "w": 2},
    "hpup":     {"kind": "target", "vit": 0, "icon": "hp-up", "w": 2},
    "protein":  {"kind": "target", "vit": 1, "icon": "protein", "w": 2},
    "iron":     {"kind": "target", "vit": 2, "icon": "iron", "w": 2},
    "calcium":  {"kind": "target", "vit": 3, "icon": "calcium", "w": 2},
    "zinc":     {"kind": "target", "vit": 4, "icon": "zinc", "w": 2},
    "carbos":   {"kind": "target", "vit": 5, "icon": "carbos", "w": 2},
    "expcharm": {"kind": "run", "n": "경험치 부적", "d": "이번 게임 동안 경험치를 더 받는다", "icon": "exp-share", "w": 3},
    "nugget":   {"kind": "money", "n": "금구슬", "d": "팔면 돈이 되는 금빛 구슬", "icon": "nugget", "w": 5},
}
TM_WEIGHT, HELD_WEIGHT, EVO_WEIGHT = 7, 5, 6
MAX_VITAMIN = 10
_VIT_ITEM = ["hp-up", "protein", "iron", "calcium", "zinc", "carbos"]


def _valid_reward(key: str) -> bool:
    if key in REWARDS:
        return True
    kind, _, val = key.partition(":")
    if kind == "tm":
        return val.isdigit() and int(val) in D.MOVES
    return kind in ("held", "evo") and val in ITEMS


def reward_info(key: str, run: dict | None = None) -> dict:
    """보상 표시용: {"n": 이름, "d": 설명, "icon": 그림 이름, "kind": ...}"""
    kind, _, val = key.partition(":")
    if kind == "tm":
        m = D.MOVES[int(val)]
        who = ""
        if run:
            names = [D.name(x["sid"]) for i, x in enumerate(run["party"]) if i in _tm_targets(run, int(val))]
            who = (" · " + ", ".join(names[:3]) + (" 등" if len(names) > 3 else "")) if names else ""
        return {"kind": "tm", "n": f"기술머신 {m['n']}",
                "d": f"{D.TYPE_KO[m['t']]} {'물리' if m['c'] == 0 else '특수'} 위력 {m['p']}{who}",
                "icon": f"tm-{D.TYPE_EN[m['t']]}"}
    if kind == "held":
        return {"kind": "held", "n": item_name(val), "d": HELD[val], "icon": val}
    if kind == "evo":
        return {"kind": "evo", "n": item_name(val), "d": "쓰면 진화하는 포켓몬이 있다", "icon": val}
    r = dict(REWARDS[key])
    if r["kind"] == "bag":
        item, cnt = r["item"]
        r.setdefault("n", item_name(item) + (f" x{cnt}" if cnt > 1 else ""))
        r.setdefault("d", ITEMS[item]["d"])
        r.setdefault("icon", item)
    elif "vit" in r:
        r["n"] = item_name(r["icon"])
        r["d"] = f"{D.STAT_KO[r['vit']]} 능력치가 오른다"
    return r


def nugget_value(wave: int) -> int:
    return 500 + wave * 40


def reroll_cost(run: dict) -> int:
    return int((150 + run["wave"] * 10) * (run.get("rerolls", 0) + 1))


def shop_price(run: dict, item: str) -> int:
    """웨이브가 오를수록 조금씩 비싸진다 (PokeRogue처럼)"""
    price = ITEMS[item]["price"] * (1 + run["wave"] // BIOME_SIZE * 0.2)
    return int(price / 10) * 10


def shop_open(run: dict) -> bool:
    return run.get("rule") != "noitems"


def _tm_targets(run: dict, mid: int) -> list[int]:
    return [i for i, m in enumerate(run["party"])
            if mid in D.SPECIES[m["sid"]]["tm"] and mid not in m["moves"] and mid not in m.get("pend", [])]


def _tm_candidates(run: dict) -> list[int]:
    out = set()
    for m in run["party"]:
        for mid in D.SPECIES[m["sid"]]["tm"]:
            if mid not in m["moves"] and D.MOVES[mid]["p"] >= 50:
                out.add(mid)
    return sorted(out)


def _evo_candidates(run: dict) -> list[str]:
    out = set()
    for m in run["party"]:
        for c, how, val in D.SPECIES[m["sid"]]["evo"]:
            if how == "item":
                out.add(val)
            elif how == "trade":
                out.add("linking-cord")
    return sorted(out)


def roll_rewards(run: dict, rng: random.Random, n: int = 3) -> list[str]:
    rng = _srng(run, rng, "reward", run["wave"], run.get("rerolls", 0))
    weights = {k: v["w"] for k, v in REWARDS.items()}
    if run.get("rule") == "noitems":
        for k, v in REWARDS.items():
            if v["kind"] == "bag" and not is_ball(v["item"][0]):
                weights[k] = 0
    hurt = sum(1 for m in run["party"] if m["hp"] < max_hp(m) * 0.5)
    fainted = sum(1 for m in run["party"] if m["hp"] <= 0)
    low_pp = any(m["pp"][j] <= max_pp(m, j) // 4 for m in run["party"] for j in range(len(m["moves"])))
    if hurt:
        for k in ("potion", "superpot", "hyperpot"):
            weights[k] *= 2
    if fainted:
        weights["revive"] *= 3
        weights["maxrevive"] *= 2
    if low_pp:
        for k in ("ether", "maxether", "elixir", "maxelixir"):
            weights[k] *= 3
    if len(run["party"]) >= MAX_PARTY:
        for k in ("balls", "great", "ultra", "quick", "timer", "net", "healball"):
            weights[k] /= 3
    if all(m["lv"] >= MAX_LEVEL for m in run["party"]):
        weights["candy"] = weights["candy3"] = 0
    # 동적 보상 (기술머신, 지닌 물건, 진화 아이템)
    tms = _tm_candidates(run)
    if tms:
        weights[f"tm:{rng.choice(tms)}"] = TM_WEIGHT
    if run.get("rule") != "noitems":
        weights[f"held:{rng.choice(list(HELD))}"] = HELD_WEIGHT
    evos = _evo_candidates(run)
    if evos:
        weights[f"evo:{rng.choice(evos)}"] = EVO_WEIGHT
    picks: list[str] = []
    for _ in range(n):
        keys = [k for k in weights if weights[k] > 0 and k not in picks]
        if not keys:
            break
        picks.append(rng.choices(keys, weights=[weights[k] for k in keys])[0])
    return picks


def reward_targets(run: dict, key: str) -> list[int]:
    """포켓몬을 골라야 하는 보상이면 고를 수 있는 번호 (아니면 [])"""
    kind, _, val = key.partition(":")
    if kind == "tm":
        return _tm_targets(run, int(val))
    if kind == "held":
        return [i for i, m in enumerate(run["party"]) if m.get("held") != val]
    if kind == "evo":
        return [i for i, m in enumerate(run["party"]) if evo_child(m, val) is not None]
    r = REWARDS[key]
    if r["kind"] != "target":
        return []
    if "vit" in r:
        return [i for i, m in enumerate(run["party"]) if m["vit"][r["vit"]] < MAX_VITAMIN]
    return [i for i, m in enumerate(run["party"]) if m["lv"] < level_cap(m)]


def needs_target(key: str) -> bool:
    return key.partition(":")[0] in ("tm", "held", "evo") or REWARDS.get(key, {}).get("kind") == "target"


def apply_reward(run: dict, key: str, target: int | None = None) -> list[str]:
    info = reward_info(key, run)
    msgs = [f"🎁 **{info['n']}**을(를) 골랐다!"]
    if needs_target(key) and target not in reward_targets(run, key):
        raise ValueError("bad target")
    kind, _, val = key.partition(":")
    if kind == "tm":
        msgs.append(learn(run["party"][target], int(val)) or "")
    elif kind == "held":
        add_item(run, val)
        msgs.extend(_give_held(run, val, target))
    elif kind == "evo":
        m = run["party"][target]
        msgs.extend(evolve(m, evo_child(m, val)))
    else:
        r = REWARDS[key]
        if r["kind"] == "bag":
            item, cnt = r["item"]
            add_item(run, item, cnt)
            msgs.append(f"가방에 {item_name(item)}을(를) {cnt}개 넣었다. (가지고 있는 수 {run['bag'][item]})")
        elif r["kind"] == "money":
            v = nugget_value(run["wave"])
            run["money"] += v
            msgs.append(f"💰 ₽{v:,}을(를) 받았다! (소지금 ₽{run['money']:,})")
        elif r["kind"] == "run":
            run["exp_mult"] = round(run.get("exp_mult", 1.0) + 0.25, 2)
            msgs.append(f"얻는 경험치가 {int(run['exp_mult'] * 100)}%가 됐다.")
        else:
            p = run["party"][target]
            if "vit" in r:
                i = r["vit"]
                old_max = max_hp(p)
                p["vit"][i] += 1
                if i == 0 and p["hp"] > 0:
                    p["hp"] += max_hp(p) - old_max
                msgs.append(f"{D.name(p['sid'])}의 {D.STAT_KO[i]}이(가) 올랐다! ({p['vit'][i]}/{MAX_VITAMIN})")
            else:
                for _ in range(3 if key == "candy3" else 1):
                    if p["lv"] < level_cap(p):
                        p["exp"] = 0
                        msgs.extend(level_up(p))
    return [x for x in msgs if x]


def _give_held(run: dict, item: str, target: int) -> list[str]:
    m = run["party"][target]
    _take(run, item)
    old = m.get("held")
    m["held"] = item
    out = [f"{D.name(m['sid'])}에게 {item_name(item)}을(를) 지니게 했다."]
    if old:
        add_item(run, old)
        out.append(f"원래 지니고 있던 {item_name(old)}은(는) 가방에 넣었다.")
    return out


def choose_reward(run: dict, index: int, rng: random.Random | None = None, target: int | None = None) -> list[str]:
    rng = rng or random.Random()
    key = run["rewards"][index]
    msgs = apply_reward(run, key, target)
    run["rewards"] = []
    msgs.extend(advance(run, rng))
    run["log"] = msgs
    return msgs


def advance(run: dict, rng: random.Random) -> list[str]:
    """보상 다음: 기술 잊기 → 다음 웨이브"""
    if learner(run) is not None:
        run["phase"] = "learn"
        run["after_learn"] = "next_wave"
        return []
    return start_wave(run, rng)


def skip_reward(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    run["rewards"] = []
    msgs = ["보상을 받지 않고 넘어갔다."] + advance(run, rng)
    run["log"] = msgs
    return msgs


def reroll(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    cost = reroll_cost(run)
    if run["money"] < cost:
        raise ValueError("no money")
    run["money"] -= cost
    run["rerolls"] = run.get("rerolls", 0) + 1
    run["rewards"] = roll_rewards(run, rng)
    run["log"] = [f"🎲 ₽{cost:,}을(를) 내고 보상을 다시 뽑았다. (소지금 ₽{run['money']:,})"]
    return run["log"]


def buy(run: dict, item: str) -> list[str]:
    price = shop_price(run, item)
    if item not in SHOP or run["money"] < price or not shop_open(run):
        raise ValueError("cannot buy")
    run["money"] -= price
    add_item(run, item)
    run["log"] = [f"🛒 {item_name(item)}을(를) ₽{price:,}에 샀다. (소지금 ₽{run['money']:,})"]
    return run["log"]
