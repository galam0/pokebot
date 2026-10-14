"""신오 지방 데이터 (플라티나를 바탕으로, 호연 챔피언이 된 뒤에 가는 네 번째 지방).

해안시티 항구에서 배를 타고 떡잎마을로 가요. 처음 들어올 때 파티·PC의 레벨을 START_LEVEL로 내려요.
- 야생 포켓몬·관장·사천왕·챔피언·라이벌·갤럭시단 팀은 플라티나 원본 (game/sinnoh_data.json,
  tools/build_sinnoh.py data 로 pret/pokeplatinum에서 만든다)
- 야생은 진화 전 모습도 섞여 있어서 만날 때 레벨에 맞게 진화시켜요 (다른 지방과 같음)
- 도로 트레이너는 그 장소의 야생 포켓몬으로 자동으로 만들어요 (auto: 트레이너 수)
- 장면: 원본 3D 맵을 그린 그림 (views: 장면 종류 → 맵 헤더, tools/build_sinnoh.py scenes)
"""

import json
import random
from pathlib import Path

from . import engine as E
from . import kanto as K

RIVAL = "라이벌 용식"
K.PRIZE.update({"갤럭시단 조무래기": 30, "갤럭시단 간부 마스": 100, "갤럭시단 간부 주피터": 100,
                "갤럭시단 간부 새턴": 100, "갤럭시단 보스 태홍": 120, RIVAL: 40, "등산가": 36, "엘리트트레이너": 60,
                "배틀걸": 40, "드래곤조련사": 60, "스키어": 40, "닌자소년": 24})

_DATA = Path(__file__).resolve().parent / "sinnoh_data.json"
DATA = json.loads(_DATA.read_text()) if _DATA.exists() else {"wild": {}, "teams": {}}

_CLASSES = ["반바지꼬마", "짧은치마", "곤충채집소년", "등산가", "피크닉걸", "캠프보이", "엘리트트레이너", "새조련사",
            "어부", "초능력자", "배틀걸", "닌자소년"]


def _wild(*keys, cap: int | None = None) -> list[tuple[int, int, int, int]]:
    """플라티나 풀숲 표 (여러 장소를 합칠 수 있다). cap: 레벨 상한 (게임 진행에 맞게)"""
    acc = {}
    for k in keys:
        for sid, lo, hi, w in DATA["wild"].get(k, []):
            a = acc.setdefault(sid, [lo, hi, 0])
            a[0], a[1], a[2] = min(a[0], lo), max(a[1], hi), a[2] + w
    out = [(s, lo, hi, w) for s, (lo, hi, w) in acc.items()]
    if cap:
        out = [(s, min(lo, cap), min(hi, cap), w) for s, lo, hi, w in out]
    return sorted(out, key=lambda x: -x[3])


def _team(stem: str) -> list[tuple[int, int]]:
    return [tuple(x) for x in DATA["teams"].get(stem, [])]


H = "MAP_HEADER_"
LOCATIONS = {
    # ---------- 떡잎마을 ~ 무쇠시티 ----------
    "s_ferry": {"n": "연락선 (해안시티 ↔ 신오)", "kind": "building", "bg": "해변", "pos": (40, 184),
                "links": ["lilycove", "s_twinleaf"], "desc": "호연의 해안시티와 신오 지방을 잇는 배."},
    "s_twinleaf": {"n": "떡잎마을", "kind": "town", "pos": (52, 168), "links": ["s_ferry", "s_route201"], "home": True,
                   "desc": "새싹처럼 작은 마을. 겨울이 가까워 땅에 눈이 조금 남아 있어요.",
                   "views": {"field": H + "TWINLEAF_TOWN", "home": H + "TWINLEAF_TOWN_PLAYER_HOUSE_1F"}},
    "s_route201": {"n": "201번도로", "kind": "route", "pos": (78, 166), "links": ["s_twinleaf", "s_verity", "s_sandgem"],
                   "rival": "s1", "enc": ["route_201"], "auto": 2,
                   "views": {"field": H + "ROUTE_201"}},
    "s_verity": {"n": "진실호수", "kind": "water", "bg": "숲", "pos": (52, 146), "links": ["s_route201"],
                 "enc": ["lake_verity"], "legend": [(481, 50, "champ4")],
                 "desc": "신오의 세 호수 중 하나. 감정의 신 엠라이트가 산다고 전해져요.",
                 "views": {"field": (H + "LAKE_VERITY", 48, 37)}},
    "s_sandgem": {"n": "잔모래마을", "kind": "town", "bg": "해변", "pos": (104, 166), "links": ["s_route201", "s_route202"],
                  "center": True, "mart": True,
                  "gift_choice": ([387, 390, 393], 5, "마박사: \"멀리서 온 트레이너로군. 신오의 포켓몬도 한 마리 데려가게.\""),
                  "views": {"field": H + "SANDGEM_TOWN", "center": H + "SANDGEM_TOWN_POKECENTER_1F",
                            "mart": H + "SANDGEM_TOWN_MART"}},
    "s_route202": {"n": "202번도로", "kind": "route", "pos": (104, 142), "links": ["s_sandgem", "s_jubilife"],
                   "enc": ["route_202"], "auto": 3, "views": {"field": H + "ROUTE_202"}},
    "s_jubilife": {"n": "축복시티", "kind": "town", "pos": (104, 116), "links": ["s_route202", "s_route203", "s_route204",
                                                                         "s_route218"],
                   "center": True, "mart": True,
                   "views": {"field": H + "JUBILIFE_CITY", "center": H + "JUBILIFE_CITY_POKECENTER_1F",
                             "mart": H + "JUBILIFE_CITY_MART"}},
    "s_route203": {"n": "203번도로·무쇠게이트", "kind": "route", "pos": (136, 112), "links": ["s_jubilife", "s_oreburgh"],
                   "rival": "s2", "enc": ["route_203", "oreburgh_gate_1f"], "auto": 3,
                   "views": {"field": H + "ROUTE_203"}},
    "s_oreburgh": {"n": "무쇠시티", "kind": "town", "bg": "동굴", "pos": (164, 118), "links": ["s_route203", "s_mine"],
                   "center": True, "mart": True, "gym": "coal",
                   "views": {"field": H + "OREBURGH_CITY", "center": H + "OREBURGH_CITY_POKECENTER_1F",
                             "mart": H + "OREBURGH_CITY_MART", "gym": H + "OREBURGH_CITY_GYM"}},
    "s_mine": {"n": "무쇠탄갱", "kind": "cave", "pos": (176, 136), "links": ["s_oreburgh"],
               "enc": ["oreburgh_mine_b1f", "oreburgh_mine_b2f"], "auto": 2, "views": {"field": H + "OREBURGH_MINE_B1F"}},
    # ---------- 꽃향기마을 ~ 영원시티 ----------
    "s_route204": {"n": "204번도로·험한 샛길", "kind": "route", "pos": (100, 88), "links": ["s_jubilife", "s_floaroma"],
                   "need": 1, "enc": ["route_204_south", "ravaged_path"], "auto": 3,
                   "views": {"field": H + "ROUTE_204_SOUTH"}},
    "s_floaroma": {"n": "꽃향기마을", "kind": "town", "pos": (92, 62), "links": ["s_route204", "s_windworks", "s_route205"],
                   "need": 1, "center": True, "mart": True,
                   "views": {"field": H + "FLOAROMA_TOWN", "center": H + "FLOAROMA_TOWN_POKECENTER_1F",
                             "mart": H + "FLOAROMA_TOWN_MART"}},
    "s_windworks": {"n": "골짜기발전소", "kind": "building", "bg": "풀숲", "pos": (126, 70), "links": ["s_floaroma"],
                    "need": 1, "enc": ["valley_windworks_outside"],
                    "trainers": [("갤럭시단 조무래기", "galactic_grunt_valley_windworks_1"),
                                 ("갤럭시단 간부 마스", "commander_mars_valley_windworks")],
                    "clear_gift": ("rare-candy", 2), "views": {"field": H + "VALLEY_WINDWORKS_OUTSIDE"}},
    "s_route205": {"n": "205번도로", "kind": "route", "pos": (96, 40), "links": ["s_floaroma", "s_eterna_forest"],
                   "need": 1, "enc": ["route_205_south"], "auto": 3, "views": {"field": H + "ROUTE_205_SOUTH"}},
    "s_eterna_forest": {"n": "영원의 숲", "kind": "route", "bg": "숲", "pos": (122, 30), "links": ["s_route205", "s_eterna"],
                        "need": 1, "enc": ["eterna_forest"], "auto": 3, "views": {"field": H + "ETERNA_FOREST"}},
    "s_eterna": {"n": "영원시티", "kind": "town", "pos": (152, 32), "links": ["s_eterna_forest", "s_galactic_eterna",
                                                                       "s_route206"],
                 "need": 1, "center": True, "mart": True, "gym": "forest",
                 "views": {"field": H + "ETERNA_CITY", "center": H + "ETERNA_CITY_POKECENTER_1F",
                           "mart": H + "ETERNA_CITY_MART", "gym": H + "ETERNA_CITY_GYM"}},
    "s_galactic_eterna": {"n": "갤럭시단 영원빌딩", "kind": "building", "bg": "도시", "pos": (170, 16), "links": ["s_eterna"],
                          "need": 2,
                          "trainers": [("갤럭시단 조무래기", "galactic_grunt_team_galactic_eterna_building_1f_1"),
                                       ("갤럭시단 조무래기", "galactic_grunt_team_galactic_eterna_building_3f"),
                                       ("갤럭시단 간부 주피터", "commander_jupiter_team_galactic_eterna_building")],
                          "clear_gift": ("rare-candy", 2), "views": {"field": H + "TEAM_GALACTIC_ETERNA_BUILDING_1F"}},
    # ---------- 천관산 ~ 연고시티 ~ 신수마을 ----------
    "s_route206": {"n": "206·207번도로", "kind": "route", "pos": (160, 64), "links": ["s_eterna", "s_coronet", "s_wayward"],
                   "need": 2, "enc": ["route_206", "route_207"], "auto": 3, "views": {"field": H + "ROUTE_206"}},
    "s_wayward": {"n": "미혹의 동굴", "kind": "cave", "pos": (180, 82), "links": ["s_route206"], "need": 2,
                  "enc": ["wayward_cave_1f"], "auto": 2, "gift": (443, 15, "동굴 깊은 곳에서 딥상어동을 만났다! 함께 가기로 했다."),
                  "views": {"field": H + "WAYWARD_CAVE_1F"}},
    "s_coronet": {"n": "천관산", "kind": "cave", "pos": (176, 52), "links": ["s_route206", "s_route208", "s_acuity",
                                                                       "s_spear", "s_coronet_n"],
                  "need": 2, "enc": ["mt_coronet_1f_south"], "auto": 2, "views": {"field": H + "MT_CORONET_1F_SOUTH"}},
    "s_route208": {"n": "208번도로", "kind": "route", "pos": (196, 104), "links": ["s_coronet", "s_hearthome"], "need": 2,
                   "enc": ["route_208"], "auto": 3, "views": {"field": H + "ROUTE_208"}},
    "s_hearthome": {"n": "연고시티", "kind": "town", "pos": (214, 122), "links": ["s_route208", "s_route209"], "need": 2,
                    "center": True, "mart": True, "gym": "relic",
                    "views": {"field": H + "HEARTHOME_CITY", "center": H + "HEARTHOME_CITY_POKECENTER_1F",
                              "mart": H + "HEARTHOME_CITY_MART", "gym": H + "HEARTHOME_CITY_GYM_LEADER_ROOM"}},
    "s_route209": {"n": "209번도로", "kind": "route", "pos": (234, 104), "links": ["s_hearthome", "s_lost_tower",
                                                                           "s_solaceon"],
                   "need": 3, "rival": "s3", "enc": ["route_209"], "auto": 3, "views": {"field": H + "ROUTE_209"}},
    "s_lost_tower": {"n": "로스트타워", "kind": "building", "bg": "유적", "pos": (252, 122), "links": ["s_route209"],
                     "need": 3, "enc": ["route_209_lost_tower_1f", "route_209_lost_tower_3f"], "auto": 2,
                     "views": {"field": H + "ROUTE_209_LOST_TOWER_1F"}},
    "s_solaceon": {"n": "신수마을", "kind": "town", "pos": (236, 82), "links": ["s_route209", "s_ruins", "s_route210"],
                   "need": 3, "center": True, "mart": True,
                   "views": {"field": H + "SOLACEON_TOWN", "center": H + "SOLACEON_TOWN_POKECENTER_1F",
                             "mart": H + "SOLACEON_TOWN_MART"}},
    "s_ruins": {"n": "신수유적", "kind": "cave", "bg": "유적", "pos": (220, 68), "links": ["s_solaceon"], "need": 3,
                "enc": ["solaceon_ruins_room_2"], "views": {"field": H + "SOLACEON_RUINS_ROOM_2"}},
    # ---------- 장막시티 ~ 들판시티 ~ 봉신마을 ----------
    "s_route210": {"n": "210·215번도로", "kind": "route", "pos": (248, 58), "links": ["s_solaceon", "s_veilstone",
                                                                               "s_celestic"],
                   "need": 3, "enc": ["route_210_south", "route_215"], "auto": 3, "views": {"field": H + "ROUTE_215"}},
    "s_veilstone": {"n": "장막시티", "kind": "town", "bg": "동굴", "pos": (276, 54), "links": ["s_route210", "s_route214",
                                                                                       "s_galactic_hq"],
                    "need": 3, "center": True, "mart": True, "dept": True, "gym": "cobble",
                    "views": {"field": H + "VEILSTONE_CITY", "center": H + "VEILSTONE_CITY_POKECENTER_1F",
                              "gym": H + "VEILSTONE_CITY_GYM"}},
    "s_route214": {"n": "214·213번도로", "kind": "route", "pos": (284, 96), "links": ["s_veilstone", "s_valor", "s_pastoria"],
                   "need": 4, "enc": ["route_214", "route_213"], "auto": 3, "views": {"field": H + "ROUTE_214"}},
    "s_valor": {"n": "입지호수", "kind": "water", "bg": "숲", "pos": (300, 128), "links": ["s_route214"], "need": 4,
                "enc": ["lake_valor"], "legend": [(482, 50, "champ4")],
                "desc": "의지의 신 아그놈이 잠들어 있다는 호수.", "views": {"field": (H + "LAKE_VALOR", 42, 15)}},
    "s_pastoria": {"n": "들판시티", "kind": "town", "pos": (264, 140), "links": ["s_route214", "s_marsh", "s_route222"], "need": 4,
                   "center": True, "mart": True, "gym": "fen", "rival": "s4",
                   "views": {"field": H + "PASTORIA_CITY", "center": H + "PASTORIA_CITY_POKECENTER_1F",
                             "mart": H + "PASTORIA_CITY_MART", "gym": H + "PASTORIA_CITY_GYM"}},
    "s_marsh": {"n": "대습초원", "kind": "route", "bg": "숲", "pos": (248, 160), "links": ["s_pastoria"], "need": 4,
                "enc": ["great_marsh_1", "great_marsh_2", "great_marsh_3"], "views": {"field": H + "GREAT_MARSH_2"}},
    "s_celestic": {"n": "봉신마을", "kind": "town", "pos": (214, 44), "links": ["s_route210", "s_route218"], "need": 5,
                   "center": True,
                   "trainers": [("갤럭시단 조무래기", "galactic_grunt_celestic_town"),
                                ("갤럭시단 보스 태홍", "galactic_boss_cyrus_celestic_town_ruins")],
                   "views": {"field": (H + "CELESTIC_TOWN", 464, 533), "center": H + "CELESTIC_TOWN_POKECENTER_1F"}},
    # ---------- 운하시티 ~ 선단시티 ----------
    "s_route218": {"n": "218번도로", "kind": "route", "pos": (72, 112), "links": ["s_jubilife", "s_canalave", "s_celestic"],
                   "need": 5, "enc": ["route_218"], "auto": 3, "views": {"field": H + "ROUTE_218"}},
    "s_canalave": {"n": "운하시티", "kind": "town", "bg": "해변", "pos": (40, 104), "links": ["s_route218", "s_iron"],
                   "need": 5, "center": True, "mart": True, "gym": "mine", "rival": "s5",
                   "views": {"field": H + "CANALAVE_CITY", "center": H + "CANALAVE_CITY_POKECENTER_1F",
                             "mart": H + "CANALAVE_CITY_MART", "gym": H + "CANALAVE_CITY_GYM"}},
    "s_iron": {"n": "강철섬", "kind": "cave", "pos": (16, 78), "links": ["s_canalave"], "need": 5,
               "enc": ["iron_island_1f", "iron_island_b1f_left_room"], "auto": 2,
               "gift": (447, 20, "강철섬에서 함께 싸운 트레이너 현이에게서 리오르를 받았다!"),
               "views": {"field": H + "IRON_ISLAND"}},
    "s_route216": {"n": "216·217번도로", "kind": "route", "bg": "설원", "pos": (176, 28), "links": ["s_acuity_front",
                                                                                              "s_coronet_n"],
                   "need": 6, "enc": ["route_216", "route_217"], "auto": 3, "views": {"field": (H + "ROUTE_216", 350, 406)}},
    "s_coronet_n": {"n": "천관산 북쪽", "kind": "cave", "bg": "설원", "pos": (190, 48), "links": ["s_route216", "s_coronet"],
                    "need": 6, "enc": ["mt_coronet_outside_north"], "views": {"field": H + "MT_CORONET_OUTSIDE_NORTH"}},
    "s_acuity_front": {"n": "예지호숫가", "kind": "route", "bg": "설원", "pos": (150, 14), "links": ["s_route216", "s_snowpoint",
                                                                                              "s_acuity"],
                       "need": 6, "enc": ["acuity_lakefront"], "views": {"field": H + "ACUITY_LAKEFRONT"}},
    "s_acuity": {"n": "예지호수", "kind": "water", "bg": "설원", "pos": (128, 8), "links": ["s_acuity_front", "s_coronet"],
                 "need": 6, "enc": ["lake_acuity"], "legend": [(480, 50, "champ4")],
                 "desc": "지식의 신 유크시가 잠들어 있다는 얼어붙은 호수.", "views": {"field": (H + "LAKE_ACUITY", 23, 43)}},
    "s_snowpoint": {"n": "선단시티", "kind": "town", "bg": "설원", "pos": (112, 10), "links": ["s_acuity_front", "s_temple"],
                    "need": 6, "center": True, "mart": True, "gym": "icicle",
                    "views": {"field": H + "SNOWPOINT_CITY", "center": H + "SNOWPOINT_CITY_POKECENTER_1F",
                              "mart": H + "SNOWPOINT_CITY_MART", "gym": H + "SNOWPOINT_CITY_GYM"}},
    "s_temple": {"n": "선단신전", "kind": "building", "bg": "설원", "pos": (88, 8), "links": ["s_snowpoint"], "need": 6,
                 "enc": ["snowpoint_temple_1f", "snowpoint_temple_b1f"],
                 "legend": [(486, 60, "champ4")], "views": {"field": H + "SNOWPOINT_TEMPLE_1F"}},
    # ---------- 갤럭시단 아지트 · 창기둥 · 물가시티 ----------
    "s_galactic_hq": {"n": "갤럭시단 아지트", "kind": "building", "bg": "도시", "pos": (300, 36), "links": ["s_veilstone"],
                      "need": 7,
                      "trainers": [("갤럭시단 조무래기", "galactic_grunt_galactic_hq_2f_1"),
                                   ("갤럭시단 조무래기", "galactic_grunt_galactic_hq_3f_1"),
                                   ("갤럭시단 간부 새턴", "commander_saturn_galactic_hq"),
                                   ("갤럭시단 보스 태홍", "galactic_boss_cyrus_galactic_hq")],
                      "clear_gift": ("master-ball", 1), "views": {"field": H + "GALACTIC_HQ_1F"}},
    "s_spear": {"n": "창기둥", "kind": "building", "bg": "하늘탑", "pos": (176, 72), "links": ["s_coronet", "s_distortion"],
                "need": 7,
                "trainers": [("갤럭시단 간부 마스", "commander_mars_spear_pillar"),
                             ("갤럭시단 간부 주피터", "commander_jupiter_spear_pillar")],
                "legend": [(483, 50, None), (484, 50, None)],
                "desc": "천관산 꼭대기의 오래된 신전. 시간과 공간의 신이 나타난다고 해요.",
                "views": {"field": H + "SPEAR_PILLAR"}},
    "s_distortion": {"n": "깨어진세계", "kind": "cave", "bg": "하늘탑", "pos": (196, 82), "links": ["s_spear"], "need": 7,
                     "trainers": [("갤럭시단 보스 태홍", "galactic_boss_cyrus_distortion_world")],
                     "legend": [(487, 50, None)],
                     "desc": "모든 것이 뒤틀린 반전세계. 기라티나의 기운이 느껴진다...",
                     "views": {"field": H + "SPEAR_PILLAR_DISTORTED"}},
    "s_route222": {"n": "222번도로", "kind": "route", "bg": "해변", "pos": (284, 158), "links": ["s_pastoria", "s_sunyshore"],
                   "need": 7, "enc": ["route_222"], "auto": 3, "views": {"field": H + "ROUTE_222"}},
    "s_sunyshore": {"n": "물가시티", "kind": "town", "bg": "해변", "pos": (300, 136),
                    "links": ["s_route222", "s_route223"], "need": 7, "center": True, "mart": True, "gym": "beacon",
                    "views": {"field": H + "SUNYSHORE_CITY", "center": H + "SUNYSHORE_CITY_POKECENTER_1F",
                              "mart": H + "SUNYSHORE_CITY_MART", "gym": H + "SUNYSHORE_CITY_GYM_ROOM_3"}},
    # ---------- 포켓몬리그 ----------
    "s_route223": {"n": "223번수로", "kind": "water", "pos": (306, 108), "links": ["s_sunyshore", "s_victory"], "need": 8,
                   "enc": ["route_223"], "auto": 3, "views": {"field": H + "ROUTE_223"}},
    "s_victory": {"n": "챔피언로드", "kind": "cave", "bg": "챔피언로드", "pos": (306, 80), "links": ["s_route223", "s_league"],
                  "need": 8, "enc": ["victory_road_1f", "victory_road_2f"], "auto": 3,
                  "views": {"field": H + "VICTORY_ROAD_1F"}},
    "s_league": {"n": "포켓몬리그", "kind": "town", "bg": "챔피언로드", "pos": (300, 54), "links": ["s_victory", "s_stark"],
                 "need": 8, "center": True, "mart": True, "league": "sinnoh", "rival": "s6",
                 "views": {"field": H + "POKEMON_LEAGUE", "center": H + "POKEMON_LEAGUE_NORTH_POKECENTER_1F"}},
    # ---------- 챔피언이 된 뒤 ----------
    "s_stark": {"n": "하드마운틴", "kind": "cave", "bg": "화산", "pos": (310, 22), "links": ["s_league", "s_fullmoon"],
                "need": 8, "champ": "champ4", "enc": ["stark_mountain_outside", "stark_mountain_room_1"], "auto": 3,
                "legend": [(485, 50, None)], "views": {"field": H + "STARK_MOUNTAIN_OUTSIDE"}},
    "s_fullmoon": {"n": "만월섬", "kind": "route", "bg": "숲", "pos": (282, 10), "links": ["s_stark"], "need": 8,
                   "champ": "champ4", "legend": [(488, 50, None)],
                   "desc": "보름달처럼 둥근 섬. 크레세리아가 머문다고 해요.", "views": {"field": H + "FULLMOON_ISLAND"}},
}
for _k, _L in LOCATIONS.items():
    _L["region"] = "sinnoh"
    _L.setdefault("champ", "champ3")          # 호연 챔피언이 된 뒤에만
    _L.setdefault("bg", {"town": "도시", "route": "풀숲", "cave": "동굴", "building": "유적", "water": "해변"}[_L["kind"]])
    _cap = None
    if _L.get("enc"):
        _L["wild"] = _wild(*_L["enc"])
    # 이름 있는 트레이너: 파일 이름 → 원본 팀
    if _L.get("trainers"):
        _L["trainers"] = [(cls, _team(stem) if isinstance(stem, str) else stem) for cls, stem in _L["trainers"]]
        _L["trainers"] = [(cls, t) for cls, t in _L["trainers"] if t]


def _auto_trainers():
    """도로 트레이너: 그 장소의 야생 포켓몬으로 팀을 만든다 (장소 이름으로 시드)"""
    for key, L in LOCATIONS.items():
        n = L.pop("auto", 0)
        wild = L.get("wild")
        if not n or not wild:
            continue
        r = random.Random(f"sinnoh:{key}")
        out = []
        for _ in range(n):
            tm = []
            for _ in range(r.choice([2, 2, 3, 3])):
                sid, lo, hi, _w = r.choices(wild, weights=[w[3] for w in wild])[0]
                lv = min(E.MAX_LEVEL, hi + r.randint(0, 2))
                tm.append((E._evolve_for_level(sid, lv, r), lv))
            out.append((r.choice(_CLASSES), tm))
        L["trainers"] = L.get("trainers", []) + out


_auto_trainers()

# 관장 (플라티나 순서: 무쇠 → 영원 → 연고 → 장막 → 들판 → 운하 → 선단 → 물가)
GYMS = {
    "coal": {"n": "무쇠시티 체육관", "leader": "강석", "badge": "콜배지", "type": 6, "tm": 317, "file": "leader_roark",
             "junior": ("등산가", [(74, 10), (95, 11)]), "line": "포켓몬과 함께 단련한 바위 같은 힘을 보여 주지!"},
    "forest": {"n": "영원시티 체육관", "leader": "유채", "badge": "포레스트배지", "type": 12, "tm": 202, "need": 1,
               "file": "leader_gardenia", "junior": ("피크닉걸", [(420, 17), (406, 18)]),
               "line": "풀 포켓몬의 아름다움과 강인함을 느껴 봐!"},
    "relic": {"n": "연고시티 체육관", "leader": "멜리사", "badge": "렐릭배지", "type": 8, "tm": 421, "need": 2,
              "file": "leader_fantina", "junior": ("무당", [(200, 22), (355, 22)]),
              "line": "봉주르! 고스트 포켓몬의 춤을 보여 드릴게요!"},
    "cobble": {"n": "장막시티 체육관", "leader": "자두", "badge": "코볼배지", "type": 2, "tm": 409, "need": 3,
               "file": "leader_maylene", "junior": ("배틀걸", [(307, 26), (66, 27)]),
               "line": "아직 관장으로서 부족하지만... 온 힘을 다할게요!"},
    "fen": {"n": "들판시티 체육관", "leader": "맥시", "badge": "펜배지", "type": 11, "tm": 362, "need": 4,
            "file": "leader_wake", "junior": ("어부", [(129, 28), (195, 29)]),
            "line": "와하하! 마스크드 맥시의 파도 같은 공격을 받아라!"},
    "mine": {"n": "운하시티 체육관", "leader": "동관", "badge": "마인배지", "type": 9, "tm": 430, "need": 5,
             "file": "leader_byron", "junior": ("엘리트트레이너", [(436, 34), (82, 35)]),
             "line": "아들 강석을 이겼다고? 강철처럼 단단한 내 포켓몬은 다르다!"},
    "icicle": {"n": "선단시티 체육관", "leader": "무청", "badge": "아이시클배지", "type": 15, "tm": 419, "need": 6,
               "file": "leader_candice", "junior": ("스키어", [(459, 37), (220, 38)]),
               "line": "집중! 얼음처럼 차갑고 뜨겁게 승부하자!"},
    "beacon": {"n": "물가시티 체육관", "leader": "전진", "badge": "비콘배지", "type": 13, "tm": 451, "need": 7,
               "file": "leader_volkner", "junior": ("엘리트트레이너", [(404, 44), (125, 45)]),
               "line": "드디어 날 짜릿하게 해 줄 도전자가 온 건가?"},
}
for _g in GYMS.values():
    _g["team"] = _team(_g.pop("file"))
GYM_ORDER = ["coal", "forest", "relic", "cobble", "fen", "mine", "icicle", "beacon"]

ELITE_FOUR = [
    {"n": "사천왕 충호", "cls": "사천왕", "type": 7, "team": _team("elite_four_aaron"),
     "line": "벌레 포켓몬의 강함을 보여 주마. 각오해!"},
    {"n": "사천왕 들국화", "cls": "사천왕", "type": 5, "team": _team("elite_four_bertha"),
     "line": "어머나, 젊은이가 여기까지 왔구나. 할머니도 진심으로 상대해 줄게."},
    {"n": "사천왕 대엽", "cls": "사천왕", "type": 10, "team": _team("elite_four_flint"),
     "line": "내 불꽃처럼 뜨거운 승부를 하자고!"},
    {"n": "사천왕 오엽", "cls": "사천왕", "type": 14, "team": _team("elite_four_lucian"),
     "line": "책을 덮을 시간이군. 네 실력을 읽어 보겠다."},
]
CHAMPION = {"n": "챔피언 난천", "cls": "챔피언", "type": 16, "team": _team("champion_cynthia"),
            "line": "포켓몬 리그 챔피언으로서, 너의 도전을 진심으로 받아들일게."}

RIVAL_LINE = {
    "s1": "야! 늦었잖아! 벌금 백만 원이다! ...아무튼 승부다!",
    "s2": "앗, 너구나! 체육관 가는 길이지? 그 전에 나랑 한 판!",
    "s3": "나 지금 엄청 강해졌다고! 확인시켜 줄게!",
    "s4": "들판시티까지 왔구나. 이번엔 진짜 안 진다!",
    "s5": "운하시티 관장은 강석의 아빠래. 그 전에 내가 먼저다!",
    "s6": "리그 앞까지 왔으니 마지막으로 내가 상대해 주지!",
}
RIVAL_FILE = {"s1": "rival_route_201", "s2": "rival_route_203", "s3": "rival_route_209", "s4": "rival_pastoria_city",
              "s5": "rival_canalave_city", "s6": "rival_pokemon_league"}
RIVAL_STARTER = {"grass": "turtwig", "fire": "chimchar", "water": "piplup"}   # 원본 파일은 "주인공이 고른 스타팅" 이름


def rival_team(stage: str, kind: str) -> list[tuple[int, int]]:
    """kind: 내 신오 스타팅의 타입 (grass/fire/water)"""
    return _team(f"{RIVAL_FILE[stage]}_{RIVAL_STARTER[kind]}")


TEAM_FILES = ([g for g in ("leader_roark", "leader_gardenia", "leader_fantina", "leader_maylene", "leader_wake",
                           "leader_byron", "leader_candice", "leader_volkner")]
              + ["elite_four_aaron", "elite_four_bertha", "elite_four_flint", "elite_four_lucian", "champion_cynthia"]
              + [f"{f}_{s}" for f in RIVAL_FILE.values() for s in RIVAL_STARTER.values()]
              + ["galactic_grunt_valley_windworks_1", "commander_mars_valley_windworks",
                 "galactic_grunt_team_galactic_eterna_building_1f_1", "galactic_grunt_team_galactic_eterna_building_3f",
                 "commander_jupiter_team_galactic_eterna_building", "galactic_grunt_celestic_town",
                 "galactic_boss_cyrus_celestic_town_ruins", "galactic_grunt_galactic_hq_2f_1",
                 "galactic_grunt_galactic_hq_3f_1", "commander_saturn_galactic_hq", "galactic_boss_cyrus_galactic_hq",
                 "commander_mars_spear_pillar", "commander_jupiter_spear_pillar",
                 "galactic_boss_cyrus_distortion_world"])

START_LEVEL = 8
LEVEL_CAPS = [16, 24, 28, 34, 38, 42, 46, 52, 66]       # 신오 배지 수별 (호연 챔피언 다음)
BADGE_RGB = [(120, 112, 104), (96, 176, 80), (176, 120, 200), (200, 96, 72), (72, 136, 232), (176, 176, 192),
             (152, 216, 240), (248, 200, 64)]
