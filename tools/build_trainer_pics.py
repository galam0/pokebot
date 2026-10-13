"""배틀 전에 나오는 트레이너 그림을 assets/battle/ 에 모은다 (game/trainer_pics.py에 적힌 것만).

    pokefirered: git sparse-checkout add graphics/trainers
    pokeemerald: git sparse-checkout add graphics/trainers
    smogon/sprites: 하트골드 트레이너 (src/_uncategorized/canonical/trainers/gen4/heartgold-soulsilver)
    python tools/build_trainer_pics.py <pokefirered> <pokeemerald> <smogon/sprites>

팔레트 0번(배경색)은 투명으로 바꾸고, 뒷모습은 첫 칸(64x64)만 쓴다.
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from game import trainer_pics as T  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
from build_places import HERO_COLORS, TONE, _shade  # noqa: E402

# 뒷모습(64x64)의 (팔레트 번호, 줄 범위) → 부위 (걷는 그림과 같은 주인공 색을 쓴다)
RED_BACK = {"hat": ({11: "main", 12: "dark"}, range(0, 30)), "brim": ({9: "light", 10: "main"}, range(0, 30)),
            "hair": ({4: "main", 8: "dark"}, range(0, 40)), "top": ({5: "light", 6: "main", 11: "main", 12: "dark",
                                                                    9: "light", 10: "main"}, range(40, 64))}
LEAF_BACK = {"hat": ({9: "light", 10: "main", 6: "edge"}, range(0, 31)), "ribbon": ({11: "main", 12: "dark"}, range(0, 31)),
             "hair": ({4: "main", 8: "dark", 1: "light"}, range(0, 64)), "top": ({6: "main", 7: "light"}, range(40, 64))}

OUT = ROOT / "assets" / "battle"
HG = "src/_uncategorized/canonical/trainers/gen4/heartgold-soulsilver"


def gba(path: Path, back: bool = False) -> Image.Image:
    src = Image.open(path)
    im = src.convert("RGBA")
    if src.mode == "P":   # 팔레트 0번 = 투명
        idx = src.load()
        px = im.load()
        for y in range(im.height):
            for x in range(im.width):
                if idx[x, y] == 0:
                    px[x, y] = (0, 0, 0, 0)
    return im.crop((0, 0, 64, 64)) if back else im


def main():
    fr, em, smogon = map(Path, sys.argv[1:4])
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sorted(T.all_files()):
        src, _, rest = name.partition("_")
        if rest.startswith("back_"):
            base = rest.removeprefix("back_")
            f = (fr / f"graphics/trainers/back_pics/{base}_back_pic.png" if src == "fr"
                 else em / f"graphics/trainers/back_pics/{base}.png")
            im = gba(f, back=True)
        elif src == "fr":
            im = gba(fr / f"graphics/trainers/front_pics/{rest}_front_pic.png")
        elif src == "em":
            im = gba(em / f"graphics/trainers/front_pics/{rest}.png")
        else:   # 하트골드 (smogon/sprites, 이미 투명 배경)
            subprocess.run(["git", "-C", str(smogon), "checkout", "HEAD", "--", f"{HG}/{rest}.png"], check=True)
            im = Image.open(smogon / HG / f"{rest}.png").convert("RGBA")
        bbox = im.getbbox()
        im = im.crop(bbox) if bbox else im
        im.save(OUT / f"{name}.png")
    hero_backs(fr)
    print(len(T.all_files()), "장 + 주인공 뒷모습", len(HERO_COLORS))


def hero_backs(fr: Path):
    """원본 뒷모습이 없는 주인공 → assets/battle/hero_back_<키>.png (레드·리프 뒷모습의 색만 바꿈)"""
    for key, (base, colors) in HERO_COLORS.items():
        f = fr / f"graphics/trainers/back_pics/{'red' if base == 'red' else 'leaf'}_back_pic.png"
        parts = RED_BACK if base == "red" else LEAF_BACK
        src = Image.open(f)
        idx = src.load()
        im = gba(f, back=True)
        px = im.load()
        for y in range(64):
            for x in range(64):
                i = idx[x, y]
                if i == 0:
                    continue
                for part, (index_tone, rows) in parts.items():
                    if part in colors and i in index_tone and y in rows:
                        px[x, y] = _shade(colors[part], TONE[index_tone[i]]) + (255,)
                        break
        bbox = im.getbbox()
        (im.crop(bbox) if bbox else im).save(OUT / f"hero_back_{key}.png")


if __name__ == "__main__":
    main()
