"""PokeRogue식 게임 배틀 엔진 (디스코드와 무관한 순수 파이썬).

게임 상태는 JSON으로 저장할 수 있는 dict 하나예요.

run = {
  "wave": 1, "phase": "battle" | "reward" | "over" | "clear",
  "p": 내 포켓몬, "e": 상대 포켓몬, "log": [최근 메시지], "rewards": [보상 id],
  "exp_mult": 1.0, "starter": 종 번호, "best_hit": 최고 데미지,
}
포켓몬 = {"sid", "lv", "exp"(현재 레벨에서 모은 양), "hp", "iv"[6], "moves"[기술 id],
         "stg"[공 방 특공 특방 스피드 랭크], "status", "rc"(다음 턴 쉬기), "vit"[6], "boss"}
"""

import math
import random

from . import data as D

MAX_LEVEL = 100
FINAL_WAVE = 100
BIOME_SIZE = 10         # 10웨이브마다 보스 + 새 지역(전체 회복)
WIN_HEAL = 0.35         # 이길 때마다 최대 HP의 35% 회복 (혼자 싸우는 대신 주는 보정)

STATUS_KO = {"par": "마비", "brn": "화상", "psn": "독", "frz": "얼음"}
AILMENT = {1: "par", 3: "frz", 4: "brn", 5: "psn"}
STATUS_IMMUNE = {"par": {13}, "brn": {10}, "psn": {4, 9}, "frz": {15}}

BIOMES = ["풀숲", "동굴", "해변", "숲", "화산", "설원", "도시", "유적", "하늘탑", "챔피언로드"]


# ---------- 능력치 ----------
def max_hp(mon: dict) -> int:
    b = D.SPECIES[mon["sid"]]["s"][0]
    if b == 1:  # 껍질몬 같은 HP 1 고정 포켓몬
        return 1
    hp = (2 * b + mon["iv"][0]) * mon["lv"] // 100 + mon["lv"] + 10
    hp = int(hp * (1 + 0.1 * mon.get("vit", [0] * 6)[0]))
    return int(hp * 1.3) if mon.get("boss") else hp


def stat(mon: dict, i: int) -> int:
    """i: 1 공격, 2 방어, 3 특공, 4 특방, 5 스피드 (랭크·비타민·상태이상 반영)"""
    b = D.SPECIES[mon["sid"]]["s"][i]
    v = (2 * b + mon["iv"][i]) * mon["lv"] // 100 + 5
    v *= 1 + 0.1 * mon.get("vit", [0] * 6)[i]
    s = mon["stg"][i - 1]
    v *= (2 + s) / 2 if s >= 0 else 2 / (2 - s)
    if i == 5 and mon.get("status") == "par":
        v *= 0.5
    return max(1, int(v))


def stats_line(mon: dict) -> list[tuple[str, int]]:
    return [("HP", max_hp(mon))] + [(D.STAT_KO[i], stat(mon, i)) for i in range(1, 6)]


def exp_to_next(mon: dict) -> int:
    if mon["lv"] >= MAX_LEVEL:
        return 0
    g = D.SPECIES[mon["sid"]]["g"]
    return D.total_exp(g, mon["lv"] + 1) - D.total_exp(g, mon["lv"])


# ---------- 기술 ----------
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
    """새 기술을 배운다. 4개가 차 있으면 가장 약한 기술을 잊는다."""
    if move_id in mon["moves"]:
        return None
    new = D.MOVES[move_id]
    if len(mon["moves"]) < 4:
        mon["moves"].append(move_id)
        return f"**{new['n']}**을(를) 배웠다!"
    weakest = min(mon["moves"], key=lambda m: _move_value(mon, m))
    if _move_value(mon, move_id) <= _move_value(mon, weakest):
        return None
    mon["moves"][mon["moves"].index(weakest)] = move_id
    return f"**{D.MOVES[weakest]['n']}**을(를) 잊고 **{new['n']}**을(를) 배웠다!"


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
        "moves": pick_moves(sid, lv), "stg": [0] * 5, "status": None, "rc": 0,
        "vit": [0] * 6, "boss": boss,
    }
    mon["hp"] = max_hp(mon)
    return mon


def new_run(starter: int, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    p = new_mon(starter, 5, rng)
    p["iv"] = [max(iv, 20) for iv in p["iv"]]   # 스타팅은 개체값 최소 20 보장
    p["hp"] = max_hp(p)
    run = {"wave": 0, "phase": "battle", "p": p, "e": None, "log": [], "rewards": [],
           "exp_mult": 1.0, "starter": starter, "best_hit": 0}
    start_wave(run, rng)
    return run


# ---------- 웨이브 ----------
def is_boss_wave(wave: int) -> bool:
    return wave % BIOME_SIZE == 0


def biome(wave: int) -> str:
    return BIOMES[((wave - 1) // BIOME_SIZE) % len(BIOMES)]


def enemy_level(wave: int, rng: random.Random) -> int:
    jitter = rng.choice([-2, -1, -1, 0]) if wave <= 10 else rng.choice([-1, 0, 0, 1])
    lv = 1.5 + wave * 0.85 + jitter
    if is_boss_wave(wave) and wave >= 30:
        lv += 2
    return max(2, min(MAX_LEVEL, round(lv)))


_BASE_POOL = [sid for sid, s in D.SPECIES.items() if not s["from"] and not s["leg"]]
_LEGEND_POOL = [sid for sid, s in D.SPECIES.items() if s["leg"] and not s["from"] and D.bst(sid) >= 580]


def _evolve_for_level(sid: int, lv: int, rng: random.Random) -> int:
    while True:
        options = [c for c, ml in D.SPECIES[sid]["evo"] if (ml and ml <= lv) or (ml is None and lv >= 32)]
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
    sid = _evolve_for_level(rng.choice(pool), lv, rng)
    if is_boss_wave(wave):   # 보스는 한 단계 더 진화 (30웨이브부터는 최종 진화형)
        sid = _evolve_for_level(sid, MAX_LEVEL if wave >= 30 else lv + 8, rng)
    return sid


def start_wave(run: dict, rng: random.Random) -> list[str]:
    run["wave"] += 1
    wave = run["wave"]
    msgs = []
    if wave > 1 and (wave - 1) % BIOME_SIZE == 0:
        heal_full(run["p"])
        msgs.append(f"🗺️ 새 지역 **{biome(wave)}**에 도착했다! 포켓몬이 모두 회복됐다.")
    nxt = run.pop("next_e", None)
    if nxt and nxt.get("wave") == wave:   # 보상 고르는 동안 미리 정해 둔 상대 (그림을 미리 받아 두려고)
        run["e"] = nxt["mon"]
    else:
        run["e"] = roll_enemy(wave, rng)
    sid, lv, boss = run["e"]["sid"], run["e"]["lv"], run["e"]["boss"]
    p = run["p"]
    p["stg"] = [0] * 5
    p["rc"] = 0
    tag = "👑 보스 " if boss else ("⚠️ 마지막 보스 " if wave == FINAL_WAVE else "야생의 ")
    msgs.append(f"{tag}**{D.name(sid)}** Lv.{lv}이(가) 나타났다!")
    run["phase"] = "battle"
    run["log"] = msgs
    return msgs


def roll_enemy(wave: int, rng: random.Random) -> dict:
    lv = enemy_level(wave, rng)
    return new_mon(wild_species(wave, lv, rng), lv, rng, boss=is_boss_wave(wave))


def heal_full(mon: dict):
    mon["hp"] = max_hp(mon)
    mon["status"] = None


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
    return (max(1, int(base * mult)) if eff > 0 else 0), eff


def _expected(att: dict, dfn: dict, mid: int) -> float:
    m = D.MOVES[mid]
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
    """시뮬레이션용: 기대 데미지가 가장 큰 기술"""
    vals = [_expected(att, dfn, m) for m in att["moves"]]
    return vals.index(max(vals))


def _act(user: dict, target: dict, mid: int, uname: str, tname: str, rng: random.Random, log: list, run: dict, is_player: bool):
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

    m = D.MOVES[mid]
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

    total, hits, crit_any = 0, _hit_count(m, rng), False
    for _ in range(hits):
        crit = rng.random() < (1 / 24, 1 / 8, 1 / 2, 1.0)[min(3, m.get("cr", 0))]
        crit_any |= crit
        dmg, _ = damage(user, target, m, rng, crit)
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

    if m.get("dr") and total:
        amt = max(1, abs(total * m["dr"]) // 100)
        if m["dr"] > 0:
            user["hp"] = min(max_hp(user), user["hp"] + amt)
            log.append(f"{tname}의 체력을 흡수했다!")
        else:
            user["hp"] = max(0, user["hp"] - amt)
            log.append(f"{uname}은(는) 반동 데미지를 입었다!")

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
                i = s_id - 2
                before = who["stg"][i]
                who["stg"][i] = max(-6, min(6, before + ch))
                if who["stg"][i] != before:
                    word = "올라갔다" if ch > 0 else "떨어졌다"
                    if abs(ch) >= 2:
                        word = "크게 " + word
                    log.append(f"{wname}의 {D.STAT_KO[s_id - 1]}이(가) {word}!")


def _end_of_turn(mon: dict, name: str, log: list):
    if mon["hp"] <= 0:
        return
    if mon.get("status") == "brn":
        d = max(1, max_hp(mon) // 16)
        mon["hp"] = max(0, mon["hp"] - d)
        log.append(f"{name}은(는) 화상 데미지를 입었다!")
    elif mon.get("status") == "psn":
        d = max(1, max_hp(mon) // 8)
        mon["hp"] = max(0, mon["hp"] - d)
        log.append(f"{name}은(는) 독 데미지를 입었다!")


def take_turn(run: dict, move_index: int, rng: random.Random | None = None) -> str:
    """플레이어가 기술을 고르면 한 턴을 진행한다. 결과: 'continue' | 'win' | 'lose'"""
    rng = rng or random.Random()
    p, e = run["p"], run["e"]
    pname, ename = D.name(p["sid"]), ("상대 " + D.name(e["sid"]))
    log: list[str] = []
    pmove = p["moves"][move_index] if not p["rc"] else p["moves"][0]
    emove = ai_move(e, p, rng)

    def order_key(mon, mid):
        return (D.MOVES[mid]["pr"] if not mon["rc"] else 0, stat(mon, 5), rng.random())

    first_player = order_key(p, pmove) >= order_key(e, emove)
    turns = [(p, e, pmove, pname, ename, True), (e, p, emove, ename, pname, False)]
    if not first_player:
        turns.reverse()
    for user, target, mid, un, tn, is_p in turns:
        if user["hp"] <= 0 or target["hp"] <= 0:
            continue
        _act(user, target, mid, un, tn, rng, log, run, is_p)
    _end_of_turn(p, pname, log)
    _end_of_turn(e, ename, log)

    run["log"] = log
    if p["hp"] <= 0:
        log.append(f"{pname}은(는) 쓰러졌다...")
        run["phase"] = "over"
        return "lose"
    if e["hp"] <= 0:
        log.append(f"{ename}은(는) 쓰러졌다!")
        log.extend(win(run, rng))
        return "win"
    return "continue"


# ---------- 승리, 경험치, 진화 ----------
def exp_gain(p: dict, e: dict, mult: float) -> int:
    b, le, lp = D.SPECIES[e["sid"]]["x"], e["lv"], p["lv"]
    exp = (b * le / 5) * ((2 * le + 10) / (le + lp + 10)) ** 2.5 + 1
    if e.get("boss"):
        exp *= 1.5
    return max(1, int(exp * mult))


def gain_exp(p: dict, amount: int) -> list[str]:
    msgs = []
    if p["lv"] >= MAX_LEVEL:
        return msgs
    p["exp"] += amount
    while p["lv"] < MAX_LEVEL and p["exp"] >= exp_to_next(p):
        p["exp"] -= exp_to_next(p)
        msgs.extend(level_up(p))
    if p["lv"] >= MAX_LEVEL:
        p["exp"] = 0
    return msgs


def level_up(p: dict) -> list[str]:
    old_max = max_hp(p)
    p["lv"] += 1
    p["hp"] = min(max_hp(p), p["hp"] + max_hp(p) - old_max)
    msgs = [f"⬆️ {D.name(p['sid'])}은(는) **Lv.{p['lv']}**(으)로 올랐다!"]
    for l, mid in D.SPECIES[p["sid"]]["ls"]:
        if l == p["lv"]:
            if (msg := learn(p, mid)):
                msgs.append(msg)
    msgs.extend(try_evolve(p))
    return msgs


def try_evolve(p: dict) -> list[str]:
    options = [c for c, ml in D.SPECIES[p["sid"]]["evo"] if ml and ml <= p["lv"]]
    if not options:
        return []
    before = D.name(p["sid"])
    old_max = max_hp(p)
    p["sid"] = options[0]
    p["hp"] = min(max_hp(p), p["hp"] + max_hp(p) - old_max)
    msgs = [f"✨ 축하합니다! **{before}**은(는) **{D.name(p['sid'])}**(으)로 진화했다!"]
    for l, mid in D.SPECIES[p["sid"]]["ls"]:
        if l in (1, p["lv"]) and mid not in p["moves"]:
            if (msg := learn(p, mid)):
                msgs.append(msg)
    return msgs


def win(run: dict, rng: random.Random) -> list[str]:
    p, e = run["p"], run["e"]
    amount = exp_gain(p, e, run.get("exp_mult", 1.0))
    msgs = [f"{D.name(p['sid'])}은(는) 경험치 **{amount}**을(를) 얻었다!"]
    msgs.extend(gain_exp(p, amount))
    p["stg"] = [0] * 5
    p["rc"] = 0
    if p["hp"] < max_hp(p):
        before = p["hp"]
        p["hp"] = min(max_hp(p), p["hp"] + int(max_hp(p) * WIN_HEAL))
        msgs.append(f"{D.name(p['sid'])}은(는) 숨을 골랐다. (HP +{p['hp'] - before})")
    if run["wave"] >= FINAL_WAVE:
        run["phase"] = "clear"
        msgs.append(f"🏆 **{FINAL_WAVE}웨이브 클리어!** 전설을 쓰러뜨렸다!")
        return msgs
    run["phase"] = "reward"
    run["rewards"] = roll_rewards(run, rng)
    run["next_e"] = {"wave": run["wave"] + 1, "mon": roll_enemy(run["wave"] + 1, rng)}
    return msgs


# ---------- 보상 ----------
REWARDS = {
    "potion":     {"n": "상처약", "d": "HP를 30% 회복", "w": 30},
    "superpot":   {"n": "좋은상처약", "d": "HP를 60% 회복", "w": 18},
    "fullrest":   {"n": "회복약", "d": "HP와 상태이상을 모두 회복", "w": 6},
    "fullheal":   {"n": "만병통치제", "d": "상태이상 회복", "w": 0},
    "candy":      {"n": "이상한사탕", "d": "레벨이 1 오른다", "w": 12},
    "candy3":     {"n": "이상한사탕 x3", "d": "레벨이 3 오른다", "w": 2},
    "hpup":       {"n": "맥스업", "d": "최대 HP +10% (이번 게임)", "w": 5},
    "protein":    {"n": "타우린", "d": "공격 +10% (이번 게임)", "w": 5},
    "iron":       {"n": "사포닌", "d": "방어 +10% (이번 게임)", "w": 5},
    "calcium":    {"n": "리보플라빈", "d": "특공 +10% (이번 게임)", "w": 5},
    "zinc":       {"n": "키토산", "d": "특방 +10% (이번 게임)", "w": 5},
    "carbos":     {"n": "알칼로이드", "d": "스피드 +10% (이번 게임)", "w": 5},
    "expcharm":   {"n": "학습장치", "d": "얻는 경험치 +25% (이번 게임)", "w": 4},
}
VITAMIN = {"hpup": 0, "protein": 1, "iron": 2, "calcium": 3, "zinc": 4, "carbos": 5}
MAX_VITAMIN = 10


def roll_rewards(run: dict, rng: random.Random, n: int = 3) -> list[str]:
    p = run["p"]
    ratio = p["hp"] / max_hp(p)
    weights = {k: v["w"] for k, v in REWARDS.items()}
    # 체력이 낮을수록 회복 아이템이 잘 나오게 (PokeRogue 방식)
    if ratio > 0.9:
        weights["potion"] = weights["superpot"] = weights["fullrest"] = 0
    elif ratio < 0.5:
        weights["potion"] *= 2
        weights["superpot"] *= 2
        weights["fullrest"] *= 2
    if p.get("status"):
        weights["fullheal"] = 25
    for k, i in VITAMIN.items():
        if p["vit"][i] >= MAX_VITAMIN:
            weights[k] = 0
    if p["lv"] >= MAX_LEVEL:
        weights["candy"] = weights["candy3"] = 0
    picks: list[str] = []
    if ratio < 0.7:   # 체력이 부족하면 회복 아이템 하나는 꼭 나오게
        heal = rng.choices(["potion", "superpot", "fullrest"], weights=[5, 4, 1])[0]
        picks.append(heal)
    for _ in range(n - len(picks)):
        keys = [k for k in weights if weights[k] > 0 and k not in picks]
        if not keys:
            break
        picks.append(rng.choices(keys, weights=[weights[k] for k in keys])[0])
    return picks


def apply_reward(run: dict, key: str) -> list[str]:
    p = run["p"]
    pname = D.name(p["sid"])
    r = REWARDS[key]
    msgs = [f"🎁 **{r['n']}**을(를) 골랐다!"]
    mh = max_hp(p)
    if key in ("potion", "superpot"):
        amt = int(mh * (0.3 if key == "potion" else 0.6))
        before = p["hp"]
        p["hp"] = min(mh, p["hp"] + amt)
        msgs.append(f"{pname}의 HP가 {p['hp'] - before} 회복됐다.")
    elif key == "fullrest":
        heal_full(p)
        msgs.append(f"{pname}의 HP와 상태가 모두 회복됐다.")
    elif key == "fullheal":
        p["status"] = None
        msgs.append(f"{pname}의 상태이상이 나았다.")
    elif key in ("candy", "candy3"):
        for _ in range(3 if key == "candy3" else 1):
            if p["lv"] < MAX_LEVEL:
                p["exp"] = 0
                msgs.extend(level_up(p))
    elif key in VITAMIN:
        i = VITAMIN[key]
        old_max = max_hp(p)
        p["vit"][i] += 1
        if i == 0:
            p["hp"] += max_hp(p) - old_max
        msgs.append(f"{pname}의 {D.STAT_KO[i]}이(가) 올랐다! ({p['vit'][i]}/{MAX_VITAMIN})")
    elif key == "expcharm":
        run["exp_mult"] = round(run.get("exp_mult", 1.0) + 0.25, 2)
        msgs.append(f"얻는 경험치가 {int(run['exp_mult'] * 100)}%가 됐다.")
    return msgs


def choose_reward(run: dict, index: int, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    key = run["rewards"][index]
    msgs = apply_reward(run, key)
    run["rewards"] = []
    msgs.extend(start_wave(run, rng))
    run["log"] = msgs
    return msgs


def skip_reward(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    run["rewards"] = []
    msgs = ["보상을 받지 않고 넘어갔다."] + start_wave(run, rng)
    run["log"] = msgs
    return msgs
