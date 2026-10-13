"""디스코드 화면(임베드·버튼) 만들기.

버튼 custom_id 형식: pr:<유저ID>:<게임 버전>:<동작>[:<값>]
- 유저ID로 본인만 누를 수 있게 하고, 게임 버전으로 지난 화면의 버튼을 막는다.
- View를 메모리에 등록하지 않고 bot.on_interaction 에서 직접 처리한다.
  → 봇이 재시작해도, 몇 시간이 지나도 버튼이 계속 동작한다.
"""

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


def cid(uid: int, ver: int, act: str, arg: str | int = "") -> str:
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
def region_screen(uid: int) -> tuple[str, list[discord.Embed], discord.ui.View]:
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
                     "• 이길 때마다 보상을 하나 골라요. 쓰러지면 게임이 끝나요."),
        color=discord.Color.blurple(),
    )
    return "", [embed], _frozen(view)


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


# ---------- 배틀 화면 ----------
SCENE_FILE = "scene.png"
SUMMARY_FILE = "summary.png"


def battle_screen(uid: int, trainer: str, run: dict, image: bool = False) -> tuple[discord.Embed, discord.ui.View]:
    """image=True면 HP·보상은 그림(scene.png)이 보여주고, 글로는 턴 기록과 버튼만 둔다."""
    p, e, wave, phase, ver = run["p"], run["e"], run["wave"], run["phase"], run.get("ver", 0)
    boss = E.is_boss_wave(wave)
    title = f"웨이브 {wave}/{E.FINAL_WAVE} · {E.biome(wave)}" + (" · 👑 보스전" if boss else "")
    color = {"over": 0x4F545C, "clear": 0xF1C40F}.get(phase, 0xE74C3C if boss else 0x5865F2)
    log = run.get("log") or []
    desc = josa("\n".join(log[-16:])) or "​"
    embed = discord.Embed(title=title, description=desc[:4000], color=color)

    if image:
        embed.set_image(url=f"attachment://{SCENE_FILE}")
    else:
        if e:
            embed.add_field(name=f"상대 · {D.name(e['sid'])} Lv.{e['lv']}" + (" 👑" if e.get("boss") else ""),
                            value=f"{mon_head(e)}\n{hp_line(e)}", inline=False)
        embed.add_field(name=f"나 · {D.name(p['sid'])} Lv.{p['lv']}",
                        value=f"{mon_head(p)}\n{hp_line(p)}\n{exp_line(p)}", inline=False)
        if e and phase == "battle":
            embed.set_thumbnail(url=D.artwork(e["sid"]))
        else:
            embed.set_thumbnail(url=D.artwork(p["sid"]))
    embed.set_author(name=f"{trainer} 트레이너", icon_url=D.sprite(p["sid"]))

    view = discord.ui.View(timeout=None)
    if phase == "battle":
        if p["rc"]:
            view.add_item(discord.ui.Button(label="반동으로 쉬기", style=discord.ButtonStyle.secondary,
                                            custom_id=cid(uid, ver, "move", 0)))
        else:
            for i, mid in enumerate(p["moves"]):
                m = D.MOVES[mid]
                eff = D.effectiveness(m["t"], D.types(e["sid"]))
                style = (discord.ButtonStyle.success if eff > 1 else discord.ButtonStyle.danger if eff == 0
                         else discord.ButtonStyle.secondary if eff < 1 else discord.ButtonStyle.primary)
                cat = "물리" if m["c"] == 0 else "특수"
                view.add_item(discord.ui.Button(
                    label=f"{m['n']} · {D.TYPE_KO[m['t']]} {cat} {m['p']}"[:80], style=style,
                    custom_id=cid(uid, ver, "move", i), row=0 if i < 2 else 1))
        view.add_item(discord.ui.Button(label="내 포켓몬", emoji="📋", style=discord.ButtonStyle.secondary,
                                        custom_id=cid(uid, ver, "info"), row=2))
        view.add_item(discord.ui.Button(label="포기", emoji="🏳️", style=discord.ButtonStyle.secondary,
                                        custom_id=cid(uid, ver, "quit"), row=2))
        embed.set_footer(text="초록 버튼은 효과가 굉장한 기술, 회색은 효과가 별로인 기술이에요.")
    elif phase == "reward":
        lines = []
        for i, key in enumerate(run["rewards"]):
            r = E.REWARDS[key]
            lines.append(f"**{r['n']}** — {r['d']}")
            view.add_item(discord.ui.Button(label=r["n"], emoji="🎁", style=discord.ButtonStyle.success,
                                            custom_id=cid(uid, ver, "reward", i)))
        view.add_item(discord.ui.Button(label="넘어가기", style=discord.ButtonStyle.secondary,
                                        custom_id=cid(uid, ver, "skip")))
        view.add_item(discord.ui.Button(label="내 포켓몬", emoji="📋", style=discord.ButtonStyle.secondary,
                                        custom_id=cid(uid, ver, "info"), row=1))
        if not image:
            embed.add_field(name="🎁 보상을 하나 고르세요", value="\n".join(lines) or "-", inline=False)
    else:
        cleared = wave if phase == "clear" else wave - 1
        embed.add_field(
            name="🏆 게임 클리어!" if phase == "clear" else "게임 종료",
            value=(f"**{cleared}웨이브** 돌파 · 스타팅 {D.name(run['starter'])} → {D.name(p['sid'])} Lv.{p['lv']}\n"
                   f"한 방 최고 데미지 {run.get('best_hit', 0)}"),
            inline=False)
        view.add_item(discord.ui.Button(label="새 게임 시작", emoji="🔁", style=discord.ButtonStyle.primary,
                                        custom_id=cid(uid, ver, "new")))
    return embed, _frozen(view)


def quit_confirm(uid: int, ver: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="정말 포기하기", style=discord.ButtonStyle.danger,
                                    custom_id=cid(uid, ver, "quitok")))
    view.add_item(discord.ui.Button(label="계속하기", style=discord.ButtonStyle.secondary,
                                    custom_id=cid(uid, ver, "back")))
    return _frozen(view)


# ---------- 상세 정보 ----------
def mon_detail(trainer: str, run: dict, image: bool = False) -> discord.Embed:
    """image=True면 능력치·HP는 그림(summary.png)이 보여주고, 글로는 기술 설명과 앞으로를 둔다."""
    p = run["p"]
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
        moves.append(f"**{m['n']}** {D.TYPE_KO[m['t']]} · {'물리' if m['c'] == 0 else '특수'} {m['p']} · {acc}"
                     + (f" · {', '.join(extra)}" if extra else ""))
    e.add_field(name="기술", value="\n".join(moves), inline=False)
    nxt = [(l, mid) for l, mid in D.SPECIES[p["sid"]]["ls"] if l > p["lv"]][:3]
    evo = [(c, ml) for c, ml in D.SPECIES[p["sid"]]["evo"] if ml]
    tips = []
    if nxt:
        tips.append("다음에 배울 기술: " + ", ".join(f"Lv.{l} {D.MOVES[mid]['n']}" for l, mid in nxt))
    if evo:
        tips.append("진화: " + ", ".join(f"Lv.{ml} {D.name(c)}" for c, ml in evo))
    if run.get("exp_mult", 1) > 1:
        tips.append(f"학습장치: 경험치 {int(run['exp_mult'] * 100)}%")
    if tips:
        e.add_field(name="앞으로", value="\n".join(tips), inline=False)
    if image:
        e.set_image(url=f"attachment://{SUMMARY_FILE}")
    else:
        e.set_thumbnail(url=D.artwork(p["sid"]))
    e.set_footer(text=f"{trainer} 트레이너 · 웨이브 {run['wave']} · 스타팅 {D.name(run['starter'])}")
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
