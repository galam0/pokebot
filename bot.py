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


# ---------- 버튼 처리 ----------
# ---------- 그림 ----------
async def render_scene(run: dict) -> discord.File | None:
    """배틀/보상 화면 그림. 실패하면 None → 글자 화면으로 대신 보여준다."""
    try:
        p, e = run["p"], run.get("e")
        reward = run["phase"] == "reward"
        await sprites.ensure(
            sids=[x for x in ([e["sid"]] if e else []) + ([p["sid"]] if reward else [])],
            backs=[p["sid"]],
            items=[scene.REWARD_ICON[k] for k in run.get("rewards", [])] if reward else [],
            timeout=1.0)
        if reward:
            png = await asyncio.to_thread(scene.rewards, run, sprites.get_sprite, sprites.get_item)
        else:
            png = await asyncio.to_thread(scene.battle, run, sprites.get_sprite)
        return discord.File(io.BytesIO(png), filename=ui.SCENE_FILE)
    except Exception as ex:
        log.warning("화면 그림 실패: %s", short_error(ex))
        return None


async def render_summary(run: dict) -> discord.File | None:
    try:
        await sprites.ensure(sids=[run["p"]["sid"]], timeout=1.0)
        png = await asyncio.to_thread(scene.summary, run, sprites.get_sprite)
        return discord.File(io.BytesIO(png), filename=ui.SUMMARY_FILE)
    except Exception as ex:
        log.warning("상태창 그림 실패: %s", short_error(ex))
        return None


def prefetch_next(run: dict):
    """응답을 보낸 뒤, 다음에 필요할 그림을 미리 받아 둔다."""
    p = run["p"]
    evos = [c for c, _ in D.SPECIES[p["sid"]]["evo"]]
    nxt = (run.get("next_e") or {}).get("mon")
    sprites.prefetch(sids=[nxt["sid"]] if nxt else [], backs=evos)


async def show_battle(interaction: discord.Interaction, run: dict):
    file = await render_scene(run)
    embed, view = ui.battle_screen(interaction.user.id, interaction.user.display_name, run, image=file is not None)
    await interaction.response.edit_message(content=None, embeds=[embed], view=view,
                                            attachments=[file] if file else [])
    prefetch_next(run)


async def send_battle(interaction: discord.Interaction, run: dict, content: str | None = None):
    file = await render_scene(run)
    embed, view = ui.battle_screen(interaction.user.id, interaction.user.display_name, run, image=file is not None)
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(content=content, embed=embed, view=view, **kwargs)
    prefetch_next(run)


async def send_summary(interaction: discord.Interaction, run: dict, ephemeral: bool):
    file = await render_summary(run)
    embed = ui.mon_detail(interaction.user.display_name, run, image=file is not None)
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral, **kwargs)


async def handle_component(interaction: discord.Interaction, custom_id: str):
    parts = custom_id.split(":")
    _, uid, ver, act = parts[:4]
    arg = parts[4] if len(parts) > 4 else ""
    uid, ver = int(uid), int(ver)
    user = interaction.user
    if user.id != uid:
        await interaction.response.send_message("다른 트레이너의 화면이에요. `/스타팅`으로 직접 모험을 시작해 보세요!", ephemeral=True)
        return

    async with storage.lock(uid):
        run = await storage.get_run(uid)

        # --- 스타팅 고르기 (게임이 없을 때) ---
        if act in ("region", "regions", "starter", "new"):
            if run and run["phase"] in ("battle", "reward"):
                await show_battle(interaction, run)   # 이미 진행 중인 게임이 있으면 그 화면으로
                return
            if act == "region":
                region = (interaction.data.get("values") or [""])[0]
                content, embeds, view = ui.starter_screen(uid, region)
                ids = ui.REGIONS.get(region, [])
                sprites.prefetch(backs=ids + [c for s in ids for c, _ in D.SPECIES[s]["evo"]])
            elif act == "starter":
                run = E.new_run(int(arg), rng)
                run["ver"] = 1
                storage.cache_run(uid, run)
                await show_battle(interaction, run)
                _bg(storage.save_run(uid, run), "게임 저장")
                log.info("새 게임: %s → %s", user, run["starter"])
                return
            else:
                content, embeds, view = ui.region_screen(uid)
            await interaction.response.edit_message(content=content or None, embeds=embeds, view=view)
            return

        if not run:
            await interaction.response.edit_message(content="이 게임은 이미 끝났어요. `/스타팅`으로 새로 시작해 보세요.",
                                                    embeds=[], view=None)
            return

        # --- 상세 정보는 버전과 상관없이 보여줌 ---
        if act == "info":
            await send_summary(interaction, run, ephemeral=True)
            return

        if ver != run.get("ver", 0):
            await interaction.response.send_message(
                "지나간 화면의 버튼이에요. 최신 화면에서 눌러 주세요. 화면을 잃어버렸다면 `/이어하기`를 써 보세요.",
                ephemeral=True)
            return

        if act == "quit":
            file = await render_scene(run)
            embed, _ = ui.battle_screen(uid, user.display_name, run, image=file is not None)
            embed.add_field(name="🏳️ 정말 포기할까요?", value="포기하면 이번 게임은 여기서 끝나고 기록만 남아요.", inline=False)
            await interaction.response.edit_message(embeds=[embed], view=ui.quit_confirm(uid, run["ver"]),
                                                    attachments=[file] if file else [])
            return
        if act == "back":
            await show_battle(interaction, run)
            return

        if act == "quitok":
            run["log"] = ["🏳️ 게임을 포기했다."]
            run["phase"] = "over"
        elif act == "move" and run["phase"] == "battle":
            idx = int(arg)
            if not run["p"]["rc"] and not 0 <= idx < len(run["p"]["moves"]):
                return await notify_failure(interaction, "그 기술은 이제 없어요.")
            E.take_turn(run, idx, rng)
        elif act == "reward" and run["phase"] == "reward":
            E.choose_reward(run, int(arg), rng)
        elif act == "skip" and run["phase"] == "reward":
            E.skip_reward(run, rng)
        else:
            await show_battle(interaction, run)
            return

        run["ver"] = run.get("ver", 0) + 1
        await show_battle(interaction, run)

        if run["phase"] in ("over", "clear"):
            cleared = run["wave"] if run["phase"] == "clear" else run["wave"] - 1
            storage.cache_run(uid, None)
            _bg(storage.finish_run(uid, user.display_name, run, cleared, run["phase"] == "clear"), "게임 기록")
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
    run = await storage.get_run(uid)
    if run and run["phase"] in ("battle", "reward"):
        await send_battle(interaction, run,
                          content="진행 중인 게임이 있어요! 이어서 하거나, 🏳️ 포기 후 새로 시작할 수 있어요.")
        return
    content, embeds, view = ui.region_screen(uid)
    await interaction.response.send_message(content=content or None, embeds=embeds, view=view)


@bot.tree.command(name="이어하기", description="진행 중인 게임 화면을 다시 불러와요")
async def resume(interaction: discord.Interaction):
    uid = interaction.user.id
    run = await storage.get_run(uid)
    if not run or run["phase"] not in ("battle", "reward"):
        await interaction.response.send_message("진행 중인 게임이 없어요. `/스타팅`으로 시작해 보세요!", ephemeral=True)
        return
    await send_battle(interaction, run)


@bot.tree.command(name="내포켓몬", description="이번 게임에서 함께하는 포켓몬의 능력치와 기술을 봐요")
async def my_pokemon(interaction: discord.Interaction):
    run = await storage.get_run(interaction.user.id)
    if not run:
        await interaction.response.send_message("진행 중인 게임이 없어요. `/스타팅`으로 시작해 보세요!", ephemeral=True)
        return
    await send_summary(interaction, run, ephemeral=False)


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
