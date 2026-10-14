"""유저끼리: 플레이어 목록·프로필(pp:), 포켓몬 교환(tx:), 대전(pv:).

bot.py 맨 끝에서 register(bot 모듈)로 명령어를 붙인다 (bot.py를 다시 import하지 않게).
모든 응답은 interaction.response.* 로 바로 보낸다 (Render 공유 IP에서 나중에 수정하는 경로는 막히기 쉬움).
교환·대전은 메모리에만 둔다 (봇이 재시작하면 진행 중인 교환·대전은 사라짐 — 모험에는 영향 없음).
"""

import asyncio
import io
import itertools
import logging
import random
import time

import discord
from discord import app_commands

import sprites
import storage
import ui
from game import adventure as A
from game import data as D
from game import engine as E
from game import pvp as P
from game import scene
from game import trade as T

log = logging.getLogger("pokebot.social")
B = None            # bot 모듈 (register에서 넣는다)
rng = random.Random()
_ids = itertools.count(1)

TRADE_TTL = 15 * 60        # 교환 창은 15분
DUEL_TTL = 60 * 60         # 대전은 마지막 행동 뒤 1시간
TRADES: dict[str, dict] = {}
DUELS: dict[str, dict] = {}
SIDE = ("🔴", "🔵")


def _new_id() -> str:
    return f"{int(time.time()) % 100000:x}{next(_ids):x}"


def _gc():
    now = time.time()
    for d, ttl in ((TRADES, TRADE_TTL), (DUELS, DUEL_TTL)):
        for k in [k for k, v in d.items() if now - v["t"] > ttl]:
            d.pop(k, None)


def _name_of(uid: int, fallback: str = "트레이너") -> str:
    run = storage._runs.get((uid, "adventure"))
    return (run or {}).get("name") or fallback


async def _deny(interaction: discord.Interaction, msg: str):
    await interaction.response.send_message(msg, ephemeral=True)


def _frozen(view):
    view.stop()
    return view


# =====================================================================
# 플레이어 목록·프로필 (pp:<보는 사람>:<동작>[:<대상>])
# =====================================================================
def _players() -> list[tuple[int, dict, int]]:
    rows = storage.adventure_rows()
    return sorted(rows, key=lambda r: (-r[1].get("hof3", 0), -r[1].get("hof2", 0), -r[1].get("hof", 0),
                                       -len(r[1]["badges"]), -r[2]))


def players_screen(viewer: int) -> tuple[discord.Embed, discord.ui.View]:
    rows = _players()
    e = discord.Embed(title="👥 플레이어 목록", color=0x5865F2,
                      description=f"모험 중인 트레이너 **{len(rows)}명** · 아래 메뉴에서 고르면 기록과 파티를 볼 수 있어요.")
    lines = []
    for i, (uid, run, dex) in enumerate(rows[:25]):
        name = run.get("name") or "트레이너"
        who = f"**{name}**" if uid == viewer else name
        lines.append(f"`{i + 1:>2}` {who} — {A.summary_line(run)} · 도감 {dex}")
    e.add_field(name="랭킹 순", value="\n".join(lines)[:1024] or "아직 모험을 시작한 사람이 없어요.", inline=False)
    view = discord.ui.View(timeout=None)
    if rows:
        view.add_item(discord.ui.Select(
            custom_id=f"pp:{viewer}:view", placeholder="볼 트레이너 고르기",
            options=[discord.SelectOption(
                label=f"{i + 1}. {(run.get('name') or '트레이너')}"[:100], value=str(uid),
                description=f"{A.summary_line(run)} · 도감 {dex}"[:100]) for i, (uid, run, dex) in enumerate(rows[:25])]))
    return e, _frozen(view)


def profile_embed(viewer: int, uid: int, run: dict, image: bool) -> discord.Embed:
    name = run.get("name") or "트레이너"
    e = discord.Embed(title=f"🪪 {name}의 트레이너 카드", color=0x3BA55D)
    champ = [f"{A.REGIONS[r]['n']} {run.get(A.REGIONS[r]['hof'], 0)}회" for r in A.REGION_ORDER
             if run.get(A.REGIONS[r]["hof"])]
    best = max(run["party"], key=lambda m: m["lv"])
    dex, shiny = storage.dex(uid), storage.shiny(uid)
    e.add_field(name="모험", value=(f"{A.summary_line(run)}\n"
                                   f"챔피언: {', '.join(champ) if champ else '아직'}\n"
                                   f"에이스: {ui.mname(best)} Lv.{best['lv']} · PC 박스 {len(run['box'])}마리"), inline=False)
    e.add_field(name="도감", value=f"{len(dex)}종" + (f" · 이로치 ✨ {len(shiny)}종" if shiny else ""), inline=True)
    st = storage.pvp(uid)
    e.add_field(name="대전", value=f"{st['w']}승 {st['l']}패" + (f" {st['d']}무" if st["d"] else ""), inline=True)
    recs = []
    for mode, period in (("daily", B.today_key()), ("challenge", B.week_key())):
        r = storage.has_result(mode, period, uid)
        if r:
            recs.append(f"{ui.MODE_KO[mode]} {r['wave']}웨이브" + (" 🏆" if r.get("clear") else ""))
    if recs:
        e.add_field(name="이번 기록", value=" · ".join(recs), inline=True)
    if not image:
        e.add_field(name="파티", value="\n".join(f"{ui.mname(m)} Lv.{m['lv']}" for m in run["party"]), inline=False)
    else:
        e.set_image(url=f"attachment://{ui.SCENE_FILE}")
    return e


def profile_view(viewer: int, uid: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="목록으로", emoji="👥", style=discord.ButtonStyle.secondary,
                                    custom_id=f"pp:{viewer}:list"))
    other = uid != viewer
    view.add_item(discord.ui.Button(label="대전 신청", emoji="⚔️", style=discord.ButtonStyle.danger, disabled=not other,
                                    custom_id=f"pp:{viewer}:duel:{uid}"))
    view.add_item(discord.ui.Button(label="교환 신청", emoji="🔁", style=discord.ButtonStyle.primary, disabled=not other,
                                    custom_id=f"pp:{viewer}:trade:{uid}"))
    return _frozen(view)


async def show_profile(interaction: discord.Interaction, uid: int, send: bool):
    viewer = interaction.user.id
    run = await B.get_run(uid, "adventure")
    if not run:
        msg = "아직 모험을 시작하지 않은 트레이너예요."
        if send:
            return await _deny(interaction, msg)
        return await interaction.response.edit_message(content=msg, embeds=[], view=profile_view(viewer, uid),
                                                       attachments=[])
    file = await B.render(run, "party", title=f"{run.get('name') or '트레이너'}의 파티")
    embed = profile_embed(viewer, uid, run, file is not None)
    view = profile_view(viewer, uid)
    if send:
        kw = {"file": file} if file else {}
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True, **kw)
    else:
        await interaction.response.edit_message(content=None, embeds=[embed], view=view,
                                                attachments=[file] if file else [])


async def handle_players(interaction: discord.Interaction, custom_id: str):
    parts = custom_id.split(":")
    viewer, act = int(parts[1]), parts[2]
    if viewer != interaction.user.id:
        return await _deny(interaction, "다른 사람이 연 목록이에요. `/플레이어`로 직접 열어 보세요.")
    if act == "list":
        e, v = players_screen(viewer)
        return await interaction.response.edit_message(content=None, embeds=[e], view=v, attachments=[])
    if act == "view":
        uid = int((interaction.data.get("values") or ["0"])[0])
        return await show_profile(interaction, uid, send=False)
    target = int(parts[3])
    if act == "duel":
        return await start_duel(interaction, target)
    if act == "trade":
        return await start_trade(interaction, target)


# =====================================================================
# 교환 (tx:<교환 번호>:<동작>[:<쪽>])
# =====================================================================
def _check_pair(me: int, other: int, other_is_bot: bool = False) -> str | None:
    if other == me:
        return "자기 자신과는 할 수 없어요."
    if other_is_bot:
        return "봇과는 할 수 없어요."
    if not storage._runs.get((me, "adventure")):
        return "먼저 `/스타팅`으로 모험을 시작해 주세요."
    if not storage._runs.get((other, "adventure")):
        return "상대가 아직 모험을 시작하지 않았어요."
    return None


async def _trade_file(t: dict, done: bool = False) -> discord.File | None:
    try:
        mons = []
        for i, uid in enumerate(t["users"]):
            m = None
            if done:
                m = t["got"][i]
            elif t["pick"][i]:
                run = storage._runs.get((uid, "adventure"))
                m = T.get(run, t["pick"][i]) if run else None
            mons.append(m)
        await sprites.ensure(sids=[D.skey(m) for m in mons if m], timeout=1.0)
        left, right = (t["names"][0], mons[0]), (t["names"][1], mons[1])
        png = await asyncio.to_thread(scene.trade, left, right, sprites.get_sprite, done)
        return discord.File(io.BytesIO(png), filename=ui.SCENE_FILE)
    except Exception as ex:
        log.warning("교환 그림 실패: %s", B.short_error(ex))
        return None


def _trade_screen(tid: str, t: dict, image: bool) -> tuple[discord.Embed, discord.ui.View]:
    a, b = t["names"]
    e = discord.Embed(title=f"🔁 포켓몬 교환 · {a} ↔ {b}", color=0x3498DB)
    lines = []
    for i, uid in enumerate(t["users"]):
        run = storage._runs.get((uid, "adventure"))
        m = T.get(run, t["pick"][i]) if run and t["pick"][i] else None
        state = "✅ 확정" if t["ok"][i] else ("고르는 중" if m is None else "확정 전")
        lines.append(f"{SIDE[i]} **{t['names'][i]}**: " + (f"{ui.mname(m)} Lv.{m['lv']}" if m else "—") + f" · {state}")
    e.description = ("\n".join(lines) + "\n\n각자 메뉴에서 줄 포켓몬을 고르고 둘 다 **확정**을 누르면 바꿔요.\n"
                     "받는 쪽 레벨 제한보다 높으면 제한 레벨로 맞춰지고, 통신 진화하는 포켓몬은 바로 진화해요.")
    if image:
        e.set_image(url=f"attachment://{ui.SCENE_FILE}")
    e.set_footer(text="15분 안에 끝내 주세요. 배틀 중에는 확정할 수 없어요.")
    view = discord.ui.View(timeout=None)
    for i, uid in enumerate(t["users"]):
        run = storage._runs.get((uid, "adventure"))
        opts = T.options(run) if run else []
        view.add_item(discord.ui.Select(
            custom_id=f"tx:{tid}:pick:{i}", row=i, placeholder=f"{SIDE[i]} {t['names'][i]}: 줄 포켓몬 고르기"[:150],
            options=[discord.SelectOption(label=lab[:100], value=v, description=desc, default=v == t["pick"][i])
                     for v, lab, desc in opts] or [discord.SelectOption(label="없음", value="none")]))
    view.add_item(discord.ui.Button(label="확정", emoji="✅", style=discord.ButtonStyle.success, row=2,
                                    custom_id=f"tx:{tid}:ok", disabled=not all(t["pick"])))
    view.add_item(discord.ui.Button(label="취소", emoji="✖️", style=discord.ButtonStyle.secondary, row=2,
                                    custom_id=f"tx:{tid}:no"))
    return e, _frozen(view)


async def start_trade(interaction: discord.Interaction, target: int, target_name: str | None = None,
                      target_bot: bool = False):
    _gc()
    me = interaction.user.id
    if (why := _check_pair(me, target, target_bot)):
        return await _deny(interaction, why)
    tid = _new_id()
    t = {"users": [me, target], "names": [interaction.user.display_name, target_name or _name_of(target)],
         "pick": [None, None], "ok": [False, False], "t": time.time()}
    TRADES[tid] = t
    file = await _trade_file(t)
    e, v = _trade_screen(tid, t, file is not None)
    kw = {"file": file} if file else {}
    await interaction.response.send_message(content=f"<@{target}> {t['names'][0]}님이 포켓몬 교환을 신청했어요!",
                                            embed=e, view=v, **kw)


async def handle_trade(interaction: discord.Interaction, custom_id: str):
    parts = custom_id.split(":")
    tid, act = parts[1], parts[2]
    t = TRADES.get(tid)
    if t is None:
        return await interaction.response.edit_message(content="⌛ 끝났거나 시간이 지난 교환이에요. `/교환`으로 다시 신청해 주세요.",
                                                       embeds=[], view=None, attachments=[])
    uid = interaction.user.id
    if uid not in t["users"]:
        return await _deny(interaction, "이 교환의 트레이너만 누를 수 있어요.")
    me = t["users"].index(uid)
    async with storage.lock(f"tx{tid}"):
        if act == "no":
            TRADES.pop(tid, None)
            return await interaction.response.edit_message(content=f"✖️ {t['names'][me]}님이 교환을 취소했어요.",
                                                           embeds=[], view=None, attachments=[])
        if act == "pick":
            side = int(parts[3])
            if side != me:
                return await _deny(interaction, "상대가 줄 포켓몬은 상대가 골라요.")
            val = (interaction.data.get("values") or ["none"])[0]
            t["pick"][me] = None if val == "none" else val
            t["ok"] = [False, False]
            t["t"] = time.time()
            file = await _trade_file(t)
            e, v = _trade_screen(tid, t, file is not None)
            return await interaction.response.edit_message(content=None, embeds=[e], view=v,
                                                           attachments=[file] if file else [])
        if act == "ok":
            if not all(t["pick"]):
                return await _deny(interaction, "둘 다 포켓몬을 골라야 확정할 수 있어요.")
            t["ok"][me] = True
            if not all(t["ok"]):
                file = await _trade_file(t)
                e, v = _trade_screen(tid, t, file is not None)
                return await interaction.response.edit_message(embeds=[e], view=v, attachments=[file] if file else [])
            return await _do_trade(interaction, tid, t)


async def _do_trade(interaction, tid, t):
    a, b = t["users"]
    first, second = sorted((a, b))
    async with storage.lock(first), storage.lock(second):
        ra, rb = await B.get_run(a, "adventure"), await B.get_run(b, "adventure")
        try:
            ma, mb = T.get(ra, t["pick"][0]), T.get(rb, t["pick"][1])
            got_a, got_b = T.swap(ra, t["pick"][0], rb, t["pick"][1])
        except (ValueError, TypeError) as ex:
            t["ok"] = [False, False]
            return await _deny(interaction, f"교환할 수 없어요: {ex}")
        t["got"] = [mb, ma]   # 교환 완료 그림: 각자 받은 포켓몬
        for uid, run in ((a, ra), (b, rb)):
            run["ver"] = run.get("ver", 0) + 1   # 열려 있던 게임 화면은 지난 화면이 된다 (파티가 바뀌었으니)
            storage.cache_run(uid, "adventure", run)
            B.record_dex(uid, run)
            B._bg(storage.save_run(uid, "adventure", run), "교환 저장")
    TRADES.pop(tid, None)
    log.info("교환: %s(%s) ↔ %s(%s)", t["names"][0], D.name(mb["sid"]), t["names"][1], D.name(ma["sid"]))
    file = await _trade_file(t, done=True)
    e = discord.Embed(title=f"🔁 교환 완료! · {t['names'][0]} ↔ {t['names'][1]}", color=0x2ECC71,
                      description=ui.josa("\n".join(
                          [f"{SIDE[0]} **{t['names'][0]}**"] + got_a + ["", f"{SIDE[1]} **{t['names'][1]}**"] + got_b)))
    e.set_footer(text="게임 화면은 /이어하기로 다시 불러와 주세요.")
    if file:
        e.set_image(url=f"attachment://{ui.SCENE_FILE}")
    await interaction.response.edit_message(content=None, embeds=[e], view=None, attachments=[file] if file else [])


# =====================================================================
# 대전 (pv:<대전 번호>:<버전>:<동작>[:<쪽>[:<값>]])
# =====================================================================
async def start_duel(interaction: discord.Interaction, target: int, target_name: str | None = None,
                     target_bot: bool = False):
    _gc()
    me = interaction.user.id
    if (why := _check_pair(me, target, target_bot)):
        return await _deny(interaction, why)
    bid = _new_id()
    DUELS[bid] = {"users": [me, target], "names": [interaction.user.display_name, target_name or _name_of(target)],
                  "b": None, "t": time.time()}
    d = DUELS[bid]
    e = discord.Embed(title=f"⚔️ 대전 신청 · {d['names'][0]} → {d['names'][1]}", color=0xE74C3C,
                      description=(f"**{d['names'][0]}**님이 **{d['names'][1]}**님에게 대전을 신청했어요!\n\n"
                                   f"• 모험 파티 그대로, 모두 **Lv.{P.LEVEL}**로 맞춰서 싸워요 (모험에는 영향 없음)\n"
                                   "• 가방은 못 쓰고, 지닌 물건은 효과가 있어요\n"
                                   "• 둘이 각자 기술을 고르면 턴이 진행돼요"))
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="수락", emoji="⚔️", style=discord.ButtonStyle.success,
                                    custom_id=f"pv:{bid}:0:yes"))
    view.add_item(discord.ui.Button(label="거절", style=discord.ButtonStyle.secondary, custom_id=f"pv:{bid}:0:no"))
    await interaction.response.send_message(content=f"<@{target}>", embed=e, view=_frozen(view))


async def _duel_file(b: dict, d: dict | None = None) -> discord.File | None:
    """대전 그림 (d에 마지막 그림을 남겨 두고, 한쪽만 고른 화면에서는 그걸 다시 붙인다)"""
    try:
        run = P.view_run(b, 0)
        p, e = E.lead(run), run["e"]
        await sprites.ensure(sids=[D.skey(e)], backs=[D.skey(p)], timeout=1.0)
        if sprites.has_anim(D.skey(e), False) and sprites.has_anim(D.skey(p), True):
            png = await asyncio.to_thread(scene.battle_gif, run, sprites.get_sprite, sprites.get_anim)
            name = ui.SCENE_GIF
        else:
            sprites.prefetch(anims=[D.skey(e)], anim_backs=[D.skey(p)])
            png = await asyncio.to_thread(scene.battle, run, sprites.get_sprite, None, sprites.get_anim)
            name = ui.SCENE_FILE
        # 다음 턴에 나올 수 있는 포켓몬도 미리
        sprites.prefetch(sids=[D.skey(m) for m in b["sides"][1]["party"]],
                         backs=[D.skey(m) for m in b["sides"][0]["party"]],
                         anims=[D.skey(m) for m in b["sides"][1]["party"]],
                         anim_backs=[D.skey(m) for m in b["sides"][0]["party"]])
        if d is not None:
            d["img"] = (png, name)
        return discord.File(io.BytesIO(png), filename=name)
    except Exception as ex:
        log.warning("대전 그림 실패: %s", B.short_error(ex))
        return None


def _duel_screen(bid: str, d: dict, file: discord.File | None) -> tuple[discord.Embed, discord.ui.View]:
    b = d["b"]
    s0, s1 = b["sides"]
    over = b["winner"] is not None
    e = discord.Embed(title=f"⚔️ {SIDE[0]} {s0['name']} vs {SIDE[1]} {s1['name']} · {b['turn'] + 1}턴" if not over
                      else f"⚔️ {s0['name']} vs {s1['name']} · 대전 끝",
                      color=0xF1C40F if over else 0xE74C3C)
    e.description = ui.josa("\n".join(b["log"][-14:]))[:4000] or "​"
    for i, s in enumerate(b["sides"]):
        p = P.lead(s)
        e.add_field(name=f"{SIDE[i]} {s['name']} · {ui.mname(p)} Lv.{p['lv']}",
                    value=f"{ui.hp_line(p)}\n남은 포켓몬 {len(P.alive(s))}/{len(s['party'])}", inline=True)
    if file:
        e.set_image(url=f"attachment://{file.filename}")
    view = discord.ui.View(timeout=None)
    if over:
        return e, _frozen(view)
    need = P.needs(b)
    waiting = []
    for i, s in enumerate(b["sides"]):
        p = P.lead(s)
        chosen = s["choice"] is not None
        can = i in need and not chosen
        if chosen:
            waiting.append(f"{SIDE[i]} {s['name']} 선택 완료")
        elif i in need:
            waiting.append(f"{SIDE[i]} {s['name']} 고르는 중...")
        # 기술 버튼 (한 줄)
        if p["rc"]:
            moves = [("반동으로 쉬기", 0, True)]
        elif not E.usable_moves(p):
            moves = [("발버둥", -1, True)]
        else:
            usable = E.usable_moves(p)
            moves = [(D.MOVES[mid]["n"] + f" {p['pp'][j]}/{E.max_pp(p, j)}", j, j in usable)
                     for j, mid in enumerate(p["moves"])]
        for label, j, ok in moves:
            eff = D.effectiveness(D.MOVES[p["moves"][j]]["t"], D.types(P.lead(b["sides"][1 - i])["sid"])) if j >= 0 else 1
            style = (discord.ButtonStyle.success if eff > 1 else discord.ButtonStyle.danger if eff == 0
                     else discord.ButtonStyle.secondary if eff < 1 else discord.ButtonStyle.primary)
            view.add_item(discord.ui.Button(label=f"{SIDE[i]} {label}"[:80], style=style, row=i,
                                            disabled=not (can and ok and not s["must_switch"]),
                                            custom_id=f"pv:{bid}:{b['ver']}:mv:{i}:{j}"))
        # 교체·항복 메뉴
        opts = [discord.SelectOption(label=f"교체: {ui.mname(m)} Lv.{m['lv']} ({m['hp']}/{E.max_hp(m)})"[:100],
                                     value=f"sw{j}") for j, m in enumerate(s["party"]) if m["hp"] > 0 and j != s["active"]]
        opts.append(discord.SelectOption(label="항복하기", value="ff", emoji="🏳️"))
        view.add_item(discord.ui.Select(
            custom_id=f"pv:{bid}:{b['ver']}:sel:{i}", row=2 + i, disabled=not can,
            placeholder=(f"{SIDE[i]} {s['name']}: " + ("기절! 다음 포켓몬을 골라 주세요" if s["must_switch"]
                                                       else "교체 / 항복"))[:150], options=opts))
    view.add_item(discord.ui.Button(label="시간 초과 승리 요청", emoji="⏰", style=discord.ButtonStyle.secondary, row=4,
                                    custom_id=f"pv:{bid}:{b['ver']}:to"))
    e.set_footer(text=" · ".join(waiting) + f" · 🔴 {s0['name']}은 아래(뒷모습), 🔵 {s1['name']}은 위")
    return e, _frozen(view)


async def handle_duel(interaction: discord.Interaction, custom_id: str):
    parts = custom_id.split(":")
    bid, ver, act = parts[1], int(parts[2]), parts[3]
    d = DUELS.get(bid)
    if d is None:
        return await interaction.response.edit_message(content="⌛ 끝났거나 시간이 지난 대전이에요. `/대전`으로 다시 신청해 주세요.",
                                                       embeds=[], view=None, attachments=[])
    uid = interaction.user.id
    if uid not in d["users"]:
        return await _deny(interaction, "이 대전의 트레이너만 누를 수 있어요.")
    me = d["users"].index(uid)
    async with storage.lock(f"pv{bid}"):
        d["t"] = time.time()
        if d["b"] is None:   # 신청 화면
            if act == "no":
                DUELS.pop(bid, None)
                who = "거절" if me == 1 else "취소"
                return await interaction.response.edit_message(content=f"✖️ {d['names'][me]}님이 대전을 {who}했어요.",
                                                               embeds=[], view=None)
            if act == "yes":
                if me != 1:
                    return await _deny(interaction, "신청받은 사람이 수락해야 해요.")
                ra, rb = await B.get_run(d["users"][0], "adventure"), await B.get_run(d["users"][1], "adventure")
                if not ra or not rb:
                    DUELS.pop(bid, None)
                    return await interaction.response.edit_message(content="모험 기록이 없어서 대전을 할 수 없어요.",
                                                                   embeds=[], view=None)
                d["b"] = P.new_battle((d["users"][0], d["names"][0], ra["party"]),
                                      (d["users"][1], d["names"][1], rb["party"]))
                log.info("대전 시작: %s vs %s", *d["names"])
                return await _show_duel(interaction, bid, d, new_image=True)
            return await _deny(interaction, "대전을 수락하거나 거절해 주세요.")
        b = d["b"]
        if ver != b["ver"]:
            return await _deny(interaction, "지나간 턴의 버튼이에요. 최신 화면에서 눌러 주세요.")
        if act == "to":
            if not P.claim_timeout(b, me):
                left = int(P.TIMEOUT - (time.time() - (b.get("wait") or time.time())))
                return await _deny(interaction, "내가 먼저 고르고, 상대가 3분 넘게 안 골라야 받을 수 있어요."
                                   + (f" (남은 시간 {left}초)" if b.get("wait") and b["sides"][me]["choice"] else ""))
            return await _show_duel(interaction, bid, d, new_image=False)
        side = int(parts[4])
        if side != me:
            return await _deny(interaction, f"{SIDE[me]} 내 줄의 버튼을 눌러 주세요.")
        if act == "mv":
            choice = ("move", int(parts[5]))
        else:
            val = (interaction.data.get("values") or [""])[0]
            choice = ("forfeit",) if val == "ff" else ("switch", int(val[2:]))
        try:
            turned = P.choose(b, me, choice, rng)
        except ValueError:
            return await _deny(interaction, "지금은 그걸 할 수 없어요.")
        await _show_duel(interaction, bid, d, new_image=turned)


async def _show_duel(interaction, bid, d, new_image: bool):
    b = d["b"]
    if new_image or not d.get("img"):
        file = await _duel_file(b, d)
    else:   # 한쪽만 고름: 그림은 그대로 (만들어 둔 그림을 다시 붙인다)
        png, name = d["img"]
        file = discord.File(io.BytesIO(png), filename=name)
    e, v = _duel_screen(bid, d, file)
    await interaction.response.edit_message(content=None, embeds=[e], view=v, attachments=[file] if file else [])
    if b["winner"] is not None:
        DUELS.pop(bid, None)
        a, c = d["users"]
        winner = None if b["winner"] == -1 else d["users"][b["winner"]]
        B._bg(storage.add_pvp(a, c, winner), "대전 기록")
        log.info("대전 끝: %s vs %s → %s", *d["names"], "무승부" if winner is None else d["names"][b["winner"]])


# =====================================================================
# 명령어 붙이기
# =====================================================================
def register(bot_module):
    global B
    B = bot_module
    tree = bot_module.bot.tree

    @tree.command(name="플레이어", description="모험 중인 트레이너 목록 — 골라서 기록과 파티를 볼 수 있어요")
    async def players_cmd(interaction: discord.Interaction):
        e, v = players_screen(interaction.user.id)
        await interaction.response.send_message(embed=e, view=v, ephemeral=True)

    @tree.command(name="프로필", description="트레이너 카드 (모험 기록·파티·대전 전적)")
    @app_commands.describe(유저="볼 트레이너 (비워 두면 나)")
    async def profile_cmd(interaction: discord.Interaction, 유저: discord.User | None = None):
        await show_profile(interaction, (유저 or interaction.user).id, send=True)

    @tree.command(name="대전", description=f"다른 트레이너와 모험 파티로 대전 (모두 Lv.{P.LEVEL})")
    @app_commands.describe(상대="대전할 트레이너")
    async def duel_cmd(interaction: discord.Interaction, 상대: discord.User):
        await start_duel(interaction, 상대.id, 상대.display_name, 상대.bot)

    @tree.command(name="교환", description="다른 트레이너와 포켓몬 교환 (통신 진화도 돼요)")
    @app_commands.describe(상대="교환할 트레이너")
    async def trade_cmd(interaction: discord.Interaction, 상대: discord.User):
        await start_trade(interaction, 상대.id, 상대.display_name, 상대.bot)


async def dispatch(interaction: discord.Interaction, custom_id: str) -> bool:
    """bot.on_interaction 에서 부른다. 처리했으면 True"""
    if custom_id.startswith("pp:"):
        await handle_players(interaction, custom_id)
    elif custom_id.startswith("tx:"):
        await handle_trade(interaction, custom_id)
    elif custom_id.startswith("pv:"):
        await handle_duel(interaction, custom_id)
    else:
        return False
    return True
