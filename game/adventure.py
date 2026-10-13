"""관동 모험 모드 (도로·체육관·사천왕). 배틀 자체는 engine을 그대로 쓰고, 여기서는 '필드'와 배틀 앞뒤를 다룬다.

run (모험) = engine의 run 필드 + {
  "mode": "adventure", "phase": "field" | "battle" | "switch" | "learn",
  "loc": 지금 장소, "center": 마지막으로 들른 포켓몬센터(기절하면 여기로), "badges": [체육관 키],
  "box": [PC에 맡긴 포켓몬], "done": {장소: [이긴 트레이너 번호]}, "flags": [라이벌·전설·선물 등 한 번뿐인 일],
  "hof": 챔피언이 된 횟수, "battle": 지금 배틀 정보 (없으면 None), "name": 트레이너 이름,
}
battle = {"kind": wild|legend|trainer|rival|gymjr|gym|e4|champion, "name": 상대 이름, "queue": [남은 상대 포켓몬],
          "total": 상대 포켓몬 수, "prize": 상금, "chain": [이어서 싸울 트레이너], ...}
"""

import random

from . import data as D
from . import engine as E
from . import kanto as K

START = "pallet"
START_MONEY = 3000
START_BAG = {"poke-ball": 5, "potion": 3}
STARTERS = [1, 4, 7]
FIND_CHANCE = 0.12        # 풀숲 탐색에서 아이템을 주울 확률
NUGGET_PRICE = 5000
EXP_MULT = 2.0            # 모험 경험치 배율 (디스코드에서 너무 오래 수련하지 않게. 레벨 제한이 있어서 너무 세지지는 않음)
TRAINER_EXP = 1.5         # 트레이너 배틀 경험치 배율 (본가처럼)
TRAINER_NAMES = ["민수", "지훈", "서연", "하은", "도윤", "예린", "준호", "수아", "현우", "지아", "태민", "유나",
                 "성민", "다은", "재원", "소희", "동현", "채원", "영호", "미나"]
TRAINER_LINES = ["눈이 마주쳤으니 승부다!", "내 포켓몬이 최고라고!", "너 강해 보이는데? 한번 붙어 보자!",
                 "여기를 지나가려면 나를 이겨야 해!", "기다리고 있었다고!", "오늘은 질 생각이 없어!"]


# ---------- 기본 ----------
def loc(run: dict) -> dict:
    return K.LOCATIONS[run["loc"]]


def loc_name(key: str) -> str:
    return K.LOCATIONS[key]["n"]


def level_cap(run: dict) -> int:
    return E.MAX_LEVEL if run.get("hof") else K.LEVEL_CAPS[min(len(run["badges"]), 8)]


def sync_caps(run: dict):
    """배지 수에 맞춰 말을 듣는 레벨(레벨 제한)을 맞춘다"""
    cap = level_cap(run)
    for m in run["party"] + run["box"]:
        m["cap"] = cap
        if m["lv"] >= cap:
            m["exp"] = 0


def new_adventure(starter: int, rng: random.Random | None = None, name: str = "") -> dict:
    rng = rng or random.Random()
    if starter not in STARTERS:
        raise ValueError("not a starter")
    p = E.new_mon(starter, 5, rng)
    p["iv"] = [max(iv, 20) for iv in p["iv"]]
    p["hp"] = E.max_hp(p)
    run = {"mode": "adventure", "wave": 0, "phase": "field", "party": [p], "active": 0, "e": None, "log": [],
           "rewards": [], "money": START_MONEY, "bag": dict(START_BAG), "rerolls": 0, "turn": 0, "exp_mult": 1.0,
           "starter": starter, "best_hit": 0, "caught": 0, "caught_list": [starter], "seed": None, "rule": None,
           "mono": None, "loc": START, "center": START, "badges": [], "box": [], "done": {}, "flags": [], "hof": 0,
           "battle": None, "name": name, "chain": []}
    sync_caps(run)
    msgs = [f"오박사에게서 **{D.name(starter)}**을(를) 받았다!",
            "오박사: \"포켓몬 도감을 완성하는 게 내 꿈이란다. 부탁하마!\""]
    msgs.extend(start_rival(run, 1, rng))
    run["log"] = msgs
    return run


def normalize(run: dict) -> dict:
    for k, v in (("loc", START), ("center", START), ("badges", []), ("box", []), ("done", {}), ("flags", []),
                 ("hof", 0), ("battle", None), ("name", ""), ("chain", [])):
        run.setdefault(k, v)
    for m in run["box"]:
        m.setdefault("pend", [])
        E.fix_pp(m)
    if run["phase"] in ("battle", "switch") and not run.get("e"):
        run["phase"] = "field"
    return run


# ---------- 이동 ----------
def can_enter(run: dict, key: str) -> tuple[bool, str]:
    L = K.LOCATIONS[key]
    if L.get("champ") and not run.get("hof"):
        return False, "챔피언이 되면 갈 수 있어요"
    need = L.get("need", 0)
    if len(run["badges"]) < need:
        return False, f"배지 {need}개가 필요해요"
    return True, ""


def neighbors(run: dict) -> list[tuple[str, bool, str]]:
    return [(k, *can_enter(run, k)) for k in loc(run)["links"]]


def move(run: dict, key: str, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    if run["phase"] != "field" or key not in loc(run)["links"]:
        raise ValueError("cannot move")
    ok, why = can_enter(run, key)
    if not ok:
        raise ValueError(why)
    run["loc"] = key
    L = loc(run)
    msgs = [f"🗺️ **{L['n']}**에 도착했다."]
    if L.get("desc"):
        msgs.append(L["desc"])
    stage = L.get("rival")
    if stage and f"rival{stage}" not in run["flags"]:
        msgs.extend(start_rival(run, stage, rng))
    run["log"] = msgs
    return msgs


# ---------- 배틀 시작 ----------
def _team(spec: list[tuple[int, int]], rng: random.Random, iv: int) -> list[dict]:
    out = []
    for sid, lv in spec:
        m = E.new_mon(sid, lv, rng)
        m["iv"] = [iv] * 6
        m["hp"] = E.max_hp(m)
        out.append(m)
    return out


def _begin(run: dict, kind: str, mons: list[dict], name: str, **meta):
    run["battle"] = {"kind": kind, "name": name, "queue": mons[1:], "total": len(mons), **meta}
    run["e"] = mons[0]
    for m in run["party"]:
        E._reset_battle_state(m)
        m["sash"] = 0
    alive = E.alive(run)
    if alive and E.lead(run)["hp"] <= 0:
        run["active"] = alive[0]
    run["turn"] = 0
    run["phase"] = "battle"


def _start_trainer(run: dict, spec: dict, rng: random.Random, chain: list[dict] | None = None) -> list[str]:
    mons = _team(spec["team"], rng, spec.get("iv", 12))
    prize = K.PRIZE[spec["cls"]] * spec["team"][-1][1]
    meta = {k: v for k, v in spec.items() if k not in ("team",)}
    _begin(run, spec["kind"], mons, spec["name"], prize=prize, chain=chain or [], **{k: v for k, v in meta.items()
                                                                                     if k not in ("kind", "name")})
    msgs = [f"⚔️ **{spec['name']}**이(가) 승부를 걸어왔다!"]
    if spec.get("line"):
        msgs.append(f"\"{spec['line']}\"")
    msgs.append(f"{spec['name']}은(는) **{D.name(mons[0]['sid'])}**을(를) 내보냈다!")
    return msgs


def _trainer_name(cls: str, key: str, idx: int) -> str:
    if " " in cls:
        return cls
    return f"{cls} {random.Random(f'{key}:{idx}').choice(TRAINER_NAMES)}"


def start_rival(run: dict, stage: int, rng: random.Random) -> list[str]:
    spec = {"kind": "rival", "cls": K.RIVAL, "name": K.RIVAL, "team": K.rival_team(stage, run["starter"]),
            "line": K.RIVAL_LINE[stage], "stage": stage, "iv": 15 + stage * 2}
    if stage == 1:
        spec["no_penalty"] = True
    return _start_trainer(run, spec, rng)


def trainers_left(run: dict, key: str | None = None) -> list[int]:
    key = key or run["loc"]
    done = run["done"].get(key, [])
    return [i for i in range(len(K.LOCATIONS[key].get("trainers", []))) if i not in done]


def fight_trainer(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    left = trainers_left(run)
    if run["phase"] != "field" or not left:
        raise ValueError("no trainer")
    i = left[0]
    cls, team = loc(run)["trainers"][i]
    spec = {"kind": "trainer", "cls": cls, "name": _trainer_name(cls, run["loc"], i), "team": team,
            "idx": i, "loc": run["loc"], "line": random.Random(f"{run['loc']}:{i}:l").choice(TRAINER_LINES),
            "iv": 20 if "비주기" in cls else 10}
    run["log"] = _start_trainer(run, spec, rng)
    return run["log"]


def gym_state(run: dict) -> tuple[str | None, bool, str]:
    """(체육관 키, 도전 가능?, 이유)"""
    key = loc(run).get("gym")
    if not key:
        return None, False, ""
    if key in run["badges"]:
        return key, False, "이미 배지를 받았어요"
    need = K.GYMS[key].get("need", 0)
    if len(run["badges"]) < need:
        return key, False, f"배지 {need}개를 모으면 문이 열려요"
    return key, True, ""


def challenge_gym(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    key, ok, why = gym_state(run)
    if run["phase"] != "field" or not ok:
        raise ValueError(why or "no gym")
    g = K.GYMS[key]
    jcls, jteam = g["junior"]
    junior = {"kind": "gymjr", "cls": jcls, "name": f"체육관 트레이너 {_trainer_name(jcls, key, 0).split(' ', 1)[1]}",
              "team": jteam, "iv": 15, "line": f"{g['leader']} 관장님께 도전하려면 나부터 이겨야 해!"}
    leader = {"kind": "gym", "cls": "관장", "name": f"관장 {g['leader']}", "team": g["team"], "gym": key,
              "line": g["line"], "iv": 24 + len(run["badges"])}
    msgs = [f"🏟️ **{g['n']}**에 도전했다!"]
    msgs.extend(_start_trainer(run, junior, rng, chain=[leader]))
    run["log"] = msgs
    return msgs


def league_ready(run: dict) -> bool:
    return bool(loc(run).get("league")) and len(run["badges"]) >= 8


def challenge_league(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    if run["phase"] != "field" or not league_ready(run):
        raise ValueError("league closed")
    specs = [{"kind": "e4", "cls": "사천왕", "name": e["n"], "team": e["team"], "line": e["line"], "iv": 31}
             for e in K.ELITE_FOUR]
    specs.append({"kind": "champion", "cls": "챔피언", "name": f"챔피언 {K.RIVAL.split()[-1]}",
                  "team": K.rival_team(7, run["starter"]), "line": K.RIVAL_LINE[7], "iv": 31})
    msgs = ["🏆 **포켓몬 리그**에 도전한다! 사천왕 4명과 챔피언을 연달아 이겨야 해요. (중간에 회복 없음)"]
    msgs.extend(_start_trainer(run, specs[0], rng, chain=specs[1:]))
    run["log"] = msgs
    return msgs


def in_league(run: dict) -> bool:
    """사천왕 방 사이 (다음 상대에게 가거나 가방만 쓸 수 있다)"""
    return bool(run.get("chain"))


def next_challenger(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    if run["phase"] != "field" or not run.get("chain"):
        raise ValueError("no chain")
    spec, rest = run["chain"][0], run["chain"][1:]
    run["chain"] = []
    run["log"] = _start_trainer(run, spec, rng, chain=rest)
    return run["log"]


def legend_available(run: dict) -> tuple[int, int] | None:
    lg = loc(run).get("legend")
    if lg and f"legend:{run['loc']}" not in run["flags"]:
        return lg
    return None


def meet_legend(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    lg = legend_available(run)
    if run["phase"] != "field" or not lg:
        raise ValueError("no legend")
    sid, lv = lg
    mons = _team([(sid, lv)], rng, 31)
    _begin(run, "legend", mons, D.name(sid))
    run["log"] = [f"✨ **{D.name(sid)}** Lv.{lv}이(가) 모습을 드러냈다!" if sid != 143 else
                  f"길을 막고 자던 **{D.name(sid)}** Lv.{lv}이(가) 눈을 떴다!"]
    return run["log"]


def gift_available(run: dict) -> tuple | None:
    g = loc(run).get("gift")
    if not g or f"gift:{run['loc']}" in run["flags"]:
        return None
    if loc(run).get("gift_clear") and trainers_left(run):
        return None
    return g


def take_gift(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    g = gift_available(run)
    if run["phase"] != "field" or not g:
        raise ValueError("no gift")
    sid, lv, text = g
    mon = E.new_mon(sid, lv, rng)
    mon["iv"] = [max(iv, 20) for iv in mon["iv"]]
    mon["hp"] = E.max_hp(mon)
    run["flags"].append(f"gift:{run['loc']}")
    run.setdefault("caught_list", []).append(sid)
    msgs = [f"🎁 {text}"] + add_caught(run, mon)
    run["log"] = msgs
    return msgs


# ---------- 탐색 ----------
def explore(run: dict, rng: random.Random | None = None) -> list[str]:
    rng = rng or random.Random()
    wild = loc(run).get("wild")
    if run["phase"] != "field" or not wild:
        raise ValueError("no grass")
    if rng.random() < FIND_CHANCE:
        badges = len(run["badges"])
        pool = [f for f in K.FIND if f[3] <= badges]
        item, cnt, *_ = rng.choices(pool, weights=[f[2] for f in pool])[0]
        if item == "type-boost":
            item = rng.choice(list(E.TYPE_BOOST))
        msgs = ["풀숲을 뒤지다가 뭔가를 발견했다!"] + give_item(run, item, cnt)
        run["log"] = msgs
        return msgs
    sid, lo, hi, _ = rng.choices(wild, weights=[w[3] for w in wild])[0]
    lv = rng.randint(lo, hi)
    mon = E.new_mon(sid, lv, rng)
    _begin(run, "wild", [mon], f"야생 {D.name(sid)}")
    run["log"] = [f"앗! 야생의 **{D.name(sid)}** Lv.{lv}이(가) 튀어나왔다!"]
    return run["log"]


def give_item(run: dict, item: str, cnt: int = 1) -> list[str]:
    if item == "nugget":
        v = NUGGET_PRICE * cnt
        run["money"] += v
        return [f"💰 금구슬을 얻어서 팔았다! ₽{v:,} (소지금 ₽{run['money']:,})"]
    E.add_item(run, item, cnt)
    return [f"🎒 **{E.item_name(item)}**" + (f" {cnt}개" if cnt > 1 else "") + "을(를) 가방에 넣었다."]


def flee(run: dict) -> list[str]:
    b = run.get("battle") or {}
    if run["phase"] != "battle" or b.get("kind") not in ("wild", "legend"):
        raise ValueError("cannot flee")
    msgs = ["무사히 도망쳤다!"]
    if b["kind"] == "legend":
        msgs.append(f"{D.name(run['e']['sid'])}은(는) 아직 그곳에 있는 것 같다...")
    _end_battle(run)
    run["log"] = msgs
    return msgs


# ---------- 배틀 끝 ----------
def _end_battle(run: dict):
    run["battle"] = None
    run["e"] = None
    run["phase"] = "field"
    run["turn"] = 0
    for m in run["party"]:
        E._reset_battle_state(m)
        m["sash"] = 0
    alive = E.alive(run)
    if alive and E.lead(run)["hp"] <= 0:
        run["active"] = alive[0]


def after_ko(run: dict, rng: random.Random, caught: bool = False) -> list[str]:
    """상대 포켓몬이 쓰러지거나 잡혔을 때 (engine.win 대신): 경험치 → 다음 포켓몬 / 배틀 끝"""
    b = run.get("battle") or {"kind": "wild", "queue": []}
    e = run["e"]
    mult = EXP_MULT * run.get("exp_mult", 1.0) * (1.0 if b["kind"] in ("wild", "legend") else TRAINER_EXP)
    msgs = []
    for m in run["party"]:
        if m["hp"] <= 0:
            continue
        amount = E.exp_gain(m, e, mult)
        if m["lv"] < E.level_cap(m):
            msgs.append(f"{D.name(m['sid'])}은(는) 경험치 **{amount}**을(를) 얻었다!")
        msgs.extend(E.gain_exp(m, amount))
    if b.get("queue"):
        nxt = b["queue"].pop(0)
        run["e"] = nxt
        run["turn"] = 0
        left = len(b["queue"]) + 1
        msgs.append(f"{b['name']}은(는) **{D.name(nxt['sid'])}**을(를) 내보냈다! (남은 포켓몬 {left})")
        if E.lead(run)["hp"] <= 0:
            run["phase"] = "switch"
            msgs.append("다음 포켓몬을 골라 주세요!")
        else:
            run["phase"] = "battle"
        E._maybe_learn(run, run["phase"])
        return msgs
    msgs.extend(_victory(run, rng, caught))
    return msgs


def _victory(run: dict, rng: random.Random, caught: bool) -> list[str]:
    b = run["battle"] or {"kind": "wild"}
    kind = b["kind"]
    msgs = []
    if kind == "legend":
        if caught:
            run["flags"].append(f"legend:{run['loc']}")
        else:
            msgs.append(f"{D.name(run['e']['sid'])}은(는) 어딘가로 날아가 버렸다... 다시 오면 만날 수 있을 것 같다.")
    elif kind != "wild":
        prize = b.get("prize", 0)
        run["money"] += prize
        msgs.append(f"🏅 **{b['name']}**에게 이겼다! 💰 ₽{prize:,}을(를) 받았다. (소지금 ₽{run['money']:,})")
        if kind == "trainer":
            done = run["done"].setdefault(b["loc"], [])
            if b["idx"] not in done:
                done.append(b["idx"])
            L = K.LOCATIONS[b["loc"]]
            flag = f"clear:{b['loc']}"
            if L.get("clear_gift") and not trainers_left(run, b["loc"]) and flag not in run["flags"]:
                run["flags"].append(flag)
                msgs.append(f"{L['n']}의 트레이너를 모두 이겼다! 선물을 받았다.")
                msgs.extend(give_item(run, *L["clear_gift"]))
        elif kind == "rival":
            run["flags"].append(f"rival{b['stage']}")
            msgs.append("그린: \"쳇... 다음엔 안 질 거다! 기억해 둬!\"")
        elif kind == "gym":
            g = K.GYMS[b["gym"]]
            run["badges"].append(b["gym"])
            sync_caps(run)
            msgs.append(f"🎖️ **{g['badge']}**를 받았다! (배지 {len(run['badges'])}개)")
            msgs.append(f"이제 Lv.{level_cap(run)}까지 말을 들어요.")
            tm = f"tm{g['tm']}"
            E.add_item(run, tm)
            msgs.append(f"{g['leader']}: \"이 기술머신도 가져가!\" → 🎒 **{E.item_name(tm)}**")
        elif kind == "champion":
            run["hof"] = run.get("hof", 0) + 1
            sync_caps(run)
            E.heal_party(run)
            msgs.append(f"🏆 **축하합니다! 포켓몬 리그 챔피언이 되었다!** (전당 등록 {run['hof']}번째)")
            if run["hof"] == 1:
                msgs.append("이제 레벨 제한이 풀렸다! 블루시티 근처의 **이름없는동굴**에 갈 수 있다.")
        if b.get("chain") and kind == "e4":   # 사천왕: 다음 방으로 가기 전에 가방으로 회복할 수 있다
            _end_battle(run)
            run["chain"] = b["chain"]
            nxt = run["chain"][0]["name"]
            msgs.append(f"다음 방에서 **{nxt}**이(가) 기다리고 있다. 가방으로 회복하고 들어가자! (밖으로 나갈 수는 없어요)")
            E._maybe_learn(run, "field")
            return msgs
        if b.get("chain"):
            spec, rest = b["chain"][0], b["chain"][1:]
            _end_battle(run)
            msgs.append("")
            msgs.extend(_start_trainer(run, spec, rng, chain=rest))
            E._maybe_learn(run, "battle")
            return [x for x in msgs if x]
    _end_battle(run)
    E._maybe_learn(run, "field")
    return msgs


def blackout(run: dict, log: list) -> str:
    """파티가 모두 쓰러짐: 돈을 잃고 마지막 포켓몬센터로"""
    b = run.get("battle") or {}
    _end_battle(run)
    run["chain"] = []
    if b.get("no_penalty"):
        E.heal_party(run)
        if b.get("kind") == "rival":
            run["flags"].append(f"rival{b['stage']}")
        log.append("그린: \"내가 이겼다! 역시 내가 고른 포켓몬이 더 강하다고!\"")
        log.append("오박사가 포켓몬을 회복시켜 줬다.")
        run["log"] = log
        return "lose"
    top = max(m["lv"] for m in run["party"])
    lost = min(run["money"], top * K.BLACKOUT_BASE[min(len(run["badges"]), 8)])
    run["money"] -= lost
    run["loc"] = run.get("center") or START
    E.heal_party(run)
    run["active"] = 0
    log.append("눈앞이 캄캄해졌다...")
    if lost:
        log.append(f"당황해서 ₽{lost:,}을(를) 잃어버렸다...")
    log.append(f"정신을 차려 보니 **{loc(run)['n']}**" + ("의 집이었다." if loc(run).get("home") else "의 포켓몬센터였다."))
    run["log"] = log
    return "lose"


# ---------- 포획·PC ----------
def add_caught(run: dict, mon: dict) -> list[str]:
    mon["cap"] = level_cap(run)
    name = D.name(mon["sid"])
    if len(run["party"]) < E.MAX_PARTY:
        run["party"].append(mon)
        return [f"{name}이(가) 파티에 들어왔다! ({len(run['party'])}/{E.MAX_PARTY})"]
    E.heal_full(mon)
    run["box"].append(mon)
    return [f"파티가 가득 차서 {name}은(는) PC 박스로 보냈다. (박스 {len(run['box'])}마리)"]


def has_center(run: dict) -> bool:
    L = loc(run)
    return bool(L.get("center") or L.get("home"))


def heal(run: dict) -> list[str]:
    if run["phase"] != "field" or not has_center(run):
        raise ValueError("no center")
    E.heal_party(run)
    run["center"] = run["loc"]
    if loc(run).get("home"):
        msgs = ["집에서 푹 쉬었다. 파티가 모두 회복됐다!"]
    else:
        msgs = ["간호순: \"맡겨 주신 포켓몬은 모두 건강해졌어요!\"", "파티가 모두 회복됐다!"]
    run["log"] = msgs
    return msgs


def deposit(run: dict, i: int) -> list[str]:
    if run["phase"] != "field" or not has_center(run) or not 0 <= i < len(run["party"]) or len(run["party"]) <= 1:
        raise ValueError("cannot deposit")
    if not any(m["hp"] > 0 for j, m in enumerate(run["party"]) if j != i):
        raise ValueError("need a healthy pokemon")
    m = run["party"].pop(i)
    if m.get("held"):
        E.add_item(run, m["held"])
        m["held"] = None
    E.heal_full(m)
    run["box"].append(m)
    run["active"] = E.alive(run)[0] if E.alive(run) else 0
    run["log"] = [f"💻 {D.name(m['sid'])}을(를) PC 박스에 맡겼다."]
    return run["log"]


def withdraw(run: dict, j: int) -> list[str]:
    if run["phase"] != "field" or not has_center(run) or not 0 <= j < len(run["box"]) or len(run["party"]) >= E.MAX_PARTY:
        raise ValueError("cannot withdraw")
    m = run["box"].pop(j)
    run["party"].append(m)
    run["log"] = [f"💻 {D.name(m['sid'])}을(를) PC에서 데려왔다. ({len(run['party'])}/{E.MAX_PARTY})"]
    return run["log"]


def set_lead(run: dict, i: int) -> list[str]:
    if run["phase"] != "field" or not 0 <= i < len(run["party"]):
        raise ValueError("bad lead")
    run["party"][0], run["party"][i] = run["party"][i], run["party"][0]
    run["active"] = 0
    run["log"] = [f"{D.name(run['party'][0]['sid'])}을(를) 맨 앞에 세웠다."]
    return run["log"]


# ---------- 상점 ----------
def mart_items(run: dict) -> list[str]:
    L = loc(run)
    if not L.get("mart"):
        return []
    badges = len(run["badges"])
    items = [it for it, need in K.MART if badges >= need]
    if L.get("dept"):
        items += [it for it in K.DEPT if it not in items]
    return items


def price(item: str) -> int:
    return E.ITEMS[item]["price"]


def buy(run: dict, item: str, count: int = 1) -> list[str]:
    if run["phase"] != "field" or item not in mart_items(run) or count < 1:
        raise ValueError("not sold here")
    if E.ITEMS[item]["cat"] == "tm" and run["bag"].get(item):
        raise ValueError("already have tm")
    cost = price(item) * count
    if run["money"] < cost:
        raise ValueError("no money")
    run["money"] -= cost
    E.add_item(run, item, count)
    msgs = [f"🛒 {E.item_name(item)}" + (f" {count}개" if count > 1 else "") + f"을(를) ₽{cost:,}에 샀다. (소지금 ₽{run['money']:,})"]
    if item == "poke-ball" and count >= 10:
        E.add_item(run, "premier-ball" if "premier-ball" in E.ITEMS else "poke-ball", 1)
        msgs.append("점원: \"덤으로 하나 더 드릴게요!\"")
    run["log"] = msgs
    return msgs


# ---------- 기록 ----------
def summary_line(run: dict) -> str:
    return (f"배지 {len(run['badges'])}개" + (f" · 🏆 챔피언 {run['hof']}회" if run.get("hof") else "")
            + f" · {loc(run)['n']}")
