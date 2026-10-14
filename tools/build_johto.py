"""성도 장면: 마을·도로는 포켓몬 크리스탈 원본 맵(pret/pokecrystal), 동굴·탑·숲은 하트골드 원본 장소 그림.

    git clone --depth 1 --filter=blob:none --sparse https://github.com/pret/pokecrystal
    (cd pokecrystal && git sparse-checkout set maps gfx/tilesets gfx/sprites gfx/overworld data/tilesets \
        data/maps data/sprites constants)
    git clone --depth 1 --filter=blob:none --no-checkout https://github.com/pret/pokeheartgold
    (cd pokeheartgold && git checkout HEAD -- 'files/fielddata/graphic/preview_graphic/preview_graphic/*_day.*')
    python tools/build_johto.py <pokecrystal> <pokeheartgold>

결과 (tools/build_places.py로 만든 places.json에 성도 장소를 더한다)
- assets/maps/gs/<맵>.png: 크리스탈 맵 (낮 색, 한 걸음 = 16픽셀이라 파이어레드 맵과 같은 칸 크기)
- assets/maps/hg/<장소>.png: 하트골드 장소 그림 256x160 (던전에 들어갈 때 나오는 그림)
- assets/people/gs/<이름>.png: 크리스탈 사람 [아래, 위, 왼쪽] 세 칸 (16x16씩)
- places.json 성도 장소: 맵 장면 {"map": "gs/...", ...} 또는 그림 장면 {"art": "hg/..."}
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT_MAPS = ROOT / "assets" / "maps"
OUT_PEOPLE = ROOT / "assets" / "people" / "gs"

# 우리 장소 키 → 크리스탈 바깥 맵 (그림 장면이 있는 곳은 ART)
OUTDOOR = {
    "newbark": "NewBarkTown", "j_route29": "Route29", "cherrygrove": "CherrygroveCity", "j_route30": "Route30",
    "violet": "VioletCity", "j_route32": "Route32", "azalea": "AzaleaTown", "goldenrod": "GoldenrodCity",
    "radio": "RadioTower1F", "j_route35": "Route36", "ecruteak": "EcruteakCity", "j_route38": "Route38",
    "olivine": "OlivineCity", "lighthouse": "OlivineLighthouse1F", "j_route40": "Route40", "cianwood": "CianwoodCity",
    "j_route42": "Route42", "mahogany": "MahoganyTown", "ragelake": "LakeOfRage", "jhideout": "TeamRocketBaseB1F",
    "blackthorn": "BlackthornCity", "j_route45": "Route45", "j_route27": "Route27",
}
ART = {   # 하트골드 장소 그림
    "sprout": "sprout_tower", "unioncave": "union_cave", "slowpoke": "slowpoke_well", "ilex": "ilex_forest",
    "burned": "burned_tower", "belltower": "bell_tower", "whirl": "whirl_islands", "j_route44": "ice_path",
    "dragonsden": "dragons_den",
}
TOWN = {"cherrygrove": "Cherrygrove", "violet": "Violet", "azalea": "Azalea", "goldenrod": "Goldenrod",
        "ecruteak": "Ecruteak", "olivine": "Olivine", "cianwood": "Cianwood", "mahogany": "Mahogany",
        "blackthorn": "Blackthorn"}
INDOOR = {"newbark": {"home": "PlayersHouse1F"}, "goldenrod": {"mart": "GoldenrodDeptStore1F"},
          "cianwood": {"mart": "CianwoodPharmacy"}, "mahogany": {"mart": "MahoganyMart1F"},
          "blackthorn": {"gym": "BlackthornGym1F"}}
WANT = {"center": {"NURSE"}, "mart": {"CLERK", "PHARMACIST"}, "home": {"MOM"},
        "gym": {"FALKNER", "BUGSY", "WHITNEY", "MORTY", "JASMINE", "CHUCK", "PRYCE", "CLAIR"}}
SERVICE = {"NURSE", "CLERK", "PHARMACIST"}   # 카운터 너머라 두 칸 앞에 선다
FACE = {"STANDING_DOWN": "down", "STANDING_UP": "up", "STANDING_LEFT": "left", "STANDING_RIGHT": "right"}
STEP = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}
BACK = {"down": "up", "up": "down", "left": "right", "right": "left"}
PAL_NAMES = ["GRAY", "RED", "GREEN", "WATER", "YELLOW", "BROWN", "ROOF", "TEXT"]
NPC_PALS = ["RED", "BLUE", "GREEN", "BROWN", "PINK", "SILVER", "TREE", "ROCK"]
WALKABLE = {"FLOOR", "TALL_GRASS", "LONG_GRASS", "00", "01"}
OWN_PAL = {"house", "radio_tower", "pokecom_center"}   # 따로 정한 팔레트를 쓰는 타일셋


def rgb(line: str) -> list[tuple]:
    v = [int(x) for x in re.findall(r"\d+", line.split(";")[0])]
    return [tuple(c * 255 // 31 for c in v[i:i + 3]) for i in range(0, len(v), 3)]


class Crystal:
    def __init__(self, src: Path):
        self.src = src
        # 맵 이름 → (타일셋, 환경, 그룹 번호)
        self.maps, group = {}, 0
        for line in (src / "data/maps/maps.asm").read_text().splitlines():
            if re.match(r"MapGroup_\w+:", line):
                group += 1
            m = re.match(r"\s*map (\w+), TILESET_(\w+), (\w+)", line)
            if m:
                self.maps[m[1]] = (m[2].lower(), m[3], group)
        const = dict(re.findall(r"map_attributes (\w+), (\w+),", (src / "data/maps/attributes.asm").read_text()))
        sizes = {m[0]: int(m[1]) for m in re.findall(r"map_const (\w+),\s*(\d+),\s*\d+",
                                                     (src / "constants/map_constants.asm").read_text())}
        self.width = {name: sizes[c] for name, c in const.items() if c in sizes}
        self.blk, labels = {}, []   # 여러 맵이 한 .blk를 같이 쓴다 (이름표 여러 개 다음에 INCBIN 하나)
        for line in (src / "data/maps/blocks.asm").read_text().splitlines():
            m = re.match(r"(\w+)_Blocks:", line)
            if m:
                labels.append(m[1])
            m = re.search(r"INCBIN \"(maps/[\w/]+\.blk)\"", line)
            if m:
                self.blk.update({lb: m[1] for lb in labels})
                labels = []
        roofs = (src / "data/maps/roofs.asm").read_text()
        names = re.findall(r"const (ROOF_\w+)", roofs)
        files = re.findall(r"INCBIN \"gfx/tilesets/roofs/(\w+)\.2bpp\"", roofs) or \
            ["new_bark", "violet", "azalea", "olivine", "goldenrod"]
        self.roof_of_group = {}
        for v, g in re.findall(r"db (ROOF_\w+|-1)\s*; *(\d+)", roofs):
            if v != "-1":
                self.roof_of_group[int(g)] = files[names.index(v)]
        bg = (src / "gfx/tilesets/bg_tiles.pal").read_text()
        self.bg = {}
        for sec in ("day", "indoor"):
            blk = bg.split(f"; {sec}\n")[1].split("\n\n")[0]
            self.bg[sec] = [rgb(l) for l in blk.splitlines() if "RGB" in l]
        self.roofpal = {}
        for g, morn in re.findall(r"; group (\d+).*\n\s*(RGB[^\n]*)", (src / "gfx/tilesets/roofs.pal").read_text()):
            self.roofpal[int(g)] = rgb(morn)

    def palettes(self, tileset: str, env: str) -> list[list[tuple]]:
        if tileset in OWN_PAL:
            cols = [c for l in (self.src / f"gfx/tilesets/{tileset}.pal").read_text().splitlines()
                    if "RGB" in l for c in rgb(l)]
            return [cols[i * 4:i * 4 + 4] for i in range(8)]
        return self.bg["day" if env in ("TOWN", "ROUTE") else "indoor"]

    def tilepal(self, tileset: str) -> tuple[list[int], list[int]]:
        b = {0: [], 1: []}
        for m in re.finditer(r"tilepal (\d),(.*)", (self.src / f"gfx/tilesets/{tileset}_palette_map.asm").read_text()):
            b[int(m[1])] += [PAL_NAMES.index(x.strip()) for x in m[2].split(",")]
        return b[0], b[1]

    def collision(self, tileset: str) -> list[list[str]]:
        return [[c.strip() for c in m.split(",")] for m in
                re.findall(r"tilecoll ([^;\n]+)", (self.src / f"data/tilesets/{tileset}_collision.asm").read_text())]

    def render(self, name: str) -> tuple[Image.Image, list[list[bool]]]:
        """맵 그림 (1배) + 걸을 수 있는 칸 [y][x] (한 칸 = 16픽셀)"""
        tileset, env, group = self.maps[name]
        w = self.width[name]
        blk = (self.src / self.blk[name]).read_bytes()
        h = len(blk) // w
        sheet = Image.open(self.src / f"gfx/tilesets/{tileset}.png").convert("L")
        meta = (self.src / f"data/tilesets/{tileset}_metatiles.bin").read_bytes()
        pals = self.palettes(tileset, env)
        b0, b1 = self.tilepal(tileset)
        roof = None
        if env in ("TOWN", "ROUTE") and group in self.roof_of_group:
            roof = Image.open(self.src / f"gfx/tilesets/roofs/{self.roof_of_group[group]}.png").convert("L")
            rp = self.roofpal.get(group)
            if rp:
                pals = [list(p) for p in pals]
                pals[6] = [pals[6][0], rp[0], rp[1], pals[6][3]]
        tiles = {}

        def tile(t: int) -> Image.Image:
            if t in tiles:
                return tiles[t]
            out = Image.new("RGB", (8, 8), (255, 255, 255))
            src, sx, sy = None, 0, 0
            if roof is not None and 0x0A <= t <= 0x12:
                k = t - 0x0A
                src, sx, sy = roof, (k % 3) * 8, (k // 3) * 8
            elif t < 0x60 or t >= 0x80:
                i = t if t < 0x60 else t - 0x20
                if i < (sheet.width // 8) * (sheet.height // 8):
                    src, sx, sy = sheet, (i % 16) * 8, (i // 16) * 8
            if src is not None:
                pi = b0[t] if t < 0x80 else (b1[t - 0x80] if t - 0x80 < len(b1) else 0)
                pal = pals[pi if pi < 8 else 0]
                op, sp = out.load(), src.load()
                for y in range(8):
                    for x in range(8):
                        op[x, y] = pal[3 - sp[sx + x, sy + y] // 64]
            tiles[t] = out
            return out
        img = Image.new("RGB", (w * 32, h * 32))
        for by in range(h):
            for bx in range(w):
                m = blk[by * w + bx]
                for ti in range(16):
                    img.paste(tile(meta[m * 16 + ti]), (bx * 32 + ti % 4 * 8, by * 32 + ti // 4 * 8))
        coll = self.collision(tileset)
        walk = [[False] * (w * 2) for _ in range(h * 2)]
        for by in range(h):
            for bx in range(w):
                c = coll[blk[by * w + bx]] if blk[by * w + bx] < len(coll) else ["WALL"] * 4
                for q in range(4):
                    walk[by * 2 + q // 2][bx * 2 + q % 2] = c[q] in WALKABLE
        return img, walk

    def events(self, name: str) -> tuple[list, list]:
        txt = (self.src / f"maps/{name}.asm").read_text()
        warps = [(int(x), int(y), d) for x, y, d in re.findall(r"warp_event\s+(\d+),\s*(\d+),\s*(\w+)", txt)]
        objs = []
        for line in re.findall(r"object_event\s+([^\n]+)", txt):
            p = [s.strip() for s in line.split(";")[0].split(",")]
            if not p[2].startswith("SPRITE_"):
                continue
            objs.append({"x": int(p[0]), "y": int(p[1]), "sprite": p[2].removeprefix("SPRITE_"),
                         "move": p[3].removeprefix("SPRITEMOVEDATA_"), "pal": p[8],
                         "time": p[7], "event": p[-1]})
        return warps, objs


def sprites(src: Path) -> dict[str, tuple[str, str]]:
    """SPRITE_이름 → (그림 파일, 기본 팔레트)"""
    consts = re.findall(r"const SPRITE_(\w+)", (src / "constants/sprite_constants.asm").read_text())
    rows = re.findall(r"overworld_sprite (\w+)SpriteGFX, \d+, \w+, PAL_OW_(\w+)",
                      (src / "data/sprites/sprites.asm").read_text())
    out = {}
    for i, (gfx, pal) in enumerate(rows, start=1):
        f = re.sub(r"(?<!^)(?=[A-Z])", "_", gfx).lower()
        if i < len(consts) and (src / f"gfx/sprites/{f}.png").exists():
            out[consts[i]] = (f, pal)
    return out


def npc_strip(src: Path, f: str, pal: str) -> Image.Image:
    sheet = Image.open(src / f"gfx/sprites/{f}.png").convert("L")
    txt = (src / "gfx/overworld/npc_sprites.pal").read_text().split("; day")[1]
    pals = [rgb(l) for l in txt.splitlines() if "RGB" in l][:8]
    cols = pals[NPC_PALS.index(pal)] if pal in NPC_PALS else pals[0]
    n = sheet.height // 16
    strip = Image.new("RGBA", (48, 16), (0, 0, 0, 0))
    sp, op = sheet.load(), strip.load()
    for slot in range(3):
        fr = slot if slot < n else 0
        for y in range(16):
            for x in range(16):
                s = 3 - sp[x, fr * 16 + y] // 64
                if s:
                    op[slot * 16 + x, y] = cols[s] + (255,)
    return strip


def nearest(walk, x0, y0, taken) -> tuple[int, int]:
    best = None
    for y, row in enumerate(walk):
        for x, ok in enumerate(row):
            if ok and (x, y) not in taken:
                d = (x - x0) ** 2 + (y - y0) ** 2
                if best is None or d < best[0]:
                    best = (d, x, y)
    return (best[1], best[2]) if best else (x0, y0)


def scene(cr: Crystal, spr: dict, name: str, kind: str, have: set) -> dict:
    img, walk = cr.render(name)
    (OUT_MAPS / "gs").mkdir(parents=True, exist_ok=True)
    img.save(OUT_MAPS / "gs" / f"{name}.png", optimize=True)
    warps, objs = cr.events(name)
    npcs, player = [], None
    for o in objs:
        if o["time"] not in ("-1", "DAY") or o["sprite"] not in spr:
            continue
        f, pal = spr[o["sprite"]]
        if o["pal"].startswith("PAL_NPC_"):
            pal = o["pal"].removeprefix("PAL_NPC_")
        key = f"{f}_{pal.lower()}"
        if key not in have:
            OUT_PEOPLE.mkdir(parents=True, exist_ok=True)
            npc_strip(cr.src, f, pal).save(OUT_PEOPLE / f"{key}.png")
            have.add(key)
        face = FACE.get(o["move"], "down")
        if any((n[1], n[2]) == (o["x"], o["y"]) for n in npcs):
            continue
        npcs.append([f"gs/{key}", o["x"], o["y"], face])
        if player is None and kind in WANT and o["sprite"] in WANT[kind]:
            dx, dy = STEP[face]
            dist = 2 if o["sprite"] in SERVICE else 1
            player = [o["x"] + dx * dist, o["y"] + dy * dist, BACK[face]]
    if player is None and kind == "field":
        doors = [w for w in warps if w[2].endswith("POKECENTER_1F")] or [w for w in warps if "PLAYERS_HOUSE" in w[2]]
        if doors:
            player = [doors[0][0], doors[0][1] + 1, "up"]
    taken = {(n[1], n[2]) for n in npcs}
    if player is None:
        x, y = nearest(walk, len(walk[0]) // 2, len(walk) // 2, taken)
        player = [x, y, "down"]
    npcs = [n for n in npcs if (n[1], n[2]) != (player[0], player[1])]
    return {"map": f"gs/{name}", "w": len(walk[0]), "h": len(walk), "player": player, "npcs": npcs}


def preview(hg: Path, name: str) -> Image.Image:
    """하트골드 장소 그림: 타일 시트 + NSCR 화면 → 256x160 (위아래 검은 띠는 자른다)"""
    import struct
    base = hg / "files/fielddata/graphic/preview_graphic/preview_graphic" / f"preview_graphic_{name}_day"
    d = (base.with_suffix(".NSCR")).read_bytes()
    i = d.find(b"NRCS")
    w, h = struct.unpack_from("<HH", d, i + 8)
    n = struct.unpack_from("<I", d, i + 16)[0]
    ents = struct.unpack_from(f"<{n // 2}H", d, i + 20)
    sheet = Image.open(base.with_suffix(".png"))
    sw = sheet.width // 8
    img = Image.new("P", (w, h))
    img.putpalette(sheet.getpalette())
    for k, e in enumerate(ents):
        t, hf, vf = e & 0x3FF, e >> 10 & 1, e >> 11 & 1
        tile = sheet.crop((t % sw * 8, t // sw * 8, t % sw * 8 + 8, t // sw * 8 + 8))
        if hf:
            tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
        if vf:
            tile = tile.transpose(Image.FLIP_TOP_BOTTOM)
        img.paste(tile, (k % (w // 8) * 8, k // (w // 8) * 8))
    return img.convert("RGB").crop((0, 16, 256, 176))


def main():
    cr = Crystal(Path(sys.argv[1]))
    hg = Path(sys.argv[2])
    spr = sprites(cr.src)
    f = OUT_MAPS / "places.json"
    places = json.loads(f.read_text())
    have: set = set()
    for key, name in OUTDOOR.items():
        p = {"field": scene(cr, spr, name, "field", have)}
        town = TOWN.get(key)
        rooms = {}
        if town:
            for kind, suffix in (("center", "Pokecenter1F"), ("mart", "Mart"), ("gym", "Gym")):
                if (cr.src / "maps" / f"{town}{suffix}.asm").exists():
                    rooms[kind] = f"{town}{suffix}"
        rooms.update(INDOOR.get(key, {}))
        for kind, room in rooms.items():
            p[kind] = scene(cr, spr, room, kind, have)
        places[key] = p
    (OUT_MAPS / "hg").mkdir(parents=True, exist_ok=True)
    for key, name in ART.items():
        preview(hg, name).save(OUT_MAPS / "hg" / f"{name}.png", optimize=True)
        places[key] = {"field": {"art": f"hg/{name}"}}
    f.write_text(json.dumps(places, ensure_ascii=False, separators=(",", ":")))
    print("성도 장소", len(OUTDOOR) + len(ART), "사람", len(have))


if __name__ == "__main__":
    main()
