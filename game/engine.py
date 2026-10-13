"""PokeRogue식 게임 배틀 엔진 (디스코드와 무관한 순수 파이썬).

게임 상태는 JSON으로 저장할 수 있는 dict 하나예요.

run = {
  "wave": 1, "phase": "battle" | "switch"(기절 후 교체) | "reward" | "replace"(파티 가득) | "over" | "clear",
  "party": [포켓몬 최대 6], "active": 앞에 나온 번호, "e": 상대 포켓몬, "log": [최근 메시지],
  "rewards": [보상 id], "money": 돈, "bag": {아이템: 개수}, "rerolls": 이번 웨이브 다시 뽑기 횟수,
  "exp_mult": 1.0, "starter": 종 번호, "best_hit": 최고 데미지, "caught": 잡은 수,
  "next_e": 다음 웨이브 상대(미리 정함), "pending": 파티가 가득 찼을 때 잡은 포켓몬,
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
WIN_HEAL = 0.15         # 이길 때마다 살아 있는 파티 포켓몬 HP 15% 회복
LEVEL_PER_WAVE = 0.85   # 웨이브당 상대 레벨 증가
MONEY_BASE = 100        # 웨이브 보상 돈 = MONEY_BASE + 웨이브 × MONEY_PER_WAVE (보스 2.5배)
MONEY_PER_WAVE = 25
EXP_BASE = 1.8          # 기본 경험치 배율 (PokeRogue처럼 넉넉하게)

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
    run = {"wave": 0, "phase": "battle", "party": [p], "active": 0, "e": None, "log": [],
           "rewards": [], "money": START_MONEY, "bag": dict(START_BAG), "rerolls": 0,
           "exp_mult": 1.0, "starter": starter, "best_hit": 0, "caught": 0}
    start_wave(run, rng)
    return run


def normalize(run: dict) -> dict:
    """예전(포켓몬 한 마리) 저장 형식을 파티 형식으로 바꾼다."""
    if "party" not in run:
        run["party"] = [run.pop("p")]
        run["active"] = 0
    run.setdefault("money", START_MONEY)
    run.setdefault("bag", dict(START_BAG))
    run.setdefault("rerolls", 0)
    run.setdefault("caught", 0)
    return run


# ---------- 파티 ----------
MAX_PARTY = 6


def lead(run: dict) -> dict:
    return run["party"][run["active"]]


def alive(run: dict) -> list[int]:
    return [i for i, m in enumerate(run["party"]) if m["hp"] > 0]


def heal_party(run: dict, revive: bool = True):
    for m in run["party"]:
        if m["hp"] > 0 or revive:
            heal_full(m)


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


def roll_enemy(wave: int, rng: random.Random) -> dict:
    lv = enemy_level(wave, rng)
    return new_mon(wild_species(wave, lv, rng), lv, rng, boss=is_boss_wave(wave))


def start_wave(run: dict, rng: random.Random) -> list[str]:
    run["wave"] += 1
    wave = run["wave"]
    msgs = []
    if wave > 1 and (wave - 1) % BIOME_SIZE == 0:
        heal_party(run)
        msgs.append(f"🗺️ 새 지역 **{biome(wave)}**에 도착했다! 파티가 모두 회복됐다.")
    nxt = run.pop("next_e", None)
    if nxt and nxt.get("wave") == wave:   # 보상 고르는 동안 미리 정해 둔 상대 (그림을 미리 받아 두려고)
        run["e"] = nxt["mon"]
    else:
        run["e"] = roll_enemy(wave, rng)
    sid, lv, boss = run["e"]["sid"], run["e"]["lv"], run["e"]["boss"]
    for m in run["party"]:
        m["stg"] = [0] * 5
        m["rc"] = 0
    if lead(run)["hp"] <= 0:
        run["active"] = alive(run)[0]
    run["rerolls"] = 0
    tag = "⚠️ 마지막 보스 " if wave == FINAL_WAVE else ("👑 보스 " if boss else "야생의 ")
    msgs.append(f"{tag}**{D.name(sid)}** Lv.{lv}이(가) 나타났다!")
    run["phase"] = "battle"
    run["log"] = msgs
    return msgs


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


def _ename(run: dict) -> str:
    return "상대 " + D.name(run["e"]["sid"])


def _after_enemy_action(run: dict, log: list, rng: random.Random) -> str:
    """턴 끝 처리(화상·독)와 기절 판정. 결과: 'continue' | 'win' | 'switch' | 'lose'"""
    p, e = lead(run), run["e"]
    _end_of_turn(p, D.name(p["sid"]), log)
    _end_of_turn(e, _ename(run), log)
    run["log"] = log
    if e["hp"] <= 0:
        log.append(f"{_ename(run)}은(는) 쓰러졌다!")
        if not alive(run):   # 같은 턴에 내 마지막 포켓몬도 쓰러짐 → 패배
            log.append(f"{D.name(p['sid'])}도 쓰러졌다...")
            return _on_lead_fainted(run, log)
        log.extend(win(run, rng))
        return "win"
    if p["hp"] <= 0:
        log.append(f"{D.name(p['sid'])}은(는) 쓰러졌다...")
        return _on_lead_fainted(run, log)
    return "continue"


def _on_lead_fainted(run: dict, log: list) -> str:
    p = lead(run)
    p["stg"] = [0] * 5
    p["rc"] = 0
    if alive(run):
        run["phase"] = "switch"
        log.append("다음 포켓몬을 골라 주세요!")
        return "switch"
    run["phase"] = "over"
    log.append("눈앞이 캄캄해졌다...")
    return "lose"


def _enemy_turn(run: dict, log: list, rng: random.Random):
    p, e = lead(run), run["e"]
    if e["hp"] > 0 and p["hp"] > 0:
        _act(e, p, ai_move(e, p, rng), _ename(run), D.name(p["sid"]), rng, log, run, False)


def take_turn(run: dict, move_index: int, rng: random.Random | None = None) -> str:
    """앞에 나온 포켓몬이 기술을 쓴다. 결과: 'continue' | 'win' | 'switch' | 'lose'"""
    rng = rng or random.Random()
    p, e = lead(run), run["e"]
    pname, ename = D.name(p["sid"]), _ename(run)
    log: list[str] = []
    pmove = p["moves"][move_index] if not p["rc"] else p["moves"][0]
    emove = ai_move(e, p, rng)

    def order_key(mon, mid):
        return (D.MOVES[mid]["pr"] if not mon["rc"] else 0, stat(mon, 5), rng.random())

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
    old["stg"] = [0] * 5
    old["rc"] = 0
    run["active"] = index
    new = lead(run)
    log = [] if forced else [f"돌아와, {D.name(old['sid'])}!"]
    log.append(f"가랏, **{D.name(new['sid'])}**!")
    run["phase"] = "battle"
    if forced:
        run["log"] = log
        return "continue"
    _enemy_turn(run, log, rng)
    return _after_enemy_action(run, log, rng)


# ---------- 가방 ----------
ITEMS = {
    "pokeball":   {"n": "몬스터볼", "d": "야생 포켓몬을 잡는다", "ball": 1.0, "price": 200},
    "greatball":  {"n": "수퍼볼", "d": "몬스터볼보다 잘 잡힌다 (1.5배)", "ball": 1.5, "price": 600},
    "ultraball":  {"n": "하이퍼볼", "d": "아주 잘 잡힌다 (2배)", "ball": 2.0, "price": 1200},
    "masterball": {"n": "마스터볼", "d": "반드시 잡힌다", "ball": 255.0, "price": 0},
    "potion":     {"n": "상처약", "d": "HP를 30% 회복", "heal": 0.3, "price": 300},
    "superpot":   {"n": "좋은상처약", "d": "HP를 60% 회복", "heal": 0.6, "price": 700},
    "fullrest":   {"n": "회복약", "d": "HP와 상태이상을 모두 회복", "heal": 1.0, "cure": True, "price": 2000},
    "fullheal":   {"n": "만병통치제", "d": "상태이상 회복", "cure": True, "price": 400},
    "revive":     {"n": "기력의조각", "d": "기절한 포켓몬을 HP 50%로 살린다", "revive": 0.5, "price": 1500},
}
SHOP = ["pokeball", "greatball", "ultraball", "potion", "superpot", "fullrest", "fullheal", "revive"]
START_MONEY = 1000
START_BAG = {"pokeball": 5, "potion": 2}


def is_ball(item: str) -> bool:
    return "ball" in ITEMS[item]


def item_targets(run: dict, item: str) -> list[int]:
    """그 아이템을 쓸 수 있는 파티 번호"""
    it = ITEMS[item]
    out = []
    for i, m in enumerate(run["party"]):
        if it.get("revive"):
            ok = m["hp"] <= 0
        else:
            ok = m["hp"] > 0 and ((it.get("heal") and m["hp"] < max_hp(m)) or (it.get("cure") and m.get("status")))
        if ok:
            out.append(i)
    return out


def _take(run: dict, item: str):
    if run["bag"].get(item, 0) <= 0:
        raise ValueError("no item")
    run["bag"][item] -= 1
    if run["bag"][item] <= 0:
        del run["bag"][item]


def use_item(run: dict, item: str, target: int, rng: random.Random | None = None) -> str:
    """회복 아이템 사용. 배틀 중이면 턴을 쓴다(상대가 공격). 보상 고르는 중이면 바로 쓴다."""
    rng = rng or random.Random()
    if target not in item_targets(run, item):
        raise ValueError("bad target")
    _take(run, item)
    it, m = ITEMS[item], run["party"][target]
    name = D.name(m["sid"])
    log = [f"🎒 {it['n']}을(를) 썼다!"]
    if it.get("revive"):
        m["hp"] = max(1, int(max_hp(m) * it["revive"]))
        m["status"] = None
        log.append(f"{name}이(가) 기운을 되찾았다!")
    else:
        if it.get("heal"):
            before = m["hp"]
            m["hp"] = min(max_hp(m), m["hp"] + max(1, int(max_hp(m) * it["heal"])))
            log.append(f"{name}의 HP가 {m['hp'] - before} 회복됐다.")
        if it.get("cure") and m.get("status"):
            m["status"] = None
            log.append(f"{name}의 상태이상이 나았다.")
    if run["phase"] != "battle":
        run["log"] = log
        return "continue"
    _enemy_turn(run, log, rng)
    return _after_enemy_action(run, log, rng)


# ---------- 포획 ----------
def catch_chance(run: dict, item: str) -> float:
    """한 번 던졌을 때 잡힐 확률 (3세대 공식)"""
    e = run["e"]
    ball = ITEMS[item]["ball"]
    if ball >= 255:
        return 1.0
    rate = D.SPECIES[e["sid"]]["cap"] or 45
    if e.get("boss"):
        rate /= 3
    mh = max_hp(e)
    a = (3 * mh - 2 * e["hp"]) * rate * ball / (3 * mh)
    a *= {"frz": 2.0, "par": 1.5, "brn": 1.5, "psn": 1.5}.get(e.get("status"), 1.0)
    if a >= 255:
        return 1.0
    b = 1048560 / math.sqrt(math.sqrt(16711680 / max(a, 0.1)))
    return (b / 65536) ** 4


def throw_ball(run: dict, item: str, rng: random.Random | None = None) -> str:
    """볼 던지기. 결과: 'caught' | 'replace'(파티가 가득) | 'continue' | 'switch' | 'lose' | 'win'"""
    rng = rng or random.Random()
    if not is_ball(item):
        raise ValueError("not a ball")
    _take(run, item)
    e = run["e"]
    ename = D.name(e["sid"])
    log = [f"🎒 {ITEMS[item]['n']}을(를) 던졌다!"]
    p_shake = catch_chance(run, item) ** 0.25
    shakes = 0
    while shakes < 4 and rng.random() < p_shake:
        shakes += 1
    if shakes >= 4:
        log.append("흔들... 흔들... 흔들... 딸깍!")
        log.append(f"✨ 신난다! **{ename}**을(를) 잡았다!")
        mon = dict(e)
        mon.update(boss=False, stg=[0] * 5, rc=0, vit=[0] * 6, exp=0)
        mon["hp"] = max(1, min(max_hp(mon), mon["hp"]))
        run["caught"] = run.get("caught", 0) + 1
        log.extend(win(run, rng, caught=True))
        if len(run["party"]) < MAX_PARTY:
            run["party"].append(mon)
            log.append(f"{ename}이(가) 파티에 들어왔다! ({len(run['party'])}/{MAX_PARTY})")
            run["log"] = log
            return "caught"
        run["pending"] = {"mon": mon, "then": run["phase"]}
        run["phase"] = "replace"
        log.append(f"파티가 가득 찼다! 놓아줄 포켓몬을 골라 주세요.")
        run["log"] = log
        return "replace"
    log.append(["앗! 볼에서 나와 버렸다!", "아깝다! 조금만 더였는데!", "아아! 거의 잡았는데!", "으악! 잡은 줄 알았는데!"][shakes])
    _enemy_turn(run, log, rng)
    return _after_enemy_action(run, log, rng)


def resolve_replace(run: dict, release: int | None) -> list[str]:
    """파티가 가득 찼을 때: release 번호의 포켓몬을 놓아주고 새 포켓몬을 넣는다. None이면 새 포켓몬을 놓아준다."""
    pend = run.pop("pending")
    new = pend["mon"]
    if release is None:
        msgs = [f"{D.name(new['sid'])}을(를) 놓아주었다."]
    else:
        old = run["party"][release]
        run["party"][release] = new
        msgs = [f"{D.name(old['sid'])}을(를) 놓아주고 **{D.name(new['sid'])}**을(를) 파티에 넣었다."]
        if run["active"] == release and new["hp"] <= 0:
            run["active"] = alive(run)[0]
    run["phase"] = pend["then"]
    run["log"] = msgs
    return msgs


# ---------- 승리, 경험치, 진화 ----------
def exp_gain(p: dict, e: dict, mult: float) -> int:
    b, le, lp = D.SPECIES[e["sid"]]["x"], e["lv"], p["lv"]
    exp = (b * le / 5) * ((2 * le + 10) / (le + lp + 10)) ** 2.5 + 1
    if e.get("boss"):
        exp *= 1.5
    return max(1, int(exp * mult * EXP_BASE))


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
    if p["hp"] > 0:
        p["hp"] = min(max_hp(p), p["hp"] + max_hp(p) - old_max)
    msgs = [f"⬆️ {D.name(p['sid'])}은(는) **Lv.{p['lv']}**(으)로 올랐다!"]
    for l, mid in D.SPECIES[p["sid"]]["ls"]:
        if l == p["lv"]:
            if (msg := learn(p, mid)):
                msgs.append(f"{D.name(p['sid'])}은(는) " + msg)
    msgs.extend(try_evolve(p))
    return msgs


def try_evolve(p: dict) -> list[str]:
    options = [c for c, ml in D.SPECIES[p["sid"]]["evo"] if ml and ml <= p["lv"]]
    if not options:
        return []
    before = D.name(p["sid"])
    old_max = max_hp(p)
    p["sid"] = options[0]
    if p["hp"] > 0:
        p["hp"] = min(max_hp(p), p["hp"] + max_hp(p) - old_max)
    msgs = [f"✨ 축하합니다! **{before}**은(는) **{D.name(p['sid'])}**(으)로 진화했다!"]
    for l, mid in D.SPECIES[p["sid"]]["ls"]:
        if l in (1, p["lv"]) and mid not in p["moves"]:
            if (msg := learn(p, mid)):
                msgs.append(f"{D.name(p['sid'])}은(는) " + msg)
    return msgs


def wave_money(wave: int, boss: bool) -> int:
    return int((MONEY_BASE + wave * MONEY_PER_WAVE) * (2.5 if boss else 1))


def win(run: dict, rng: random.Random, caught: bool = False) -> list[str]:
    """상대를 쓰러뜨리거나 잡았을 때: 파티 전원 경험치, 돈, 보상"""
    e = run["e"]
    msgs = []
    for m in run["party"]:
        if m["hp"] <= 0:
            continue
        amount = exp_gain(m, e, run.get("exp_mult", 1.0))
        if m["lv"] < MAX_LEVEL:
            msgs.append(f"{D.name(m['sid'])}은(는) 경험치 **{amount}**을(를) 얻었다!")
        msgs.extend(gain_exp(m, amount))
        m["stg"] = [0] * 5
        m["rc"] = 0
        if WIN_HEAL and m["hp"] < max_hp(m):
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
    run["next_e"] = {"wave": run["wave"] + 1, "mon": roll_enemy(run["wave"] + 1, rng)}
    return msgs


# ---------- 보상 (웨이브마다 하나 무료) ----------
# kind: bag(가방에 넣기) / target(포켓몬 하나에 쓰기) / run(이번 게임 전체) / money
REWARDS = {
    "balls":    {"n": "몬스터볼 x5", "d": "가방에 몬스터볼 5개", "kind": "bag", "item": ("pokeball", 5), "w": 14},
    "great":    {"n": "수퍼볼 x3", "d": "가방에 수퍼볼 3개", "kind": "bag", "item": ("greatball", 3), "w": 8},
    "ultra":    {"n": "하이퍼볼 x2", "d": "가방에 하이퍼볼 2개", "kind": "bag", "item": ("ultraball", 2), "w": 3},
    "master":   {"n": "마스터볼", "d": "반드시 잡히는 볼", "kind": "bag", "item": ("masterball", 1), "w": 0.4},
    "potion":   {"n": "상처약 x3", "d": "가방에 상처약 3개", "kind": "bag", "item": ("potion", 3), "w": 14},
    "superpot": {"n": "좋은상처약 x2", "d": "가방에 좋은상처약 2개", "kind": "bag", "item": ("superpot", 2), "w": 9},
    "fullrest": {"n": "회복약", "d": "가방에 회복약 1개", "kind": "bag", "item": ("fullrest", 1), "w": 3},
    "revive":   {"n": "기력의조각 x2", "d": "가방에 기력의조각 2개", "kind": "bag", "item": ("revive", 2), "w": 5},
    "candy":    {"n": "이상한사탕", "d": "포켓몬 하나의 레벨 +1", "kind": "target", "w": 12},
    "candy3":   {"n": "이상한사탕 x3", "d": "포켓몬 하나의 레벨 +3", "kind": "target", "w": 2},
    "hpup":     {"n": "맥스업", "d": "포켓몬 하나의 최대 HP +10%", "kind": "target", "vit": 0, "w": 3},
    "protein":  {"n": "타우린", "d": "포켓몬 하나의 공격 +10%", "kind": "target", "vit": 1, "w": 3},
    "iron":     {"n": "사포닌", "d": "포켓몬 하나의 방어 +10%", "kind": "target", "vit": 2, "w": 3},
    "calcium":  {"n": "리보플라빈", "d": "포켓몬 하나의 특공 +10%", "kind": "target", "vit": 3, "w": 3},
    "zinc":     {"n": "키토산", "d": "포켓몬 하나의 특방 +10%", "kind": "target", "vit": 4, "w": 3},
    "carbos":   {"n": "알칼로이드", "d": "포켓몬 하나의 스피드 +10%", "kind": "target", "vit": 5, "w": 3},
    "expcharm": {"n": "학습장치", "d": "얻는 경험치 +25% (이번 게임)", "kind": "run", "w": 3},
    "nugget":   {"n": "금구슬", "d": "돈을 받는다", "kind": "money", "w": 6},
}
MAX_VITAMIN = 10


def nugget_value(wave: int) -> int:
    return 500 + wave * 40


def reroll_cost(run: dict) -> int:
    return int((150 + run["wave"] * 10) * (run.get("rerolls", 0) + 1))


def shop_price(run: dict, item: str) -> int:
    """웨이브가 오를수록 조금씩 비싸진다 (PokeRogue처럼)"""
    return int(ITEMS[item]["price"] * (1 + run["wave"] // BIOME_SIZE * 0.2) / 10) * 10


def roll_rewards(run: dict, rng: random.Random, n: int = 3) -> list[str]:
    weights = {k: v["w"] for k, v in REWARDS.items()}
    hurt = sum(1 for m in run["party"] if m["hp"] < max_hp(m) * 0.5)
    fainted = sum(1 for m in run["party"] if m["hp"] <= 0)
    if hurt:
        weights["potion"] *= 2
        weights["superpot"] *= 2
    if fainted:
        weights["revive"] *= 3
    if len(run["party"]) >= MAX_PARTY:
        for k in ("balls", "great", "ultra"):
            weights[k] /= 3
    if all(m["lv"] >= MAX_LEVEL for m in run["party"]):
        weights["candy"] = weights["candy3"] = 0
    picks: list[str] = []
    for _ in range(n):
        keys = [k for k in weights if weights[k] > 0 and k not in picks]
        if not keys:
            break
        picks.append(rng.choices(keys, weights=[weights[k] for k in keys])[0])
    return picks


def reward_targets(run: dict, key: str) -> list[int]:
    r = REWARDS[key]
    if r["kind"] != "target":
        return []
    if "vit" in r:
        return [i for i, m in enumerate(run["party"]) if m["vit"][r["vit"]] < MAX_VITAMIN]
    return [i for i, m in enumerate(run["party"]) if m["lv"] < MAX_LEVEL]


def apply_reward(run: dict, key: str, target: int | None = None) -> list[str]:
    r = REWARDS[key]
    msgs = [f"🎁 **{r['n']}**을(를) 골랐다!"]
    if r["kind"] == "bag":
        item, cnt = r["item"]
        run["bag"][item] = run["bag"].get(item, 0) + cnt
        msgs.append(f"가방에 {ITEMS[item]['n']}을(를) {cnt}개 넣었다. (가지고 있는 수 {run['bag'][item]})")
    elif r["kind"] == "money":
        v = nugget_value(run["wave"])
        run["money"] += v
        msgs.append(f"💰 ₽{v:,}을(를) 받았다! (소지금 ₽{run['money']:,})")
    elif r["kind"] == "run":
        run["exp_mult"] = round(run.get("exp_mult", 1.0) + 0.25, 2)
        msgs.append(f"얻는 경험치가 {int(run['exp_mult'] * 100)}%가 됐다.")
    else:
        if target not in reward_targets(run, key):
            raise ValueError("bad target")
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
                if p["lv"] < MAX_LEVEL:
                    p["exp"] = 0
                    msgs.extend(level_up(p))
    return msgs


def choose_reward(run: dict, index: int, rng: random.Random | None = None, target: int | None = None) -> list[str]:
    rng = rng or random.Random()
    key = run["rewards"][index]
    msgs = apply_reward(run, key, target)
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
    if item not in SHOP or run["money"] < price:
        raise ValueError("cannot buy")
    run["money"] -= price
    run["bag"][item] = run["bag"].get(item, 0) + 1
    run["log"] = [f"🛒 {ITEMS[item]['n']}을(를) ₽{price:,}에 샀다. (소지금 ₽{run['money']:,})"]
    return run["log"]
