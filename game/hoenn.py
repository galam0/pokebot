"""호연 지방 데이터 (루비·사파이어·에메랄드를 바탕으로, 성도 챔피언이 된 뒤에 가는 세 번째 지방).

담청시티 항구에서 배를 타고 미로마을로 가요. 처음 들어올 때 파티·PC의 레벨을 START_LEVEL로 내려요.
레벨은 루비·사파이어와 비슷하게 (체육관 12~43, 사천왕 46~55, 챔피언 성호 58).
- 야생 포켓몬은 진화 전 모습으로 적고, 만날 때 레벨에 맞게 진화시켜요.
- 도로 트레이너는 그 장소의 야생 포켓몬으로 자동으로 만들어요 (auto: 트레이너 수).
"""

import random

from . import engine as E
from . import kanto as K

RIVAL = "라이벌 봄이"
K.PRIZE.update({"마그마단 조무래기": 30, "아쿠아단 조무래기": 30, "마그마단 리더 마적": 100, "아쿠아단 리더 아강": 100,
                RIVAL: 40, "어부": 36, "등산객": 36, "배틀걸": 40, "드래곤조련사": 60})

_CLASSES = ["반바지꼬마", "짧은치마", "곤충채집소년", "등산가", "피크닉걸", "캠프보이", "엘리트트레이너", "새조련사",
            "어부", "초능력자", "가라데왕", "배틀걸"]

LOCATIONS = {
    # ---------- 미로마을 ~ 금탄도시 ----------
    "h_ferry": {"n": "연락선 타이드호", "kind": "building", "bg": "해변", "pos": (128, 184), "links": ["olivine", "littleroot"],
                "desc": "담청시티와 호연 지방을 잇는 배. 바닷바람이 시원해요."},
    "littleroot": {"n": "미로마을", "kind": "town", "pos": (96, 164), "links": ["h_ferry", "h_route101"], "home": True,
                   "desc": "아직 아무것도 물들지 않은 마을. 털보박사 연구소가 있어요.",
                   "gift_choice": ([252, 255, 258], 5, "털보박사: \"멀리서 왔구나! 호연의 포켓몬도 한 마리 데려가렴.\"")},
    "h_route101": {"n": "101·103번도로", "kind": "route", "pos": (96, 138), "links": ["littleroot", "oldale"], "rival": "h1",
                   "wild": [(263, 2, 4, 35), (265, 2, 4, 35), (261, 2, 4, 30)], "auto": 2},
    "oldale": {"n": "고도마을", "kind": "town", "pos": (96, 114), "links": ["h_route101", "h_route102"],
               "center": True, "mart": True},
    "h_route102": {"n": "102·104번도로", "kind": "route", "pos": (60, 118), "links": ["oldale", "petalburg"],
                   "wild": [(263, 3, 5, 25), (261, 3, 5, 20), (265, 3, 5, 15), (270, 3, 5, 15), (273, 3, 5, 15),
                            (280, 4, 5, 10)], "auto": 3},
    "petalburg": {"n": "등화도시", "kind": "town", "pos": (34, 126), "links": ["h_route102", "h_woods", "h_boat"],
                  "center": True, "mart": True, "gym": "balance"},
    "h_woods": {"n": "등화숲", "kind": "route", "bg": "숲", "pos": (34, 96), "links": ["petalburg", "rustboro"],
                "wild": [(265, 5, 6, 30), (285, 5, 6, 25), (287, 5, 6, 15), (276, 5, 6, 15), (263, 5, 6, 15)],
                "trainers": [("아쿠아단 조무래기", [(261, 9)])], "auto": 1},
    "rustboro": {"n": "금탄도시", "kind": "town", "pos": (34, 64), "links": ["h_woods", "h_tunnel"],
                 "center": True, "mart": True, "gym": "stone"},
    "h_tunnel": {"n": "금잔터널", "kind": "cave", "pos": (74, 62), "links": ["rustboro", "verdanturf"], "need": 3,
                 "wild": [(293, 8, 11, 100)],
                 "trainers": [("마그마단 조무래기", [(261, 18), (322, 18)])]},
    # ---------- 무로마을 ~ 보라시티 ----------
    "h_boat": {"n": "104·106번수로 (뱃사공)", "kind": "water", "pos": (20, 160), "links": ["petalburg", "dewford"], "need": 1,
               "wild": [(72, 6, 12, 40), (278, 6, 12, 40), (129, 5, 10, 20)], "auto": 2},
    "dewford": {"n": "무로마을", "kind": "town", "pos": (34, 184), "links": ["h_boat", "granite", "h_route109"], "need": 1,
                "center": True, "mart": True, "gym": "knuckle"},
    "granite": {"n": "바위동굴", "kind": "cave", "pos": (8, 184), "links": ["dewford"], "need": 1,
                "wild": [(41, 7, 10, 30), (304, 7, 10, 25), (293, 7, 10, 20), (296, 8, 10, 15), (302, 9, 10, 10)],
                "auto": 2},
    "h_route109": {"n": "109번수로", "kind": "water", "pos": (88, 186), "links": ["dewford", "slateport"], "need": 2,
                   "wild": [(72, 10, 14, 35), (278, 10, 14, 30), (320, 10, 14, 25), (129, 10, 14, 10)], "auto": 3},
    "slateport": {"n": "잿빛도시", "kind": "town", "pos": (150, 176), "links": ["h_route109", "h_route110"], "need": 2,
                  "center": True, "mart": True},
    "h_route110": {"n": "110번도로", "kind": "route", "pos": (150, 146), "links": ["slateport", "mauville"], "need": 2,
                   "rival": "h2",
                   "wild": [(263, 12, 14, 20), (81, 12, 14, 15), (316, 12, 14, 15), (309, 12, 14, 20), (311, 12, 14, 10),
                            (312, 12, 14, 10), (278, 12, 14, 10)], "auto": 3},
    "mauville": {"n": "보라시티", "kind": "town", "pos": (150, 112), "links": ["h_route110", "verdanturf", "h_route111",
                                                                          "h_route119"],
                 "need": 2, "center": True, "mart": True, "gym": "dynamo"},
    "verdanturf": {"n": "잔디마을", "kind": "town", "pos": (110, 90), "links": ["mauville", "h_tunnel"], "need": 2,
                   "center": True, "mart": True},
    # ---------- 용암마을·단풍마을 ----------
    "h_route111": {"n": "111·112번도로·사막", "kind": "route", "bg": "유적", "pos": (150, 76),
                   "links": ["mauville", "chimney", "fallarbor"], "need": 3,
                   "wild": [(27, 19, 22, 25), (328, 19, 22, 25), (331, 19, 22, 25), (343, 19, 22, 25)], "auto": 3},
    "chimney": {"n": "굴뚝산·울퉁불퉁산길", "kind": "cave", "bg": "화산", "pos": (122, 46), "links": ["h_route111", "lavaridge"],
                "need": 3,
                "wild": [(322, 20, 24, 35), (74, 20, 24, 25), (325, 20, 24, 20), (66, 20, 24, 20)],
                "trainers": [("마그마단 조무래기", [(262, 22), (322, 22)]), ("마그마단 조무래기", [(41, 23), (218, 23)]),
                             ("마그마단 리더 마적", [(262, 24), (42, 24), (323, 25)])],
                "clear_gift": ("rare-candy", 2)},
    "lavaridge": {"n": "용암마을", "kind": "town", "bg": "화산", "pos": (92, 36), "links": ["chimney"], "need": 3,
                  "center": True, "mart": True, "gym": "heat"},
    "fallarbor": {"n": "단풍마을", "kind": "town", "pos": (176, 34), "links": ["h_route111", "meteor"], "need": 3,
                  "center": True, "mart": True},
    "meteor": {"n": "유성의폭포", "kind": "cave", "pos": (206, 20), "links": ["fallarbor"], "need": 3,
               "wild": [(41, 24, 30, 35), (337, 24, 30, 20), (338, 24, 30, 20), (129, 20, 25, 15), (371, 25, 30, 10)],
               "auto": 2},
    # ---------- 검방울시티 ~ 해안시티 ----------
    "h_route119": {"n": "118·119번도로", "kind": "route", "pos": (192, 108), "links": ["mauville", "fortree"], "need": 5,
                   "rival": "h3",
                   "wild": [(263, 25, 27, 20), (357, 25, 27, 10), (43, 25, 27, 20), (352, 25, 27, 10), (276, 25, 27, 20),
                            (318, 25, 27, 20)], "auto": 3},
    "fortree": {"n": "검방울시티", "kind": "town", "pos": (204, 74), "links": ["h_route119", "h_route120"], "need": 5,
                "center": True, "mart": True, "gym": "feather"},
    "h_route120": {"n": "120·121번도로", "kind": "route", "pos": (242, 74), "links": ["fortree", "lilycove", "pyre"], "need": 6,
                   "wild": [(352, 26, 29, 15), (313, 26, 29, 10), (314, 26, 29, 10), (43, 26, 29, 15), (335, 26, 29, 15),
                            (336, 26, 29, 15), (359, 27, 29, 5), (278, 26, 29, 15)], "auto": 3},
    "pyre": {"n": "송화산", "kind": "cave", "bg": "유적", "pos": (238, 104), "links": ["h_route120"], "need": 6,
             "wild": [(353, 27, 30, 45), (355, 27, 30, 45), (358, 28, 30, 10)],
             "trainers": [("무당", [(353, 28), (355, 28)]), ("무당", [(354, 29)]),
                          ("아쿠아단 조무래기", [(318, 29), (261, 29)])]},
    "lilycove": {"n": "해안시티", "kind": "town", "pos": (276, 66), "links": ["h_route120", "aquahideout", "h_route124"],
                 "need": 6, "center": True, "mart": True, "dept": True, "rival": "h4"},
    "aquahideout": {"n": "아쿠아단 아지트", "kind": "building", "bg": "도시", "pos": (300, 44), "links": ["lilycove"], "need": 6,
                    "trainers": [("아쿠아단 조무래기", [(318, 30), (41, 30)]), ("아쿠아단 조무래기", [(262, 31), (319, 31)]),
                                 ("아쿠아단 리더 아강", [(262, 33), (42, 33), (319, 35)])],
                    "clear_gift": ("master-ball", 1)},
    # ---------- 이끼시티 ~ 루네시티 ----------
    "h_route124": {"n": "124~126번수로", "kind": "water", "pos": (288, 100), "links": ["lilycove", "mossdeep", "sootopolis"],
                   "need": 6,
                   "wild": [(72, 30, 35, 30), (278, 30, 35, 20), (320, 30, 35, 20), (366, 30, 35, 10), (369, 32, 35, 5),
                            (222, 30, 35, 15)], "auto": 3},
    "mossdeep": {"n": "이끼시티", "kind": "town", "pos": (308, 128), "links": ["h_route124", "seafloor"], "need": 6,
                 "center": True, "mart": True, "gym": "mind"},
    "seafloor": {"n": "해저동굴", "kind": "cave", "pos": (310, 158), "links": ["mossdeep"], "need": 7,
                 "wild": [(41, 35, 40, 50), (72, 35, 40, 50)],
                 "trainers": [("마그마단 조무래기", [(262, 38), (323, 38)]), ("아쿠아단 조무래기", [(319, 38), (42, 38)])]},
    "sootopolis": {"n": "루네시티", "kind": "town", "pos": (258, 136), "links": ["h_route124", "origin", "h_route128"],
                   "need": 7, "center": True, "mart": True, "gym": "rain"},
    "origin": {"n": "각성의 사당", "kind": "cave", "pos": (234, 152), "links": ["sootopolis"], "need": 7,
               "wild": [(41, 38, 42, 60), (302, 38, 42, 20), (303, 38, 42, 20)],
               "legend": [(382, 45, None), (383, 45, None)]},
    # ---------- 황금마을·그랜드시티 ----------
    "h_route128": {"n": "128~131번수로", "kind": "water", "pos": (226, 176), "links": ["sootopolis", "pacifidlog", "h_victory"],
                   "need": 8,
                   "wild": [(72, 36, 42, 30), (279, 36, 42, 20), (320, 36, 42, 20), (369, 38, 42, 10), (222, 36, 42, 20)],
                   "auto": 3},
    "pacifidlog": {"n": "황금마을", "kind": "town", "bg": "해변", "pos": (186, 160), "links": ["h_route128", "skypillar", "sealed"],
                   "need": 8, "center": True, "mart": True},
    "skypillar": {"n": "하늘기둥", "kind": "building", "bg": "하늘탑", "pos": (178, 132), "links": ["pacifidlog"], "need": 8,
                  "wild": [(42, 48, 52, 30), (344, 48, 52, 25), (354, 48, 52, 20), (303, 48, 52, 15), (302, 48, 52, 10)],
                  "legend": [(384, 70, None)]},
    "sealed": {"n": "고대 석실", "kind": "cave", "bg": "유적", "pos": (204, 186), "links": ["pacifidlog"], "need": 8,
               "legend": [(377, 40, "champ3"), (378, 40, "champ3"), (379, 40, "champ3"), (380, 50, "champ3"),
                          (381, 50, "champ3")]},
    "h_victory": {"n": "챔피언로드", "kind": "cave", "bg": "챔피언로드", "pos": (282, 172), "links": ["h_route128", "evergrande"],
                  "need": 8,
                  "wild": [(42, 40, 44, 20), (305, 40, 44, 20), (67, 40, 44, 15), (297, 40, 44, 15), (302, 40, 44, 10),
                           (303, 40, 44, 10), (308, 40, 44, 10)],
                  "trainers": [("드래곤조련사", [(334, 44), (330, 45)]), ("엘리트트레이너", [(373, 44), (306, 45)]),
                               ("배틀걸", [(308, 44), (297, 45)])]},
    "evergrande": {"n": "그랜드시티", "kind": "town", "bg": "챔피언로드", "pos": (306, 186), "links": ["h_victory"], "need": 8,
                   "center": True, "mart": True, "league": "hoenn"},
}
for _k, _L in LOCATIONS.items():
    _L["region"] = "hoenn"
    _L["champ"] = "champ2"          # 성도 챔피언이 된 뒤에만
    _L.setdefault("bg", {"town": "도시", "route": "풀숲", "cave": "동굴", "building": "유적", "water": "해변"}[_L["kind"]])


def _auto_trainers():
    """도로 트레이너: 그 장소의 야생 포켓몬으로 팀을 만든다 (장소 이름으로 시드)"""
    for key, L in LOCATIONS.items():
        n = L.pop("auto", 0)
        if not n:
            continue
        r = random.Random(f"hoenn:{key}")
        wild = L["wild"]
        out = []
        for _ in range(n):
            team = []
            for _ in range(r.choice([2, 2, 3, 3])):
                sid, lo, hi, _w = r.choices(wild, weights=[w[3] for w in wild])[0]
                lv = min(E.MAX_LEVEL, hi + r.randint(0, 2))
                team.append((E._evolve_for_level(sid, lv, r), lv))
            out.append((r.choice(_CLASSES), team))
        L["trainers"] = L.get("trainers", []) + out


_auto_trainers()

GYMS = {
    "stone": {"n": "금탄도시 체육관", "leader": "원규", "badge": "스톤배지", "type": 6, "tm": 317,
              "junior": ("등산가", [(74, 10), (74, 11)]), "team": [(74, 12), (74, 12), (299, 15)],
              "line": "포켓몬 학교에서 배운 걸 실전에서 보여 줄게요!"},
    "knuckle": {"n": "무로마을 체육관", "leader": "철구", "badge": "너클배지", "type": 2, "tm": 409, "need": 1,
                "junior": ("가라데왕", [(66, 15), (307, 15)]), "team": [(66, 16), (307, 16), (296, 19)],
                "line": "파도처럼 밀려오는 내 격투 포켓몬을 막아 봐!"},
    "dynamo": {"n": "보라시티 체육관", "leader": "암페어", "badge": "다이나모배지", "type": 13, "tm": 9, "need": 2,
               "junior": ("엔지니어", [(81, 19), (309, 20)]), "team": [(100, 20), (309, 20), (82, 22), (310, 24)],
               "line": "와하하! 짜릿한 전기 승부를 해 보자고!"},
    "heat": {"n": "용암마을 체육관", "leader": "민지", "badge": "히트배지", "type": 10, "tm": 315, "need": 3,
             "junior": ("등산가", [(322, 24), (218, 24)]), "team": [(322, 24), (218, 24), (323, 26), (324, 29)],
             "line": "관장이 된 지 얼마 안 됐지만... 뜨거운 승부는 자신 있어!"},
    "balance": {"n": "등화도시 체육관", "leader": "종길", "badge": "밸런스배지", "type": 1, "tm": 263, "need": 4,
                "junior": ("엘리트트레이너", [(287, 27), (264, 28)]), "team": [(327, 27), (288, 27), (264, 29), (289, 31)],
                "line": "아버지로서가 아니라 관장으로서 상대해 주지!"},
    "feather": {"n": "검방울시티 체육관", "leader": "은송", "badge": "페더배지", "type": 3, "tm": 332, "need": 5,
                "junior": ("새조련사", [(277, 30), (279, 30)]),
                "team": [(333, 29), (357, 29), (279, 30), (227, 31), (334, 33)],
                "line": "하늘을 나는 포켓몬들과 함께라면 두려울 게 없어요."},
    "mind": {"n": "이끼시티 체육관", "leader": "풍&란", "badge": "마인드배지", "type": 14, "tm": 248, "need": 6,
             "junior": ("초능력자", [(326, 40), (281, 40)]), "team": [(344, 41), (178, 41), (337, 42), (338, 42)],
             "line": "우리 둘의 호흡을 깰 수 있을까?"},
    "rain": {"n": "루네시티 체육관", "leader": "아단", "badge": "레인배지", "type": 11, "tm": 56, "need": 7,
             "junior": ("비키니아가씨", [(370, 41), (119, 42)]),
             "team": [(370, 40), (340, 42), (364, 40), (119, 42), (350, 43)],
             "line": "물 포켓몬과 함께 펼치는 우아한 승부를 보여 드리죠."},
}
GYM_ORDER = ["stone", "knuckle", "dynamo", "heat", "balance", "feather", "mind", "rain"]

ELITE_FOUR = [
    {"n": "사천왕 혁진", "cls": "사천왕", "type": 17, "team": [(262, 46), (275, 48), (332, 46), (342, 48), (359, 49)],
     "line": "좋아, 신나는 승부를 해 보자고!"},
    {"n": "사천왕 회연", "cls": "사천왕", "type": 8, "team": [(356, 48), (354, 49), (302, 50), (354, 49), (356, 51)],
     "line": "송화산에서 수행하며 고스트 포켓몬과 마음이 통하게 됐어."},
    {"n": "사천왕 미혜", "cls": "사천왕", "type": 15, "team": [(364, 50), (362, 50), (364, 52), (362, 52), (365, 53)],
     "line": "얼어붙을 만큼 뜨거운 승부를 기대할게요."},
    {"n": "사천왕 권수", "cls": "사천왕", "type": 16, "team": [(372, 52), (334, 54), (330, 53), (330, 53), (373, 55)],
     "line": "포켓몬 트레이너에게 필요한 것이 무엇인지 아는가?"},
]
CHAMPION = {"n": "챔피언 성호", "cls": "챔피언", "type": 9,
            "team": [(227, 57), (344, 55), (306, 56), (346, 56), (348, 56), (376, 58)],
            "line": "여기까지 온 트레이너가 너라서 기쁘군. 진심으로 상대하지!"}

RIVAL_LINE = {
    "h1": "어, 너 털보박사님이 말한 그 트레이너지? 나랑 포켓몬 승부 해 볼래?",
    "h2": "벌써 여기까지 왔구나! 내 포켓몬도 많이 강해졌다고!",
    "h3": "하늘 위로 날아다니는 포켓몬을 조사하고 있었어. 승부 한 판 어때?",
    "h4": "이제 곧 리그에 도전하겠네. 마지막으로 실력을 확인해 줄게!",
}


def rival_team(stage: str, line: tuple[int, int, int]) -> list[tuple[int, int]]:
    a, b, c = line
    return {
        "h1": [(a, 5)],
        "h2": [(278, 18), (271, 18), (b, 20)],
        "h3": [(279, 29), (271, 29), (c, 31)],
        "h4": [(357, 31), (272, 32), (279, 32), (c, 34)],
    }[stage]


START_LEVEL = 8
LEVEL_CAPS = [17, 21, 26, 31, 33, 35, 44, 48, 60]       # 호연 배지 수별 (성도 챔피언 다음)
BADGE_RGB = [(176, 152, 120), (200, 96, 72), (240, 200, 64), (232, 96, 48), (200, 72, 72), (120, 176, 232),
             (232, 136, 200), (72, 136, 232)]
