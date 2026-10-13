"""파이어레드 디컴파일(pret/pokefirered)의 맵 이벤트로 장소마다 '어디에 서 있을지'를 만든다.

    git clone --depth 1 --filter=blob:none --sparse https://github.com/pret/pokefirered
    (cd pokefirered && git sparse-checkout set data/maps data/layouts graphics/object_events/pics/people \
        graphics/pokemon_storage)
    git clone --depth 1 --filter=blob:none --sparse https://github.com/pret/pokeemerald
    (cd pokeemerald && git sparse-checkout set data/maps data/layouts data/tilesets graphics/object_events/pics/people)
    python tools/render_maps.py <pokeemerald 경로> emerald   # 호연 맵 그림 먼저
    python tools/build_places.py <pokefirered 경로> <pokeemerald 경로>

결과
- assets/maps/places.json: {장소 키: {장면: {"map", "w", "h", "player": [x, y, 방향], "npcs": [[그림, x, y, 방향]]}}}
  장면: field(마을·도로 바깥), center(센터 안), mart(숍 안), gym(체육관 안), home(집 안)
- assets/people/<이름>.png: 걷는 그림의 [아래, 위, 왼쪽] 세 칸 (16x32씩, 오른쪽은 왼쪽을 뒤집는다)
- assets/pc/forest.png: PC 박스 배경지 (숲)
"""
import json
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT_MAPS = ROOT / "assets" / "maps"
OUT_PEOPLE = ROOT / "assets" / "people"
OUT_PC = ROOT / "assets" / "pc"

# 우리 장소 키 → (바깥 맵, 센터·숍·체육관이 있는 마을 이름)
OUTDOOR = {
    "pallet": "PalletTown", "route1": "Route1", "viridian": "ViridianCity", "route22": "Route22", "route2": "Route2",
    "forest": "ViridianForest", "pewter": "PewterCity", "route3": "Route3", "mtmoon": "MtMoon_1F", "route4": "Route4",
    "cerulean": "CeruleanCity", "route24": "Route24", "cerucave": "CeruleanCave_1F", "route5": "Route5",
    "vermilion": "VermilionCity", "ssanne": "SSAnne_1F_Corridor", "route11": "Route11", "digletts": "DiglettsCave_B1F",
    "route9": "Route9", "powerplant": "PowerPlant", "rocktunnel": "RockTunnel_1F", "lavender": "LavenderTown",
    "tower": "PokemonTower_1F", "route8": "Route8", "celadon": "CeladonCity", "hideout": "RocketHideout_B1F",
    "route16": "Route16", "route12": "Route12", "fuchsia": "FuchsiaCity", "safari": "SafariZone_Center",
    "saffron": "SaffronCity", "silph": "SilphCo_1F", "route19": "Route19", "seafoam": "SeafoamIslands_1F",
    "route20": "Route20", "cinnabar": "CinnabarIsland", "mansion": "PokemonMansion_1F", "route21": "Route21_North",
    "route23": "VictoryRoad_1F", "plateau": "IndigoPlateau_Exterior",
}
INDOOR = {   # 장소 키 → {장면: 맵}
    "pallet": {"home": "PalletTown_PlayersHouse_1F"},
    "plateau": {"center": "IndigoPlateau_PokemonCenter_1F", "mart": "IndigoPlateau_PokemonCenter_1F"},
    "celadon": {"mart": "CeladonCity_DepartmentStore_1F"},
}
TOWNS = {"viridian": "ViridianCity", "pewter": "PewterCity", "cerulean": "CeruleanCity",
         "vermilion": "VermilionCity", "lavender": "LavenderTown", "celadon": "CeladonCity",
         "fuchsia": "FuchsiaCity", "saffron": "SaffronCity", "cinnabar": "CinnabarIsland"}
LEADERS = {"BROCK", "MISTY", "LT_SURGE", "ERIKA", "KOGA", "SABRINA", "BLAINE", "GIOVANNI",
           "ROXANNE", "BRAWLY", "WATTSON", "FLANNERY", "NORMAN", "WINONA", "TATE", "LIZA", "JUAN"}
SERVICE = {"NURSE", "CLERK", "MART_EMPLOYEE"}   # 카운터 너머라 두 칸 앞에 선다

# 호연 (에메랄드): 장소 키 → 바깥 맵, 센터·숍·체육관이 있는 마을 이름
HOENN_OUTDOOR = {
    "h_ferry": "SSTidalCorridor", "littleroot": "LittlerootTown", "h_route101": "Route101", "oldale": "OldaleTown",
    "h_route102": "Route102", "petalburg": "PetalburgCity", "h_woods": "PetalburgWoods", "rustboro": "RustboroCity",
    "h_tunnel": "RusturfTunnel", "h_boat": "Route106", "dewford": "DewfordTown", "granite": "GraniteCave_1F",
    "h_route109": "Route109", "slateport": "SlateportCity", "h_route110": "Route110", "mauville": "MauvilleCity",
    "verdanturf": "VerdanturfTown", "h_route111": "Route111", "chimney": "MtChimney", "lavaridge": "LavaridgeTown",
    "fallarbor": "FallarborTown", "meteor": "MeteorFalls_1F_1R", "h_route119": "Route119", "fortree": "FortreeCity",
    "h_route120": "Route120", "pyre": "MtPyre_1F", "lilycove": "LilycoveCity", "aquahideout": "AquaHideout_1F",
    "h_route124": "Route124", "mossdeep": "MossdeepCity", "seafloor": "SeafloorCavern_Entrance",
    "sootopolis": "SootopolisCity", "origin": "CaveOfOrigin_Entrance", "h_route128": "Route128",
    "pacifidlog": "PacifidlogTown", "skypillar": "SkyPillar_Outside", "sealed": "SealedChamber_OuterRoom",
    "h_victory": "VictoryRoad_1F", "evergrande": "EverGrandeCity",
}
HOENN_TOWNS = {k: v for k, v in HOENN_OUTDOOR.items() if v.endswith(("Town", "City"))}
HOENN_INDOOR = {"littleroot": {"home": "LittlerootTown_BrendansHouse_1F"},
                "evergrande": {"center": "EverGrandeCity_PokemonLeague_1F", "mart": "EverGrandeCity_PokemonLeague_1F"},
                "lilycove": {"mart": "LilycoveCity_DepartmentStore_1F"}}
FACE = {"MOVEMENT_TYPE_FACE_DOWN": "down", "MOVEMENT_TYPE_FACE_UP": "up", "MOVEMENT_TYPE_FACE_LEFT": "left",
        "MOVEMENT_TYPE_FACE_RIGHT": "right"}
STEP = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}
BACK = {"down": "up", "up": "down", "left": "right", "right": "left"}
EXTRA_PEOPLE = ["boy", "fat_man", "old_man_1", "woman_1", "woman_2", "woman_3", "little_girl", "little_boy",
                "worker_f", "worker_m", "old_woman", "man", "cooltrainer_m", "cooltrainer_f", "youngster", "lass"]


def snake_to_file(gfx: str) -> str:
    return gfx.removeprefix("OBJ_EVENT_GFX_").lower()


def hoenn_maps(em: Path) -> list[str]:
    """호연 장면에 쓰는 에메랄드 맵 이름 (tools/render_maps.py emerald도 이걸로 그린다)"""
    names = list(HOENN_OUTDOOR.values())
    for key, town in HOENN_TOWNS.items():
        for suffix in ("PokemonCenter_1F", "Mart", "Gym"):
            if (em / "data/maps" / f"{town}_{suffix}").exists():
                names.append(f"{town}_{suffix}")
    for d in HOENN_INDOOR.values():
        names.extend(d.values())
    return sorted(set(names))


def load_map(src: Path, name: str) -> dict:
    return json.loads((src / "data" / "maps" / name / "map.json").read_text())


def layout_of(src: Path, layouts: dict, m: dict) -> dict:
    return layouts[m["layout"]]


def collisions(src: Path, lay: dict) -> list[list[int]]:
    w, h = lay["width"], lay["height"]
    blocks = struct.unpack(f"<{w * h}H", (src / lay["blockdata_filepath"]).read_bytes()[:w * h * 2])
    return [[(blocks[y * w + x] >> 10) & 3 for x in range(w)] for y in range(h)]


def walkable_near(col, x0, y0, taken) -> tuple[int, int]:
    """(x0, y0)에서 가장 가까운 걸을 수 있는 칸"""
    h, w = len(col), len(col[0])
    best = None
    for y in range(h):
        for x in range(w):
            if col[y][x] == 0 and (x, y) not in taken:
                dist = (x - x0) ** 2 + (y - y0) ** 2
                if best is None or dist < best[0]:
                    best = (dist, x, y)
    return (best[1], best[2]) if best else (x0, y0)


def scene_of(src: Path, layouts: dict, map_name: str, kind: str, have: set[str], prefix: str = "") -> dict:
    m = load_map(src, map_name)
    lay = layout_of(src, layouts, m)
    col = collisions(src, lay)
    npcs, objs = [], m.get("object_events", [])
    for o in objs:
        g = o.get("graphics_id", "")
        f = snake_to_file(g)
        if prefix + f in have and isinstance(o.get("x"), int):
            npcs.append([prefix + f, o["x"], o["y"], FACE.get(o.get("movement_type"), "down")])
    taken = {(n[1], n[2]) for n in npcs}
    player = None
    if kind in ("center", "mart", "gym", "home"):
        want = {"center": {"NURSE"}, "mart": {"CLERK", "WORKER_F", "MART_EMPLOYEE"}, "gym": LEADERS, "home": {"MOM"}}[kind]
        for o in objs:
            g = o.get("graphics_id", "").removeprefix("OBJ_EVENT_GFX_")
            if g in want:
                face = FACE.get(o.get("movement_type"), "down")
                dx, dy = STEP[face]
                dist = 2 if g in SERVICE else 1
                player = [o["x"] + dx * dist, o["y"] + dy * dist, BACK[face]]
                break
    elif kind == "field":
        doors = [w for w in m.get("warp_events", []) if "POKEMON_CENTER_1F" in w["dest_map"]] or \
                [w for w in m.get("warp_events", []) if "PLAYERS_HOUSE_1F" in w["dest_map"]
                 or "BRENDANS_HOUSE_1F" in w["dest_map"]]
        if doors:
            player = [doors[0]["x"], doors[0]["y"] + 1, "up"]
    if player is None:   # 맵 가운데에서 가장 가까운 걸을 수 있는 칸
        x, y = walkable_near(col, lay["width"] // 2, lay["height"] // 2, taken)
        player = [x, y, "down"]
    npcs = [n for n in npcs if (n[1], n[2]) != (player[0], player[1])]
    return {"map": prefix + lay["name"].removesuffix("_Layout"), "w": lay["width"], "h": lay["height"],
            "player": player, "npcs": npcs}


def strip_of(f: Path) -> Image.Image:
    """걷는 그림 시트 → [아래, 위, 왼쪽] 세 칸 (배경색은 투명)"""
    sheet = Image.open(f)
    bg = sheet.convert("RGBA").getpixel((0, 0))
    sheet = sheet.convert("RGBA")
    fw = sheet.width // 9 if sheet.width % 9 == 0 else (16 if sheet.height == 32 else sheet.height)
    n = sheet.width // fw
    frames = [sheet.crop((i * fw, 0, i * fw + fw, sheet.height)) for i in (0, 1, 2) if i < n]
    while len(frames) < 3:
        frames.append(frames[0])
    strip = Image.new("RGBA", (fw * 3, sheet.height), (0, 0, 0, 0))
    for i, fr_im in enumerate(frames):
        data = [(0, 0, 0, 0) if px[:3] == bg[:3] else px for px in fr_im.getdata()]
        fr_im.putdata(data)
        strip.paste(fr_im, (i * fw, 0))
    return strip


def people(fr: Path, em: Path) -> set[str]:
    """관동 사람들 (파이어레드) + 에메랄드 주인공 둘"""
    OUT_PEOPLE.mkdir(parents=True, exist_ok=True)
    sources = {f.stem: f for f in (fr / "graphics/object_events/pics/people").glob("*.png")}
    sources["brendan"] = em / "graphics/object_events/pics/people/brendan/walking.png"
    sources["may"] = em / "graphics/object_events/pics/people/may/walking.png"
    want = {p.stem for p in OUT_PEOPLE.glob("*.png")} | set(EXTRA_PEOPLE) | {"brendan", "may", "worker_f"}
    done = set()
    for name in sorted(want):
        f = sources.get(name)
        if not f or not f.exists():
            print("사람 없음:", name)
            continue
        strip_of(f).save(OUT_PEOPLE / f"{name}.png")
        done.add(name)
    return done


def hoenn_people(em: Path) -> set[str]:
    """호연 맵에 서 있는 사람들 (에메랄드) → assets/people/em/"""
    out = OUT_PEOPLE / "em"
    out.mkdir(parents=True, exist_ok=True)
    gfx = set()
    for m in hoenn_maps(em):
        for o in load_map(em, m).get("object_events", []):
            gfx.add(snake_to_file(o.get("graphics_id", "")))
    done = set()
    for name in sorted(gfx):
        f = em / "graphics/object_events/pics/people" / f"{name}.png"
        if f.exists():
            strip_of(f).save(out / f"{name}.png")
            done.add(f"em/{name}")
    return done


def wallpaper(fr: Path):
    OUT_PC.mkdir(parents=True, exist_ok=True)
    d = fr / "graphics/pokemon_storage/wallpapers/forest"
    tiles = Image.open(d / "tiles.png")
    pal, px, tw = tiles.getpalette(), tiles.load(), tiles.width // 8
    entries = struct.unpack("<360H", (d / "tilemap.bin").read_bytes()[:720])
    out = Image.new("RGBA", (160, 144), (0, 0, 0, 0))   # 팔레트 0번은 투명
    op = out.load()
    for i, v in enumerate(entries):
        t, hf, vf = v & 0x3FF, (v >> 10) & 1, (v >> 11) & 1
        tx, ty = (t % tw) * 8, (t // tw) * 8
        for y in range(8):
            for x in range(8):
                c = px[tx + (7 - x if hf else x), ty + (7 - y if vf else y)]
                if c % 16:
                    op[(i % 20) * 8 + x, (i // 20) * 8 + y] = tuple(pal[c * 3:c * 3 + 3]) + (255,)
    out.save(OUT_PC / "forest.png")


def main():
    fr, em = Path(sys.argv[1]), Path(sys.argv[2])
    layouts = {l["id"]: l for l in json.loads((fr / "data/layouts/layouts.json").read_text())["layouts"] if "id" in l}
    have = people(fr, em)
    hero_walkers(fr)
    wallpaper(fr)
    places = {}
    for key, outdoor in OUTDOOR.items():
        p = {"field": scene_of(fr, layouts, outdoor, "field", have)}
        town = TOWNS.get(key)
        if town:
            for kind, suffix in (("center", "PokemonCenter_1F"), ("mart", "Mart"), ("gym", "Gym")):
                if (fr / "data/maps" / f"{town}_{suffix}").exists():
                    p[kind] = scene_of(fr, layouts, f"{town}_{suffix}", kind, have)
        for kind, name in INDOOR.get(key, {}).items():
            p[kind] = scene_of(fr, layouts, name, kind, have)
        for kind, sc in p.items():
            if not (OUT_MAPS / f"{sc['map']}.png").exists():
                print("맵 그림 없음:", key, kind, sc["map"])
        places[key] = p
    # 호연 (에메랄드)
    em_layouts = {l["id"]: l for l in json.loads((em / "data/layouts/layouts.json").read_text())["layouts"] if "id" in l}
    em_have = hoenn_people(em)
    for key, outdoor in HOENN_OUTDOOR.items():
        p = {"field": scene_of(em, em_layouts, outdoor, "field", em_have, "em/")}
        town = HOENN_TOWNS.get(key)
        if town:
            for kind, suffix in (("center", "PokemonCenter_1F"), ("mart", "Mart"), ("gym", "Gym")):
                if (em / "data/maps" / f"{town}_{suffix}").exists():
                    p[kind] = scene_of(em, em_layouts, f"{town}_{suffix}", kind, em_have, "em/")
        for kind, name in HOENN_INDOOR.get(key, {}).items():
            p[kind] = scene_of(em, em_layouts, name, kind, em_have, "em/")
        for kind, sc in p.items():
            if not (OUT_MAPS / f"{sc['map']}.png").exists():
                print("맵 그림 없음:", key, kind, sc["map"])
        places[key] = p
    (OUT_MAPS / "places.json").write_text(json.dumps(places, ensure_ascii=False, separators=(",", ":")))
    print("장소", len(places), "사람", len(have) + len(em_have))



# ---------- 주인공 걷는 그림 (원본이 없는 주인공은 레드·리프 그림의 색을 바꿔 만든다) ----------
def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


# 바탕 그림의 (팔레트 번호, 줄 범위) → 부위. 줄은 16x32 칸 안의 y (위에서부터)
RED_PARTS = {"hat": ({11: "main", 12: "dark", 8: "edge"}, range(0, 19)), "brim": ({9: "light", 10: "main"}, range(0, 19)),
             "hair": ({6: "main"}, range(19, 23)), "top": ({11: "main", 12: "dark", 9: "light", 10: "main"}, range(19, 32)),
             "pants": ({6: "dark", 7: "main"}, range(23, 32))}
LEAF_PARTS = {"hat": ({9: "light", 10: "main", 6: "edge"}, range(0, 20)), "ribbon": ({11: "main", 12: "dark"}, range(0, 20)),
              "hair": ({4: "main"}, range(0, 32)), "top": ({5: "main", 6: "dark", 7: "light"}, range(20, 32)),
              "skirt": ({12: "main", 11: "light"}, range(20, 32))}
HERO_COLORS = {   # 주인공 → (바탕, {부위: 대표 색})
    "ethan": ("red", {"hair": (40, 40, 48), "hat": (64, 64, 72), "brim": (240, 200, 56), "top": (208, 56, 56), "pants": (56, 56, 64)}),
    "lucas": ("red", {"hair": (40, 40, 56), "hat": (208, 56, 64), "brim": (232, 232, 240), "top": (72, 104, 192), "pants": (64, 64, 80)}),
    "hilbert": ("red", {"hair": (96, 56, 32), "hat": (216, 56, 56), "brim": (240, 240, 248), "top": (64, 112, 200), "pants": (48, 48, 56)}),
    "nate": ("red", {"hair": (112, 64, 40), "hat": (224, 72, 64), "brim": (40, 40, 48), "top": (72, 136, 216), "pants": (208, 208, 216)}),
    "calem": ("red", {"hair": (56, 40, 32), "hat": (200, 48, 56), "brim": (56, 56, 64), "top": (48, 64, 120), "pants": (96, 104, 120)}),
    "elio": ("red", {"hair": (32, 32, 40), "hat": (56, 56, 64), "brim": (232, 200, 64), "top": (96, 160, 224), "pants": (48, 48, 56)}),
    "victor": ("red", {"hair": (72, 48, 32), "hat": (96, 96, 104), "brim": (200, 200, 208), "top": (152, 152, 160), "pants": (64, 72, 96)}),
    "florian": ("red", {"hair": (120, 72, 40), "hat": (120, 72, 40), "brim": (120, 72, 40), "top": (240, 140, 48), "pants": (224, 200, 136)}),
    "lyra": ("leaf", {"hat": (240, 240, 248), "ribbon": (216, 56, 56), "hair": (136, 88, 48), "top": (216, 72, 72),
                      "skirt": (64, 104, 200)}),
    "dawn": ("leaf", {"hat": (240, 240, 248), "ribbon": (248, 120, 168), "hair": (40, 48, 96), "top": (56, 56, 64),
                      "skirt": (240, 104, 160)}),
    "hilda": ("leaf", {"hat": (240, 240, 248), "ribbon": (232, 104, 152), "hair": (120, 72, 40), "top": (232, 232, 240),
                       "skirt": (72, 104, 176)}),
    "rosa": ("leaf", {"hat": (240, 120, 168), "ribbon": (240, 240, 248), "hair": (136, 88, 48), "top": (72, 120, 200),
                      "skirt": (248, 208, 64)}),
    "serena": ("leaf", {"hat": (232, 120, 152), "ribbon": (56, 56, 64), "hair": (232, 200, 96), "top": (56, 56, 64),
                        "skirt": (208, 56, 64)}),
    "selene": ("leaf", {"hat": (216, 56, 56), "ribbon": (216, 56, 56), "hair": (48, 40, 48), "top": (240, 240, 232),
                        "skirt": (96, 176, 96)}),
    "gloria": ("leaf", {"hat": (96, 160, 96), "ribbon": (96, 160, 96), "hair": (128, 80, 48), "top": (176, 176, 184),
                        "skirt": (232, 120, 152)}),
    "juliana": ("leaf", {"hat": (120, 72, 40), "ribbon": (120, 72, 40), "hair": (120, 72, 40), "top": (152, 96, 200),
                         "skirt": (96, 80, 120)}),
}
TONE = {"main": 1.0, "dark": 0.72, "light": 1.18, "edge": 0.5}


def hero_walkers(fr: Path):
    """원본 걷는 그림이 없는 주인공 16명 → assets/people/hero_<키>.png (레드·리프 그림의 색만 바꿈)"""
    bases = {"red": ("red_normal", RED_PARTS), "leaf": ("green_normal", LEAF_PARTS)}
    for key, (base, colors) in HERO_COLORS.items():
        name, parts = bases[base]
        src = Image.open(fr / "graphics/object_events/pics/people" / f"{name}.png")
        idx, pal = src.load(), src.getpalette()
        out = strip_of(fr / "graphics/object_events/pics/people" / f"{name}.png")
        op = out.load()
        fw = src.width // 9
        for slot, frame in enumerate((0, 1, 2)):   # [아래, 위, 왼쪽]
            for y in range(src.height):
                for x in range(fw):
                    i = idx[frame * fw + x, y]
                    if i == 0:
                        continue
                    for part, (index_tone, rows) in parts.items():
                        if part in colors and i in index_tone and y in rows:
                            op[slot * fw + x, y] = _shade(colors[part], TONE[index_tone[i]]) + (255,)
                            break
        out.save(OUT_PEOPLE / f"hero_{key}.png")


if __name__ == "__main__":
    main()
