"""PokeRogue식 포켓몬 디스코드 봇.

/스타팅 → 지방·스타팅 선택 → 웨이브 배틀 → 보상 선택 → … → 쓰러지면 게임 종료
"""

import asyncio
import io
import logging
import os
import random

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
        if not custom_id.startswith("pr:"):
            return
        try:
            await handle_component(interaction, custom_id)
        except Exception as e:
            log.exception("버튼 처리 실패 (%s): %s", custom_id, short_error(e))
            await notify_failure(interaction)


bot = PokeBot()


ACTIVE = ("battle", "reward", "switch", "replace", "learn")


async def get_run(uid: int) -> dict | None:
    run = await storage.get_run(uid)
    return E.normalize(run) if run else None


# ---------- 그림 ----------
def _party_sids(run: dict) -> list[int]:
    return [m["sid"] for m in run["party"]]


async def render(run: dict, kind: str = "scene", **kwargs) -> discord.File | None:
    """화면 그림. kind: scene(배틀/보상) / party / summary. 실패하면 None → 글자 화면으로 대신 보여준다."""
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


def _main(uid: int, trainer: str, run: dict):
    return lambda image: ui.battle_screen(uid, trainer, run, image)


async def send_summary(interaction: discord.Interaction, run: dict, index: int | None, ephemeral: bool):
    file = await render(run, "summary", index=index)
    embed = ui.mon_detail(interaction.user.display_name, run, index, image=file is not None)
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral, **kwargs)


# ---------- 버튼 처리 ----------
async def handle_component(interaction: discord.Interaction, custom_id: str):
    parts = custom_id.split(":")
    _, uid, ver, act = parts[:4]
    arg = ":".join(parts[4:])
    uid, ver = int(uid), int(ver)
    user = interaction.user
    name = user.display_name
    if user.id != uid:
        await interaction.response.send_message("다른 트레이너의 화면이에요. `/스타팅`으로 직접 모험을 시작해 보세요!", ephemeral=True)
        return

    async with storage.lock(uid):
        run = await get_run(uid)

        # --- 스타팅 고르기 (게임이 없을 때) ---
        if act in ("region", "regions", "starter", "new"):
            if run and run["phase"] in ACTIVE:
                await show(interaction, run, _main(uid, name, run))   # 이미 진행 중인 게임이 있으면 그 화면으로
                return
            if act == "region":
                region = (interaction.data.get("values") or [""])[0]
                content, embeds, view = ui.starter_screen(uid, region)
                ids = ui.REGIONS.get(region, [])
                sprites.prefetch(backs=ids + [c for s in ids for c, *_ in D.SPECIES[s]["evo"]])
            elif act == "starter":
                run = E.new_run(int(arg), rng)
                run["ver"] = 1
                storage.cache_run(uid, run)
                await show(interaction, run, _main(uid, name, run))
                _bg(storage.save_run(uid, run), "게임 저장")
                log.info("새 게임: %s → %s", user, run["starter"])
                return
            else:
                content, embeds, view = ui.region_screen(uid)
            await interaction.response.edit_message(content=content or None, embeds=embeds, view=view, attachments=[])
            return

        if not run:
            await interaction.response.edit_message(content="이 게임은 이미 끝났어요. `/스타팅`으로 새로 시작해 보세요.",
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
            await show(interaction, run, lambda image: ui.party_screen(uid, name, run, image), send=True, ephemeral=True)
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
            "quit": lambda image: ui.quit_screen(uid, name, run, image),
            "bag": lambda image: ui.bag_screen(uid, name, run, arg or None, image),
            "swmenu": lambda image: ui.switch_screen(uid, name, run, image),
            "shop": lambda image: ui.shop_screen(uid, name, run, arg or None, image),
            "back": _main(uid, name, run),
        }
        if act == "bag" and phase not in ("battle", "reward"):
            act = "back"
        if act in menus:
            if act == "swmenu" and (phase != "battle" or len(E.alive(run)) < 2):
                act = "back"
            if act == "shop" and phase != "reward":
                act = "back"
            await show(interaction, run, menus[act])
            return
        if act == "item" and arg in run["bag"] and not E.is_ball(arg):
            targets = E.item_targets(run, arg) if E.item_usable_now(run, arg) else []
            if not targets:
                return await notify_failure(interaction, "지금 쓸 수 있는 포켓몬이 없어요.")
            title = f"🎒 {E.item_name(arg)}"
            await show(interaction, run,
                       lambda image: ui.target_screen(uid, name, run, title, "itemt", arg, targets, image, item=arg))
            return
        if act == "itemt" and phase in ("battle", "reward"):
            item, _, t = arg.rpartition(".")
            if item in run["bag"] and t.isdigit() and E.item_moves(run, item, int(t)):
                await show(interaction, run, lambda image: ui.move_pick_screen(uid, name, run, item, int(t), image))
                return
        if act == "reward" and phase == "reward" and arg.isdigit() and int(arg) < len(run["rewards"]):
            key = run["rewards"][int(arg)]
            if E.needs_target(key):
                targets = E.reward_targets(run, key)
                if not targets:
                    return await notify_failure(interaction, "이 보상을 쓸 수 있는 포켓몬이 없어요. 다른 보상을 골라 주세요.")
                title = f"🎁 {E.reward_info(key, run)['n']}"
                await show(interaction, run,
                           lambda image: ui.target_screen(uid, name, run, title, "rewardt", arg, targets, image))
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
                await show(interaction, run, _main(uid, name, run))
                return
        except (ValueError, IndexError, KeyError) as ex:
            log.info("안 되는 동작 %s (%s): %s", act, arg, ex)
            await notify_failure(interaction, "지금은 그걸 할 수 없어요. 화면을 다시 확인해 주세요.")
            return

        run["ver"] = run.get("ver", 0) + 1
        if stay == "shop":
            await show(interaction, run, lambda image: ui.shop_screen(uid, name, run, shop_cat, image))
        else:
            await show(interaction, run, _main(uid, name, run))

        if run["phase"] in ("over", "clear"):
            cleared = run["wave"] if run["phase"] == "clear" else run["wave"] - 1
            storage.cache_run(uid, None)
            _bg(storage.finish_run(uid, name, run, cleared, run["phase"] == "clear"), "게임 기록")
            log.info("게임 종료: %s %d웨이브", user, cleared)
        else:
            _bg(storage.save_run(uid, run), "게임 저장")


# ---------- 명령어 ----------
@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    cmd = interaction.command.name if interaction.command else "?"
    log.warning("/%s 처리 실패: %s", cmd, short_error(getattr(error, "original", error)))
    await notify_failure(interaction)


@bot.tree.command(name="스타팅", description="스타팅 포켓몬을 골라 새 게임(모험)을 시작해요")
async def start(interaction: discord.Interaction):
    uid = interaction.user.id
    run = await get_run(uid)
    if run and run["phase"] in ACTIVE:
        await show(interaction, run, _main(uid, interaction.user.display_name, run), send=True,
                   content="진행 중인 게임이 있어요! 이어서 하거나, 🏳️ 포기 후 새로 시작할 수 있어요.")
        return
    content, embeds, view = ui.region_screen(uid)
    await interaction.response.send_message(content=content or None, embeds=embeds, view=view)


@bot.tree.command(name="이어하기", description="진행 중인 게임 화면을 다시 불러와요")
async def resume(interaction: discord.Interaction):
    uid = interaction.user.id
    run = await get_run(uid)
    if not run or run["phase"] not in ACTIVE:
        await interaction.response.send_message("진행 중인 게임이 없어요. `/스타팅`으로 시작해 보세요!", ephemeral=True)
        return
    await show(interaction, run, _main(uid, interaction.user.display_name, run), send=True)


@bot.tree.command(name="내포켓몬", description="이번 게임의 파티를 보고, 한 마리씩 자세히 볼 수 있어요")
async def my_pokemon(interaction: discord.Interaction):
    uid = interaction.user.id
    run = await get_run(uid)
    if not run:
        await interaction.response.send_message("진행 중인 게임이 없어요. `/스타팅`으로 시작해 보세요!", ephemeral=True)
        return
    await show(interaction, run, lambda image: ui.party_screen(uid, interaction.user.display_name, run, image), send=True)


@bot.tree.command(name="기록", description="내 최고 기록과 랭킹을 봐요")
async def records(interaction: discord.Interaction):
    try:
        trainer, top = await asyncio.wait_for(
            asyncio.gather(storage.get_trainer(interaction.user.id), storage.leaderboard(10)), timeout=2.5)
    except asyncio.TimeoutError:
        await interaction.response.send_message("기록을 불러오는 중이에요. 잠깐 뒤에 다시 시도해 주세요.", ephemeral=True)
        return
    await interaction.response.send_message(embed=ui.records(trainer, top, interaction.user.id))


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN 환경변수를 설정해 주세요 (.env 파일 참고)")
    bot.run(TOKEN, root_logger=True)
