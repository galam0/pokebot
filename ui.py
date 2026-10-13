"""디스코드 화면(임베드·버튼) 만들기.

버튼 custom_id 형식: pr:<유저ID>:<게임 버전>:<동작>[:<값>]
- 유저ID로 본인만 누를 수 있게 하고, 게임 버전으로 지난 화면의 버튼을 막는다.
- View를 메모리에 등록하지 않고 bot.on_interaction 에서 직접 처리한다.
  → 봇이 재시작해도, 몇 시간이 지나도 버튼이 계속 동작한다.
"""

from dataclasses import dataclass, field

import discord

from game import data as D
from game import engine as E
from game.text import josa

REGIONS = {
    "관동": [1, 4, 7], "성도": [152, 155, 158], "호연": [252, 255, 258],
    "신오": [387, 390, 393], "하나": [495, 498, 501], "칼로스": [650, 653, 656],
    "알로라": [722, 725, 728], "가라르": [810, 813, 816], "팔데아": [906, 909, 912],
}
GEN = {name: i + 1 for i, name in enumerate(REGIONS)}

TYPE_COLOR = {10: 0xEE8130, 11: 0x6390F0, 12: 0x7AC74C}


MODE_PREFIX = {"normal": "", "daily": "d", "challenge": "c"}
MODE_KO = {"normal": "일반", "daily": "📅 데일리", "challenge": "🏆 주간 챌린지"}


def slot_of(uid: int, mode: str = "normal") -> str:
    """버튼 주인 표시: 일반 '123', 데일리 'd123', 챌린지 'c123'"""
    return f"{MODE_PREFIX[mode]}{uid}"


def parse_slot(slot: str) -> tuple[int, str]:
    for mode, pre in MODE_PREFIX.items():
        if pre and slot.startswith(pre):
            return int(slot[len(pre):]), mode
    return int(slot), "normal"


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
def region_screen(uid, dex_count: int = 0) -> tuple[str, list[discord.Embed], discord.ui.View]:
    view = discord.ui.View(timeout=None)
    select = discord.ui.Select(
        custom_id=cid(uid, 0, "region"), placeholder="지방을 골라주세요",
        options=[discord.SelectOption(label=f"{GEN[r]}세대 · {r}", value=r,
                                      description=" / ".join(D.name(s) for s in ids))
                 for r, ids in REGIONS.items()],
    )
    view.add_item(select)
    embed = discord.Embed(
        title="새 모험 준비",
        description=("함께 떠날 스타팅 포켓몬을 고르세요.\n\n"
                     f"• 야생 포켓몬을 이기며 웨이브를 하나씩 넘어가요. **{E.FINAL_WAVE}웨이브**가 마지막이에요.\n"
                     f"• {E.BIOME_SIZE}웨이브마다 👑 보스가 나오고, 보스를 넘기면 새 지역에서 회복돼요.\n"
                     "• 이길 때마다 보상을 하나 골라요. 쓰러지면 게임이 끝나요.\n"
                     "• 잡은 포켓몬은 도감에 남고, 다음 게임부터 스타팅으로 고를 수 있어요."),
        color=discord.Color.blurple(),
    )
    view.add_item(discord.ui.Button(label=f"도감에서 고르기 ({dex_count}종)", emoji="📖", style=discord.ButtonStyle.success,
                                    custom_id=cid(uid, 0, "dexpick", 0), disabled=dex_count == 0, row=1))
    return "", [embed], _frozen(view)


DEX_PAGE = 25


def dex_pick_screen(uid, sids: list[int], page: int = 0) -> tuple[str, list[discord.Embed], discord.ui.View]:
    """도감에서 해금된 포켓몬(진화 전 모습)을 스타팅으로 고르기"""
    pages = max(1, (len(sids) + DEX_PAGE - 1) // DEX_PAGE)
    page = max(0, min(page, pages - 1))
    chunk = sids[page * DEX_PAGE:(page + 1) * DEX_PAGE]
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Select(
        custom_id=cid(uid, 0, "starter"), placeholder=f"스타팅으로 고를 포켓몬 ({page + 1}/{pages}쪽)",
        options=[discord.SelectOption(label=f"No.{s} {D.name(s)}", value=str(s),
                                      description=f"{D.type_text(s)} · 종족값 {D.bst(s)}") for s in chunk]))
    view.add_item(discord.ui.Button(label="이전", style=discord.ButtonStyle.secondary, row=1,
                                    custom_id=cid(uid, 0, "dexpick", page - 1), disabled=page == 0))
    view.add_item(discord.ui.Button(label="다음", style=discord.ButtonStyle.secondary, row=1,
                                    custom_id=cid(uid, 0, "dexpick", page + 1), disabled=page >= pages - 1))
    view.add_item(discord.ui.Button(label="지방에서 고르기", style=discord.ButtonStyle.secondary, row=1,
                                    custom_id=cid(uid, 0, "regions")))
    embed = discord.Embed(title="📖 도감에서 스타팅 고르기",
                          description=(f"지금까지 잡은 포켓몬 {len(sids)}종을 고를 수 있어요 (진화 전 첫 모습, Lv.5로 시작).\n"
                                       "강한 포켓몬일수록 초반이 쉬워지지만, 웨이브는 똑같이 어려워져요."),
                          color=0x3BA55D)
    return "", [embed], _frozen(view)


def mode_start_screen(uid, mode: str, seed: str, starters: list[int]) -> tuple[str, list[discord.Embed], discord.ui.View]:
    """데일리·주간 챌린지 시작: 정해진 스타팅 3마리 중 고르기"""
    if mode == "daily":
        title = f"📅 데일리 · {seed}"
        desc = ("오늘은 모두가 **같은 상대, 같은 보상, 같은 갈림길**로 도전해요. 하루에 한 번만 할 수 있어요.\n"
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


def starter_screen(uid: int, region: str) -> tuple[str, list[discord.Embed], discord.ui.View]:
    ids = REGIONS[region]
    embeds = []
    view = discord.ui.View(timeout=None)
    for sid in ids:
        s = D.SPECIES[sid]
        st = s["s"]
        e = discord.Embed(
            title=D.name(sid),
            description=(f"{D.type_text(sid)} 타입 · 종족값 합계 {sum(st)}\n"
                         f"HP {st[0]} · 공격 {st[1]} · 방어 {st[2]}\n특공 {st[3]} · 특방 {st[4]} · 스피드 {st[5]}"),
            color=TYPE_COLOR.get(s["t"][0], 0x5865F2),
        )
        e.set_thumbnail(url=D.artwork(sid))
        embeds.append(e)
        view.add_item(discord.ui.Button(label=D.name(sid), style=discord.ButtonStyle.primary,
                                        custom_id=cid(uid, 0, "starter", sid)))
    view.add_item(discord.ui.Button(label="다른 지방", style=discord.ButtonStyle.secondary,
                                    custom_id=cid(uid, 0, "regions")))
    return f"**{GEN[region]}세대 · {region}** 스타팅 포켓몬이에요. 함께할 포켓몬을 골라주세요!", embeds, _frozen(view)


# ---------- 화면 ----------
SCENE_FILE = "scene.png"
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


def _base_embed(trainer: str, run: dict, title: str | None = None, color: int | None = None) -> discord.Embed:
    wave, phase = run["wave"], run["phase"]
    boss = E.is_boss_wave(wave)
    title = title or (f"웨이브 {wave}/{E.FINAL_WAVE} · {E.biome(wave)}" + (" · 👑 보스전" if boss else "")
                      + (" · ⚔️ 강적" if run.get("elite") and phase == "battle" else ""))
    mode = run.get("mode", "normal")
    if mode != "normal":
        title = f"{MODE_KO[mode]} · " + title
    color = color if color is not None else {"over": 0x4F545C, "clear": 0xF1C40F}.get(phase, 0xE74C3C if boss else 0x5865F2)
    log = run.get("log") or []
    desc = josa("\n".join(log[-16:])) or "​"
    embed = discord.Embed(title=title, description=desc[:4000], color=color)
    p = E.lead(run)
    embed.set_author(name=f"{trainer} 트레이너 · ₽{run.get('money', 0):,}", icon_url=D.sprite(p["sid"]))
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
    embed = _base_embed(trainer, run)
    view = discord.ui.View(timeout=None)

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
        _btn(view, "포기", uid, ver, "quit", emoji="🏳️", row=2)
        tip = "초록 버튼은 효과가 굉장한 기술, 회색은 효과가 별로인 기술이에요."
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

    if phase == "path":
        embed.title = "🧭 갈림길이 나왔어요"
        if image:
            embed.set_image(url=f"attachment://{SCENE_FILE}")
        embed.add_field(name="어느 길로 갈까요?", value="\n".join(
            f"**{E.PATHS[k]['n']}** — {E.PATHS[k]['d']}" for k in run.get("paths", [])), inline=False)
        for k in run.get("paths", []):
            _btn(view, E.PATHS[k]["n"], uid, ver, "path", k, style=B.primary)
        _btn(view, "파티", uid, ver, "party", emoji="📋", row=1)
        return Screen(embed, _frozen(view), "path")

    if phase == "reward":
        _image(embed, run, image)
        for i, key in enumerate(run["rewards"]):
            _btn(view, E.reward_info(key, run)["n"], uid, ver, "reward", i, style=B.success, emoji="🎁", row=0)
        if run.get("elite"):
            embed.title += " · ⚔️ 강적 보상"
        cost = E.reroll_cost(run)
        _btn(view, f"다시 뽑기 ₽{cost:,}", uid, ver, "reroll", emoji="🎲", row=1, disabled=run["money"] < cost)
        _btn(view, "상점" + (" (30% 할인)" if run.get("discount_wave") == run["wave"] else ""), uid, ver, "shop",
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
    embed.description = ("배틀 중에 쓰면 턴을 써요 (상대가 공격해요). 지닌 물건·진화·포인트업은 보상을 고를 때 쓸 수 있어요."
                         if in_battle else "보상을 고르기 전이라 턴을 쓰지 않아요. 볼과 배틀용 아이템은 배틀 중에만 써요.")
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
            if E.allowed(run, run["e"]["sid"]):
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


# ---------- 파티·상세 정보 ----------
def party_screen(uid: int, trainer: str, run: dict, image: bool = True) -> Screen:
    """📋 파티 (본인에게만 보이는 메시지). 버튼으로 한 마리씩 자세히 볼 수 있다."""
    embed = discord.Embed(title=f"📋 {trainer} 트레이너의 파티", color=0x5865F2)
    embed.description = (f"소지금 ₽{run['money']:,} · 웨이브 {run['wave']} · 잡은 포켓몬 {run.get('caught', 0)}마리\n"
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
    e.set_footer(text=f"{trainer} 트레이너 · 웨이브 {run['wave']} · 스타팅 {D.name(run['starter'])}")
    return e


# ---------- 메뉴 ----------
MENU = [("new", "새 게임", "🎮"), ("daily", "데일리", "📅"), ("challenge", "주간 챌린지", "🏆"),
        ("resume", "이어하기", "▶️"), ("dex", "도감", "📖"), ("records", "기록·랭킹", "📊"), ("help", "도움말", "❔")]


def menu_view(uid: int) -> discord.ui.View:
    """uid=0 이면 누구나 누를 수 있는 공용 패널"""
    view = discord.ui.View(timeout=None)
    for i, (act, label, emoji) in enumerate(MENU):
        view.add_item(discord.ui.Button(label=label, emoji=emoji, row=i // 4,
                                        style=discord.ButtonStyle.primary if act == "new" else discord.ButtonStyle.secondary,
                                        custom_id=f"pm:{uid}:{act}"))
    return _frozen(view)


def menu_embed(public: bool = False) -> discord.Embed:
    e = discord.Embed(title="🎮 포켓몬 로그라이크", color=0x5865F2, description=(
        "야생 포켓몬을 잡고 키우며 100웨이브까지 도전하는 PokeRogue식 게임이에요.\n\n"
        "**새 게임** 스타팅을 골라 시작 (잡은 포켓몬은 도감에 남아 다음 스타팅으로 쓸 수 있어요)\n"
        "**데일리** 오늘 모두 같은 조건으로 하루 한 번 도전\n"
        "**주간 챌린지** 이번 주 특별 규칙으로 도전\n"
        "**이어하기** 진행 중인 게임 화면 다시 불러오기"))
    if public:
        e.set_footer(text="누구나 버튼을 눌러 시작할 수 있어요. 게임은 전용 스레드에서 진행돼요.")
    return e


def help_embed() -> discord.Embed:
    e = discord.Embed(title="❔ 도움말", color=0x5865F2)
    e.add_field(name="배틀", value="기술 버튼으로 공격해요. 초록 버튼은 효과가 굉장한 기술이에요. "
                "🎒 가방(볼·회복약), 🔄 교체는 턴을 써요. 기술마다 PP가 있어요.", inline=False)
    e.add_field(name="웨이브", value=f"{E.BIOME_SIZE}웨이브마다 👑 보스가 나와요. 보스는 HP 보호막이 여러 칸이고, "
                "칸이 깨질 때마다 강해져요. 보스를 넘기면 새 지역에서 파티가 회복돼요.", inline=False)
    e.add_field(name="보상·상점·갈림길", value="이길 때마다 보상을 하나 골라요. 돈으로 다시 뽑거나 상점에서 살 수 있어요. "
                "가끔 갈림길에서 쉼터·강적·상인·수상한 상자·수련장 중 길을 골라요.", inline=False)
    e.add_field(name="포획·도감", value="야생 포켓몬은 볼로 잡아 파티(최대 6)에 넣어요. 잡은 포켓몬은 도감에 영구로 남고, "
                "새 게임에서 스타팅으로 고를 수 있어요.", inline=False)
    e.add_field(name="성장", value="기술머신, 진화의 돌, 지닌 물건, 이상한사탕, 비타민으로 강해져요. "
                "새 기술이 5번째면 잊을 기술을 골라요.", inline=False)
    return e


def dex_embed(trainer: str, dex: dict[int, int]) -> discord.Embed:
    total = len(D.SPECIES)
    e = discord.Embed(title=f"📖 {trainer}의 도감", color=0x3BA55D,
                      description=f"잡은 포켓몬 **{len(dex)}** / {total}종 · 스타팅으로 고를 수 있는 포켓몬 "
                                  f"**{len({E.root_species(s) for s in dex})}**종")
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


def records(trainer: dict | None, top: list[dict], me: int) -> discord.Embed:
    e = discord.Embed(title="🏆 PokeRogue 기록", color=0xF1C40F)
    if trainer:
        best = (f"{D.name(trainer['best_starter'])} → {D.name(trainer['best_final'])}"
                if trainer.get("best_starter") else "-")
        e.add_field(name="내 기록", value=(f"최고 **{trainer['best_wave']}웨이브** ({best})\n"
                                          f"게임 {trainer['runs']}번 · 클리어 {trainer['clears']}번 · 누적 {trainer['total_waves']}웨이브"),
                    inline=False)
    else:
        e.add_field(name="내 기록", value="아직 끝낸 게임이 없어요.", inline=False)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, t in enumerate(top):
        who = f"**{t['name']}**" if t["user_id"] == me else t["name"]
        mark = medals[i] if i < 3 else f"{i + 1}."
        fin = f" · {D.name(t['best_final'])}" if t.get("best_final") else ""
        lines.append(f"{mark} {who} — {t['best_wave']}웨이브{fin}")
    e.add_field(name="랭킹", value="\n".join(lines) or "아직 기록이 없어요.", inline=False)
    return e
