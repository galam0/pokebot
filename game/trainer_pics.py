"""배틀 전에 나오는 상대 트레이너 그림 (assets/battle/<파일>.png, tools/build_trainer_pics.py로 만든다).

- fr_: 파이어레드 (관동·성도의 일반 트레이너, 관동 관장·사천왕·라이벌)
- em_: 에메랄드 (호연 트레이너 전부)
- hg_: 하트골드 (성도의 이름 있는 인물: 관장·사천왕·챔피언·라이벌·로켓단 간부)
"""

FR_CLASS = {
    "반바지꼬마": "youngster", "짧은치마": "lass", "곤충채집소년": "bug_catcher", "등산가": "hiker",
    "슈퍼너드": "super_nerd", "로켓단 조무래기": "rocket_grunt_m", "캠프보이": "camper", "피크닉걸": "picnicker",
    "선원": "sailor", "신사": "gentleman", "엔지니어": "engineer", "도박사": "gamer", "무당": "channeler",
    "초능력자": "psychic_m", "폭주족": "biker", "낚시꾼": "fisherman", "과학자": "scientist", "좀도둑": "burglar",
    "수영팬티소년": "swimmer_m", "비키니아가씨": "swimmer_f", "엘리트트레이너": "cool_trainer_m",
    "포켓몬매니아": "pokemaniac", "가라데왕": "black_belt", "저글러": "juggler", "아가씨": "beauty",
    "새조련사": "bird_keeper", "용의 사도": "cool_trainer_m", "로켓단 보스 비주기": "leader_giovanni",
}
EM_CLASS = {
    "반바지꼬마": "youngster", "짧은치마": "lass", "곤충채집소년": "bug_catcher", "등산가": "hiker",
    "캠프보이": "camper", "피크닉걸": "picnicker", "무당": "hex_maniac", "초능력자": "psychic_m",
    "엘리트트레이너": "cooltrainer_m", "가라데왕": "black_belt", "새조련사": "bird_keeper", "어부": "fisherman",
    "드래곤조련사": "dragon_tamer", "배틀걸": "battle_girl", "엔지니어": "expert_m", "비키니아가씨": "swimmer_f",
    "마그마단 조무래기": "magma_grunt_m", "아쿠아단 조무래기": "aqua_grunt_m",
    "마그마단 리더 마적": "magma_leader_maxie", "아쿠아단 리더 아강": "aqua_leader_archie",
}
HG_CLASS = {"스님": "Sage", "로켓단 간부": "Proton"}   # 파이어레드에 없는 성도 분류
NAMED = {   # (지방, 배틀 이름) → 파일
    ("kanto", "관장 웅"): "fr_leader_brock", ("kanto", "관장 이슬"): "fr_leader_misty",
    ("kanto", "관장 마티스"): "fr_leader_lt_surge", ("kanto", "관장 민화"): "fr_leader_erika",
    ("kanto", "관장 독수"): "fr_leader_koga", ("kanto", "관장 초련"): "fr_leader_sabrina",
    ("kanto", "관장 강연"): "fr_leader_blaine", ("kanto", "관장 비주기"): "fr_leader_giovanni",
    ("kanto", "사천왕 칸나"): "fr_elite_four_lorelei", ("kanto", "사천왕 시바"): "fr_elite_four_bruno",
    ("kanto", "사천왕 국화"): "fr_elite_four_agatha", ("kanto", "사천왕 목호"): "fr_elite_four_lance",
    ("kanto", "챔피언 그린"): "fr_champion_rival",
    ("johto", "관장 비상"): "hg_Falkner", ("johto", "관장 호일"): "hg_Bugsy", ("johto", "관장 꼭두"): "hg_Whitney",
    ("johto", "관장 유빈"): "hg_Morty", ("johto", "관장 사도"): "hg_Chuck", ("johto", "관장 규리"): "hg_Jasmine",
    ("johto", "관장 류옹"): "hg_Pryce", ("johto", "관장 이향"): "hg_Clair",
    ("johto", "사천왕 일목"): "hg_Will", ("johto", "사천왕 독수"): "hg_Koga", ("johto", "사천왕 시바"): "hg_Bruno",
    ("johto", "사천왕 카렌"): "hg_Karen", ("johto", "챔피언 목호"): "hg_Lance", ("johto", "라이벌 실버"): "hg_Silver",
    ("hoenn", "관장 원규"): "em_leader_roxanne", ("hoenn", "관장 철구"): "em_leader_brawly",
    ("hoenn", "관장 암페어"): "em_leader_wattson", ("hoenn", "관장 민지"): "em_leader_flannery",
    ("hoenn", "관장 종길"): "em_leader_norman", ("hoenn", "관장 은송"): "em_leader_winona",
    ("hoenn", "관장 풍&란"): "em_leader_tate_and_liza", ("hoenn", "관장 아단"): "em_leader_juan",
    ("hoenn", "사천왕 혁진"): "em_elite_four_sidney", ("hoenn", "사천왕 회연"): "em_elite_four_phoebe",
    ("hoenn", "사천왕 미혜"): "em_elite_four_glacia", ("hoenn", "사천왕 권수"): "em_elite_four_drake",
    ("hoenn", "챔피언 성호"): "em_steven", ("hoenn", "라이벌 봄이"): "em_may",
}
# 주인공 뒷모습 (파이어레드·에메랄드에 있는 넷, 나머지는 남녀에 맞춰)
BACK = {"red": "fr_back_red", "leaf": "fr_back_leaf", "brendan": "em_back_brendan", "may": "em_back_may"}
FEMALE = {"leaf", "lyra", "may", "dawn", "hilda", "rosa", "serena", "selene", "gloria", "juliana"}


def opponent(region: str, battle: dict) -> str | None:
    """배틀 정보(run["battle"])로 상대 트레이너 그림 파일 이름"""
    name, cls = battle.get("name", ""), battle.get("cls", "")
    if (region, name) in NAMED:
        return NAMED[(region, name)]
    if battle.get("kind") == "rival" and region == "kanto":
        return "fr_rival_early" if battle.get("stage", 1) <= 4 else "fr_rival_late"
    if region == "hoenn" and cls in EM_CLASS:
        return "em_" + EM_CLASS[cls]
    if cls in HG_CLASS:
        return "hg_" + HG_CLASS[cls]
    if cls in FR_CLASS:
        return "fr_" + FR_CLASS[cls]
    return None


def player_back(hero: str) -> str:
    return BACK.get(hero) or ("fr_back_leaf" if hero in FEMALE else "fr_back_red")


def all_files() -> set[str]:
    files = set(NAMED.values()) | set(BACK.values()) | {"fr_rival_early", "fr_rival_late"}
    files |= {"fr_" + v for v in FR_CLASS.values()} | {"em_" + v for v in EM_CLASS.values()}
    files |= {"hg_" + v for v in HG_CLASS.values()}
    return files
