"""유저끼리 대전 (모험 파티끼리, 모두 Lv.50으로 맞춤). 화면·버튼은 bot.py, 여기서는 규칙만.

battle = {
  "sides": [side, side], "turn": 턴 수, "log": [이번 턴 메시지], "winner": None | 0 | 1 | -1(무승부),
  "ver": 화면 번호 (지난 버튼 막기), "wait": 한쪽만 고른 시각 (시간 초과 판정),
}
side = {"uid", "name", "party": [Lv.50 사본], "active": 앞 칸, "choice": None | ("move", i) | ("switch", i) | ("forfeit",),
        "must_switch": 기절해서 다음 포켓몬을 골라야 함}
배틀 계산은 engine._act 를 그대로 쓴다 (상태이상·급소·지닌 물건 모두 같음). 아이템(가방)은 못 쓴다.
"""

import copy
import random
import time

from . import data as D
from . import engine as E

LEVEL = 50
TIMEOUT = 180   # 한쪽만 고르고 이만큼(초) 지나면, 고른 쪽이 시간 초과 승리를 받을 수 있다


def _prep(party: list[dict]) -> list[dict]:
    out = []
    for m in party[:E.MAX_PARTY]:
        c = copy.deepcopy(m)
        for k in ("evolved", "pend"):
            c.pop(k, None)
        c["lv"], c["exp"], c["cap"] = LEVEL, 0, LEVEL
        c["status"] = None
        c["sash"] = 0
        E._reset_battle_state(c)
        E.heal_full(c)
        out.append(c)
    return out


def new_battle(a: tuple[int, str, list[dict]], b: tuple[int, str, list[dict]]) -> dict:
    sides = []
    for uid, name, party in (a, b):
        p = _prep(party)
        sides.append({"uid": uid, "name": name, "party": p, "active": 0, "choice": None, "must_switch": False})
    log = [f"⚔️ **{sides[0]['name']}** vs **{sides[1]['name']}** 대전 시작! (모두 Lv.{LEVEL})"]
    for s in sides:
        log.append(f"{s['name']}은(는) **{D.name(lead(s)['sid'])}**을(를) 내보냈다!")
    return {"sides": sides, "turn": 0, "log": log, "winner": None, "ver": 1, "wait": None}


def lead(side: dict) -> dict:
    return side["party"][side["active"]]


def alive(side: dict) -> list[int]:
    return [i for i, m in enumerate(side["party"]) if m["hp"] > 0]


def side_of(b: dict, uid: int) -> int | None:
    for i, s in enumerate(b["sides"]):
        if s["uid"] == uid:
            return i
    return None


def needs(b: dict) -> list[int]:
    """지금 골라야 하는 쪽 (기절 교체가 있으면 그쪽만)"""
    if b["winner"] is not None:
        return []
    forced = [i for i, s in enumerate(b["sides"]) if s["must_switch"]]
    return forced or [0, 1]


def pending(b: dict) -> list[int]:
    """아직 안 고른 쪽"""
    return [i for i in needs(b) if b["sides"][i]["choice"] is None]


def _mname(side: dict, m: dict | None = None) -> str:
    return f"{side['name']}의 {D.name((m or lead(side))['sid'])}"


def choose(b: dict, i: int, choice: tuple, rng: random.Random | None = None) -> bool:
    """i쪽이 고른다. 둘 다 골랐으면 턴을 진행하고 True"""
    rng = rng or random.Random()
    if b["winner"] is not None or i not in needs(b):
        raise ValueError("not your turn")
    s = b["sides"][i]
    if s["choice"] is not None:
        raise ValueError("already chosen")
    kind = choice[0]
    if kind == "move":
        if s["must_switch"]:
            raise ValueError("must switch")
        p = lead(s)
        usable = E.usable_moves(p)
        if not p["rc"]:
            if choice[1] == -1 and usable:
                raise ValueError("struggle only when no PP")
            if choice[1] != -1 and choice[1] not in usable:
                raise ValueError("move not usable")
    elif kind == "switch":
        j = choice[1]
        if not 0 <= j < len(s["party"]) or s["party"][j]["hp"] <= 0 or j == s["active"]:
            raise ValueError("bad switch")
    elif kind != "forfeit":
        raise ValueError("bad choice")
    s["choice"] = tuple(choice)
    if pending(b):
        b["wait"] = time.time()
        return False
    _resolve(b, rng)
    return True


def claim_timeout(b: dict, i: int) -> bool:
    """고르고 기다리던 i쪽이 시간 초과 승리를 받는다"""
    other = 1 - i
    if (b["winner"] is None and b["sides"][i]["choice"] is not None and other in pending(b)
            and b.get("wait") and time.time() - b["wait"] >= TIMEOUT):
        b["winner"] = i
        b["log"] = [f"⏰ {b['sides'][other]['name']}이(가) 시간 안에 고르지 않아서 **{b['sides'][i]['name']}**의 승리!"]
        b["ver"] += 1
        return True
    return False


def _resolve(b: dict, rng: random.Random):
    log: list[str] = []
    sides = b["sides"]
    b["ver"] += 1
    b["wait"] = None
    # 항복
    quit_ = [i for i, s in enumerate(sides) if s["choice"] and s["choice"][0] == "forfeit"]
    if quit_:
        for i in quit_:
            log.append(f"🏳️ {sides[i]['name']}은(는) 항복했다!")
        b["winner"] = -1 if len(quit_) == 2 else 1 - quit_[0]
        _finish(b, log)
        return
    forced = any(s["must_switch"] for s in sides)
    # 교체 먼저
    for s in sides:
        c = s["choice"]
        if c and c[0] == "switch":
            old = lead(s)
            E._reset_battle_state(old)
            s["active"] = c[1]
            s["must_switch"] = False
            log.append(f"{s['name']}은(는) **{D.name(lead(s)['sid'])}**을(를) 내보냈다!" if forced and old["hp"] <= 0
                       else f"{s['name']}은(는) {D.name(old['sid'])}을(를) 불러들이고 **{D.name(lead(s)['sid'])}**을(를) 내보냈다!")
    if forced:   # 기절 교체만 한 턴
        for s in sides:
            s["choice"] = None
        b["log"] = log
        return
    # 기술 (빠른 순서)
    acts = []
    for i, s in enumerate(sides):
        c = s["choice"]
        if c[0] != "move":
            continue
        p = lead(s)
        if p["rc"]:
            mid = p["moves"][0]
        elif c[1] == -1:
            mid = -1
        else:
            mid = p["moves"][c[1]]
            p["pp"][c[1]] -= 1
            if p.get("held") in E.CHOICE:
                p["lock"] = c[1]
        acts.append((i, mid, (E.move(mid)["pr"] if not p["rc"] else 0, E.stat(p, 5), rng.random())))
    acts.sort(key=lambda a: a[2], reverse=True)
    for i, mid, _ in acts:
        me, foe = sides[i], sides[1 - i]
        user, target = lead(me), lead(foe)
        if user["hp"] <= 0 or target["hp"] <= 0:
            continue
        E._act(user, target, mid, _mname(me), _mname(foe), rng, log, {}, False)
    for s in sides:
        E._end_of_turn(lead(s), _mname(s), log)
    b["turn"] += 1
    # 기절
    lost = []
    for i, s in enumerate(sides):
        s["choice"] = None
        if lead(s)["hp"] <= 0:
            log.append(f"{_mname(s)}은(는) 쓰러졌다!")
            E._reset_battle_state(lead(s))
            if alive(s):
                s["must_switch"] = True
                log.append(f"{s['name']}은(는) 다음 포켓몬을 골라 주세요!")
            else:
                lost.append(i)
    if lost:
        b["winner"] = -1 if len(lost) == 2 else 1 - lost[0]
    _finish(b, log)


def _finish(b: dict, log: list[str]):
    for s in b["sides"]:
        s["choice"] = None
    if b["winner"] is not None:
        if b["winner"] == -1:
            log.append("🤝 둘 다 쓰러졌다! **무승부!**")
        else:
            log.append(f"🏆 **{b['sides'][b['winner']]['name']}**의 승리!")
    b["log"] = log


def view_run(b: dict, i: int = 0) -> dict:
    """그림용 가짜 run (i쪽이 앞(뒷모습), 상대가 위)"""
    me, foe = b["sides"][i], b["sides"][1 - i]
    return {"mode": "pvp", "wave": 0, "phase": "battle", "party": me["party"], "active": me["active"],
            "e": lead(foe), "log": b["log"], "foe_party": foe["party"], "money": 0}
