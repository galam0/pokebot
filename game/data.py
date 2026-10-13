"""포켓몬 데이터 (game/pokedata.json.gz) 불러오기와 조회 도우미."""

import gzip
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "pokedata.json.gz"
with gzip.open(_PATH, "rt", encoding="utf-8") as _f:
    _RAW = json.load(_f)

SPECIES: dict[int, dict] = {int(k): v for k, v in _RAW["species"].items()}
MOVES: dict[int, dict] = {int(k): v for k, v in _RAW["moves"].items()}
ITEM_KO: dict[str, str] = _RAW.get("items", {})
_CHART: dict[tuple[int, int], float] = {
    tuple(map(int, k.split(","))): v for k, v in _RAW["chart"].items()
}

TACKLE = 33  # 배울 공격 기술이 없을 때 쓰는 기본 기술 (몸통박치기)

TYPE_KO = {
    1: "노말", 2: "격투", 3: "비행", 4: "독", 5: "땅", 6: "바위", 7: "벌레", 8: "고스트", 9: "강철",
    10: "불꽃", 11: "물", 12: "풀", 13: "전기", 14: "에스퍼", 15: "얼음", 16: "드래곤", 17: "악", 18: "페어리",
}
STAT_KO = ["HP", "공격", "방어", "특공", "특방", "스피드"]
TYPE_EN = {
    1: "normal", 2: "fighting", 3: "flying", 4: "poison", 5: "ground", 6: "rock", 7: "bug", 8: "ghost", 9: "steel",
    10: "fire", 11: "water", 12: "grass", 13: "electric", 14: "psychic", 15: "ice", 16: "dragon", 17: "dark", 18: "fairy",
}


def item_name(ident: str) -> str:
    return ITEM_KO.get(ident, ident)

SPRITE_BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"


def name(sid: int) -> str:
    return SPECIES[sid]["n"]


def types(sid: int) -> list[int]:
    return SPECIES[sid]["t"]


def bst(sid: int) -> int:
    return sum(SPECIES[sid]["s"])


def effectiveness(move_type: int, target_types: list[int]) -> float:
    mult = 1.0
    for t in target_types:
        mult *= _CHART.get((move_type, t), 1.0)
    return mult


def artwork(sid: int) -> str:
    return f"{SPRITE_BASE}/other/official-artwork/{sid}.png"


def sprite(sid: int) -> str:
    return f"{SPRITE_BASE}/{sid}.png"


def type_text(sid: int) -> str:
    return "/".join(TYPE_KO[t] for t in types(sid))


# ---------- 경험치 곡선 (growth_rates.csv 의 6가지 그룹) ----------
def total_exp(growth: int, n: int) -> int:
    if n <= 1:
        return 0
    n3 = n ** 3
    if growth == 1:                       # 느림
        return 5 * n3 // 4
    if growth == 2:                       # 보통
        return n3
    if growth == 3:                       # 빠름
        return 4 * n3 // 5
    if growth == 4:                       # 중간 느림
        return max(0, 6 * n3 // 5 - 15 * n * n + 100 * n - 140)
    if growth == 5:                       # 변동 (처음 빠르고 나중 매우 느림이 아닌, 처음 느리고 나중 매우 빠름)
        if n < 50:
            return n3 * (100 - n) // 50
        if n < 68:
            return n3 * (150 - n) // 100
        if n < 98:
            return n3 * ((1911 - 10 * n) // 3) // 500
        return n3 * (160 - n) // 100
    if growth == 6:                       # 요동
        if n < 15:
            return n3 * ((n + 1) // 3 + 24) // 50
        if n < 36:
            return n3 * (n + 14) // 50
        return n3 * (n // 2 + 32) // 50
    return n3
