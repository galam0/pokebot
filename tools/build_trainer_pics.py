"""배틀 전에 나오는 트레이너 그림을 assets/battle/ 에 모은다 (game/trainer_pics.py에 적힌 것만).

    pokefirered: git sparse-checkout add graphics/trainers
    pokeemerald: git sparse-checkout add graphics/trainers
    smogon/sprites: 하트골드 트레이너 (src/_uncategorized/canonical/trainers/gen4/heartgold-soulsilver)
    pokeplatinum: res/graphics/battle/trainer_backs (광휘·빛나 뒷모습)
    python tools/build_trainer_pics.py <pokefirered> <pokeemerald> <smogon/sprites> <pokeplatinum>

팔레트 0번(배경색)은 투명으로 바꾸고, 뒷모습은 첫 칸(64x64)만 쓴다.
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from game import trainer_pics as T  # noqa: E402

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
    fr, em, smogon, pt = map(Path, sys.argv[1:5])
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sorted(T.all_files()):
        src, _, rest = name.partition("_")
        if rest.startswith("back_") and src == "pt":   # 플라티나 뒷모습 (80x80 다섯 칸 중 첫 칸)
            im = gba(pt / f"res/graphics/battle/trainer_backs/{rest.removeprefix('back_')}_dp.png")
            im = im.crop((0, 0, 80, 80))
        elif rest.startswith("back_"):
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
    print(len(T.all_files()), "장")


if __name__ == "__main__":
    main()
