"""모험 모드 밸런스 확인: 자동 플레이어가 태초마을부터 챔피언까지 간다.

    python tools/sim_adventure.py [판 수]

자동 플레이어: 다음 체육관을 향해 이동 → 트레이너와 싸움 → 레벨이 모자라면 풀숲에서 수련 → 체육관 도전.
HP가 낮으면 가까운 포켓몬센터로 돌아가고, 돈이 있으면 볼과 회복약을 산다.
"""
import random
import statistics
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from game import adventure as A, data as D, engine as E, kanto as K  # noqa: E402
import simulate as S  # noqa: E402


def path_to(run, goal_fn):
    """지금 장소에서 goal_fn(장소)이 참인 가장 가까운 장소까지의 경로 (첫 이동만 필요)"""
    start = run["loc"]
    prev = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if goal_fn(cur) and cur != start:
            path = []
            while cur != start:
                path.append(cur)
                cur = prev[cur]
            return path[::-1]
        for nb in K.LOCATIONS[cur]["links"]:
            if nb not in prev and A.can_enter(run, nb)[0]:
                prev[nb] = cur
                q.append(nb)
    return None


def battle_action(run, rng):
    p, e = E.lead(run), run["e"]
    owned = {m["sid"] for m in run["party"] + run["box"]}
    want = (E.can_catch(run) and e["sid"] not in owned and
            (len(run["party"]) < E.MAX_PARTY or D.bst(e["sid"]) >= min(D.bst(m["sid"]) for m in run["party"]) + 60))
    if (run["battle"] or {}).get("kind") == "legend":
        want = True
    if want and e["hp"] < E.max_hp(e) * 0.6:
        for ball in ("master-ball",) if (run["battle"] or {}).get("kind") == "legend" and run["bag"].get("master-ball") else S.BALLS:
            if run["bag"].get(ball) and E.catch_chance(run, ball) > 0.2:
                return E.throw_ball(run, ball, rng)
    if (run["battle"] or {}).get("kind") == "wild" and not want and p["hp"] < E.max_hp(p) * 0.25:
        return A.flee(run)
    return _fight(run, rng)


def _fight(run, rng):
    p, e = E.lead(run), run["e"]
    bag = run["bag"]
    if p["hp"] < E.max_hp(p) * 0.3 and not p["rc"]:
        for it in S.HEALS:
            if bag.get(it) and run["active"] in E.item_targets(run, it):
                return E.use_item(run, it, run["active"], rng)
    if not E.usable_moves(p) and not p["rc"]:
        for it in ("max-elixir", "elixir", "max-ether", "ether"):
            if bag.get(it) and E.ITEMS[it]["one"] is False:
                return E.use_item(run, it, run["active"], rng)
    if len(E.alive(run)) > 1 and not p["rc"]:
        b = S.best_member(run, exclude=run["active"])
        if S.power(run["party"][b], e) > S.power(p, e) * 2 and run["party"][b]["hp"] > E.max_hp(run["party"][b]) * 0.5:
            return E.switch(run, b, rng)
    return E.take_turn(run, E.best_move_index(p, e) if not p["rc"] else 0, rng)


def field_items(run, rng):
    # 기술머신·진화·지닌 물건·사탕·영양제를 쓸 수 있으면 쓴다
    for it in list(run["bag"]):
        cat = E.ITEMS[it]["cat"]
        if cat not in ("tm", "evo", "held", "candy", "vit"):
            continue
        guard = 0
        while run["bag"].get(it) and guard < 10 and run["phase"] == "field":
            guard += 1
            ts = E.item_targets(run, it)
            if cat == "held":
                ts = [i for i in ts if not run["party"][i].get("held")]
            if cat == "tm":
                ts = [i for i in ts if E._move_value(run["party"][i], E.ITEMS[it]["mid"]) >
                      min(E._move_value(run["party"][i], x) for x in run["party"][i]["moves"])]
            if not ts:
                break
            target = max(ts, key=lambda i: run["party"][i]["lv"])
            E.use_item(run, it, target, rng)
            while run["phase"] == "learn":
                S.learn_action(run, rng)
            if cat == "tm":
                break


def strength(run):
    lv = sorted((m["lv"] for m in run["party"]), reverse=True)[:3]
    return sum(lv) / len(lv)


def goal(run):
    if len(run["badges"]) >= 8:
        return "plateau"
    for g in K.GYM_ORDER:
        if g not in run["badges"]:
            return next(k for k, L in K.LOCATIONS.items() if L.get("gym") == g)


def gym_ace(run):
    if len(run["badges"]) >= 8:
        return 60
    g = next(g for g in K.GYM_ORDER if g not in run["badges"])
    return max(lv for _, lv in K.GYMS[g]["team"])


def hurt(run):
    return sum(m["hp"] for m in run["party"]) < sum(E.max_hp(m) for m in run["party"]) * 0.5 or \
        sum(1 for m in run["party"] if m["hp"] <= 0) >= max(1, len(run["party"]) // 2)


def field_action(run, rng, stats):
    field_items(run, rng)
    if run["phase"] != "field":
        return
    if A.in_league(run):
        S._use_all(run, rng)
        return A.next_challenger(run, rng)
    L = A.loc(run)
    if A.has_center(run) and (hurt(run) or any(m["hp"] < E.max_hp(m) for m in run["party"])):
        return A.heal(run)
    if L.get("mart"):
        items = A.mart_items(run)
        for it, want in (("ultra-ball", 5), ("great-ball", 5), ("poke-ball", 8), ("hyper-potion", 4),
                         ("super-potion", 5), ("potion", 5), ("revive", 3), ("full-restore", 4), ("max-revive", 2)):
            while it in items and run["bag"].get(it, 0) < want and run["money"] >= A.price(it) + 1500:
                A.buy(run, it)
        if L.get("dept"):
            for it in ("tm85", "tm58", "tm53", "tm57", "tm247", "tm280"):
                if not run["bag"].get(it) and run["money"] >= A.price(it) + 3000:
                    A.buy(run, it)
    if hurt(run):
        stats["retreats"] += 1
        p = path_to(run, lambda k: K.LOCATIONS[k].get("center") or K.LOCATIONS[k].get("home"))
        if p:
            return A.move(run, p[0], rng)
    if A.gift_available(run):
        return A.take_gift(run, rng)
    if A.trainers_left(run) and not hurt(run):
        return A.fight_trainer(run, rng)
    if A.legend_available(run) and run["bag"].get("master-ball"):
        return A.meet_legend(run, rng)
    gkey, ok, _ = A.gym_state(run)
    if ok and strength(run) >= min(gym_ace(run), A.level_cap(run)) - 3:
        stats["gym_tries"] += 1
        return A.challenge_gym(run, rng)
    if A.league_ready(run) and strength(run) >= 56:
        stats["league_tries"] += 1
        return A.challenge_league(run, rng)
    # 레벨이 모자라면 수련
    need_lv = min(gym_ace(run), A.level_cap(run)) - 3 if len(run['badges']) < 8 else 56
    if strength(run) < need_lv:
        if L.get("wild"):
            stats["grind"] += 1
            return A.explore(run, rng)
        p = path_to(run, lambda k: K.LOCATIONS[k].get("wild"))
        return A.move(run, p[0], rng)
    tgt = goal(run)
    if run["loc"] != tgt:
        p = path_to(run, lambda k: k == tgt)
        if p is None:
            raise RuntimeError(f"no path to {tgt} from {run['loc']} badges={len(run['badges'])}")
        return A.move(run, p[0], rng)
    if L.get("wild"):
        return A.explore(run, rng)
    p = path_to(run, lambda k: K.LOCATIONS[k].get("wild"))
    return A.move(run, p[0], rng)


def play(starter, rng, max_steps=40000):
    run = A.new_adventure(starter, rng, "sim")
    stats = {"steps": 0, "battles": 0, "blackouts": 0, "retreats": 0, "grind": 0, "gym_tries": 0, "league_tries": 0,
             "badge_steps": []}
    badges = 0
    while stats["steps"] < max_steps and not run.get("hof"):
        stats["steps"] += 1
        ph = run["phase"]
        if ph == "battle":
            before = run["loc"]
            r = battle_action(run, rng)
            if r == "lose" and before:
                stats["blackouts"] += 1
        elif ph == "switch":
            E.switch(run, S.best_member(run), rng)
        elif ph == "learn":
            S.learn_action(run, rng)
        elif ph == "field":
            field_action(run, rng, stats)
            if run["phase"] == "battle":
                stats["battles"] += 1
        if len(run["badges"]) != badges:
            badges = len(run["badges"])
            stats["badge_steps"].append((stats["steps"], round(strength(run))))
    stats["hof"] = run.get("hof", 0)
    stats["badges"] = len(run["badges"])
    stats["party"] = [(D.name(m["sid"]), m["lv"]) for m in run["party"]]
    stats["box"] = len(run["box"])
    return stats


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    res = []
    for i in range(n):
        st = (1, 4, 7)[i % 3]
        s = play(st, random.Random(i))
        res.append(s)
        print(D.name(st), "챔피언" if s["hof"] else f"배지 {s['badges']}", "| 행동", s["steps"], "| 배틀", s["battles"],
              "| 기절", s["blackouts"], "| 체육관 도전", s["gym_tries"], "| 리그 도전", s["league_tries"],
              "| 수련", s["grind"], "| 배지별 (행동, 레벨)", s["badge_steps"])
        print("   파티", s["party"], "박스", s["box"])
    print("챔피언", sum(1 for s in res if s["hof"]), "/", n, "| 행동 중앙값", statistics.median(s["steps"] for s in res))
