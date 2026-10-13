"""고를 수 있는 주인공 (역대 본편 주인공). 그림은 assets/trainers/<키>.png, 없으면 쇼다운에서 받는다."""

# (키, 이름, 세대, 나온 게임)
HEROES = [
    ("red", "레드", 1, "파이어레드"), ("leaf", "리프", 1, "리프그린"),
    ("ethan", "히비키", 2, "하트골드"), ("lyra", "코토네", 2, "소울실버"),
    ("brendan", "휘웅", 3, "에메랄드"), ("may", "봄이", 3, "에메랄드"),
    ("lucas", "광휘", 4, "플라티나"), ("dawn", "빛나", 4, "플라티나"),
    ("hilbert", "투야", 5, "블랙"), ("hilda", "투코", 5, "화이트"),
    ("nate", "쿄헤이", 5, "블랙2"), ("rosa", "메이", 5, "화이트2"),
    ("calem", "칼름", 6, "X"), ("serena", "세레나", 6, "Y"),
    ("elio", "선", 7, "썬"), ("selene", "문", 7, "문"),
    ("victor", "빅터", 8, "소드"), ("gloria", "글로리아", 8, "실드"),
    ("florian", "플로리안", 9, "스칼렛"), ("juliana", "줄리아나", 9, "바이올렛"),
]
DEFAULT = "red"
NAMES = {k: n for k, n, _, _ in HEROES}


def valid(key: str | None) -> str:
    return key if key in NAMES else DEFAULT


def of(run: dict | None) -> str:
    return valid((run or {}).get("hero"))
