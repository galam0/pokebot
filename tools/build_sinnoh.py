"""신오 지방 데이터·장면 만들기 (pret/pokeplatinum).

    python tools/build_sinnoh.py <pokeplatinum 경로> data     # game/sinnoh_data.json (야생 포켓몬·트레이너 팀)
    python tools/build_sinnoh.py <pokeplatinum 경로> scenes   # assets/maps/pt/*.png + places.json (3D 맵을 그린다)

- 야생: 장소마다 플래티나 풀숲 표(12칸, 칸 확률 20·20·10·10·10·10·5·5·4·4·1·1%) — 풀숲이 없으면 파도타기 표
- 트레이너: 관장·사천왕·챔피언·라이벌·갤럭시단 (플래티나 원본 팀과 레벨)
- 장면: tools/sinnoh_maps.py 로 원본 3D 맵을 필드 카메라로 그려 320x192 그림으로 (주인공은 봇이 얹는다)
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

LAND_W = [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1]


def species_ids(pp: Path) -> dict[str, int]:
    names = [l.strip() for l in open(pp / "generated/species.txt")]
    return {n: i for i, n in enumerate(names)}


def wild(pp: Path, key: str, sid_of: dict) -> list[tuple[int, int, int, int]]:
    d = json.load(open(pp / f"res/field/encounters/encounters_{key}.json"))
    acc = defaultdict(lambda: [999, 0, 0])
    land = d.get("land_encounters") or []
    if d.get("land_rate") and land:
        for w, e in zip(LAND_W, land):
            s = sid_of.get(e["species"], 0)
            if not s:
                continue
            a = acc[s]
            a[0], a[1], a[2] = min(a[0], e["level"]), max(a[1], e["level"]), a[2] + w
    else:
        for w, e in zip([60, 30, 5, 4, 1], d.get("surf_encounters") or []):
            s = sid_of.get(e["species"], 0)
            if not s:
                continue
            a = acc[s]
            a[0], a[1], a[2] = min(a[0], e["level_min"]), max(a[1], e["level_max"]), a[2] + w
    return sorted([(s, lo, hi, w) for s, (lo, hi, w) in acc.items()], key=lambda x: -x[3])


def team(pp: Path, stem: str, sid_of: dict) -> list[tuple[int, int]]:
    d = json.load(open(pp / f"res/trainers/data/{stem}.json"))
    return [(sid_of[m["species"]], m["level"]) for m in d["party"] if sid_of.get(m["species"])]


def build_data(pp: Path):
    from game import sinnoh as S
    sid_of = species_ids(pp)
    out = {"wild": {}, "teams": {}}
    for key, L in S.LOCATIONS.items():
        for enc in L.get("enc", []):
            out["wild"][enc] = wild(pp, enc, sid_of)
    stems = set(S.TEAM_FILES)
    for st in sorted(stems):
        out["teams"][st] = team(pp, st, sid_of)
    (ROOT / "game/sinnoh_data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print("wild", len(out["wild"]), "teams", len(out["teams"]))


def build_scenes(pp: Path, only: list[str] | None = None):
    import sinnoh_maps as SM
    from game import sinnoh as S
    pl = SM.Platinum(str(pp))
    out_dir = ROOT / "assets/maps/pt"
    out_dir.mkdir(parents=True, exist_ok=True)
    places_f = ROOT / "assets/maps/places.json"
    places = json.loads(places_f.read_text())
    for key, L in S.LOCATIONS.items():
        for kind, view in (L.get("views") or {}).items():
            name = f"{key}_{kind}"
            if only and key not in only and name not in only:
                continue
            if isinstance(view, str):
                header, (x, z), zoom = view, SM.auto_view(pl, view, kind), 1.0
            else:
                header, x, z = view[:3]
                zoom = view[3] if len(view) > 3 else 1.0
            bg = (16, 24, 16) if kind == "field" else (0, 0, 0)
            im = SM.render(pl, header, x, z, scale=1, zoom=zoom, bg=bg)
            im.save(out_dir / f"{name}.png", optimize=True)
            places.setdefault(key, {})[kind] = {"full": f"pt/{name}"}
            print("그림", name, header, x, z)
    places_f.write_text(json.dumps(places, ensure_ascii=False, separators=(",", ":")))


def build_pics(pp: Path):
    """배틀 전 상대 트레이너 그림: 플라티나 front.png 첫 칸(80x80), 팔레트 0번은 투명"""
    from PIL import Image
    from game import trainer_pics as TP
    out = ROOT / "assets/battle"
    for f in sorted(x for x in TP.all_files() if x.startswith("pt_") and not x.startswith("pt_back")):
        src = pp / "res/trainers/classes" / f[3:] / "front.png"
        im = Image.open(src)
        cell = im.crop((0, 0, 80, 80))
        rgba = cell.convert("RGBA")
        if cell.mode == "P":
            px = cell.load()
            a = rgba.load()
            for y in range(80):
                for x in range(80):
                    if px[x, y] == 0:
                        a[x, y] = (0, 0, 0, 0)
        bbox = rgba.getbbox()
        rgba.crop(bbox).save(out / f"{f}.png", optimize=True)
        print("트레이너", f)


if __name__ == "__main__":
    pp = Path(sys.argv[1])
    if sys.argv[2] == "pics":
        build_pics(pp)
    elif sys.argv[2] == "data":
        build_data(pp)
    else:
        build_scenes(pp, sys.argv[3:] or None)
