"""밸런스 확인용 시뮬레이션: 스타팅마다 여러 판을 자동으로 돌려 도달 웨이브를 본다.

자동 플레이어는 포획, 교체, 가방 아이템, 상점 구매까지 한다.

    python tools/simulate.py [판 수]
"""
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from game import data as D, engine as E  # noqa: E402

STARTERS = [1, 4, 7, 152, 155, 158, 252, 255, 258, 387, 390, 393, 495, 498, 501,
            650, 653, 656, 722, 725, 728, 810, 813, 816, 906, 909, 912]


def power(mon, enemy):
    """mon이 enemy에게 줄 수 있는 최대 기대 데미지 비율 (PP 남은 기술만)"""
    idx = E.usable_moves(mon) or [-1]
    return max(E._expected(mon, enemy, mon["moves"][i] if i >= 0 else -1) for i in idx) / max(1, enemy["hp"])


def best_member(run, exclude=None):
    e = run["e"]
    cands = [i for i in E.alive(run) if i != exclude]
    return max(cands, key=lambda i: power(run["party"][i], e) * (run["party"][i]["hp"] / E.max_hp(run["party"][i])) ** 0.5)


BALLS = ("ultra-ball", "great-ball", "net-ball", "timer-ball", "quick-ball", "poke-ball", "heal-ball")
HEALS = ("hyper-potion", "super-potion", "moomoo-milk", "lemonade", "soda-pop", "fresh-water", "potion", "max-potion",
         "full-restore")


def battle_action(run, rng):
    p, e = E.lead(run), run["e"]
    bag = run["bag"]
    # 포획: 보스가 아니고 파티에 자리가 있으면, 상대 HP가 적당히 깎였을 때
    if len(run["party"]) < E.MAX_PARTY and not e["boss"] and e["hp"] < E.max_hp(e) * 0.6 and E.allowed(run, e["sid"]):
        for ball in BALLS:
            if bag.get(ball) and E.catch_chance(run, ball) > 0.25:
                return E.throw_ball(run, ball, rng)
    # 회복
    if p["hp"] < E.max_hp(p) * 0.3 and not p["rc"]:
        for it in HEALS:
            if bag.get(it) and run["active"] in E.item_targets(run, it):
                return E.use_item(run, it, run["active"], rng)
    # PP가 바닥나면 PP 회복
    if not E.usable_moves(p) and not p["rc"]:
        for it in ("max-elixir", "elixir"):
            if bag.get(it):
                return E.use_item(run, it, run["active"], rng)
    # 상성이 나쁘면 교체
    if len(E.alive(run)) > 1 and not p["rc"]:
        b = best_member(run, exclude=run["active"])
        if power(run["party"][b], e) > power(p, e) * 2 and run["party"][b]["hp"] > E.max_hp(run["party"][b]) * 0.5:
            return E.switch(run, b, rng)
    return E.take_turn(run, E.best_move_index(p, e) if not p["rc"] else 0, rng)


def _use_all(run, rng):
    """보상 단계: 가방으로 회복 (턴을 안 씀)"""
    for it in ("max-revive", "revive", "sacred-ash") + HEALS + ("full-heal", "max-elixir", "elixir"):
        guard = 0
        while run["bag"].get(it) and guard < 6:
            guard += 1
            ts = E.item_targets(run, it)
            if E.ITEMS[it]["cat"] == "heal":
                ts = [i for i in ts if run["party"][i]["hp"] < E.max_hp(run["party"][i]) * 0.6]
            if E.ITEMS[it]["cat"] == "pp":
                ts = [i for i in ts if any(m <= 3 for m in run["party"][i]["pp"])]
            if not ts:
                break
            E.use_item(run, it, ts[0], rng)
    # 지닌 물건: 가방에 있으면 아무것도 안 든 포켓몬에게
    for it in [k for k in list(run["bag"]) if E.ITEMS[k]["cat"] in ("held", "evo")]:
        ts = [i for i in E.item_targets(run, it) if E.ITEMS[it]["cat"] == "evo" or not run["party"][i].get("held")]
        if ts and run["bag"].get(it):
            E.use_item(run, it, ts[0], rng)


def reward_action(run, rng):
    _use_all(run, rng)
    if run["phase"] != "reward":
        return
    # 상점
    if not E.shop_open(run):
        pass
    elif len(run["party"]) < E.MAX_PARTY and run["bag"].get("poke-ball", 0) + run["bag"].get("great-ball", 0) < 3:
        while run["money"] >= E.shop_price(run, "poke-ball") + 500 and run["bag"].get("poke-ball", 0) < 5:
            E.buy(run, "poke-ball")
    if E.shop_open(run) and not run["bag"].get("super-potion") and run["money"] >= E.shop_price(run, "super-potion") + 300:
        E.buy(run, "super-potion")
    if E.shop_open(run) and not run["bag"].get("revive") and run["money"] >= E.shop_price(run, "revive") + 300:
        E.buy(run, "revive")
    # 보상 고르기 (점수가 높은 것)
    def score(k):
        kind = k.partition(":")[0]
        base = {"tm": 7, "evo": 9, "held": 6}.get(kind)
        if base is None:
            base = {"master": 10, "candy3": 9, "maxrevive": 8, "revive": 7, "ultra": 6, "great": 5, "balls": 5,
                    "candy": 6, "expcharm": 6, "sacred": 7}.get(k, 3)
        return base
    for k in sorted(run["rewards"], key=score, reverse=True):
        idx = run["rewards"].index(k)
        target = None
        if E.needs_target(k):
            ts = E.reward_targets(run, k)
            if not ts:
                continue
            target = max(ts, key=lambda i: run["party"][i]["lv"]) if k.startswith(("held", "tm")) or "vit" in E.REWARDS.get(k, {}) \
                else min(ts, key=lambda i: run["party"][i]["lv"])
        return E.choose_reward(run, idx, rng, target)
    return E.skip_reward(run, rng)


def learn_action(run, rng):
    m = run["party"][E.learner(run)]
    new = m["pend"][0]
    vals = [E._move_value(m, x) for x in m["moves"]]
    worst = vals.index(min(vals))
    E.resolve_learn(run, worst if E._move_value(m, new) > vals[worst] else None, rng)


def play(starter, rng, mode="normal", seed=None):
    run = E.new_run(starter, rng, mode, seed)
    steps = 0
    while run["phase"] in ("battle", "reward", "switch", "replace", "learn", "path"):
        steps += 1
        if steps > 20000:
            break
        ph = run["phase"]
        if ph == "battle":
            battle_action(run, rng)
        elif ph == "switch":
            E.switch(run, best_member(run), rng)
        elif ph == "learn":
            learn_action(run, rng)
        elif ph == "path":
            hurt = sum(1 for m in run["party"] if m["hp"] < E.max_hp(m) * 0.5)
            pref = (["rest"] if hurt >= 2 else []) + ["train", "mystery", "market", "elite", "rest"]
            E.resolve_path(run, next(k for k in pref if k in run["paths"]), rng)
        elif ph == "replace":
            new = run["pending"]["mon"]
            weakest = min(range(len(run["party"])), key=lambda i: D.bst(run["party"][i]["sid"]) + run["party"][i]["lv"] * 3)
            w = run["party"][weakest]
            E.resolve_replace(run, weakest if D.bst(new["sid"]) + new["lv"] * 3 > D.bst(w["sid"]) + w["lv"] * 3 else None)
        else:
            reward_action(run, rng)
    cleared = run["wave"] - (0 if run["phase"] == "clear" else 1)
    return cleared, max(m["lv"] for m in run["party"]), run["phase"] == "clear", len(run["party"]), run.get("caught", 0)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rng = random.Random(1)
    allw, caught, size = [], [], []
    for s in STARTERS:
        res = [play(s, rng) for _ in range(n)]
        w = [r[0] for r in res]
        allw += w
        caught += [r[4] for r in res]
        size += [r[3] for r in res]
        print(f"{D.name(s):6s} 웨이브 중앙값 {statistics.median(w):5.1f}  평균 {statistics.mean(w):5.1f}  "
              f"최고 {max(w):3d}  클리어 {sum(r[2] for r in res)}/{n}  끝 레벨 {statistics.median(r[1] for r in res):.0f}")
    q = statistics.quantiles(allw, n=10)
    print(f"전체: 중앙값 {statistics.median(allw)}, 10%={q[0]:.0f} 90%={q[-1]:.0f}, "
          f"클리어율 {sum(1 for x in allw if x >= E.FINAL_WAVE)/len(allw):.1%}, "
          f"잡은 수 평균 {statistics.mean(caught):.1f}, 끝 파티 평균 {statistics.mean(size):.1f}")
