"""성도 지방 데이터 (금·은·크리스탈을 바탕으로, 관동 챔피언이 된 뒤에 가는 두 번째 지방).

처음 들어올 때 파티·PC의 레벨을 START_LEVEL로 내리고, 레벨은 금·은과 비슷하게 맞췄어요 (체육관 9~40, 리그 40~50).
- 야생 포켓몬은 진화 전 모습으로 적어 두고, 만날 때 레벨에 맞게 진화시켜요 (region == "johto").
- 도로 트레이너는 그 장소의 야생 포켓몬으로 자동으로 만들어요 (auto: 트레이너 수).
- 장소 키는 관동과 겹치지 않게 'j_'로 시작하거나 성도 마을 이름을 써요.
"""

import random

from . import engine as E
from . import kanto as K

RIVAL = "라이벌 실버"
K.PRIZE.update({"스님": 32, "새조련사": 32, "기모노걸": 70, "닌자소년": 24, "용의 사도": 60, RIVAL: 40,
                "로켓단 간부": 80})

_CLASSES = ["반바지꼬마", "짧은치마", "곤충채집소년", "등산가", "피크닉걸", "캠프보이", "엘리트트레이너", "새조련사",
            "낚시꾼", "초능력자", "가라데왕", "아가씨"]

LOCATIONS = {
    # ---------- 연두마을 ~ 도라지시티 ----------
    "newbark": {"n": "연두마을", "kind": "town", "pos": (300, 150), "links": ["j_route29", "j_route27"],
                "home": True, "desc": "새로운 바람이 부는 마을. 공박사 연구소가 있어요.",
                "gift_choice": ([152, 155, 158], 5, "공박사: \"관동 챔피언이라니! 이 아이도 데려가 주겠니?\"")},
    "j_route29": {"n": "29번도로", "kind": "route", "pos": (262, 150), "links": ["newbark", "cherrygrove", "j_route45"],
                  "wild": [(16, 2, 5, 25), (161, 2, 5, 30), (19, 2, 4, 20), (163, 2, 5, 25)], "auto": 2},
    "cherrygrove": {"n": "무궁시티", "kind": "town", "pos": (226, 162), "links": ["j_route29", "j_route30"],
                    "center": True, "mart": True, "rival": "j1"},
    "j_route30": {"n": "30·31번도로", "kind": "route", "pos": (226, 122), "links": ["cherrygrove", "violet"],
                  "wild": [(10, 3, 7, 15), (13, 3, 7, 15), (165, 3, 7, 25), (167, 3, 7, 25), (60, 3, 7, 20)],
                  "auto": 3},
    "violet": {"n": "도라지시티", "kind": "town", "pos": (196, 84), "links": ["j_route30", "sprout", "j_route32", "j_route35"],
               "center": True, "mart": True, "gym": "zephyr"},
    "sprout": {"n": "모다피의탑", "kind": "building", "pos": (210, 60), "links": ["violet"],
               "wild": [(19, 4, 7, 50), (92, 5, 8, 50)],
               "trainers": [("스님", [(69, 5), (69, 5)]), ("스님", [(69, 6), (69, 7)]), ("스님", [(69, 7), (70, 9)])],
               "clear_gift": ("rare-candy", 2)},
    # ---------- 고동마을 ~ 금빛시티 ----------
    "j_route32": {"n": "32번도로", "kind": "route", "pos": (190, 130), "links": ["violet", "unioncave"], "need": 1,
                  "wild": [(23, 5, 9, 20), (179, 5, 9, 25), (187, 5, 9, 20), (194, 5, 9, 20), (41, 5, 9, 15)],
                  "auto": 3},
    "unioncave": {"n": "연결동굴", "kind": "cave", "pos": (164, 156), "links": ["j_route32", "azalea"], "need": 1,
                  "wild": [(74, 6, 10, 30), (41, 6, 10, 25), (27, 6, 10, 15), (194, 6, 10, 15), (95, 6, 10, 10),
                           (131, 7, 10, 5)],
                  "auto": 2},
    "azalea": {"n": "고동마을", "kind": "town", "pos": (128, 170), "links": ["unioncave", "slowpoke", "ilex"], "need": 1,
               "center": True, "mart": True, "gym": "hive", "rival": "j2"},
    "slowpoke": {"n": "야돈의우물", "kind": "cave", "pos": (104, 184), "links": ["azalea"], "need": 1,
                 "wild": [(79, 7, 11, 60), (41, 7, 11, 40)],
                 "trainers": [("로켓단 조무래기", [(19, 9), (41, 10)]), ("로켓단 조무래기", [(23, 11), (109, 11)]),
                              ("로켓단 간부", [(41, 12), (109, 12), (19, 14)])],
                 "clear_gift": ("rare-candy", 2)},
    "ilex": {"n": "너도밤나무숲", "kind": "route", "pos": (92, 146), "links": ["azalea", "goldenrod"], "need": 2,
             "wild": [(43, 6, 10, 20), (69, 6, 10, 20), (204, 6, 10, 20), (46, 6, 10, 15), (163, 6, 10, 15),
                      (10, 6, 10, 10)],
             "auto": 2, "legend": [(251, 50, "champ2")]},
    "goldenrod": {"n": "금빛시티", "kind": "town", "pos": (92, 108), "links": ["ilex", "j_route35", "radio"], "need": 2,
                  "center": True, "mart": True, "dept": True, "gym": "plain"},
    "radio": {"n": "라디오타워", "kind": "building", "pos": (66, 118), "links": ["goldenrod"], "need": 7, "rival": "j4",
              "trainers": [("로켓단 조무래기", [(110, 28), (89, 28)]), ("로켓단 조무래기", [(42, 29), (20, 29)]),
                           ("과학자", [(101, 30), (82, 30)]), ("로켓단 간부", [(24, 31), (110, 31), (42, 33)])],
              "clear_gift": ("master-ball", 1)},
    # ---------- 인주시티 ----------
    "j_route35": {"n": "35·36·37번도로", "kind": "route", "pos": (128, 80), "links": ["goldenrod", "violet", "ecruteak"],
                  "need": 2,
                  "wild": [(39, 12, 17, 15), (29, 12, 17, 15), (32, 12, 17, 15), (48, 12, 17, 15), (58, 12, 17, 10),
                           (37, 12, 17, 10), (185, 14, 17, 5), (123, 14, 17, 5), (127, 14, 17, 5), (209, 12, 17, 5)],
                  "auto": 3},
    "ecruteak": {"n": "인주시티", "kind": "town", "pos": (128, 48), "links": ["j_route35", "burned", "belltower",
                                                                            "j_route38", "j_route42"],
                 "need": 2, "center": True, "mart": True, "gym": "fog"},
    "burned": {"n": "불탄탑", "kind": "building", "pos": (106, 30), "links": ["ecruteak"], "need": 3, "rival": "j3",
               "wild": [(19, 13, 18, 35), (109, 13, 18, 35), (58, 13, 18, 15), (88, 13, 18, 15)],
               "legend": [(243, 40, None), (244, 40, None), (245, 40, None)]},
    "belltower": {"n": "방울탑", "kind": "building", "pos": (150, 24), "links": ["ecruteak"], "need": 8,
                  "legend": [(250, 50, None)]},
    # ---------- 담청시티·진청시티 ----------
    "j_route38": {"n": "38·39번도로", "kind": "route", "pos": (80, 50), "links": ["ecruteak", "olivine"], "need": 3,
                  "wild": [(19, 15, 19, 15), (52, 15, 19, 15), (241, 15, 19, 10), (241, 15, 19, 5), (128, 15, 19, 15),
                           (163, 15, 19, 15), (56, 15, 19, 15), (69, 15, 19, 10)],
                  "auto": 3},
    "olivine": {"n": "담청시티", "kind": "town", "pos": (40, 60), "links": ["j_route38", "lighthouse", "j_route40"],
                "need": 3, "center": True, "mart": True, "gym": "mineral"},
    "lighthouse": {"n": "반짝반짝등대", "kind": "building", "pos": (56, 36), "links": ["olivine"], "need": 3,
                   "trainers": [("선원", [(56, 20), (66, 20)]), ("새조련사", [(21, 21), (84, 21)]),
                                ("아가씨", [(39, 22), (35, 22)]), ("신사", [(58, 23), (77, 23)])]},
    "j_route40": {"n": "40·41번수로", "kind": "water", "pos": (30, 102), "links": ["olivine", "whirl", "cianwood"], "need": 4,
                  "wild": [(72, 18, 23, 40), (226, 20, 23, 10), (222, 18, 23, 15), (116, 18, 23, 15), (118, 18, 23, 10),
                           (170, 18, 23, 10)],
                  "auto": 3},
    "whirl": {"n": "소용돌이섬", "kind": "cave", "pos": (60, 128), "links": ["j_route40"], "need": 8,
              "wild": [(41, 22, 28, 25), (74, 22, 28, 20), (86, 22, 28, 20), (98, 22, 28, 20), (79, 22, 28, 15)],
              "legend": [(249, 50, None)]},
    "cianwood": {"n": "진청시티", "kind": "town", "pos": (16, 140), "links": ["j_route40"], "need": 4,
                 "center": True, "mart": True, "gym": "storm"},
    # ---------- 황토마을 ~ 검은먹시티 ----------
    "j_route42": {"n": "42·43번도로", "kind": "route", "pos": (168, 50), "links": ["ecruteak", "mahogany"], "need": 4,
                  "wild": [(56, 16, 22, 20), (21, 16, 22, 20), (179, 16, 22, 20), (203, 16, 22, 15), (118, 16, 22, 15),
                           (41, 16, 22, 10)],
                  "auto": 3},
    "mahogany": {"n": "황토마을", "kind": "town", "pos": (204, 42), "links": ["j_route42", "ragelake", "jhideout", "j_route44"],
                 "need": 4, "center": True, "mart": True, "gym": "glacier"},
    "ragelake": {"n": "분노의호수", "kind": "water", "pos": (204, 18), "links": ["mahogany"], "need": 4,
                 "wild": [(129, 15, 23, 60), (130, 23, 25, 15), (118, 22, 24, 15), (234, 22, 24, 10)],
                 "legend": [(130, 30, None)]},
    "jhideout": {"n": "로켓단 아지트", "kind": "building", "pos": (232, 26), "links": ["mahogany"], "need": 5,
                 "trainers": [("로켓단 조무래기", [(109, 23), (41, 23)]), ("로켓단 조무래기", [(19, 24), (23, 24)]),
                              ("과학자", [(81, 25), (100, 25), (101, 26)]), ("로켓단 간부", [(42, 26), (110, 27), (24, 28)])],
                 "clear_gift": ("rare-candy", 3)},
    "j_route44": {"n": "44번도로·얼음샛길", "kind": "cave", "pos": (244, 60), "links": ["mahogany", "blackthorn"], "need": 7,
                  "wild": [(220, 24, 30, 25), (215, 24, 30, 15), (225, 24, 30, 10), (124, 24, 30, 10), (41, 24, 30, 20),
                           (86, 24, 30, 20)],
                  "auto": 3},
    "blackthorn": {"n": "검은먹시티", "kind": "town", "pos": (280, 64), "links": ["j_route44", "dragonsden", "j_route45"],
                   "need": 7, "center": True, "mart": True, "gym": "rising"},
    "dragonsden": {"n": "용의굴", "kind": "cave", "pos": (306, 40), "links": ["blackthorn"], "need": 7,
                   "wild": [(147, 22, 25, 45), (116, 22, 25, 25), (129, 15, 21, 30)],
                   "trainers": [("용의 사도", [(147, 30), (148, 32)]), ("용의 사도", [(148, 33), (148, 35)])]},
    "j_route45": {"n": "45·46번도로", "kind": "route", "pos": (290, 104), "links": ["blackthorn", "j_route29"], "need": 7,
                  "wild": [(74, 28, 32, 25), (207, 28, 32, 20), (231, 28, 32, 20), (227, 30, 32, 10), (22, 28, 32, 15),
                           (246, 25, 30, 10)],
                  "auto": 3},
    # ---------- 석영고원 쪽 ----------
    "j_route27": {"n": "26·27번도로", "kind": "route", "pos": (314, 178), "links": ["newbark", "plateau"],
                  "desc": "석영고원과 성도를 잇는 길. 동쪽으로 가면 연두마을이에요.",
                  "rival": "j5", "rival_need": 8},
}
for _k, _L in LOCATIONS.items():
    _L["region"] = "johto"
    _L["champ"] = True          # 관동 챔피언이 된 뒤에만
    _L.setdefault("bg", {"town": "도시", "route": "풀숲", "cave": "동굴", "building": "유적", "water": "해변"}[_L["kind"]])
LOCATIONS["ilex"]["bg"] = "숲"
LOCATIONS["j_route44"]["bg"] = "설원"
LOCATIONS["dragonsden"]["bg"] = "하늘탑"
LOCATIONS["radio"]["bg"] = "도시"


def _auto_trainers():
    """도로 트레이너: 그 장소의 야생 포켓몬으로 팀을 만든다 (항상 같은 팀이 나오게 장소 이름으로 시드)"""
    for key, L in LOCATIONS.items():
        n = L.pop("auto", 0)
        if not n:
            continue
        r = random.Random(f"johto:{key}")
        wild = L["wild"]
        out = []
        for _ in range(n):
            team = []
            for _ in range(r.choice([2, 2, 3, 3, 4])):
                sid, lo, hi, _w = r.choices(wild, weights=[w[3] for w in wild])[0]
                lv = min(E.MAX_LEVEL, hi + r.randint(0, 2))
                team.append((E._evolve_for_level(sid, lv, r), lv))
            out.append((r.choice(_CLASSES), team))
        L["trainers"] = L.get("trainers", []) + out


_auto_trainers()

GYMS = {
    "zephyr": {"n": "도라지시티 체육관", "leader": "비상", "badge": "윙배지", "type": 3, "tm": 19,
               "junior": ("새조련사", [(16, 6), (16, 7)]), "team": [(16, 7), (17, 9)],
               "line": "비행 포켓몬의 진짜 힘을 보여 주마! 아버지께 물려받은 이 날개로!"},
    "hive": {"n": "고동마을 체육관", "leader": "호일", "badge": "인섹트배지", "type": 7, "tm": 404, "need": 1,
             "junior": ("곤충채집소년", [(11, 12), (14, 12)]), "team": [(11, 14), (14, 14), (123, 16)],
             "line": "벌레 포켓몬이라고 얕보면 큰코다칠걸!"},
    "plain": {"n": "금빛시티 체육관", "leader": "꼭두", "badge": "레귤러배지", "type": 1, "tm": 304, "need": 2,
              "junior": ("짧은치마", [(35, 16), (39, 17)]), "team": [(35, 18), (241, 20)],
              "line": "귀여운 포켓몬이 좋아? 나도 좋아! 그래도 봐주진 않을 거야!"},
    "fog": {"n": "인주시티 체육관", "leader": "유빈", "badge": "팬텀배지", "type": 8, "tm": 247, "need": 3,
            "junior": ("무당", [(92, 20), (93, 21)]), "team": [(92, 21), (93, 21), (93, 23), (94, 25)],
            "line": "전설의 포켓몬을 만나기 위해 수행해 왔어. 네 실력도 보여 줘."},
    "storm": {"n": "진청시티 체육관", "leader": "사도", "badge": "쇼크배지", "type": 2, "tm": 370, "need": 4,
              "junior": ("가라데왕", [(66, 26), (107, 27)]), "team": [(57, 27), (62, 30)],
              "line": "우오오! 근성으로 덤벼라!"},
    "mineral": {"n": "담청시티 체육관", "leader": "규리", "badge": "스틸배지", "type": 9, "tm": 231, "need": 5,
                "junior": ("신사", [(81, 29), (25, 29)]), "team": [(81, 30), (81, 30), (208, 35)],
                "line": "...단단한 강철 포켓몬과 함께라면 지지 않아요."},
    "glacier": {"n": "황토마을 체육관", "leader": "류옹", "badge": "아이스배지", "type": 15, "tm": 59, "need": 6,
                "junior": ("스님", [(86, 27), (220, 28)]), "team": [(86, 27), (87, 29), (221, 31)],
                "line": "50년 동안 얼음과 함께 살아온 이 늙은이의 힘을 보거라."},
    "rising": {"n": "검은먹시티 체육관", "leader": "이향", "badge": "라이징배지", "type": 16, "tm": 406, "need": 7,
               "junior": ("용의 사도", [(147, 34), (148, 36)]), "team": [(148, 37), (148, 37), (148, 37), (230, 40)],
               "line": "나는 세계 최고의 드래곤 조련사야! 각오는 됐겠지?"},
}
GYM_ORDER = ["zephyr", "hive", "plain", "fog", "storm", "mineral", "glacier", "rising"]

ELITE_FOUR = [
    {"n": "사천왕 일목", "cls": "사천왕", "type": 14, "team": [(178, 40), (124, 41), (103, 41), (80, 41), (178, 42)],
     "line": "나는 초능력 포켓몬과 함께 세계를 돌며 수행해 왔다."},
    {"n": "사천왕 독수", "cls": "사천왕", "type": 4, "team": [(168, 40), (49, 41), (205, 43), (89, 42), (169, 44)],
     "line": "후후후... 관동 체육관 관장이었던 나를 기억하나?"},
    {"n": "사천왕 시바", "cls": "사천왕", "type": 2, "team": [(237, 42), (107, 42), (106, 42), (95, 43), (68, 46)],
     "line": "다시 만났군! 더 단련한 내 주먹을 받아라!"},
    {"n": "사천왕 카렌", "cls": "사천왕", "type": 17, "team": [(197, 42), (45, 42), (94, 45), (198, 44), (229, 47)],
     "line": "강한 포켓몬, 약한 포켓몬... 그건 사람이 정하는 거야."},
]
CHAMPION = {"n": "챔피언 목호", "cls": "챔피언", "type": 16,
            "team": [(130, 44), (149, 47), (6, 46), (142, 46), (149, 47), (149, 50)],
            "line": "기다리고 있었다. 성도의 챔피언으로서 상대해 주지!"}

# 라이벌 실버: 내 첫 스타팅 타입에 유리한 성도 스타팅을 데려온다
RIVAL_LINE = {
    "j1": "...너, 관동에서 왔다며? 약한 녀석은 흥미 없어. 내 포켓몬의 힘을 확인해 볼까.",
    "j2": "체육관 배지를 모으고 있나? 그런 건 강해지는 데 아무 의미 없어.",
    "j3": "전설의 포켓몬을 잡으러 왔다! 방해하면 너부터 쓰러뜨린다!",
    "j4": "로켓단 따위... 무리 지어야만 강한 척하는 녀석들은 싫어. 너도 마찬가지야!",
    "j5": "나는 깨달았다. 포켓몬을 믿지 않으면 강해질 수 없다는 걸. 마지막 승부다!",
}


def rival_team(stage: str, line: tuple[int, int, int]) -> list[tuple[int, int]]:
    a, b, c = line
    return {
        "j1": [(a, 5)],
        "j2": [(92, 14), (41, 16), (b, 16)],
        "j3": [(41, 20), (95, 18), (92, 20), (b, 22)],
        "j4": [(42, 30), (95, 29), (93, 30), (64, 30), (81, 28), (c, 32)],
        "j5": [(42, 38), (95, 36), (82, 37), (93, 37), (64, 38), (c, 40)],
    }[stage]


START_LEVEL = 8                                         # 처음 들어올 때 파티·PC를 이 레벨로
LEVEL_CAPS = [12, 18, 22, 27, 32, 37, 37, 42, 52]       # 성도 배지 수별 (관동 챔피언 다음)
BADGE_RGB = [(160, 176, 200), (232, 120, 152), (240, 208, 72), (152, 96, 176), (176, 120, 72), (200, 208, 216),
             (128, 200, 232), (56, 80, 168)]
