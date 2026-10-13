"""밸런스 확인용 시뮬레이션: 스타팅마다 여러 판을 자동으로 돌려 도달 웨이브를 본다.

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


def pick_reward(run):
    p = run["p"]
    ratio = p["hp"] / E.max_hp(p)
    order = (["fullrest", "superpot", "potion"] if ratio < 0.6 else []) + [
        "fullheal", "candy3", "candy", "expcharm", "protein", "calcium", "carbos", "hpup", "iron", "zinc",
        "superpot", "potion", "fullrest"]
    for k in order:
        if k in run["rewards"]:
            return run["rewards"].index(k)
    return 0


def play(starter, rng):
    run = E.new_run(starter, rng)
    turns = 0
    while run["phase"] in ("battle", "reward"):
        if run["phase"] == "battle":
            E.take_turn(run, E.best_move_index(run["p"], run["e"]), rng)
            turns += 1
            if turns > 5000:
                break
        else:
            E.choose_reward(run, pick_reward(run), rng)
    cleared = run["wave"] - (0 if run["phase"] == "clear" else 1)
    return cleared, run["p"]["lv"], run["phase"] == "clear"


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rng = random.Random(1)
    allw = []
    for s in STARTERS:
        res = [play(s, rng) for _ in range(n)]
        w = [r[0] for r in res]
        allw += w
        print(f"{D.name(s):6s} 웨이브 중앙값 {statistics.median(w):5.1f}  평균 {statistics.mean(w):5.1f}  "
              f"최고 {max(w):3d}  클리어 {sum(r[2] for r in res)}/{n}  끝 레벨 {statistics.median(r[1] for r in res):.0f}")
    q = statistics.quantiles(allw, n=10)
    print(f"전체: 중앙값 {statistics.median(allw)}, 10%={q[0]:.0f} 90%={q[-1]:.0f}, 클리어율 {sum(1 for x in allw if x >= E.FINAL_WAVE)/len(allw):.1%}")
