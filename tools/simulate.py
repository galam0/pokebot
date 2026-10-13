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
    """mon이 enemy에게 줄 수 있는 최대 기대 데미지 비율"""
    return max(E._expected(mon, enemy, m) for m in mon["moves"]) / max(1, enemy["hp"])


def best_member(run, exclude=None):
    e = run["e"]
    cands = [i for i in E.alive(run) if i != exclude]
    return max(cands, key=lambda i: power(run["party"][i], e) * (run["party"][i]["hp"] / E.max_hp(run["party"][i])) ** 0.5)


def battle_action(run, rng):
    p, e = E.lead(run), run["e"]
    bag = run["bag"]
    # 포획: 보스가 아니고 파티에 자리가 있으면, 상대 HP가 적당히 깎였을 때
    if len(run["party"]) < E.MAX_PARTY and not e["boss"] and e["hp"] < E.max_hp(e) * 0.6:
        for ball in ("ultraball", "greatball", "pokeball"):
            if bag.get(ball) and E.catch_chance(run, ball) > 0.25:
                return E.throw_ball(run, ball, rng)
    # 회복
    if p["hp"] < E.max_hp(p) * 0.3 and not p["rc"]:
        for it in ("superpot", "potion", "fullrest"):
            if bag.get(it) and run["active"] in E.item_targets(run, it):
                return E.use_item(run, it, run["active"], rng)
    # 상성이 나쁘면 교체
    if len(E.alive(run)) > 1 and not p["rc"]:
        b = best_member(run, exclude=run["active"])
        if power(run["party"][b], e) > power(p, e) * 2 and run["party"][b]["hp"] > E.max_hp(run["party"][b]) * 0.5:
            return E.switch(run, b, rng)
    return E.take_turn(run, E.best_move_index(p, e) if not p["rc"] else 0, rng)


def reward_action(run, rng):
    # 가방으로 회복 (보상 중에는 턴을 안 씀)
    for it in ("revive", "superpot", "potion"):
        while run["bag"].get(it):
            ts = [i for i in E.item_targets(run, it)
                  if it == "revive" or run["party"][i]["hp"] < E.max_hp(run["party"][i]) * 0.6]
            if not ts:
                break
            E.use_item(run, it, ts[0], rng)
    # 상점
    if len(run["party"]) < E.MAX_PARTY and run["bag"].get("pokeball", 0) + run["bag"].get("greatball", 0) < 3:
        while run["money"] >= E.shop_price(run, "pokeball") + 500 and run["bag"].get("pokeball", 0) < 5:
            E.buy(run, "pokeball")
    if not run["bag"].get("superpot") and run["money"] >= E.shop_price(run, "superpot") + 300:
        E.buy(run, "superpot")
    if not run["bag"].get("revive") and run["money"] >= E.shop_price(run, "revive") + 300:
        E.buy(run, "revive")
    # 보상 고르기
    order = ["master", "candy3", "revive", "ultra", "great", "balls", "candy", "expcharm", "superpot",
             "protein", "calcium", "carbos", "hpup", "iron", "zinc", "fullrest", "potion", "nugget"]
    for k in order:
        if k in run["rewards"]:
            idx = run["rewards"].index(k)
            target = None
            if E.REWARDS[k]["kind"] == "target":
                ts = E.reward_targets(run, k)
                if not ts:
                    continue
                target = max(ts, key=lambda i: run["party"][i]["lv"]) if "vit" in E.REWARDS[k] else \
                    min(ts, key=lambda i: run["party"][i]["lv"])
            return E.choose_reward(run, idx, rng, target)
    return E.skip_reward(run, rng)


def play(starter, rng):
    run = E.new_run(starter, rng)
    steps = 0
    while run["phase"] in ("battle", "reward", "switch", "replace"):
        steps += 1
        if steps > 20000:
            break
        ph = run["phase"]
        if ph == "battle":
            battle_action(run, rng)
        elif ph == "switch":
            E.switch(run, best_member(run), rng)
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
