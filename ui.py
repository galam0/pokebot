"""디스코드 화면(임베드·버튼) 만들기.

버튼 custom_id 형식: pr:<유저ID>:<게임 버전>:<동작>[:<값>]
- 유저ID로 본인만 누를 수 있게 하고, 게임 버전으로 지난 화면의 버튼을 막는다.
- View를 메모리에 등록하지 않고 bot.on_interaction 에서 직접 처리한다.
  → 봇이 재시작해도, 몇 시간이 지나도 버튼이 계속 동작한다.
"""

from dataclasses import dataclass, field

import discord

from game import adventure as A
from game import data as D
from game import engine as E
from game import heroes as H
from game import kanto as K
from game.text import josa

TYPE_COLOR = {10: 0xEE8130, 11: 0x6390F0, 12: 0x7AC74C}


MODE_PREFIX = {"adventure": "", "daily": "d", "challenge": "c"}
MODE_KO = {"adventure": "🗺️ 모험", "daily": "📅 데일리", "challenge": "🏆 주간 챌린지"}
MODES = list(MODE_PREFIX)


def slot_of(uid: int, mode: str = "adventure") -> str:
    """버튼 주인 표시: 모험 '123', 데일리 'd123', 챌린지 'c123'"""
    return f"{MODE_PREFIX[mode]}{uid}"


def parse_slot(slot: str) -> tuple[int, str]:
    for mode, pre in MODE_PREFIX.items():
        if pre and slot.startswith(pre):
            return int(slot[len(pre):]), mode
    return int(slot), "adventure"


def cid(uid, ver: int, act: str, arg: str | int = "") -> str:
    return f"pr:{uid}:{ver}:{act}" + (f":{arg}" if arg != "" else "")


def _frozen(view: discord.ui.View) -> discord.ui.View:
    view.stop()   # discord.py가 View를 저장하지 않게 → 클릭은 on_interaction이 처리
    return view


# ---------- 막대 ----------
def bar(cur: int, total: int, width: int = 10) -> str:
    filled = 0 if total <= 0 else max(0, min(width, round(cur * width / total)))
    if cur > 0 and filled == 0:
        filled = 1
    return "▰" * filled + "▱" * (width - filled)


def hp_line(mon: dict) -> str:
    mh = E.max_hp(mon)
    ratio = mon["hp"] / mh if mh else 0
    dot = "🟢" if ratio > 0.5 else ("🟡" if ratio > 0.2 else "🔴")
    return f"{dot} `{bar(mon['hp'], mh)}` {mon['hp']}/{mh}"


def exp_line(mon: dict) -> str:
    need = E.exp_to_next(mon)
    if not need:
        return "EXP 최고 레벨!"
    return f"EXP `{bar(mon['exp'], need)}` {mon['exp']}/{need} (다음 레벨까지 {need - mon['exp']})"


def mon_head(mon: dict) -> str:
    st = f" · **{E.STATUS_KO[mon['status']]}**" if mon.get("status") else ""
    return f"{D.type_text(mon['sid'])}{st}"


# ---------- 스타팅 선택 ----------
REGIONS = {
    "관동": [1, 4, 7], "성도": [152, 155, 158], "호연": [252, 255, 258],
    "신오": [387, 390, 393], "하나": [495, 498, 501], "칼로스": [650, 653, 656],
    "알로라": [722, 725, 728], "가라르": [810, 813, 816], "팔데아": [906, 909, 912],
}


HEROES_FILE = "heroes.png"
INTRO_FILE = "intro.png"


INTRO_TEXT = ("오박사: \"오오, 왔구나! 함께 떠날 포켓몬을 골라 보거라. 먼 지방에서 온 포켓몬도 있단다.\"\n\n"
              "• 태초마을에서 출발해 관동의 도로와 동굴을 지나며 포켓몬을 잡고 키워요.\n"
              "• 체육관 8곳의 배지를 모아 석영고원에서 사천왕과 챔피언에게 도전해요.\n"
              "• 관동 챔피언이 되면 파티와 PC를 그대로 데리고 **성도 지방**으로 떠날 수 있어요.\n"
              "• 배지가 늘수록 더 높은 레벨까지 말을 들어요. 지면 마지막 포켓몬센터로 돌아가요.\n"
              "• 진행은 계속 저장되고, `/초기화`로 처음부터 다시 할 수 있어요.")


def adventure_intro_screen(uid, image: bool = False) -> tuple[str, list[discord.Embed], discord.ui.View]:
    """모험 시작 1단계: 오박사 연구소 설명 → 다음"""
    e = discord.Embed(title="🧪 오박사 연구소 (1/3)", color=0x3BA55D,
                      description="설명을 읽고 다음으로 넘어가 주인공과 스타팅을 골라 주세요." if image else INTRO_TEXT)
    if image:
        e.set_image(url=f"attachment://{INTRO_FILE}")
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="다음: 주인공 고르기", emoji="▶️", style=discord.ButtonStyle.success,
                                    custom_id=cid(uid, 0, "heropick", H.DEFAULT)))
    return "", [e], _frozen(view)


def hero_screen(uid, hero: str = H.DEFAULT, image: bool = False) -> tuple[str, list[discord.Embed], discord.ui.View]:
    """모험 시작 2단계: 역대 주인공 20명 중 고르기 → 다음"""
    hero = H.valid(hero)
    _, hname, hgen, hgame = next(h for h in H.HEROES if h[0] == hero)
    desc = f"지금 고른 주인공: **{hname}** ({hgen}세대 · {hgame})\n메뉴에서 바꾸고, 다 골랐으면 다음으로 넘어가요."
    if not image:
        desc += "\n\n" + "\n".join(f"• {n} ({g}세대 · {game})" for _, n, g, game in H.HEROES)
    e = discord.Embed(title="🧢 주인공 고르기 (2/3)", color=0x3BA55D, description=desc)
    if image:
        e.set_image(url=f"attachment://{HEROES_FILE}")
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Select(
        custom_id=cid(uid, 0, "hero"), placeholder="주인공 고르기", row=0,
        options=[discord.SelectOption(label=n, value=k, default=k == hero, description=f"{g}세대 · {game}")
                 for k, n, g, game in H.HEROES]))
    view.add_item(discord.ui.Button(label="다음: 스타팅 고르기", emoji="▶️", style=discord.ButtonStyle.success, row=1,
                                    custom_id=cid(uid, 0, "region", hero)))
    return "", [e], _frozen(view)


STARTERS_FILE = "starters.png"


def adventure_start_screen(uid, region: str = "관동", hero: str = H.DEFAULT,
                           image: bool = False) -> tuple[str, list[discord.Embed], discord.ui.View]:
    """모험 시작 3단계: 1~9세대 스타팅 27마리 중 하나 (지방을 고르면 그 지방 스타팅 3마리, 그림 한 장에)"""
    region = region if region in REGIONS else "관동"
    hero = H.valid(hero)
    _, hname, hgen, hgame = next(h for h in H.HEROES if h[0] == hero)
    embeds = [discord.Embed(
        title="🧪 스타팅 고르기 (3/3)",
        description=(f"주인공: **{hname}** ({hgen}세대 · {hgame}) · 모험 중에도 `/주인공`으로 바꿀 수 있어요.\n"
                     f"함께 떠날 포켓몬을 골라 주세요. 메뉴에서 지방을 바꾸면 다른 세대 스타팅도 고를 수 있어요. "
                     f"지금: **{region}**"),
        color=0x3BA55D)]
    if image:
        embeds[0].set_image(url=f"attachment://{STARTERS_FILE}")
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Select(
        custom_id=cid(uid, 0, "region", hero), placeholder="다른 지방 스타팅 보기", row=1,
        options=[discord.SelectOption(label=f"{i + 1}세대 · {r}", value=r, default=r == region,
                                      description=" / ".join(D.name(x) for x in ids))
                 for i, (r, ids) in enumerate(REGIONS.items())]))
    for sid in REGIONS[region]:
        if not image:   # 그림이 없으면 예전처럼 한 마리씩 글로
            st = D.SPECIES[sid]["s"]
            e = discord.Embed(title=D.name(sid), color=TYPE_COLOR.get(D.types(sid)[0], 0x5865F2),
                              description=(f"{D.type_text(sid)} 타입 · 종족값 합계 {sum(st)}\n"
                                           f"HP {st[0]} · 공격 {st[1]} · 방어 {st[2]} · 특공 {st[3]} · 특방 {st[4]} · "
                                           f"스피드 {st[5]}"))
            e.set_thumbnail(url=D.artwork(sid))
            embeds.append(e)
        view.add_item(discord.ui.Button(label=D.name(sid), style=discord.ButtonStyle.primary, row=0,
                                        custom_id=cid(uid, 0, "starter", f"{sid}.{hero}")))
    view.add_item(discord.ui.Button(label="주인공 다시 고르기", emoji="◀️", style=discord.ButtonStyle.secondary, row=2,
                                    custom_id=cid(uid, 0, "heropick", hero)))
    return "", embeds, _frozen(view)


def mode_start_screen(uid, mode: str, seed: str, starters: list[int]) -> tuple[str, list[discord.Embed], discord.ui.View]:
    """데일리·주간 챌린지 시작: 정해진 스타팅 3마리 중 고르기"""
    if mode == "daily":
        title = f"📅 데일리 · {seed}"
        desc = ("오늘은 모두가 **같은 상대, 같은 보상**으로 도전해요. 하루에 한 번만 할 수 있어요.\n"
                "가장 멀리 간 웨이브로 오늘의 랭킹이 정해져요.")
    else:
        rule, mono = E.weekly_rules(seed)
        rule_text = E.RULES[rule] + (f" (**{D.TYPE_KO[mono]}** 타입)" if mono else "")
        title = f"🏆 주간 챌린지 · {seed}"
        desc = (f"이번 주 규칙: **{rule_text}**\n"
                "모두가 같은 상대와 보상으로 도전하고, 이번 주에 한 번만 할 수 있어요. 주간 랭킹을 겨뤄요.")
    embeds = [discord.Embed(title=title, description=desc, color=0xF1C40F)]
    view = discord.ui.View(timeout=None)
    for sid in starters:
        st = D.SPECIES[sid]["s"]
        e = discord.Embed(title=D.name(sid), color=TYPE_COLOR.get(D.types(sid)[0], 0x5865F2),
                          description=(f"{D.type_text(sid)} 타입 · 종족값 합계 {sum(st)}\n"
                                       f"HP {st[0]} · 공격 {st[1]} · 방어 {st[2]} · 특공 {st[3]} · 특방 {st[4]} · 스피드 {st[5]}"))
        e.set_thumbnail(url=D.artwork(sid))
        embeds.append(e)
        view.add_item(discord.ui.Button(label=D.name(sid), style=discord.ButtonStyle.primary,
                                        custom_id=cid(uid, 0, "starter", sid)))
    return "", embeds, _frozen(view)


# ---------- 화면 ----------
SCENE_FILE = "scene.png"
SCENE_GIF = "scene.gif"   # 배틀 화면 (포켓몬이 움직임)
SUMMARY_FILE = "summary.png"
B = discord.ButtonStyle


@dataclass
class Screen:
    """embed + 버튼 + 붙일 그림 종류 ("scene" 배틀/보상 장면, "party" 파티, "summary" 상태창)"""
    embed: discord.Embed
    view: discord.ui.View
    image: str = "scene"
    image_args: dict = field(default_factory=dict)
    content: str | None = None


def _btn(view, label, uid, ver, act, arg="", style=B.secondary, emoji=None, row=None, disabled=False):
    view.add_item(discord.ui.Button(label=label[:80], style=style, emoji=emoji, row=row, disabled=disabled,
                                    custom_id=cid(uid, ver, act, arg)))


BATTLE_KO = {"wild": "", "legend": "✨ ", "trainer": "⚔️ ", "rival": "⚔️ ", "gymjr": "🏟️ ", "gym": "🏟️ ",
             "e4": "🏆 ", "champion": "👑 "}


def _base_embed(trainer: str, run: dict, title: str | None = None, color: int | None = None) -> discord.Embed:
    wave, phase = run["wave"], run["phase"]
    mode = run.get("mode", "adventure")
    if mode == "adventure":
        b = run.get("battle") if phase in ("battle", "switch", "learn") else None
        place = A.loc(run)["n"]
        title = title or (f"📍 {place}" + (f" · {BATTLE_KO.get(b['kind'], '')}{b['name']}" if b else ""))
        boss = bool(b and b["kind"] in ("gym", "e4", "champion", "legend"))
        color = color if color is not None else (0xE67E22 if boss else (0xE74C3C if b else 0x3BA55D))
    else:
        boss = E.is_boss_wave(wave)
        title = f"{MODE_KO[mode]} · " + (title or (f"웨이브 {wave}/{E.FINAL_WAVE} · {E.biome(wave)}"
                                                    + (" · 👑 보스전" if boss else "")))
        color = color if color is not None else {"over": 0x4F545C, "clear": 0xF1C40F}.get(phase, 0xE74C3C if boss else 0x5865F2)
    log = run.get("log") or []
    desc = josa("\n".join(x for x in log[-16:] if x)) or "​"
    embed = discord.Embed(title=title, description=desc[:4000], color=color)
    p = E.lead(run)
    extra = ""
    if mode == "adventure":
        region = A.region_of(run["loc"])
        extra = f" · {A.REGIONS[region]['n']} 배지 {len(A.region_badges(run, region))}개"
    embed.set_author(name=f"{trainer} 트레이너 · ₽{run.get('money', 0):,}{extra}", icon_url=D.sprite(p["sid"]))
    if run.get("rule"):
        embed.set_footer(text="이번 주 규칙: " + E.RULES[run["rule"]]
                         + (f" ({D.TYPE_KO[run['mono']]} 타입)" if run.get("mono") else ""))
    return embed


def _text_status(embed: discord.Embed, run: dict):
    """그림을 못 붙였을 때 대신 보여줄 글자 상태"""
    e, p = run.get("e"), E.lead(run)
    if e:
        embed.add_field(name=f"상대 · {D.name(e['sid'])} Lv.{e['lv']}", value=f"{mon_head(e)}\n{hp_line(e)}", inline=False)
    embed.add_field(name=f"나 · {D.name(p['sid'])} Lv.{p['lv']}", value=f"{mon_head(p)}\n{hp_line(p)}\n{exp_line(p)}",
                    inline=False)


def _image(embed: discord.Embed, run: dict, image: bool, file: str = SCENE_FILE):
    if image:
        embed.set_image(url=f"attachment://{file}")
    else:
        _text_status(embed, run)


def _move_label(mon: dict, i: int) -> str:
    m = D.MOVES[mon["moves"][i]]
    return (f"{m['n']} · {D.TYPE_KO[m['t']]} {'물리' if m['c'] == 0 else '특수'} {m['p']} · "
            f"PP {mon['pp'][i]}/{E.max_pp(mon, i)}")


def battle_screen(uid: int, trainer: str, run: dict, image: bool = True) -> Screen:
    """지금 단계(phase)에 맞는 기본 화면"""
    phase, ver = run["phase"], run.get("ver", 0)
    if phase == "field":
        return field_screen(uid, trainer, run, image)
    embed = _base_embed(trainer, run)
    view = discord.ui.View(timeout=None)

    if phase == "battle" and (run.get("battle") or {}).get("intro"):   # 포켓몬이 나오기 전: 트레이너 등장
        b = run["battle"]
        embed.description = josa(f"**{b['name']}**이(가) 승부를 걸어왔다!" + (f"\n\"{b['line']}\"" if b.get("line") else ""))
        if image:
            embed.set_image(url=f"attachment://{SCENE_FILE}")
        _btn(view, "승부!", uid, ver, "fight", style=B.danger, emoji="⚔️", row=0)
        _btn(view, "파티", uid, ver, "party", emoji="📋", row=0)
        embed.set_footer(text=f"{b['name']}의 포켓몬 {b.get('total', 1)}마리 · 승부를 누르면 포켓몬이 나와요.")
        return Screen(embed, _frozen(view), "intro")

    if phase == "battle":
        p, e = E.lead(run), run["e"]
        _image(embed, run, image)
        usable = E.usable_moves(p)
        if p["rc"]:
            _btn(view, "반동으로 쉬기", uid, ver, "move", 0)
        elif not usable:
            _btn(view, "발버둥 (PP가 모두 떨어졌어요)", uid, ver, "move", -1, style=B.danger)
        else:
            for i, mid in enumerate(p["moves"]):
                m = D.MOVES[mid]
                eff = D.effectiveness(m["t"], D.types(e["sid"]))
                style = B.success if eff > 1 else B.danger if eff == 0 else B.secondary if eff < 1 else B.primary
                _btn(view, _move_label(p, i), uid, ver, "move", i, style=style, row=0 if i < 2 else 1,
                     disabled=i not in usable)
        _btn(view, "가방", uid, ver, "bag", emoji="🎒", row=2)
        _btn(view, "교체", uid, ver, "swmenu", emoji="🔄", row=2, disabled=len(E.alive(run)) < 2)
        _btn(view, "파티", uid, ver, "party", emoji="📋", row=2)
        if run.get("mode") != "adventure":
            _btn(view, "포기", uid, ver, "quit", emoji="🏳️", row=2)
        elif (run.get("battle") or {}).get("kind") in ("wild", "legend"):
            _btn(view, "도망치기", uid, ver, "flee", emoji="🏃", row=2)
        tip = "초록 버튼은 효과가 굉장한 기술, 회색은 효과가 별로인 기술이에요."
        b = run.get("battle") or {}
        if b.get("total", 1) > 1:
            tip = f"{b['name']}의 남은 포켓몬 {len(b.get('queue', [])) + 1}마리 · " + tip
        if p.get("lock") is not None:
            tip = f"{E.item_name(p['held'])} 때문에 {D.MOVES[p['moves'][p['lock']]]['n']}만 쓸 수 있어요. 교체하면 풀려요."
        embed.set_footer(text=tip)
        return Screen(embed, _frozen(view))

    if phase == "switch":
        embed.title = "다음 포켓몬을 골라 주세요"
        if image:
            embed.set_image(url=f"attachment://{SCENE_FILE}")
        for i in E.alive(run):
            m = run["party"][i]
            _btn(view, f"{D.name(m['sid'])} Lv.{m['lv']}", uid, ver, "sw", i, style=B.primary, row=i // 3)
        return Screen(embed, _frozen(view), "party", {"title": "다음 포켓몬을 골라 주세요", "mark": E.alive(run)})

    if phase == "replace":
        new = run["pending"]["mon"]
        embed.title = "파티가 가득 찼어요"
        embed.add_field(name=f"새로 잡은 포켓몬 · {D.name(new['sid'])} Lv.{new['lv']}",
                        value=f"{D.type_text(new['sid'])} · 종족값 {D.bst(new['sid'])}\n놓아줄 포켓몬을 골라 주세요.",
                        inline=False)
        if image:
            embed.set_image(url=f"attachment://{SCENE_FILE}")
        for i, m in enumerate(run["party"]):
            _btn(view, f"{D.name(m['sid'])} Lv.{m['lv']} 놓아주기", uid, ver, "rel", i, row=i // 3)
        _btn(view, f"새로 잡은 {D.name(new['sid'])} 놓아주기", uid, ver, "relnew", style=B.danger, row=2)
        return Screen(embed, _frozen(view), "party", {"title": f"새 포켓몬: {D.name(new['sid'])} Lv.{new['lv']}"})

    if phase == "learn":
        li = E.learner(run)
        m = run["party"][li]
        new = D.MOVES[m["pend"][0]]
        name = D.name(m["sid"])
        embed.title = josa(f"{name}은(는) {new['n']}을(를) 배우고 싶어 한다!")
        embed.description = josa(
            f"하지만 {name}은(는) 이미 기술을 4개 알고 있어요. 잊을 기술을 고르세요.\n\n"
            f"**새 기술 · {new['n']}** {D.TYPE_KO[new['t']]} · {'물리' if new['c'] == 0 else '특수'} {new['p']} · "
            f"{'명중 ' + str(new['a']) if new['a'] else '반드시 명중'} · PP {new['pp']}")
        if image:
            embed.set_image(url=f"attachment://{SUMMARY_FILE}")
        for j in range(len(m["moves"])):
            _btn(view, f"잊기: {_move_label(m, j)}", uid, ver, "forget", j, style=B.primary, row=j // 2)
        _btn(view, f"{new['n']} 배우지 않기", uid, ver, "noforget", style=B.danger, row=2)
        return Screen(embed, _frozen(view), "summary", {"index": li})

    if phase == "reward":
        _image(embed, run, image)
        for i, key in enumerate(run["rewards"]):
            _btn(view, E.reward_info(key, run)["n"], uid, ver, "reward", i, style=B.success, emoji="🎁", row=0)
        cost = E.reroll_cost(run)
        _btn(view, f"다시 뽑기 ₽{cost:,}", uid, ver, "reroll", emoji="🎲", row=1, disabled=run["money"] < cost)
        _btn(view, "상점", uid, ver, "shop",
             emoji="🛒", row=1, disabled=not E.shop_open(run))
        _btn(view, "가방", uid, ver, "bag", emoji="🎒", row=1)
        _btn(view, "파티", uid, ver, "party", emoji="📋", row=1)
        _btn(view, "넘어가기", uid, ver, "skip", row=2)
        embed.add_field(name="🎁 보상을 하나 고르세요", value="\n".join(
            f"**{(r := E.reward_info(k, run))['n']}** — {r['d']}" for k in run["rewards"]) or "-", inline=False)
        embed.set_footer(text="보상을 고르기 전에 가방에서 회복하거나, 지닌 물건을 주거나, 상점에서 물건을 살 수 있어요.")
        return Screen(embed, _frozen(view))

    # over / clear
    _image(embed, run, image)
    cleared = run["wave"] if phase == "clear" else run["wave"] - 1
    p = run["party"]
    best = max(p, key=lambda m: m["lv"])
    embed.add_field(
        name="🏆 게임 클리어!" if phase == "clear" else "게임 종료",
        value=(f"**{cleared}웨이브** 돌파 · 스타팅 {D.name(run['starter'])}\n"
               f"파티 {len(p)}마리 · 잡은 포켓몬 {run.get('caught', 0)}마리 · 최고 레벨 {D.name(best['sid'])} Lv.{best['lv']}\n"
               f"한 방 최고 데미지 {run.get('best_hit', 0)} · 남은 돈 ₽{run.get('money', 0):,}"),
        inline=False)
    _btn(view, "새 게임 시작", uid, ver, "new", style=B.primary, emoji="🔁")
    return Screen(embed, _frozen(view))


def quit_screen(uid: int, trainer: str, run: dict, image: bool = True) -> Screen:
    sc = battle_screen(uid, trainer, run, image)
    sc.embed.add_field(name="🏳️ 정말 포기할까요?", value="포기하면 이번 게임은 여기서 끝나고 기록만 남아요.", inline=False)
    view = discord.ui.View(timeout=None)
    _btn(view, "정말 포기하기", uid, run["ver"], "quitok", style=B.danger)
    _btn(view, "계속하기", uid, run["ver"], "back")
    sc.view = _frozen(view)
    return sc


# ---------- 가방 ----------
def bag_categories(run: dict) -> list[str]:
    cats = {E.ITEMS[k]["cat"] for k in run["bag"]}
    return [c for c in E.CAT_ORDER if c in cats]


def default_bag_category(run: dict) -> str | None:
    cats = bag_categories(run)
    pref = ["ball", "heal", "revive", "pp", "battle", "status"] if run["phase"] == "battle" else \
        ["held", "evo", "heal", "revive", "pp", "ppup", "status", "ball", "battle"]
    for c in pref:
        if c in cats:
            return c
    return cats[0] if cats else None


def bag_screen(uid: int, trainer: str, run: dict, cat: str | None = None, image: bool = True) -> Screen:
    ver, in_battle = run["ver"], run["phase"] == "battle"
    cats = bag_categories(run)
    cat = cat if cat in cats else default_bag_category(run)
    embed = _base_embed(trainer, run, title="🎒 가방" + (f" · {E.CAT_KO[cat]}" if cat else ""), color=0xC27C0E)
    adv = run.get("mode") == "adventure"
    if in_battle:
        embed.description = ("배틀 중에 쓰면 턴을 써요 (상대가 공격해요). 기술머신·진화·지닌 물건 같은 건 "
                             + ("배틀 밖에서 쓸 수 있어요." if adv else "보상을 고를 때 쓸 수 있어요."))
    else:
        embed.description = ("배틀 밖이라 턴을 쓰지 않아요. 볼과 배틀용 아이템은 배틀 중에만 써요."
                             + (" 기술머신은 써도 없어지지 않아요." if adv else ""))
    _image(embed, run, image)
    view = discord.ui.View(timeout=None)
    if cats:
        view.add_item(discord.ui.Select(
            custom_id=cid(uid, ver, "bagcat"), placeholder="종류 고르기", row=0,
            options=[discord.SelectOption(label=f"{E.CAT_KO[c]} ({sum(v for k, v in run['bag'].items() if E.ITEMS[k]['cat'] == c)})",
                                          value=c, default=c == cat) for c in cats]))
    items = [k for k in sorted(run["bag"], key=lambda k: list(E.ITEMS).index(k)) if E.ITEMS[k]["cat"] == cat][:15]
    lines = []
    for n, item in enumerate(items):
        it, cnt = E.ITEMS[item], run["bag"][item]
        lines.append(f"**{E.item_name(item)}** x{cnt} — {it['d']}")
        ok = E.item_usable_now(run, item) and (E.is_ball(item) or bool(E.item_targets(run, item)))
        label = f"{E.item_name(item)} x{cnt}"
        if E.is_ball(item) and in_battle:
            if not E.can_catch(run):
                ok = False
                label += " (남의 포켓몬)"
            elif E.allowed(run, run["e"]["sid"]):
                label += f" ({int(E.catch_chance(run, item) * 100)}%)"
            else:
                ok = False
                label += " (규칙상 못 잡아요)"
        _btn(view, label, uid, ver, "ball" if E.is_ball(item) else "item", item,
             style=B.success if ok else B.secondary, row=1 + n // 5, disabled=not ok)
    embed.add_field(name="아이템", value="\n".join(lines)[:1024] or "가방이 비어 있어요.", inline=False)
    _btn(view, "돌아가기", uid, ver, "back", row=4)
    return Screen(embed, _frozen(view))


def target_screen(uid: int, trainer: str, run: dict, title: str, act: str, key: str, targets: list[int],
                  image: bool = True, item: str | None = None) -> Screen:
    """아이템이나 보상을 쓸 포켓몬 고르기"""
    ver = run["ver"]
    embed = _base_embed(trainer, run, title=title, color=0x3BA55D)
    embed.description = "어느 포켓몬에게 쓸까요?"
    if image:
        embed.set_image(url=f"attachment://{SCENE_FILE}")
    view = discord.ui.View(timeout=None)
    for i in targets:
        m = run["party"][i]
        label = f"{D.name(m['sid'])} Lv.{m['lv']} ({m['hp']}/{E.max_hp(m)})"
        evo_item = item or (key.partition(":")[2] if key.startswith("evo:") else None)
        if evo_item and E.ITEMS.get(evo_item, {}).get("cat") == "evo" and E.evo_child(m, evo_item):
            label = f"{D.name(m['sid'])} → {D.name(E.evo_child(m, evo_item))}"
        elif m.get("held") and (key.startswith("held:") or E.ITEMS.get(item or "", {}).get("cat") == "held"):
            label += f" · {E.item_name(m['held'])} 들고 있음"
        _btn(view, label, uid, ver, act, f"{key}.{i}", style=B.primary, row=i // 3)
    _btn(view, "돌아가기", uid, ver, "back", row=2)
    return Screen(embed, _frozen(view), "party", {"title": title, "mark": targets})


def move_pick_screen(uid: int, trainer: str, run: dict, item: str, target: int, image: bool = True) -> Screen:
    """PP에이드·포인트업처럼 기술 하나에 쓰는 아이템: 기술 고르기"""
    ver = run["ver"]
    m = run["party"][target]
    embed = _base_embed(trainer, run, title=f"🎒 {E.item_name(item)} · {D.name(m['sid'])}", color=0x3BA55D)
    embed.description = "어느 기술에 쓸까요?"
    if image:
        embed.set_image(url=f"attachment://{SUMMARY_FILE}")
    view = discord.ui.View(timeout=None)
    ok = E.item_moves(run, item, target)
    for j in range(len(m["moves"])):
        _btn(view, _move_label(m, j), uid, ver, "itemm", f"{item}.{target}.{j}", style=B.primary, row=j // 2,
             disabled=j not in ok)
    _btn(view, "돌아가기", uid, ver, "back", row=2)
    return Screen(embed, _frozen(view), "summary", {"index": target})


def switch_screen(uid: int, trainer: str, run: dict, image: bool = True) -> Screen:
    ver = run["ver"]
    targets = [i for i in E.alive(run) if i != run["active"]]
    embed = _base_embed(trainer, run, title="🔄 교체", color=0x3BA55D)
    embed.description = "누구로 바꿀까요? 교체하면 턴을 써요 (상대가 공격해요)."
    if image:
        embed.set_image(url=f"attachment://{SCENE_FILE}")
    view = discord.ui.View(timeout=None)
    for i in targets:
        m = run["party"][i]
        _btn(view, f"{D.name(m['sid'])} Lv.{m['lv']}", uid, ver, "sw", i, style=B.primary, row=i // 3)
    _btn(view, "돌아가기", uid, ver, "back", row=2)
    return Screen(embed, _frozen(view), "party", {"title": "누구로 바꿀까요?", "mark": targets})


# ---------- 상점 ----------
SHOP_CATS = {"ball": "볼", "heal": "회복", "status": "상태이상·기절", "pp": "PP", "battle": "배틀용"}


def _shop_cat(item: str) -> str:
    c = E.ITEMS[item]["cat"]
    return "status" if c == "revive" else c


def shop_screen(uid: int, trainer: str, run: dict, cat: str | None = None, image: bool = True) -> Screen:
    ver = run["ver"]
    cat = cat if cat in SHOP_CATS else "ball"
    embed = _base_embed(trainer, run, title=f"🛒 상점 · {SHOP_CATS[cat]} · 소지금 ₽{run['money']:,}", color=0x1ABC9C)
    embed.description = "산 물건은 가방에 들어가요. 웨이브가 올라갈수록 조금씩 비싸져요."
    _image(embed, run, image)
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Select(
        custom_id=cid(uid, ver, "shopcat"), placeholder="종류 고르기", row=0,
        options=[discord.SelectOption(label=v, value=k, default=k == cat) for k, v in SHOP_CATS.items()]))
    lines = []
    for n, item in enumerate(i for i in E.SHOP if _shop_cat(i) == cat):
        it, price = E.ITEMS[item], E.shop_price(run, item)
        have = run["bag"].get(item, 0)
        lines.append(f"**{E.item_name(item)}** ₽{price:,} — {it['d']}" + (f" (가지고 있는 수 {have})" if have else ""))
        _btn(view, f"{E.item_name(item)} ₽{price:,}", uid, ver, "buy", item, style=B.primary, row=1 + n // 4,
             disabled=run["money"] < price)
    embed.add_field(name="팔고 있는 물건", value="\n".join(lines)[:1024], inline=False)
    _btn(view, "돌아가기", uid, ver, "back", row=4)
    return Screen(embed, _frozen(view))


# ---------- 모험: 필드 ----------
def field_screen(uid: int, trainer: str, run: dict, image: bool = True) -> Screen:
    """마을·도로에 서 있을 때: 탐색, 트레이너, 체육관, 센터, 상점, PC, 이동"""
    ver = run.get("ver", 0)
    L = A.loc(run)
    embed = _base_embed(trainer, run)
    if image:
        embed.set_image(url=f"attachment://{SCENE_FILE}")
    view = discord.ui.View(timeout=None)
    if A.in_league(run):   # 사천왕 방 사이
        nxt = run["chain"][0]["name"]
        embed.title = f"🏆 포켓몬 리그 · 다음 상대 {nxt}"
        _btn(view, f"{nxt}에게 도전하기", uid, ver, "next", style=B.danger, emoji="⚔️", row=0)
        _btn(view, "가방", uid, ver, "bag", emoji="🎒", row=1)
        _btn(view, "파티", uid, ver, "party", emoji="📋", row=1)
        embed.set_footer(text="사천왕은 연달아 싸워요. 가방으로 회복하고 다음 방으로 들어가세요. (지면 포켓몬센터로 돌아가요)")
        return Screen(embed, _frozen(view), "field", {"place": run.get("place") or "field"})

    if L.get("wild"):
        _btn(view, "풀숲 탐색", uid, ver, "explore", style=B.success, emoji="🌿", row=0)
    left = A.trainers_left(run)
    if L.get("trainers"):
        _btn(view, f"트레이너와 싸우기 ({len(left)}명 남음)" if left else "트레이너를 모두 이겼어요", uid, ver, "trainer",
             style=B.primary, emoji="⚔️", row=0, disabled=not left)
    gkey, ok, why = A.gym_state(run)
    if gkey:
        g = A.GYMS[gkey]
        label = (f"체육관 도전 · 관장 {g['leader']}" if ok else
                 (f"{g['badge']} 획득!" if gkey in run["badges"] else f"체육관 ({why})"))
        _btn(view, label, uid, ver, "gym", style=B.danger, emoji="🏟️", row=0, disabled=not ok)
    if L.get("league"):
        league, ok, why = A.league_info(run)
        name = f"{A.REGIONS[league]['n']} 리그"
        _btn(view, (f"{name} 도전" if ok else f"{name} ({why})"), uid, ver, "league",
             style=B.danger, emoji="🏆", row=0, disabled=not ok)
    lg = A.legend_available(run)
    if lg:
        _btn(view, "기운이 느껴지는 곳으로", uid, ver, "legend", style=B.danger, emoji="✨", row=0)
    if A.gift_available(run):
        _btn(view, "포켓몬 받기", uid, ver, "gift", style=B.success, emoji="🎁", row=0)
    gc = A.gift_choices(run)
    if gc:
        for sid in gc[0]:
            _btn(view, f"공박사: {D.name(sid)} 받기", uid, ver, "gift2", sid, style=B.success, emoji="🎁", row=4)

    if A.has_center(run):
        _btn(view, "집에서 쉬기" if L.get("home") else "포켓몬센터", uid, ver, "heal", emoji="🏥", row=1)
        _btn(view, "PC", uid, ver, "pc", emoji="💻", row=1)
    if L.get("mart"):
        _btn(view, "백화점" if L.get("dept") else "프렌들리숍", uid, ver, "mart", emoji="🛒", row=1)
    _btn(view, "이동하기", uid, ver, "go", style=B.primary, emoji="🗺️", row=1)
    _btn(view, "가방", uid, ver, "bag", emoji="🎒", row=2)
    _btn(view, "파티", uid, ver, "party", emoji="📋", row=2)
    if len(run["party"]) > 1:
        view.add_item(discord.ui.Select(
            custom_id=cid(uid, ver, "lead"), placeholder=f"맨 앞: {D.name(run['party'][0]['sid'])} (바꾸려면 고르세요)", row=3,
            options=[discord.SelectOption(label=f"{i + 1}. {D.name(m['sid'])} Lv.{m['lv']}", value=str(i),
                                          description=f"HP {m['hp']}/{E.max_hp(m)}", default=i == 0)
                     for i, m in enumerate(run["party"])]))
    if not image:
        embed.add_field(name="파티", value="\n".join(f"{D.name(m['sid'])} Lv.{m['lv']} {hp_line(m)}"
                                                     for m in run["party"]), inline=False)
    places = []
    for k, ok, why in A.neighbors(run):
        places.append(f"{A.LOC[k]['n']}" + ("" if ok else f" 🔒 {why}"))
    embed.add_field(name="갈 수 있는 곳", value=" · ".join(places), inline=False)
    cap = "없음" if A.level_cap(run) >= E.MAX_LEVEL else f"Lv.{A.level_cap(run)}"
    region = A.region_of(run["loc"])
    embed.set_footer(text=f"{A.REGIONS[region]['n']} 배지 {len(A.region_badges(run, region))}/8 · 레벨 제한 {cap} · "
                          f"박스 {len(run['box'])}마리")
    if run.get("result") and image:   # 배틀이 막 끝났으면 결과 (포켓몬마다 얻은 경험치)
        embed.title = "🏅 배틀 결과 · " + embed.title
        return Screen(embed, _frozen(view), "result")
    return Screen(embed, _frozen(view), "field", {"place": run.get("place") or "field"})


def move_screen(uid: int, trainer: str, run: dict, image: bool = True) -> Screen:
    ver = run["ver"]
    embed = _base_embed(trainer, run, title=f"🗺️ 어디로 갈까요? · 지금 {A.loc(run)['n']}", color=0x3498DB)
    embed.description = "갈 곳을 고르세요. 잠긴 곳은 배지를 더 모으면 열려요."
    if image:
        embed.set_image(url=f"attachment://{SCENE_FILE}")
    view = discord.ui.View(timeout=None)
    for n, (k, ok, why) in enumerate(A.neighbors(run)):
        L = A.LOC[k]
        icon = {"town": "🏘️", "route": "🌿", "cave": "⛰️", "building": "🏢", "water": "🌊"}[L["kind"]]
        _btn(view, L["n"] + ("" if ok else f" ({why})"), uid, ver, "goto", k, style=B.primary if ok else B.secondary,
             emoji=icon, row=n // 3, disabled=not ok)
    _btn(view, "돌아가기", uid, ver, "back", row=4)
    return Screen(embed, _frozen(view), "map")


PC_PAGE = 25


def pc_screen(uid: int, trainer: str, run: dict, page: int = 0, image: bool = True) -> Screen:
    ver = run["ver"]
    box = run["box"]
    pages = max(1, (len(box) + PC_PAGE - 1) // PC_PAGE)
    page = max(0, min(page, pages - 1))
    embed = _base_embed(trainer, run, title=f"💻 PC · 박스 {len(box)}마리", color=0x95A5A6)
    embed.description = ("파티의 포켓몬을 맡기거나, 박스의 포켓몬을 데려와요. 맡긴 포켓몬은 회복되고, "
                         "지니고 있던 물건은 가방에 돌아와요.")
    if image:
        embed.set_image(url=f"attachment://{SCENE_FILE}")
    view = discord.ui.View(timeout=None)
    for i, m in enumerate(run["party"]):
        _btn(view, f"맡기기: {D.name(m['sid'])} Lv.{m['lv']}", uid, ver, "dep", i, row=i // 3,
             disabled=len(run["party"]) <= 1)
    if box:
        chunk = list(enumerate(box))[page * PC_PAGE:(page + 1) * PC_PAGE]
        view.add_item(discord.ui.Select(
            custom_id=cid(uid, ver, "wd"), row=2,
            placeholder=("데려올 포켓몬 고르기" if len(run["party"]) < E.MAX_PARTY else "파티가 가득 찼어요 (먼저 맡기세요)")
            + (f" ({page + 1}/{pages}쪽)" if pages > 1 else ""),
            disabled=len(run["party"]) >= E.MAX_PARTY,
            options=[discord.SelectOption(label=f"{D.name(m['sid'])} Lv.{m['lv']}", value=str(j),
                                          description=f"{D.type_text(m['sid'])} · 종족값 {D.bst(m['sid'])}")
                     for j, m in chunk]))
        embed.add_field(name=f"박스 ({len(box)}마리)", value=", ".join(
            f"{D.name(m['sid'])} Lv.{m['lv']}" for m in box[:60])[:1024], inline=False)
    else:
        embed.add_field(name="박스", value="비어 있어요. 파티가 6마리일 때 잡은 포켓몬은 여기로 와요.", inline=False)
    if pages > 1:
        _btn(view, "이전 쪽", uid, ver, "pc", page - 1, row=3, disabled=page == 0)
        _btn(view, "다음 쪽", uid, ver, "pc", page + 1, row=3, disabled=page >= pages - 1)
    _btn(view, "돌아가기", uid, ver, "back", row=4)
    return Screen(embed, _frozen(view), "pc", {"page": page})


MART_CATS = {"ball": "볼", "heal": "회복", "pp": "PP", "battle": "배틀용", "vit": "영양제", "evo": "진화", "tm": "기술머신"}


def _mart_cat(item: str) -> str:
    c = E.ITEMS[item]["cat"]
    return "heal" if c in ("status", "revive") else c


def mart_screen(uid: int, trainer: str, run: dict, cat: str | None = None, image: bool = True) -> Screen:
    ver = run["ver"]
    items = A.mart_items(run)
    cats = [c for c in MART_CATS if any(_mart_cat(i) == c for i in items)]
    cat = cat if cat in cats else (cats[0] if cats else "ball")
    L = A.loc(run)
    shop = "백화점" if L.get("dept") else "프렌들리숍"
    embed = _base_embed(trainer, run, title=f"🛒 {L['n']} {shop} · {MART_CATS.get(cat, '')} · 소지금 ₽{run['money']:,}",
                        color=0x1ABC9C)
    embed.description = ("점원: \"어서 오세요!\" 배지가 많을수록 파는 물건이 늘어나요."
                         + (" 백화점에서는 영양제·진화의 돌·기술머신도 팔아요." if L.get("dept") else ""))
    if image:
        embed.set_image(url=f"attachment://{SCENE_FILE}")
    view = discord.ui.View(timeout=None)
    if len(cats) > 1:
        view.add_item(discord.ui.Select(
            custom_id=cid(uid, ver, "martcat"), placeholder="종류 고르기", row=0,
            options=[discord.SelectOption(label=MART_CATS[c], value=c, default=c == cat) for c in cats]))
    sold = [i for i in items if _mart_cat(i) == cat]
    many = cat in ("ball", "heal") and len(sold) * 2 <= 15
    lines, n = [], 0
    for item in sold:
        price, have = A.price(item), run["bag"].get(item, 0)
        tm_have = E.ITEMS[item]["cat"] == "tm" and have
        lines.append(f"**{E.item_name(item)}** ₽{price:,} — {E.ITEMS[item]['d']}" + (f" (가진 수 {have})" if have else ""))
        _btn(view, f"{E.item_name(item)} ₽{price:,}" + (" (있음)" if tm_have else ""), uid, ver, "buy", f"{item}.1",
             style=B.primary, row=1 + n // 5, disabled=run["money"] < price or bool(tm_have))
        n += 1
        if many:
            _btn(view, f"x5 ₽{price * 5:,}", uid, ver, "buy", f"{item}.5", row=1 + n // 5, disabled=run["money"] < price * 5)
            n += 1
    embed.add_field(name="팔고 있는 물건", value="\n".join(lines)[:1024] or "-", inline=False)
    _btn(view, "돌아가기", uid, ver, "back", row=4)
    return Screen(embed, _frozen(view), "field", {"place": "mart"})


# ---------- 파티·상세 정보 ----------
def party_screen(uid: int, trainer: str, run: dict, image: bool = True) -> Screen:
    """📋 파티 (본인에게만 보이는 메시지). 버튼으로 한 마리씩 자세히 볼 수 있다."""
    embed = discord.Embed(title=f"📋 {trainer} 트레이너의 파티", color=0x5865F2)
    where = (f"배지 {len(run['badges'])}개 · {A.loc(run)['n']} · 박스 {len(run['box'])}마리"
             if run.get("mode") == "adventure" else f"웨이브 {run['wave']}")
    embed.description = (f"소지금 ₽{run['money']:,} · {where} · 잡은 포켓몬 {run.get('caught', 0)}마리\n"
                         f"가방: 아이템 {sum(run['bag'].values())}개 ({', '.join(E.CAT_KO[c] for c in bag_categories(run)) or '비어 있음'})")
    if image:
        embed.set_image(url=f"attachment://{SCENE_FILE}")
    embed.add_field(name="파티", value="\n".join(
        f"{i + 1}. {D.name(m['sid'])} Lv.{m['lv']}" + ("" if image else f" {hp_line(m)}")
        + (f" · 🎒 {E.item_name(m['held'])}" if m.get("held") else "") for i, m in enumerate(run["party"])), inline=False)
    view = discord.ui.View(timeout=None)
    for i, m in enumerate(run["party"]):
        _btn(view, f"{i + 1}. {D.name(m['sid'])}", uid, 0, "info", i, row=i // 3)
    return Screen(embed, _frozen(view), "party", {"title": "내 파티"})


def mon_detail(trainer: str, run: dict, index: int | None = None, image: bool = False) -> discord.Embed:
    """한 마리 상세 정보. image=True면 능력치·HP는 그림(summary.png)이 보여준다."""
    p = run["party"][run["active"] if index is None else index]
    e = discord.Embed(title=f"{D.name(p['sid'])} Lv.{p['lv']}",
                      description=None if image else f"{mon_head(p)}\n{hp_line(p)}\n{exp_line(p)}",
                      color=TYPE_COLOR.get(D.types(p["sid"])[0], 0x5865F2))
    if not image:
        stats = E.stats_line(p)
        e.add_field(name="능력치", value="\n".join(
            f"{n} **{v}**" + (f" (+{p['vit'][i] * 10}%)" if p["vit"][i] else "") for i, (n, v) in enumerate(stats)))
    moves = []
    for mid in p["moves"]:
        m = D.MOVES[mid]
        acc = f"명중 {m['a']}" if m["a"] else "반드시 명중"
        extra = []
        if m.get("h"):
            extra.append(f"{m['h'][0]}~{m['h'][1]}회" if m["h"][0] != m["h"][1] else f"{m['h'][0]}회")
        if m.get("dr"):
            extra.append(f"흡수 {m['dr']}%" if m["dr"] > 0 else f"반동 {-m['dr']}%")
        if m.get("rc"):
            extra.append("다음 턴 쉬기")
        if m.get("ai"):
            extra.append(f"{m['ai'][1]}% {E.STATUS_KO[E.AILMENT[m['ai'][0]]]}")
        if m.get("pr", 0) > 0:
            extra.append("선공")
        j = len(moves)
        moves.append(f"**{m['n']}** {D.TYPE_KO[m['t']]} · {'물리' if m['c'] == 0 else '특수'} {m['p']} · {acc} · "
                     f"PP {p['pp'][j]}/{E.max_pp(p, j)}" + (f" · {', '.join(extra)}" if extra else ""))
    e.add_field(name="기술", value="\n".join(moves), inline=False)
    nxt = [(l, mid) for l, mid in D.SPECIES[p["sid"]]["ls"] if l > p["lv"]][:3]
    evo = D.SPECIES[p["sid"]]["evo"]
    tips = []
    if nxt:
        tips.append("다음에 배울 기술: " + ", ".join(f"Lv.{l} {D.MOVES[mid]['n']}" for l, mid in nxt))
    if evo:
        how_ko = {"lv": lambda v: f"Lv.{v}", "item": lambda v: E.item_name(v), "trade": lambda v: "연결의끈",
                  "other": lambda v: f"Lv.{E.OTHER_EVO_LEVEL}"}
        tips.append("진화: " + ", ".join(f"{how_ko[how](val)} → {D.name(c)}" for c, how, val in evo))
    if run.get("exp_mult", 1) > 1:
        tips.append(f"학습장치: 경험치 {int(run['exp_mult'] * 100)}%")
    if p.get("held"):
        e.add_field(name="지닌 물건", value=f"**{E.item_name(p['held'])}** — {E.HELD[p['held']]}", inline=False)
    if tips:
        e.add_field(name="앞으로", value="\n".join(tips), inline=False)
    if image:
        e.set_image(url=f"attachment://{SUMMARY_FILE}")
    else:
        e.set_thumbnail(url=D.artwork(p["sid"]))
    where = f"배지 {len(run['badges'])}개" if run.get("mode") == "adventure" else f"웨이브 {run['wave']}"
    e.set_footer(text=f"{trainer} 트레이너 · {where} · 스타팅 {D.name(run['starter'])}")
    return e


# ---------- 메뉴 ----------
MENU = [("new", "모험", "🗺️"), ("daily", "데일리", "📅"), ("challenge", "주간 챌린지", "🏆"),
        ("resume", "이어하기", "▶️"), ("dex", "도감", "📖"), ("records", "기록·랭킹", "📊"), ("help", "도움말", "❔"),
        ("reset", "모험 초기화", "🗑️")]


def menu_view(uid: int) -> discord.ui.View:
    """uid=0 이면 누구나 누를 수 있는 공용 패널"""
    view = discord.ui.View(timeout=None)
    for i, (act, label, emoji) in enumerate(MENU):
        view.add_item(discord.ui.Button(label=label, emoji=emoji, row=i // 4,
                                        style=discord.ButtonStyle.primary if act == "new" else discord.ButtonStyle.secondary,
                                        custom_id=f"pm:{uid}:{act}"))
    return _frozen(view)


MENU_FILE = "menu.png"


def menu_embed(public: bool = False, image: bool = False) -> discord.Embed:
    e = discord.Embed(title="🎮 포켓몬 모험", color=0x5865F2, description=(
        "관동에서 배지 8개를 모아 챔피언이 되고, 같은 포켓몬과 성도·호연까지 도전해요.\n"
        "**모험** 시작·이어하기 · **데일리** 하루 한 번 · **주간 챌린지** 주에 한 번 · **모험 초기화** 처음부터"))
    if image:
        e.set_image(url=f"attachment://{MENU_FILE}")
    if public:
        e.set_footer(text="누구나 버튼을 눌러 시작할 수 있어요. 게임은 전용 스레드에서 진행돼요.")
    return e


HELP = {   # 주제: (메뉴 이름, 이모지, 한 줄 설명, [(제목, 내용)])
    "start": ("시작하기", "🎮", "처음 하는 법", [
        ("모험 시작", "`/메뉴`의 🗺️ 모험 버튼이나 `/스타팅`으로 시작해요. 게임은 나만의 스레드에서 진행돼요.\n"
                    "① 오박사 설명 → ② 주인공 고르기 (역대 주인공 20명) → ③ 스타팅 고르기 (1~9세대 27마리) 순서예요."),
        ("버튼으로 진행", "화면 아래 버튼을 눌러 진행해요. 버튼은 게임 주인만 누를 수 있어요. "
                      "화면이 오래돼서 안 눌리면 `/이어하기`로 지금 화면을 다시 불러와요."),
        ("저장", "진행은 자동으로 저장돼요. `/초기화`로 모험을 처음부터 다시 할 수 있어요 (도감 기록은 남아요)."),
    ]),
    "commands": ("명령어", "⌨️", "모든 명령어", [
        ("모험", "`/메뉴` 내 메뉴 카드와 버튼 · `/스타팅` 모험 시작·이어서 · `/이어하기` 진행 중인 화면 다시 열기\n"
               "`/주인공` 주인공 바꾸기 · `/초기화` 모험 처음부터"),
        ("포켓몬·기록", "`/내포켓몬` 파티 · `/도감` 세대별 그림 도감 · `/기록` 내 기록과 랭킹"),
        ("데일리·챌린지", "`/데일리` 오늘의 도전 · `/챌린지` 이번 주 도전"),
        ("관리자", "`/세팅` 이 채널에 누구나 쓰는 게임 버튼 패널 올리기"),
        ("도움말", "`/도움말` 이 화면"),
    ]),
    "adventure": ("모험", "🗺️", "이동·탐색·체육관·센터", [
        ("이동", "🗺️ 이동하기로 연결된 마을·도로·동굴로 가요. 🔒 잠긴 곳은 배지를 더 모으면 열려요."),
        ("탐색·트레이너", "🌿 풀숲 탐색으로 야생 포켓몬을 만나거나 아이템을 주워요. "
                       "⚔️ 트레이너는 장소마다 한 번씩 싸울 수 있고, 이기면 상금을 받아요."),
        ("체육관·리그", "🏟️ 체육관 트레이너를 이기면 관장과 싸워 배지와 기술머신을 받아요. "
                     "배지 8개면 🏆 포켓몬 리그에서 사천왕 4명과 챔피언에게 연달아 도전해요 (방 사이에 가방으로 회복)."),
        ("레벨 제한", "배지가 늘수록 더 높은 레벨까지 말을 들어요 (관동 16 → … → 65). 필드 화면과 메뉴 카드에 지금 제한이 나와요."),
        ("센터·상점·PC", "🏥 포켓몬센터에서 무료로 회복해요. 파티가 모두 쓰러지면 돈을 조금 잃고 마지막 센터로 돌아가요.\n"
                      "🛒 상점은 배지가 늘수록 파는 물건이 늘어요. 💻 PC에서 포켓몬을 맡기고 데려와요 (파티가 6마리면 잡은 포켓몬은 PC로)."),
    ]),
    "battle": ("배틀", "⚔️", "기술·잡기·상태이상", [
        ("기술", "기술 버튼으로 공격해요. 🟩 초록은 효과가 굉장한 기술, ⬜ 회색은 효과가 별로인 기술, 🟥 빨강은 효과가 없는 기술이에요. "
               "기술마다 PP가 있고, 센터에서 다시 채워져요."),
        ("가방·교체·도망", "🎒 가방에서 볼·회복약을 쓰고, 🔄 교체로 포켓몬을 바꿔요 (둘 다 턴을 써요). "
                       "🏃 도망치기는 야생·전설 배틀에서만 돼요."),
        ("잡기", "야생 포켓몬에게 볼을 던져요. HP가 적을수록, 상태이상일수록 잘 잡혀요. 다른 트레이너의 포켓몬은 못 잡아요."),
        ("상태이상", "마비·화상·독·얼음 상태가 되면 정보창 HP 아래에 표시돼요. 센터나 회복약으로 고쳐요."),
        ("트레이너 등장", "트레이너·관장·라이벌과 싸울 때는 먼저 상대가 나와서 대사를 해요. ⚔️ 승부!를 누르면 포켓몬이 나와요."),
        ("배틀 화면", "배틀 화면은 움직이는 그림(GIF)이에요. 1~5세대는 블랙·화이트처럼 움직이고, 6세대부터는 통통 뛰어요."),
    ]),
    "growth": ("성장·진화", "⬆️", "레벨업·기술·진화·물건", [
        ("레벨업", "상대 포켓몬을 쓰러뜨리면 그 상대와 싸운 포켓몬(한 번이라도 나와 있던 포켓몬)만 경험치를 받아요. "
                 "기절한 포켓몬은 못 받아요. 배틀은 파티 맨 앞 포켓몬부터 나가요. "
                 "배틀이 끝나면 포켓몬마다 얻은 경험치와 레벨 변화를 보여 줘요. "
                 "레벨이 오르면 기술을 배우는데, 기술이 4개면 잊을 기술을 직접 골라요."),
        ("진화", "레벨, 진화의 돌, 연결의끈(통신 진화)으로 진화해요. 친밀도·시간 진화는 Lv.25에 진화해요."),
        ("물건", "기술머신은 몇 번이고 쓸 수 있어요. 영양제·이상한사탕은 가방에서 쓰고, 지닌 물건은 배틀에서 효과가 나요."),
    ]),
    "regions": ("지방·전설", "🌏", "성도·호연·전설 포켓몬", [
        ("다음 지방", "관동 챔피언이 되면 석영고원 동쪽 26·27번도로로 성도에, 성도 챔피언이 되면 담청시티 항구에서 배를 타고 호연에 가요.\n"
                   "파티·PC·가방·돈은 그대로지만, 새 지방에 처음 들어가면 레벨이 Lv.8로 맞춰져요 (진화·기술은 유지). "
                   "지방마다 스타팅을 하나 더 받아요."),
        ("전설", "관동: 썬더·프리저·파이어·잠만보, 챔피언 후 뮤츠·뮤\n성도: 라이코·앤테이·스이쿤·칠색조·루기아, 챔피언 후 세레비\n"
               "호연: 가이오가·그란돈·레쿠쟈, 챔피언 후 레지 3마리·라티아스·라티오스\n"
               "모험의 전설은 잘 잡히게 해 뒀고, 쓰러뜨리거나 도망쳐도 다시 만날 수 있어요."),
    ]),
    "waves": ("데일리·챌린지", "📅", "웨이브 게임과 랭킹", [
        ("데일리", "하루에 한 번, 모두가 같은 스타팅 후보·상대·보상으로 도전해요. 가장 멀리 간 웨이브로 오늘의 랭킹이 정해져요."),
        ("주간 챌린지", "주에 한 번, 매주 규칙이 바뀌어요 (단일 타입 / 아이템 금지 / 하드코어 / 레벨 제한). 주간 랭킹을 겨뤄요."),
        ("진행", "100웨이브가 마지막이에요. 10웨이브마다 보스(HP 보호막 2~5칸)와 새 지역(전체 회복)이 나와요. "
               "웨이브마다 보상 하나를 고르고, 돈으로 다시 뽑거나 상점에서 물건을 사요."),
    ]),
}


def help_embed(topic: str = "start") -> discord.Embed:
    topic = topic if topic in HELP else "start"
    label, emoji, _, fields = HELP[topic]
    e = discord.Embed(title=f"❔ 도움말 · {emoji} {label}", color=0x5865F2)
    for name, value in fields:
        e.add_field(name=name, value=value, inline=False)
    e.set_footer(text="아래 메뉴에서 다른 주제를 볼 수 있어요.")
    return e


def help_view(uid: int, topic: str = "start") -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Select(
        custom_id=f"pm:{uid}:helpt", placeholder="도움말 주제 고르기",
        options=[discord.SelectOption(label=label, value=k, emoji=emoji, description=desc, default=k == topic)
                 for k, (label, emoji, desc, _) in HELP.items()]))
    view.stop()
    return view


DEX_FILE = "dex.png"


def dex_screen(uid: int, trainer: str, dex: dict[int, int], gen: int, page: int,
               image: bool = True) -> tuple[discord.Embed, discord.ui.View]:
    """그림 도감: 세대 고르기 + 쪽 넘기기. 버튼 custom_id: pd:<유저>:<세대>:<쪽>"""
    from game import scene
    gen = max(1, min(9, gen))
    pages = scene.dex_pages(gen)
    page = max(0, min(page, pages - 1))
    region, a, b = scene.GENS[gen - 1]
    got = sum(1 for s in range(a, b + 1) if s in dex)
    e = discord.Embed(title=f"📖 {trainer}의 도감 · {gen}세대 {region}",
                      description=f"이 지방 **{got}/{b - a + 1}** · 전체 **{len(dex)}/{len(D.SPECIES)}**종 · "
                                  f"{page + 1}/{pages}쪽", color=0xD83C3C)
    if image:
        e.set_image(url=f"attachment://{DEX_FILE}")
    else:
        names = [f"`{s:03d}` {D.name(s) if s in dex else '???'}" for s in scene.dex_page_sids(gen, page)]
        e.add_field(name="목록", value="\n".join(names)[:1024], inline=False)
    view = discord.ui.View(timeout=None)
    opts = []
    for i, (r, lo, hi) in enumerate(scene.GENS, 1):
        n = sum(1 for s in range(lo, hi + 1) if s in dex)
        opts.append(discord.SelectOption(label=f"{i}세대 · {r}", value=str(i), description=f"{n}/{hi - lo + 1}",
                                         default=i == gen))
    view.add_item(discord.ui.Select(custom_id=f"pd:{uid}:sel:0", placeholder="세대 고르기", options=opts, row=0))
    view.add_item(discord.ui.Button(label="◀ 이전", style=discord.ButtonStyle.secondary, row=1,
                                    custom_id=f"pd:{uid}:{gen}:{page - 1}", disabled=page == 0))
    view.add_item(discord.ui.Button(label=f"{page + 1} / {pages}", style=discord.ButtonStyle.secondary, row=1,
                                    custom_id=f"pd:{uid}:{gen}:{page}:x", disabled=True))
    view.add_item(discord.ui.Button(label="다음 ▶", style=discord.ButtonStyle.secondary, row=1,
                                    custom_id=f"pd:{uid}:{gen}:{page + 1}", disabled=page >= pages - 1))
    return e, _frozen(view)


def dex_embed(trainer: str, dex: dict[int, int]) -> discord.Embed:
    total = len(D.SPECIES)
    e = discord.Embed(title=f"📖 {trainer}의 도감", color=0x3BA55D,
                      description=f"잡은 포켓몬 **{len(dex)}** / {total}종 · 관동 도감 "
                                  f"**{sum(1 for s in dex if s <= 151)}** / 151종")
    gens = [(1, 151), (152, 251), (252, 386), (387, 493), (494, 649), (650, 721), (722, 809), (810, 905), (906, 1025)]
    lines = []
    for g, (a, b) in enumerate(gens, 1):
        n = sum(1 for s in dex if a <= s <= b)
        lines.append(f"{g}세대 `{bar(n, b - a + 1, 8)}` {n}/{b - a + 1}")
    e.add_field(name="세대별", value="\n".join(lines), inline=True)
    by_type = {t: 0 for t in D.TYPE_KO}
    for s in dex:
        for t in D.types(s):
            by_type[t] += 1
    top = sorted(by_type.items(), key=lambda kv: -kv[1])[:9]
    e.add_field(name="많이 잡은 타입", value="\n".join(f"{D.TYPE_KO[t]} {n}" for t, n in top if n) or "-", inline=True)
    most = sorted(dex.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    if most:
        e.add_field(name="자주 잡은 포켓몬", value=", ".join(f"{D.name(s)}({n})" for s, n in most), inline=False)
    return e


def period_board_embed(title: str, rows: list[dict], me: int, extra: str = "") -> discord.Embed:
    e = discord.Embed(title=title, color=0xF1C40F, description=extra or None)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, r in enumerate(rows):
        who = f"**{r['name']}**" if r["user_id"] == me else r["name"]
        lines.append(f"{medals[i] if i < 3 else f'{i + 1}.'} {who} — {r['wave']}웨이브"
                     + (f" · {D.name(r['final'])}" if r.get("final") else "") + (" 🏆" if r.get("clear") else ""))
    e.add_field(name="랭킹", value="\n".join(lines) or "아직 기록이 없어요.", inline=False)
    return e


def adventure_board(rows: list[tuple[int, dict, int]], me: int) -> discord.Embed:
    """모험 랭킹. rows: (유저, 모험 상태, 도감 수) — 챔피언 횟수 → 배지 → 도감 순"""
    e = discord.Embed(title="🗺️ 관동 모험 랭킹", color=0x3BA55D)
    rows = sorted(rows, key=lambda r: (-r[1].get("hof3", 0), -r[1].get("hof2", 0), -r[1].get("hof", 0),
                                       -len(r[1]["badges"]), -r[2]))
    mine = next(((i, r) for i, r in enumerate(rows) if r[0] == me), None)
    if mine:
        i, (_, run, dex) = mine
        best = max(run["party"], key=lambda m: m["lv"])
        e.add_field(name="내 모험", value=(f"{i + 1}위 · {A.summary_line(run)} · 도감 {dex}종\n"
                                          f"에이스 {D.name(best['sid'])} Lv.{best['lv']}"), inline=False)
    else:
        e.add_field(name="내 모험", value="아직 모험을 시작하지 않았어요. `/스타팅`으로 시작해 보세요!", inline=False)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, run, dex) in enumerate(rows[:10]):
        name = run.get("name") or "트레이너"
        who = f"**{name}**" if uid == me else name
        lines.append(f"{medals[i] if i < 3 else f'{i + 1}.'} {who} — {A.summary_line(run)} · 도감 {dex}종")
    e.add_field(name="랭킹", value="\n".join(lines) or "아직 기록이 없어요.", inline=False)
    return e
