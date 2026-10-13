"""파이어레드 디컴파일(pret/pokefirered)의 맵 데이터로 실제 게임 맵 그림을 만든다.

    git clone --depth 1 --filter=blob:none --sparse https://github.com/pret/pokefirered
    (cd pokefirered && git sparse-checkout set data/layouts data/tilesets graphics/object_events/pics/people)
    python tools/render_maps.py <pokefirered 경로>

결과: assets/maps/<레이아웃>.png (16px 블록 그대로), assets/people/<이름>.png (걷는 그림 첫 칸)
"""
import json
import re
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT_MAPS = ROOT / "assets" / "maps"
OUT_PEOPLE = ROOT / "assets" / "people"
NUM_TILES_PRIMARY = 640
NUM_METATILES_PRIMARY = 640
NUM_PALS_PRIMARY = 7

# 우리 게임 장소 → 디컴파일 레이아웃 이름 (안쪽 화면은 공용 레이아웃)
LAYOUTS = [
    "PalletTown", "Route1", "ViridianCity", "Route22", "Route2", "ViridianForest", "PewterCity", "Route3",
    "MtMoon_1F", "Route4", "CeruleanCity", "Route24", "Route25", "CeruleanCave_1F", "Route5", "Route6", "VermilionCity",
    "SSAnne_1F_Corridor", "Route11", "DiglettsCave_B1F", "Route9", "Route10", "PowerPlant", "RockTunnel_1F",
    "LavenderTown", "PokemonTower_1F", "Route8", "Route7", "CeladonCity", "RocketHideout_B1F", "Route16", "Route17",
    "Route12", "Route13", "FuchsiaCity", "SafariZone_Center", "SaffronCity", "SilphCo_1F", "Route19", "SeafoamIslands_1F",
    "Route20", "CinnabarIsland", "PokemonMansion_1F", "Route21_North", "Route23", "VictoryRoad_1F", "IndigoPlateau_Exterior",
    "PokemonCenter_1F", "Mart", "PalletTown_ProfessorOaksLab", "PewterCity_Gym", "CeruleanCity_Gym",
    "VermilionCity_Gym", "CeladonCity_Gym", "FuchsiaCity_Gym", "SaffronCity_Gym", "CinnabarIsland_Gym",
    "ViridianCity_Gym", "CeladonCity_DepartmentStore_1F", "PalletTown_PlayersHouse_1F", "IndigoPlateau_PokemonCenter_1F",
]
PEOPLE = ["red_normal", "green_normal", "nurse", "clerk", "prof_oak", "blue", "mom", "brock", "misty", "lt_surge",
          "erika", "koga", "sabrina", "blaine", "giovanni", "lorelei", "bruno", "agatha", "lance",
          "youngster", "lass", "bug_catcher", "hiker", "gentleman", "rocket_m", "rocket_f", "cooltrainer_m",
          "cooltrainer_f", "fisher", "swimmer_m_land", "swimmer_f_land", "scientist", "channeler", "biker",
          "black_belt", "camper", "picnicker", "sailor", "beauty", "super_nerd", "gym_guy", "old_man_1", "woman_1"]


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def tileset_dir(src: Path, label: str) -> Path:
    want = label.replace("gTileset_", "").replace("_", "").lower()
    for kind in ("primary", "secondary"):
        for p in (src / "data" / "tilesets" / kind).iterdir():
            if p.name.replace("_", "").lower() == want:
                return p
    raise FileNotFoundError(label)


def load_pal(path: Path) -> list[tuple[int, int, int]]:
    lines = path.read_text().split()
    nums = list(map(int, lines[3:]))   # JASC-PAL 헤더 3줄
    return [tuple(nums[i:i + 3]) for i in range(0, 48, 3)]


class Tileset:
    def __init__(self, d: Path):
        self.tiles = Image.open(d / "tiles.png")
        self.idx = self.tiles.load()
        self.ntiles = (self.tiles.width // 8) * (self.tiles.height // 8)
        raw = (d / "metatiles.bin").read_bytes()
        self.metatiles = [struct.unpack_from("<8H", raw, i) for i in range(0, len(raw), 16)]
        self.pals = [load_pal(d / "palettes" / f"{i:02d}.pal") for i in range(16)]

    def tile_pixels(self, t: int):
        w = self.tiles.width // 8
        tx, ty = (t % w) * 8, (t // w) * 8
        return [[self.idx[tx + x, ty + y] for x in range(8)] for y in range(8)]


def render_layout(src: Path, layout: dict) -> Image.Image:
    prim = Tileset(tileset_dir(src, layout["primary_tileset"]))
    sec = Tileset(tileset_dir(src, layout["secondary_tileset"]))
    pals = prim.pals[:NUM_PALS_PRIMARY] + sec.pals[NUM_PALS_PRIMARY:]
    w, h = layout["width"], layout["height"]
    blocks = struct.unpack(f"<{w * h}H", (src / layout["blockdata_filepath"]).read_bytes()[:w * h * 2])
    img = Image.new("RGB", (w * 16, h * 16))
    px = img.load()
    cache: dict[int, Image.Image] = {}

    def metatile_img(mid: int) -> Image.Image:
        if mid in cache:
            return cache[mid]
        ts, local = (prim, mid) if mid < NUM_METATILES_PRIMARY else (sec, mid - NUM_METATILES_PRIMARY)
        m = Image.new("RGB", (16, 16), pals[0][0])
        mp = m.load()
        if local < len(ts.metatiles):
            entries = ts.metatiles[local]
            for layer in range(2):
                for k in range(4):
                    e = entries[layer * 4 + k]
                    tid, hf, vf, pal = e & 0x3FF, (e >> 10) & 1, (e >> 11) & 1, e >> 12
                    tset, tl = (prim, tid) if tid < NUM_TILES_PRIMARY else (sec, tid - NUM_TILES_PRIMARY)
                    if tl >= tset.ntiles:
                        continue
                    pix = tset.tile_pixels(tl)
                    ox, oy = (k % 2) * 8, (k // 2) * 8
                    for y in range(8):
                        for x in range(8):
                            c = pix[7 - y if vf else y][7 - x if hf else x] & 15
                            if c == 0 and layer == 1:
                                continue
                            if c == 0 and layer == 0:
                                mp[ox + x, oy + y] = pals[pal][0]
                                continue
                            mp[ox + x, oy + y] = pals[pal][c]
        cache[mid] = m
        return m

    for i, b in enumerate(blocks):
        img.paste(metatile_img(b & 0x3FF), ((i % w) * 16, (i // w) * 16))
    return img


def main():
    src = Path(sys.argv[1])
    OUT_MAPS.mkdir(parents=True, exist_ok=True)
    OUT_PEOPLE.mkdir(parents=True, exist_ok=True)
    table = json.loads((src / "data/layouts/layouts.json").read_text())["layouts"]
    by_name = {l["name"].removesuffix("_Layout"): l for l in table if "name" in l}
    for name in LAYOUTS:
        lay = by_name.get(name)
        if not lay:
            print("없음:", name)
            continue
        try:
            img = render_layout(src, lay)
        except FileNotFoundError as e:
            print("건너뜀:", name, e)
            continue
        img.save(OUT_MAPS / f"{name}.png", optimize=True)
        print(name, img.size)
    for p in PEOPLE:
        f = src / "graphics/object_events/pics/people" / f"{p}.png"
        if not f.exists():
            print("사람 없음:", p)
            continue
        sheet = Image.open(f).convert("RGBA")
        fw = 16 if sheet.width % 16 == 0 and sheet.height == 32 else sheet.height
        frame = sheet.crop((0, 0, 16, sheet.height)) if sheet.height == 32 else sheet.crop((0, 0, fw, sheet.height))
        # 팔레트 0번(배경색)을 투명으로
        bg = Image.open(f).convert("RGBA").getpixel((0, 0))
        data = [(0, 0, 0, 0) if px[:3] == bg[:3] else px for px in frame.getdata()]
        frame.putdata(data)
        frame.save(OUT_PEOPLE / f"{p}.png")


if __name__ == "__main__":
    main()
