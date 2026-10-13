"""PokeAPI 원본 CSV로 봇이 쓰는 포켓몬 데이터 파일(game/pokedata.json.gz)을 만든다.

봇은 실행 중에 PokeAPI를 부르지 않는다 (디스코드는 3초 안에 응답해야 해서).
데이터를 다시 만들고 싶을 때만 실행하면 된다.

    git clone --depth 1 --filter=blob:none --sparse https://github.com/PokeAPI/pokeapi
    cd pokeapi && git sparse-checkout set data/v2/csv
    python tools/build_data.py /path/to/pokeapi/data/v2/csv
"""

import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

KO = 3  # languages.csv: 3 = 한국어
MAX_SPECIES = 1025

# 레벨업 기술을 가져올 게임 버전 (앞쪽이 우선, 최신 본가 게임부터)
VERSION_PREF = [25, 20, 18, 17, 16, 15, 14, 11, 10, 9, 8, 7, 6, 5, 3, 1, 23, 24, 30]

# 봇에서 쓰지 않는 기술 (자폭, 조건부 기술 등)
EXCLUDE_MOVES = {
    "explosion", "self-destruct", "misty-explosion", "final-gambit", "memento",
    "dream-eater", "focus-punch", "last-resort", "belch", "synchronoise",
    "natural-gift", "fling", "spit-up", "steel-roller", "burn-up", "double-shock",
    "shell-trap", "beak-blast", "poltergeist", "sucker-punch", "upper-hand",
    "fake-out", "first-impression", "snore", "struggle", "mind-blown", "chloroblast",
}
# 쓰고 나면 다음 턴을 쉬어야 하는 기술 (반동으로 쉬기 / 모으기를 '쉬기'로 단순화)
RECHARGE_MOVES = {
    "hyper-beam", "giga-impact", "blast-burn", "hydro-cannon", "frenzy-plant",
    "rock-wrecker", "roar-of-time", "eternabeam", "meteor-assault", "prismatic-laser",
    "solar-beam", "solar-blade", "sky-attack", "razor-wind", "skull-bash", "fly", "dig",
    "dive", "bounce", "phantom-force", "shadow-force", "meteor-beam", "freeze-shock",
    "ice-burn", "electro-shot", "sky-drop",
}


def rows(base: Path, name: str):
    with open(base / name, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def num(v, default=None):
    return int(v) if v not in ("", None) else default


def build(base: Path) -> dict:
    # ---------- 기술 ----------
    move_ko = {num(r["move_id"]): r["name"] for r in rows(base, "move_names.csv") if num(r["local_language_id"]) == KO}
    meta = {num(r["move_id"]): r for r in rows(base, "move_meta.csv")}
    stat_changes = defaultdict(list)
    for r in rows(base, "move_meta_stat_changes.csv"):
        stat_changes[num(r["move_id"])].append([num(r["stat_id"]), num(r["change"])])

    moves = {}
    for r in rows(base, "moves.csv"):
        mid, power, cls = num(r["id"]), num(r["power"]), num(r["damage_class_id"])
        type_id = num(r["type_id"])
        if mid > 10000 or cls not in (2, 3) or not power or power <= 1 or type_id > 18:
            continue
        if r["identifier"] in EXCLUDE_MOVES or r["identifier"].startswith("max-") or r["identifier"].startswith("g-max"):
            continue
        if mid not in move_ko:
            continue
        m = meta.get(mid, {})
        cat = num(m.get("meta_category_id"), 0)
        entry = {
            "n": move_ko[mid],
            "t": type_id,
            "p": power,
            "a": num(r["accuracy"]),          # None = 반드시 명중
            "c": 0 if cls == 2 else 1,        # 0 물리 / 1 특수
            "pr": num(r["priority"], 0),
            "pp": num(r["pp"], 10) or 10,
        }
        drain = num(m.get("drain"), 0)
        if drain:
            entry["dr"] = drain               # +흡수 / -반동 (%)
        if num(m.get("crit_rate"), 0):
            entry["cr"] = num(m.get("crit_rate"))
        if num(m.get("min_hits")):
            entry["h"] = [num(m["min_hits"]), num(m["max_hits"])]
        if r["identifier"] in RECHARGE_MOVES:
            entry["rc"] = 1
        ailment = num(m.get("meta_ailment_id"), 0)
        if cat == 4 and ailment in (1, 3, 4, 5):     # 마비, 얼음, 화상, 독
            entry["ai"] = [ailment, num(m.get("ailment_chance"), 0) or 100]
        if cat in (6, 7) and stat_changes.get(mid):
            sc = [s for s in stat_changes[mid] if 2 <= s[0] <= 6]
            if sc:
                entry["sc"] = {"self": cat == 7, "ch": num(m.get("stat_chance"), 0) or 100, "s": sc}
        moves[mid] = entry

    # ---------- 포켓몬 ----------
    species_ko = {num(r["pokemon_species_id"]): r["name"] for r in rows(base, "pokemon_species_names.csv") if num(r["local_language_id"]) == KO}
    base_exp = {num(r["id"]): num(r["base_experience"], 50) for r in rows(base, "pokemon.csv")}
    stats = defaultdict(lambda: [0] * 6)
    for r in rows(base, "pokemon_stats.csv"):
        pid = num(r["pokemon_id"])
        if pid <= MAX_SPECIES:
            stats[pid][num(r["stat_id"]) - 1] = num(r["base_stat"])
    types = defaultdict(list)
    for r in sorted(rows(base, "pokemon_types.csv"), key=lambda r: num(r["slot"])):
        pid = num(r["pokemon_id"])
        if pid <= MAX_SPECIES:
            types[pid].append(num(r["type_id"]))

    species_rows = {num(r["id"]): r for r in rows(base, "pokemon_species.csv") if num(r["id"]) <= MAX_SPECIES}

    # 진화 방법: ["lv", 레벨] / ["item", 아이템] / ["trade", None] / ["other", None] (친밀도·시간 등)
    item_ident = {num(r["id"]): r["identifier"] for r in rows(base, "items.csv")}
    best: dict[int, list] = {}
    rank = {"lv": 0, "item": 1, "trade": 2, "other": 3}
    for r in rows(base, "pokemon_evolution.csv"):
        child = num(r["evolved_species_id"])
        if child > MAX_SPECIES or child not in species_rows:
            continue
        trig = num(r["evolution_trigger_id"])
        if trig == 1 and num(r["minimum_level"]):
            how = ["lv", num(r["minimum_level"])]
        elif trig == 3 and num(r["trigger_item_id"]):
            how = ["item", item_ident[num(r["trigger_item_id"])]]
        elif trig == 2:
            how = ["trade", None]
        else:
            how = ["other", None]
        if child not in best or rank[how[0]] < rank[best[child][0]]:
            best[child] = how
    evos = defaultdict(list)
    for child, how in sorted(best.items()):
        parent = num(species_rows[child]["evolves_from_species_id"])
        if parent:
            evos[parent].append([child] + how)

    learn = defaultdict(lambda: defaultdict(list))   # pid -> version -> [(lv, move)]
    machine = defaultdict(lambda: defaultdict(set))  # pid -> version -> {기술머신으로 배울 수 있는 기술}
    for r in rows(base, "pokemon_moves.csv"):
        pid, mid = num(r["pokemon_id"]), num(r["move_id"])
        if pid > MAX_SPECIES or mid not in moves:
            continue
        method = num(r["pokemon_move_method_id"])
        if method == 1:
            learn[pid][num(r["version_group_id"])].append((max(1, num(r["level"], 1)), mid))
        elif method == 4:
            machine[pid][num(r["version_group_id"])].add(mid)

    species = {}
    for sid, r in species_rows.items():
        if sid not in species_ko or sid not in types:
            continue
        ls = []
        for vg in VERSION_PREF:
            if learn[sid].get(vg):
                ls = sorted(set(learn[sid][vg]))
                break
        tm = []
        for vg in VERSION_PREF:
            if machine[sid].get(vg):
                tm = sorted(machine[sid][vg])
                break
        species[sid] = {
            "n": species_ko[sid],
            "t": types[sid],
            "s": stats[sid],                               # HP 공격 방어 특공 특방 스피드
            "x": base_exp.get(sid) or 50,
            "g": num(r["growth_rate_id"]),
            "cap": num(r["capture_rate"]),
            "from": num(r["evolves_from_species_id"]),
            "leg": 1 if (r["is_legendary"] == "1" or r["is_mythical"] == "1") else 0,
            "evo": evos.get(sid, []),
            "ls": [list(x) for x in ls],
            "tm": tm,
        }

    # ---------- 타입 상성 ----------
    chart = {}
    for r in rows(base, "type_efficacy.csv"):
        a, d, f = num(r["damage_type_id"]), num(r["target_type_id"]), num(r["damage_factor"])
        if a <= 18 and d <= 18 and f != 100:
            chart[f"{a},{d}"] = f / 100

    # ---------- 아이템 한국어 이름 ----------
    item_ko = {item_ident[num(r["item_id"])]: r["name"] for r in rows(base, "item_names.csv")
               if num(r["local_language_id"]) == KO and num(r["item_id"]) in item_ident}

    return {"moves": moves, "species": species, "chart": chart, "items": item_ko}


if __name__ == "__main__":
    src = Path(sys.argv[1])
    out = Path(__file__).resolve().parent.parent / "game" / "pokedata.json.gz"
    data = build(src)
    out.parent.mkdir(exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"species={len(data['species'])} moves={len(data['moves'])} chart={len(data['chart'])} -> {out} ({out.stat().st_size // 1024} KB)")
