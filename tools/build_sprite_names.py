"""포켓몬 번호 → smogon/sprites 파일 이름 (모든 세대를 블랙·화이트 도트 스타일로 통일).

    git clone --depth 1 --filter=blob:none --no-checkout https://github.com/smogon/sprites
    curl -O https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/pokemon_species.csv
    python tools/build_sprite_names.py <smogon/sprites 경로> pokemon_species.csv

결과: game/sprite_names.json {번호: [앞모습, 뒷모습, 아이콘]}
- 앞·뒷모습: src/sprites/gen5 (1~5세대는 움직이는 .gif, 6세대부터는 .png). 없으면 "sd:<쇼다운 이름>"
- 아이콘: src/minisprites/pokemon/gen6 (PC·도감 같은 작은 칸)
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_SPECIES = 1025


def tree(repo: Path, path: str) -> set[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD", path],
                         capture_output=True, text=True, check=True).stdout
    return {line.rsplit("/", 1)[-1] for line in out.splitlines()}


def pick(files: set[str], *stems: str) -> str | None:
    for stem in stems:
        for ext in ("gif", "png"):
            if f"{stem}.{ext}" in files:
                return f"{stem}.{ext}"
    return None


def main():
    repo, species_csv = Path(sys.argv[1]), Path(sys.argv[2])
    sprites = tree(repo, "src/sprites/gen5")
    icons = tree(repo, "src/minisprites/pokemon/gen6")
    out, missing = {}, []
    for r in csv.DictReader(species_csv.open()):
        sid = int(r["id"])
        if sid > MAX_SPECIES:
            continue
        stem = "s" + r["identifier"].replace("-", "_")
        front, back = pick(sprites, stem), pick(sprites, f"{stem}-b")
        icon = pick(icons, stem, f"{stem}-vsmogon")
        if not (front and back and icon):
            missing.append(r["identifier"])
        sd = r["identifier"].replace("-", "")   # 쇼다운 이름 (smogon에 아직 없는 그림은 쇼다운에서)
        front, back = front or f"sd:{sd}", back or f"sd:{sd}"
        out[sid] = [front, back, icon]
    (ROOT / "game" / "sprite_names.json").write_text(json.dumps(out, separators=(",", ":")))
    print(len(out), "마리, smogon에 없는 그림:", missing)


if __name__ == "__main__":
    main()
