"""유저끼리 포켓몬 교환 (모험 파티·PC). 화면·버튼은 bot.py, 여기서는 고르기·바꾸기만.

- 고르는 값(ref): "p:<파티 칸>:<종>" 또는 "b:<박스 칸>:<종>" (종은 그사이 바뀌었는지 확인용)
- 받는 쪽 레벨 제한보다 높으면 제한 레벨로 맞춘다 (새 지방에 들어갈 때처럼, 진화·기술은 그대로)
- 통신 진화하는 포켓몬은 받자마자 진화한다
"""

from . import adventure as A
from . import data as D
from . import engine as E

MAX_OPTIONS = 25   # 디스코드 선택 메뉴 한도


def why_not(run: dict | None) -> str | None:
    """교환할 수 없는 이유 (없으면 None)"""
    if not run:
        return "아직 모험을 시작하지 않았어요"
    if run["phase"] != "field":
        return "배틀 중이에요. 배틀을 끝내고 교환해 주세요"
    if A.in_league(run):
        return "포켓몬 리그 도전 중이에요"
    return None


def options(run: dict) -> list[tuple[str, str, str]]:
    """(값, 이름, 설명) — 파티 먼저, 나머지 칸은 박스"""
    out = []
    for i, m in enumerate(run["party"]):
        out.append((f"p:{i}:{m['sid']}", f"{D.name(m['sid'])} Lv.{m['lv']}" + (" ✨" if m.get("shiny") else ""),
                    f"파티 {i + 1}번"))
    for j, m in enumerate(run["box"][:MAX_OPTIONS - len(out)]):
        out.append((f"b:{j}:{m['sid']}", f"{D.name(m['sid'])} Lv.{m['lv']}" + (" ✨" if m.get("shiny") else ""),
                    f"PC 박스 {j + 1}번"))
    return out


def get(run: dict, ref: str) -> dict | None:
    """고른 포켓몬 (그사이 자리가 바뀌었으면 None)"""
    try:
        where, idx, sid = ref.split(":")
        lst = run["party"] if where == "p" else run["box"]
        m = lst[int(idx)]
    except (ValueError, IndexError, KeyError):
        return None
    return m if m["sid"] == int(sid) else None


def _receive(run: dict, mon: dict) -> list[str]:
    """받은 포켓몬을 이 모험에 맞춘다"""
    msgs = []
    cap = A.level_cap(run)
    if mon["lv"] > cap:
        msgs.append(f"{D.name(mon['sid'])}의 레벨이 받는 쪽 레벨 제한에 맞춰 Lv.{mon['lv']} → **Lv.{cap}**이(가) 됐다.")
        mon["lv"] = cap
    mon["exp"] = 0
    mon["cap"] = cap
    E._reset_battle_state(mon)
    for c, how, _ in D.SPECIES[mon["sid"]]["evo"]:
        if how == "trade":
            msgs.extend(E.evolve(mon, c))
            break
    E.heal_full(mon)
    return msgs


def swap(run_a: dict, ref_a: str, run_b: dict, ref_b: str) -> tuple[list[str], list[str]]:
    """두 모험의 포켓몬을 맞바꾼다. (a가 받은 쪽 메시지, b가 받은 쪽 메시지)"""
    for run in (run_a, run_b):
        if (why := why_not(run)):
            raise ValueError(why)
    ma, mb = get(run_a, ref_a), get(run_b, ref_b)
    if ma is None or mb is None:
        raise ValueError("고른 포켓몬의 자리가 바뀌었어요. 다시 골라 주세요")

    def put(run, ref, new):
        where, idx, _ = ref.split(":")
        (run["party"] if where == "p" else run["box"])[int(idx)] = new

    put(run_a, ref_a, mb)
    put(run_b, ref_b, ma)
    for run, m in ((run_a, mb), (run_b, ma)):   # 도감 (진화하면 진화한 모습은 evolve가 따로 남긴다)
        run.setdefault("caught_list", []).append(m["sid"])
        if m.get("shiny"):
            run.setdefault("shiny_list", []).append(m["sid"])
    got_a = [f"🔁 **{D.name(mb['sid'])}**을(를) 받았다!"] + _receive(run_a, mb)
    got_b = [f"🔁 **{D.name(ma['sid'])}**을(를) 받았다!"] + _receive(run_b, ma)
    for run in (run_a, run_b):
        if not any(p["hp"] > 0 for p in run["party"]):   # 혹시 모두 기절이면 회복 (교환 뒤 배틀 못 하는 일 없게)
            E.heal_party(run)
        alive = E.alive(run)
        run["active"] = alive[0] if alive else 0
        run["log"] = got_a if run is run_a else got_b
    return got_a, got_b
