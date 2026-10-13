"""PokeRogue식 포켓몬 디스코드 봇.

/메뉴 → 새 게임·데일리·주간 챌린지 → (전용 스레드) 스타팅 선택 → 웨이브 배틀 → 보상 → … → 쓰러지면 게임 종료
"""

import asyncio
import io
import logging
import os
import random
from datetime import datetime, timedelta, timezone

import discord
from aiohttp import web
from discord import app_commands
from dotenv import load_dotenv

import sprites
import storage
import ui
from game import data as D
from game import engine as E
from game import scene

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

log = logging.getLogger("pokebot")
rng = random.Random()

BUSY_MSG = "디스코드 연결이 잠시 불안정해요. 잠깐 뒤에 다시 시도해 주세요."

# 참고: Render 무료 플랜의 공유 IP는 디스코드의 '응답 나중에 수정' 경로
# (defer 후 edit_original_response / followup)가 Cloudflare에 막히는 일이 있어요.
# 그래서 모든 응답을 interaction.response.* 로 '즉시' 보내고, defer는 쓰지 않아요.
# 디스코드는 3초 안에 응답해야 하므로 버튼을 누를 때는 외부 API도 DB도 기다리지 않아요.
# (게임은 메모리에서 바로 처리하고, 응답을 보낸 뒤에 DB에 저장해요)


def short_error(error: Exception) -> str:
    """Cloudflare 차단 시 HTML 페이지 전체가 로그에 찍히지 않도록 첫 줄만 남긴다."""
    return str(error).split("\n", 1)[0][:200]


async def notify_failure(interaction: discord.Interaction, msg: str = BUSY_MSG):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


def _bg(coro, what: str):
    """응답을 보낸 뒤 DB 저장을 백그라운드로 실행 (실패하면 로그만)"""
    async def runner():
        try:
            await coro
        except Exception as e:
            log.warning("%s 실패: %s", what, short_error(e))
    asyncio.create_task(runner())


# ---------- Health check (Render 웹 서비스는 포트를 열어두어야 해요) ----------
async def start_health_server():
    port = os.getenv("PORT")
    if not port:
        return
    app = web.Application()

    async def ok(_request):
        return web.Response(text="ok")

    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(port)).start()


# ---------- Bot ----------
class PokeBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await start_health_server()
        await storage.init()

    # 전역 등록은 반영이 느려서, 봇이 들어가 있는 서버마다 '서버 전용'으로 등록해요.
    async def sync_guild(self, guild: discord.abc.Snowflake) -> int:
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        return len(synced)

    async def on_ready(self):
        log.info("로그인: %s / 서버 %d곳", self.user, len(self.guilds))
        if getattr(self, "_synced", False):
            return
        self._synced = True
        for guild in self.guilds:
            try:
                count = await self.sync_guild(guild)
                log.info("명령어 %d개 동기화: %s", count, guild.name)
            except Exception as e:
                log.warning("명령어 동기화 실패 (%s): %s", guild.name, short_error(e))

    async def on_guild_join(self, guild: discord.Guild):
        try:
            count = await self.sync_guild(guild)
            log.info("새 서버 참가: %s → 명령어 %d개 등록", guild.name, count)
        except Exception as e:
            log.warning("새 서버 명령어 등록 실패 (%s): %s", guild.name, short_error(e))

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        try:
            if custom_id.startswith("pr:"):
                await handle_component(interaction, custom_id)
            elif custom_id.startswith("pm:"):
                await handle_menu(interaction, custom_id)
        except Exception as e:
            log.exception("버튼 처리 실패 (%s): %s", custom_id, short_error(e))
            await notify_failure(interaction)


bot = PokeBot()

ACTIVE = ("battle", "reward", "switch", "replace", "learn", "path")
KST = timezone(timedelta(hours=9))


def today_key() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def week_key() -> str:
    y, w, _ = datetime.now(KST).isocalendar()
    return f"{y}-W{w:02d}"


def period_of(mode: str) -> str:
    return today_key() if mode == "daily" else week_key()


async def get_run(uid: int, mode: str = "normal") -> dict | None:
    run = await storage.get_run(uid, mode)
    return E.normalize(run) if run else None


def unlocked_starters(uid: int) -> list[int]:
    """도감에서 스타팅으로 고를 수 있는 포켓몬 (잡은 포켓몬의 진화 전 첫 모습)"""
    return sorted({E.root_species(s) for s in storage.dex(uid)})


def record_dex(uid: int, run: dict):
    """잡거나 진화한 포켓몬을 도감에 남긴다 (응답 뒤 백그라운드)"""
    sids = list(run.pop("caught_list", []) or [])
    for m in run["party"]:
        sids += m.pop("evolved", []) or []
    if sids:
        _bg(storage.add_dex(uid, sids), "도감 저장")


# ---------- 그림 ----------
def _party_sids(run: dict) -> list[int]:
    return [m["sid"] for m in run["party"]]


async def render(run: dict, kind: str = "scene", **kwargs) -> discord.File | None:
    """화면 그림. kind: scene(배틀/보상) / party / summary / path. 실패하면 None → 글자 화면으로 대신 보여준다."""
    try:
        p, e = E.lead(run), run.get("e")
        if kind == "party":
            await sprites.ensure(sids=_party_sids(run), timeout=1.0)
            png = await asyncio.to_thread(scene.party, run, sprites.get_sprite, **kwargs)
            name = ui.SCENE_FILE
        elif kind == "summary":
            idx = kwargs.get("index")
            await sprites.ensure(sids=[run["party"][run["active"] if idx is None else idx]["sid"]], timeout=1.0)
            png = await asyncio.to_thread(scene.summary, run, sprites.get_sprite, idx)
            name = ui.SUMMARY_FILE
        elif kind == "path":
            await sprites.ensure(sids=_party_sids(run), timeout=1.0)
            png = await asyncio.to_thread(scene.paths, run, sprites.get_sprite)
            name = ui.SCENE_FILE
        elif run["phase"] == "reward":
            await sprites.ensure(sids=_party_sids(run),
                                 items=[scene.reward_icon(k) for k in run.get("rewards", [])], timeout=1.0)
            png = await asyncio.to_thread(scene.rewards, run, sprites.get_sprite, sprites.get_item)
            name = ui.SCENE_FILE
        else:
            await sprites.ensure(sids=[e["sid"]] if e else [], backs=[p["sid"]], timeout=1.0)
            png = await asyncio.to_thread(scene.battle, run, sprites.get_sprite)
            name = ui.SCENE_FILE
        return discord.File(io.BytesIO(png), filename=name)
    except Exception as ex:
        log.warning("그림 실패 (%s): %s", kind, short_error(ex))
        return None


def prefetch_next(run: dict):
    """응답을 보낸 뒤, 다음에 필요할 그림을 미리 받아 둔다."""
    evos = [c for m in run["party"] for c, *_ in D.SPECIES[m["sid"]]["evo"]]
    nxt = (run.get("next_e") or {}).get("mon")
    sprites.prefetch(sids=([nxt["sid"]] if nxt else []) + _party_sids(run), backs=evos + _party_sids(run))


async def show(interaction: discord.Interaction, run: dict, make, send: bool = False, ephemeral: bool = False,
               content: str | None = None):
    """make(image: bool) -> ui.Screen 를 그림과 함께 보여준다 (send=False면 지금 메시지를 바꿈)"""
    probe = make(True)
    file = await render(run, probe.image, **probe.image_args)
    sc = probe if file else make(False)
    if send:
        kwargs = {"file": file} if file else {}
        await interaction.response.send_message(content=content or sc.content, embed=sc.embed, view=sc.view,
                                                ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.edit_message(content=content, embeds=[sc.embed], view=sc.view,
                                                attachments=[file] if file else [])
    prefetch_next(run)


def _main(slot: str, trainer: str, run: dict):
    return lambda image: ui.battle_screen(slot, trainer, run, image)


async def send_summary(interaction: discord.Interaction, run: dict, index: int | None, ephemeral: bool):
    file = await render(run, "summary", index=index)
    embed = ui.mon_detail(interaction.user.display_name, run, index, image=file is not None)
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral, **kwargs)


# ---------- 스레드 ----------
async def post_in_thread(interaction: discord.Interaction, thread_name: str, content: str | None,
                         embeds: list[discord.Embed], view: discord.ui.View):
    """게임 전용 스레드를 만들어 그 안에 올린다. 스레드를 못 만들면(권한·DM 등) 지금 채널에 바로 올린다."""
    ch = interaction.channel
    if isinstance(ch, discord.TextChannel):
        try:
            thread = await ch.create_thread(name=thread_name[:90], type=discord.ChannelType.public_thread,
                                            auto_archive_duration=1440)
            await thread.send(content=content, embeds=embeds, view=view)
            await interaction.response.send_message(f"🎮 {thread.mention} 에서 게임을 시작했어요!", ephemeral=True)
            return
        except Exception as ex:   # 권한이 없으면 지금 채널에서
            log.info("스레드를 못 만들어서 채널에 올려요: %s", short_error(ex))
    await interaction.response.send_message(content=content, embeds=embeds, view=view)


async def start_game(interaction: discord.Interaction, mode: str):
    """새 게임 / 데일리 / 주간 챌린지 시작 화면"""
    user = interaction.user
    uid, name = user.id, user.display_name
    slot = ui.slot_of(uid, mode)
    run = await get_run(uid, mode)
    if run and run["phase"] in ACTIVE:
        await show(interaction, run, _main(slot, name, run), send=True,
                   content="진행 중인 게임이 있어요! 이어서 하거나, 🏳️ 포기 후 새로 시작할 수 있어요.")
        return
    if mode == "normal":
        content, embeds, view = ui.region_screen(slot, len(unlocked_starters(uid)))
        title = f"{name}의 포켓몬 모험"
    else:
        period = period_of(mode)
        done = storage.has_result(mode, period, uid)
        if done:
            board = storage.period_board(mode, period, 100)
            rank = next((i + 1 for i, r in enumerate(board) if r["user_id"] == uid), "?")
            word = "오늘" if mode == "daily" else "이번 주"
            await interaction.response.send_message(
                f"{word} {ui.MODE_KO[mode]}는 이미 했어요! 기록 **{done['wave']}웨이브** · 현재 {rank}위", ephemeral=True)
            return
        starters = E.daily_starters(period) if mode == "daily" else E.challenge_starters(period)
        content, embeds, view = ui.mode_start_screen(slot, mode, period, starters)
        sprites.prefetch(backs=starters)
        title = f"{name}의 {ui.MODE_KO[mode].split(' ', 1)[1]} {period}"
    await post_in_thread(interaction, title, content or None, embeds, view)


# ---------- 메뉴 버튼 (pm:<유저 또는 0>:<동작>) ----------
async def handle_menu(interaction: discord.Interaction, custom_id: str):
    _, owner, act = custom_id.split(":")[:3]
    user = interaction.user
    if owner != "0" and int(owner) != user.id:
        await interaction.response.send_message("다른 트레이너의 메뉴예요. `/메뉴`로 내 메뉴를 열어 보세요.", ephemeral=True)
        return
    await menu_action(interaction, act)


async def menu_action(interaction: discord.Interaction, act: str):
    user = interaction.user
    uid, name = user.id, user.display_name
    if act in ("new", "daily", "challenge"):
        await start_game(interaction, {"new": "normal"}.get(act, act))
    elif act == "resume":
        runs = [(m, r) for m in ("normal", "daily", "challenge") if (r := await get_run(uid, m)) and r["phase"] in ACTIVE]
        if not runs:
            await interaction.response.send_message("진행 중인 게임이 없어요. 새 게임을 시작해 보세요!", ephemeral=True)
            return
        mode, run = runs[0]
        await show(interaction, run, _main(ui.slot_of(uid, mode), name, run), send=True,
                   content=None if len(runs) == 1 else f"진행 중인 게임이 {len(runs)}개라 {ui.MODE_KO[mode]} 게임을 불러왔어요. "
                                                       "다른 게임은 `/이어하기`에서 골라 주세요.")
    elif act == "dex":
        await interaction.response.send_message(embed=ui.dex_embed(name, storage.dex(uid)), ephemeral=True)
    elif act == "records":
        await send_records(interaction, ephemeral=True)
    elif act == "help":
        await interaction.response.send_message(embed=ui.help_embed(), ephemeral=True)
    else:
        await interaction.response.send_message("알 수 없는 메뉴예요.", ephemeral=True)


# ---------- 게임 버튼 (pr:<슬롯>:<버전>:<동작>[:<값>]) ----------
async def handle_component(interaction: discord.Interaction, custom_id: str):
    parts = custom_id.split(":")
    _, slot, ver, act = parts[:4]
    arg = ":".join(parts[4:])
    ver = int(ver)
    uid, mode = ui.parse_slot(slot)
    user = interaction.user
    name = user.display_name
    if user.id != uid:
        await interaction.response.send_message("다른 트레이너의 화면이에요. `/메뉴`로 직접 모험을 시작해 보세요!", ephemeral=True)
        return

    async with storage.lock(uid):
        run = await get_run(uid, mode)

        # --- 스타팅 고르기 (게임이 없을 때) ---
        if act in ("region", "regions", "starter", "new", "dexpick"):
            if run and run["phase"] in ACTIVE:
                await show(interaction, run, _main(slot, name, run))   # 이미 진행 중인 게임이 있으면 그 화면으로
                return
            if act == "new" and mode != "normal":
                await interaction.response.edit_message(view=None)
                return
            if act == "region":
                region = (interaction.data.get("values") or [""])[0]
                content, embeds, view = ui.starter_screen(slot, region)
                ids = ui.REGIONS.get(region, [])
                sprites.prefetch(backs=ids + [c for s in ids for c, *_ in D.SPECIES[s]["evo"]])
            elif act == "dexpick":
                content, embeds, view = ui.dex_pick_screen(slot, unlocked_starters(uid), int(arg or 0))
            elif act == "starter":
                sid = int(arg or (interaction.data.get("values") or ["0"])[0])
                seed = period_of(mode) if mode != "normal" else None
                if mode == "normal":
                    ok = sid in E.STARTER_POOL or sid in unlocked_starters(uid)
                elif storage.has_result(mode, seed, uid):
                    return await notify_failure(interaction, "이번 기간에는 이미 도전했어요.")
                else:
                    ok = sid in (E.daily_starters(seed) if mode == "daily" else E.challenge_starters(seed))
                if not ok or sid not in D.SPECIES:
                    return await notify_failure(interaction, "고를 수 없는 포켓몬이에요.")
                run = E.new_run(sid, rng, mode, seed)
                run["ver"] = 1
                storage.cache_run(uid, mode, run)
                record_dex(uid, run)
                await show(interaction, run, _main(slot, name, run))
                _bg(storage.save_run(uid, mode, run), "게임 저장")
                log.info("새 게임(%s): %s → %s", mode, user, sid)
                return
            else:
                content, embeds, view = ui.region_screen(slot, len(unlocked_starters(uid)))
            await interaction.response.edit_message(content=content or None, embeds=embeds, view=view, attachments=[])
            return

        if not run:
            await interaction.response.edit_message(content="이 게임은 이미 끝났어요. `/메뉴`에서 새로 시작해 보세요.",
                                                    embeds=[], view=None, attachments=[])
            return

        # --- 보기만 하는 화면 (버전과 상관없이, 본인에게만) ---
        if act == "info":
            idx = int(arg) if arg else None
            if idx is not None and not 0 <= idx < len(run["party"]):
                idx = None
            await send_summary(interaction, run, idx, ephemeral=True)
            return
        if act == "party":
            await show(interaction, run, lambda image: ui.party_screen(slot, name, run, image), send=True, ephemeral=True)
            return

        if ver != run.get("ver", 0):
            await interaction.response.send_message(
                "지나간 화면의 버튼이에요. 최신 화면에서 눌러 주세요. 화면을 잃어버렸다면 `/이어하기`를 써 보세요.",
                ephemeral=True)
            return

        phase = run["phase"]
        # --- 메뉴 열기 (게임 상태는 그대로) ---
        if act in ("bagcat", "shopcat"):   # 종류 고르기 (선택 메뉴)
            arg = (interaction.data.get("values") or [""])[0]
            act = act[:-3]
        menus = {
            "quit": lambda image: ui.quit_screen(slot, name, run, image),
            "bag": lambda image: ui.bag_screen(slot, name, run, arg or None, image),
            "swmenu": lambda image: ui.switch_screen(slot, name, run, image),
            "shop": lambda image: ui.shop_screen(slot, name, run, arg or None, image),
            "back": _main(slot, name, run),
        }
        if act == "bag" and phase not in ("battle", "reward"):
            act = "back"
        if act in menus:
            if act == "swmenu" and (phase != "battle" or len(E.alive(run)) < 2):
                act = "back"
            if act == "shop" and (phase != "reward" or not E.shop_open(run)):
                act = "back"
            await show(interaction, run, menus[act])
            return
        if act == "item" and arg in run["bag"] and not E.is_ball(arg):
            targets = E.item_targets(run, arg) if E.item_usable_now(run, arg) else []
            if not targets:
                return await notify_failure(interaction, "지금 쓸 수 있는 포켓몬이 없어요.")
            title = f"🎒 {E.item_name(arg)}"
            await show(interaction, run,
                       lambda image: ui.target_screen(slot, name, run, title, "itemt", arg, targets, image, item=arg))
            return
        if act == "itemt" and phase in ("battle", "reward"):
            item, _, t = arg.rpartition(".")
            if item in run["bag"] and t.isdigit() and E.item_moves(run, item, int(t)):
                await show(interaction, run, lambda image: ui.move_pick_screen(slot, name, run, item, int(t), image))
                return
        if act == "reward" and phase == "reward" and arg.isdigit() and int(arg) < len(run["rewards"]):
            key = run["rewards"][int(arg)]
            if E.needs_target(key):
                targets = E.reward_targets(run, key)
                if not targets:
                    return await notify_failure(interaction, "이 보상을 쓸 수 있는 포켓몬이 없어요. 다른 보상을 골라 주세요.")
                title = f"🎁 {E.reward_info(key, run)['n']}"
                await show(interaction, run,
                           lambda image: ui.target_screen(slot, name, run, title, "rewardt", arg, targets, image))
                return

        # --- 게임 상태를 바꾸는 동작 ---
        stay = None   # 바뀐 뒤 보여줄 메뉴 (없으면 기본 화면)
        shop_cat = ui._shop_cat(arg) if act == "buy" and arg in E.ITEMS else None
        try:
            if act == "quitok":
                run["log"] = ["🏳️ 게임을 포기했다."]
                run["phase"] = "over"
            elif act == "move" and phase == "battle":
                E.take_turn(run, int(arg), rng)
            elif act == "sw" and phase in ("battle", "switch"):
                E.switch(run, int(arg), rng)
            elif act == "ball" and phase == "battle":
                E.throw_ball(run, arg, rng)
            elif act == "itemt" and phase in ("battle", "reward"):
                item, t = arg.rsplit(".", 1)
                E.use_item(run, item, int(t), rng)
            elif act == "itemm" and phase in ("battle", "reward"):
                item, t, j = arg.rsplit(".", 2)
                E.use_item(run, item, int(t), rng, move_index=int(j))
            elif act == "forget" and phase == "learn":
                E.resolve_learn(run, int(arg), rng)
            elif act == "noforget" and phase == "learn":
                E.resolve_learn(run, None, rng)
            elif act == "path" and phase == "path":
                E.resolve_path(run, arg, rng)
            elif act == "reward" and phase == "reward":
                E.choose_reward(run, int(arg), rng)
            elif act == "rewardt" and phase == "reward":
                i, t = arg.split(".")
                E.choose_reward(run, int(i), rng, target=int(t))
            elif act == "skip" and phase == "reward":
                E.skip_reward(run, rng)
            elif act == "reroll" and phase == "reward":
                E.reroll(run, rng)
            elif act == "buy" and phase == "reward":
                E.buy(run, arg)
                stay = "shop"
            elif act == "rel" and phase == "replace":
                E.resolve_replace(run, int(arg))
            elif act == "relnew" and phase == "replace":
                E.resolve_replace(run, None)
            else:
                await show(interaction, run, _main(slot, name, run))
                return
        except (ValueError, IndexError, KeyError) as ex:
            log.info("안 되는 동작 %s (%s): %s", act, arg, ex)
            await notify_failure(interaction, "지금은 그걸 할 수 없어요. 화면을 다시 확인해 주세요.")
            return

        run["ver"] = run.get("ver", 0) + 1
        record_dex(uid, run)
        if stay == "shop":
            await show(interaction, run, lambda image: ui.shop_screen(slot, name, run, shop_cat, image))
        else:
            await show(interaction, run, _main(slot, name, run))

        if run["phase"] in ("over", "clear"):
            cleared = run["wave"] if run["phase"] == "clear" else run["wave"] - 1
            storage.cache_run(uid, mode, None)
            if mode != "normal":   # 기록은 바로 메모리에 (다시 도전 못 하게)
                storage._results.setdefault((mode, run.get("seed") or ""), {})[uid] = {
                    "mode": mode, "period": run.get("seed"), "user_id": uid, "name": name, "wave": cleared,
                    "starter": run["starter"], "final": max(run["party"], key=lambda m: m["lv"])["sid"],
                    "clear": run["phase"] == "clear"}
            _bg(storage.finish_run(uid, mode, name, run, cleared, run["phase"] == "clear"), "게임 기록")
            log.info("게임 종료(%s): %s %d웨이브", mode, user, cleared)
        else:
            _bg(storage.save_run(uid, mode, run), "게임 저장")


# ---------- 명령어 ----------
@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    cmd = interaction.command.name if interaction.command else "?"
    log.warning("/%s 처리 실패: %s", cmd, short_error(getattr(error, "original", error)))
    await notify_failure(interaction)


@bot.tree.command(name="메뉴", description="포켓몬 로그라이크 메뉴 (새 게임·데일리·챌린지·도감·기록)")
async def menu(interaction: discord.Interaction):
    await interaction.response.send_message(embed=ui.menu_embed(), view=ui.menu_view(interaction.user.id), ephemeral=True)


@bot.tree.command(name="세팅", description="(관리자) 이 채널에 누구나 쓰는 게임 버튼 패널을 올려요")
@app_commands.default_permissions(manage_guild=True)
async def setup_panel(interaction: discord.Interaction):
    await interaction.response.send_message(embed=ui.menu_embed(public=True), view=ui.menu_view(0))


@bot.tree.command(name="스타팅", description="스타팅 포켓몬을 골라 새 게임(모험)을 시작해요")
async def start(interaction: discord.Interaction):
    await start_game(interaction, "normal")


@bot.tree.command(name="데일리", description="오늘의 데일리 도전 (모두 같은 조건, 하루 한 번)")
async def daily(interaction: discord.Interaction):
    await start_game(interaction, "daily")


@bot.tree.command(name="챌린지", description="이번 주 챌린지 (특별 규칙, 주에 한 번)")
async def challenge(interaction: discord.Interaction):
    await start_game(interaction, "challenge")


@bot.tree.command(name="이어하기", description="진행 중인 게임 화면을 다시 불러와요")
@app_commands.describe(종류="불러올 게임 (비워 두면 진행 중인 게임 하나)")
@app_commands.choices(종류=[app_commands.Choice(name="일반", value="normal"),
                          app_commands.Choice(name="데일리", value="daily"),
                          app_commands.Choice(name="주간 챌린지", value="challenge")])
async def resume(interaction: discord.Interaction, 종류: app_commands.Choice[str] | None = None):
    uid = interaction.user.id
    modes = [종류.value] if 종류 else ["normal", "daily", "challenge"]
    for mode in modes:
        run = await get_run(uid, mode)
        if run and run["phase"] in ACTIVE:
            await show(interaction, run, _main(ui.slot_of(uid, mode), interaction.user.display_name, run), send=True)
            return
    await interaction.response.send_message("진행 중인 게임이 없어요. `/메뉴`에서 시작해 보세요!", ephemeral=True)


@bot.tree.command(name="내포켓몬", description="진행 중인 게임의 파티를 보고, 한 마리씩 자세히 볼 수 있어요")
async def my_pokemon(interaction: discord.Interaction):
    uid = interaction.user.id
    for mode in ("normal", "daily", "challenge"):
        run = await get_run(uid, mode)
        if run and run["phase"] in ACTIVE:
            slot = ui.slot_of(uid, mode)
            await show(interaction, run, lambda image: ui.party_screen(slot, interaction.user.display_name, run, image),
                       send=True)
            return
    await interaction.response.send_message("진행 중인 게임이 없어요. `/메뉴`에서 시작해 보세요!", ephemeral=True)


@bot.tree.command(name="도감", description="지금까지 잡은 포켓몬 도감을 봐요")
async def dex_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=ui.dex_embed(interaction.user.display_name,
                                                               storage.dex(interaction.user.id)))


async def send_records(interaction: discord.Interaction, ephemeral: bool = False):
    try:
        trainer, top = await asyncio.wait_for(
            asyncio.gather(storage.get_trainer(interaction.user.id), storage.leaderboard(10)), timeout=2.2)
    except asyncio.TimeoutError:
        trainer, top = None, None
    me = interaction.user.id
    embeds = []
    if top is not None:
        embeds.append(ui.records(trainer, top, me))
    day, week = today_key(), week_key()
    embeds.append(ui.period_board_embed(f"📅 오늘의 데일리 · {day}", storage.period_board("daily", day), me))
    rule, mono = E.weekly_rules(week)
    embeds.append(ui.period_board_embed(
        f"🏆 주간 챌린지 · {week}", storage.period_board("challenge", week), me,
        "규칙: " + E.RULES[rule] + (f" ({D.TYPE_KO[mono]})" if mono else "")))
    await interaction.response.send_message(embeds=embeds, ephemeral=ephemeral)


@bot.tree.command(name="기록", description="내 최고 기록과 랭킹, 오늘의 데일리·이번 주 챌린지 랭킹")
async def records(interaction: discord.Interaction):
    await send_records(interaction)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN 환경변수를 설정해 주세요 (.env 파일 참고)")
    bot.run(TOKEN, root_logger=True)
