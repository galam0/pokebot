"""포켓몬 디스코드 봇.

- 모험: 관동 지방을 돌아다니며 체육관 배지 8개 → 사천왕·챔피언 (계속 저장, /초기화로 처음부터)
- 데일리·주간 챌린지: PokeRogue식 웨이브 게임 (모두 같은 조건, 랭킹)
"""

import asyncio
import time
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
from game import adventure as A
from game import data as D
from game import engine as E
from game import heroes as H
from game import kanto as K
from game import scene
from game.text import josa

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
_health_started = False


async def start_health_server():
    global _health_started
    port = os.getenv("PORT")
    if not port or _health_started:
        return
    _health_started = True
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
        # 채널 보기·메시지 보내기·임베드·파일 첨부·기록 보기·공개 스레드 만들기·스레드에 메시지 보내기
        perms = 1024 | 2048 | 16384 | 32768 | 65536 | (1 << 35) | (1 << 38)
        log.info("초대 링크: https://discord.com/oauth2/authorize?client_id=%s&scope=bot+applications.commands"
                 "&permissions=%d", self.application_id or self.user.id, perms)
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
            elif custom_id.startswith("pd:"):
                await handle_dex(interaction, custom_id)
            elif custom_id.startswith("pm:"):
                await handle_menu(interaction, custom_id)
        except Exception as e:
            log.exception("버튼 처리 실패 (%s): %s", custom_id, short_error(e))
            await notify_failure(interaction)


bot = PokeBot()

ACTIVE = ("battle", "reward", "switch", "replace", "learn", "field")
KST = timezone(timedelta(hours=9))


def today_key() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def week_key() -> str:
    y, w, _ = datetime.now(KST).isocalendar()
    return f"{y}-W{w:02d}"


def period_of(mode: str) -> str:
    return today_key() if mode == "daily" else week_key()


async def get_run(uid: int, mode: str = "adventure") -> dict | None:
    run = await storage.get_run(uid, mode)
    if not run:
        return None
    E.normalize(run)
    return A.normalize(run) if run.get("mode") == "adventure" else run


def record_dex(uid: int, run: dict):
    """잡거나 진화한 포켓몬을 도감에 남긴다 (응답 뒤 백그라운드)"""
    sids = list(run.pop("caught_list", []) or [])
    for m in run["party"] + run.get("box", []):
        sids += m.pop("evolved", []) or []
    if sids:
        _bg(storage.add_dex(uid, sids), "도감 저장")


# ---------- 그림 ----------
def _party_sids(run: dict) -> list[int]:
    return [m["sid"] for m in run["party"]]


GIF_SLOW_SEC = 2.0        # 배틀 GIF를 응답 안에서 만드는 데 이보다 오래 걸리면 한동안 멈춘 그림으로
_gif_slow_until = 0.0


def _note_slow_gif(sec: float):
    global _gif_slow_until
    _gif_slow_until = time.monotonic() + 300
    log.warning("배틀 GIF가 %.1f초 걸려서 5분 동안 멈춘 그림으로 응답해요", sec)


async def render(run: dict, kind: str = "scene", animate: bool = False, **kwargs) -> discord.File | None:
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
        elif kind == "result":
            await sprites.ensure(icons=_party_sids(run), timeout=1.0)
            png = await asyncio.to_thread(scene.battle_result, run, sprites.get_icon, sprites.get_sprite)
            name = ui.SCENE_FILE
        elif kind == "intro":
            await sprites.ensure(trainers=[H.of(run)], timeout=1.0)
            png = await asyncio.to_thread(scene.trainer_intro, run, sprites.get_trainer)
            name = ui.SCENE_FILE
        elif kind == "pc":
            page = kwargs.get("page", 0)
            shown = run["box"][page * ui.PC_PAGE:(page + 1) * ui.PC_PAGE] + run["party"]
            await sprites.ensure(icons=[m["sid"] for m in shown], timeout=1.0)
            png = await asyncio.to_thread(scene.pc, run, page, sprites.get_icon, sprites.get_sprite, ui.PC_PAGE)
            name = ui.SCENE_FILE
        elif kind == "map":
            png = await asyncio.to_thread(scene.kanto_map, run)
            name = ui.SCENE_FILE
        elif kind == "field" or run["phase"] == "field":
            place = kwargs.get("place", "field")
            if not scene.place_data(run["loc"], "field"):   # 원본 맵이 없는 곳은 그린 배경 (포켓몬 그림 필요)
                await sprites.ensure(sids=_party_sids(run), trainers=[H.of(run)], timeout=1.0)
            else:   # 걷는 그림이 없는 주인공은 얼굴 그림
                await sprites.ensure(trainers=[H.of(run)], timeout=1.0)
            png = await asyncio.to_thread(scene.field, run, sprites.get_sprite, sprites.get_trainer, place)
            name = ui.SCENE_FILE
        elif run["phase"] == "reward":
            await sprites.ensure(sids=_party_sids(run),
                                 items=[scene.reward_icon(k) for k in run.get("rewards", [])], timeout=1.0)
            png = await asyncio.to_thread(scene.rewards, run, sprites.get_sprite, sprites.get_item)
            name = ui.SCENE_FILE
        elif animate:   # 배틀 GIF (버튼이 먼저 나간 뒤 뒤에서 만들어 바꿔 끼운다)
            await sprites.ensure(sids=[e["sid"]] if e else [], backs=[p["sid"]], anims=[e["sid"]] if e else [],
                                 anim_backs=[p["sid"]], timeout=4.0)
            png = await asyncio.to_thread(scene.battle_gif, run, sprites.get_sprite, sprites.get_anim)
            name = ui.SCENE_GIF
        else:   # 배틀: 움직이는 그림을 미리 받아 뒀으면 바로 GIF, 아니면 멈춘 그림 (응답은 3초 안에)
            await sprites.ensure(sids=[e["sid"]] if e else [], backs=[p["sid"]], timeout=1.0)
            ready = (e is None or sprites.has_anim(e["sid"], False)) and sprites.has_anim(p["sid"], True)
            if ready and time.monotonic() >= _gif_slow_until:
                t0 = time.monotonic()
                png = await asyncio.to_thread(scene.battle_gif, run, sprites.get_sprite, sprites.get_anim)
                name = ui.SCENE_GIF
                if time.monotonic() - t0 > GIF_SLOW_SEC:
                    _note_slow_gif(time.monotonic() - t0)
            else:
                sprites.prefetch(anims=[e["sid"]] if e else [], anim_backs=[p["sid"]])
                png = await asyncio.to_thread(scene.battle, run, sprites.get_sprite, None, sprites.get_anim)
                name = ui.SCENE_FILE
        return discord.File(io.BytesIO(png), filename=name)
    except Exception as ex:
        log.warning("그림 실패 (%s): %s", kind, short_error(ex))
        return None


def prefetch_next(run: dict):
    """응답을 보낸 뒤, 다음에 필요할 그림을 미리 받아 둔다."""
    evos = [c for m in run["party"] for c, *_ in D.SPECIES[m["sid"]]["evo"]]
    nxt = (run.get("next_e") or {}).get("mon")
    ahead = [nxt["sid"]] if nxt else []
    if run.get("e"):   # 트레이너 등장 화면 다음에 나올 상대 포켓몬
        ahead.append(run["e"]["sid"])
    if run.get("mode") == "adventure":   # 이 장소의 야생 포켓몬, 트레이너의 다음 포켓몬
        ahead += [w[0] for w in A.loc(run).get("wild", [])]
        ahead += [m["sid"] for m in (run.get("battle") or {}).get("queue", [])[:1]]
    sprites.prefetch(sids=ahead + _party_sids(run), backs=evos + _party_sids(run),
                     anims=ahead[:6], anim_backs=_party_sids(run)[:2])


async def show(interaction: discord.Interaction, run: dict, make, send: bool = False, ephemeral: bool = False,
               content: str | None = None):
    """make(image: bool) -> ui.Screen 를 그림과 함께 보여준다 (send=False면 지금 메시지를 바꿈)"""
    probe = make(True)
    seq = _screen_seq[interaction.user.id] = _screen_seq.get(interaction.user.id, 0) + 1
    file = await render(run, probe.image, **probe.image_args)
    sc = probe if file else make(False)
    if file and sc.embed.image and sc.embed.image.url != f"attachment://{file.filename}":
        sc.embed.set_image(url=f"attachment://{file.filename}")
    if send:
        kwargs = {"file": file} if file else {}
        await interaction.response.send_message(content=content or sc.content, embed=sc.embed, view=sc.view,
                                                ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.edit_message(content=content, embeds=[sc.embed], view=sc.view,
                                                attachments=[file] if file else [])
    prefetch_next(run)
    if file and file.filename == ui.SCENE_FILE and probe.image == "scene" and _is_battle_scene(run):
        # 멈춘 그림으로 응답했으면 움직이는 그림을 뒤에서 바꿔 끼워 본다 (Render 공유 IP는 429로 막히는 일이 많다)
        _bg(_animate(interaction, run, sc.embed, seq), "배틀 GIF")


_screen_seq: dict[int, int] = {}   # 유저 -> 마지막으로 보여 준 화면 번호 (가방·교체 메뉴는 ver가 안 바뀌어서 따로 센다)


def _is_battle_scene(run: dict) -> bool:
    return run["phase"] not in ("field", "reward") and not (run.get("battle") or {}).get("intro")


_gif_pause_until = 0.0   # 디스코드(클라우드플레어)가 429를 주면 잠시 GIF 바꿔 끼우기를 쉰다 (계속 두드리면 더 오래 막힌다)


async def _animate(interaction: discord.Interaction, run: dict, embed: discord.Embed, seq: int):
    """배틀 화면의 멈춘 그림을 움직이는 GIF로 바꿔 끼운다. 그사이 화면이 바뀌었으면(다음 턴·가방 등) 버린다.
    버튼 메시지는 봇 계정 경로(채널 메시지 수정)로 바꾼다: 인터랙션 웹후크 경로(edit_original_response)는
    Render 공유 IP에서 클라우드플레어 429로 막힌다 (로그에서 확인)."""
    global _gif_pause_until
    if time.monotonic() < _gif_pause_until:
        return
    uid = interaction.user.id
    p, e = E.lead(run), run.get("e")
    await sprites.ensure(anims=[e["sid"]] if e else [], anim_backs=[p["sid"]], timeout=4.0)
    if _screen_seq.get(uid) != seq:   # 그림을 받는 사이에 화면이 바뀌었다
        return
    gif = await render(run, "scene", animate=True)
    if not gif or _screen_seq.get(uid) != seq:
        return
    embed = embed.copy()
    embed.set_image(url=f"attachment://{gif.filename}")
    msg = interaction.message
    try:
        if msg is not None and not msg.flags.ephemeral:
            await msg.edit(embeds=[embed], attachments=[gif])
        else:   # 슬래시 명령어 응답·나만 보이는 메시지는 웹후크 경로뿐
            await interaction.edit_original_response(embeds=[embed], attachments=[gif])
    except discord.HTTPException as ex:
        if ex.status == 429:
            _gif_pause_until = time.monotonic() + 600
            log.warning("배틀 GIF: 429라서 10분 동안 멈춘 그림만 보여줘요")
            return
        raise


def _main(slot: str, trainer: str, run: dict):
    return lambda image: ui.battle_screen(slot, trainer, run, image)


async def send_summary(interaction: discord.Interaction, run: dict, index: int | None, ephemeral: bool):
    file = await render(run, "summary", index=index)
    embed = ui.mon_detail(interaction.user.display_name, run, index, image=file is not None)
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral, **kwargs)


# ---------- 스레드 ----------
async def post_in_thread(interaction: discord.Interaction, thread_name: str, content: str | None,
                         embeds: list[discord.Embed], view: discord.ui.View, files: list[discord.File] = ()):
    """게임 전용 스레드를 만들어 그 안에 올린다. 스레드를 못 만들면(권한·DM 등) 지금 채널에 바로 올린다."""
    ch = interaction.channel
    kwargs = {"files": list(files)} if files else {}
    if isinstance(ch, discord.TextChannel):
        try:
            thread = await ch.create_thread(name=thread_name[:90], type=discord.ChannelType.public_thread,
                                            auto_archive_duration=1440)
        except Exception as ex:   # 권한이 없으면 지금 채널에서
            log.info("스레드를 못 만들어서 채널에 올려요: %s", short_error(ex))
        else:
            # 3초 제한: 그림 올리기(느림)보다 응답을 먼저 보낸다
            await interaction.response.send_message(f"🎮 {thread.mention} 에서 게임을 시작했어요!", ephemeral=True)
            try:
                await thread.send(content=content, embeds=embeds, view=view, **kwargs)
            except Exception as ex:
                log.warning("스레드에 올리기 실패: %s", short_error(ex))
                for f in files:
                    f.reset()
                await thread.send(content=content, embeds=embeds, view=view, **kwargs)
            return
    await interaction.response.send_message(content=content, embeds=embeds, view=view, **kwargs)


async def heroes_file(hero: str) -> discord.File | None:
    """주인공 고르기 그림 (6·8·9세대 주인공 그림은 처음 한 번 받아 온다)"""
    try:
        await sprites.ensure(trainers=[k for k, *_ in H.HEROES], timeout=1.0)
        png = await asyncio.to_thread(scene.heroes, hero, sprites.get_trainer)
        return discord.File(io.BytesIO(png), filename=ui.HEROES_FILE)
    except Exception as ex:
        log.warning("주인공 그림 실패: %s", short_error(ex))
        return None


async def starters_file(region: str) -> discord.File | None:
    """스타팅 후보 3마리 그림"""
    try:
        sids = ui.REGIONS[region]
        await sprites.ensure(sids=sids, timeout=1.0)
        png = await asyncio.to_thread(scene.starters, region, sids, sprites.get_sprite)
        return discord.File(io.BytesIO(png), filename=ui.STARTERS_FILE)
    except Exception as ex:
        log.warning("스타팅 그림 실패: %s", short_error(ex))
        return None


async def intro_file() -> discord.File | None:
    """모험 시작 설명 그림 (오박사 연구소)"""
    try:
        png = await asyncio.to_thread(scene.intro)
        return discord.File(io.BytesIO(png), filename=ui.INTRO_FILE)
    except Exception as ex:
        log.warning("시작 화면 그림 실패: %s", short_error(ex))
        return None


async def start_game(interaction: discord.Interaction, mode: str):
    """모험 / 데일리 / 주간 챌린지 시작 화면"""
    user = interaction.user
    uid, name = user.id, user.display_name
    slot = ui.slot_of(uid, mode)
    run = await get_run(uid, mode)
    if run and run["phase"] in ACTIVE:
        await show(interaction, run, _main(slot, name, run), send=True,
                   content="모험을 이어서 해요!" if mode == "adventure" else
                   "진행 중인 게임이 있어요! 이어서 하거나, 🏳️ 포기 후 새로 시작할 수 있어요.")
        return
    files = []
    if mode == "adventure":
        file = await intro_file()
        files = [file] if file else []
        content, embeds, view = ui.adventure_intro_screen(slot, image=bool(files))
        sprites.prefetch(trainers=[k for k, *_ in H.HEROES])
        sprites.prefetch(backs=ui.REGIONS["관동"] + [4, 7, 1])
        title = f"{name}의 관동 모험"
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
    await post_in_thread(interaction, title, content or None, embeds, view, files)


# ---------- 그림 도감 (pd:<유저>:<세대|sel>:<쪽>) ----------
async def show_dex(interaction: discord.Interaction, user, gen: int, page: int, send: bool, ephemeral: bool = False):
    from game import scene as S
    dex = storage.dex(user.id)
    gen = max(1, min(9, gen))
    page = max(0, min(page, S.dex_pages(gen) - 1))
    file = None
    try:
        sids = [s for s in S.dex_page_sids(gen, page) if s in dex]
        await sprites.ensure(icons=sids, timeout=1.5)
        png = await asyncio.to_thread(S.dex_page, gen, page, dex, sprites.get_sprite, user.display_name,
                                      sprites.get_icon)
        file = discord.File(io.BytesIO(png), filename=ui.DEX_FILE)
    except Exception as ex:
        log.warning("도감 그림 실패: %s", short_error(ex))
    embed, view = ui.dex_screen(user.id, user.display_name, dex, gen, page, image=file is not None)
    if send:
        kwargs = {"file": file} if file else {}
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral, **kwargs)
    else:
        await interaction.response.edit_message(embeds=[embed], view=view, attachments=[file] if file else [])
    nxt = [s for s in S.dex_page_sids(gen, page + 1) if s in dex] if page + 1 < S.dex_pages(gen) else []
    sprites.prefetch(icons=nxt)


async def handle_dex(interaction: discord.Interaction, custom_id: str):
    _, owner, gen, page = custom_id.split(":")[:4]
    if int(owner) != interaction.user.id:
        await interaction.response.send_message("다른 트레이너의 도감이에요. `/도감`으로 내 도감을 열어 보세요.", ephemeral=True)
        return
    if gen == "sel":
        gen, page = (interaction.data.get("values") or ["1"])[0], "0"
    await show_dex(interaction, interaction.user, int(gen), int(page), send=False)


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
        await start_game(interaction, {"new": "adventure"}.get(act, act))
    elif act == "reset":
        await ask_reset(interaction)
    elif act == "resetok":
        if not await get_run(uid, "adventure"):
            await interaction.response.edit_message(content="지울 모험이 없어요.", embeds=[], view=None)
            return
        async with storage.lock(uid):
            await storage.delete_run(uid, "adventure")
        log.info("모험 초기화: %s", user)
        await interaction.response.edit_message(
            content="🗑️ 모험을 초기화했어요. `/스타팅`으로 오박사 연구소에서 다시 시작할 수 있어요. (도감 기록은 남아 있어요)",
            embeds=[], view=None)
    elif act == "resetno":
        await interaction.response.edit_message(content="초기화를 취소했어요.", embeds=[], view=None)
    elif act == "resume":
        runs = [(m, r) for m in ui.MODES if (r := await get_run(uid, m)) and r["phase"] in ACTIVE]
        if not runs:
            await interaction.response.send_message("진행 중인 게임이 없어요. 새 게임을 시작해 보세요!", ephemeral=True)
            return
        mode, run = runs[0]
        await show(interaction, run, _main(ui.slot_of(uid, mode), name, run), send=True,
                   content=None if len(runs) == 1 else f"진행 중인 게임이 {len(runs)}개라 {ui.MODE_KO[mode]} 게임을 불러왔어요. "
                                                       "다른 게임은 `/이어하기`에서 골라 주세요.")
    elif act == "dex":
        await show_dex(interaction, user, 1, 0, send=True, ephemeral=True)
    elif act == "records":
        await send_records(interaction, ephemeral=True)
    elif act == "help":
        await interaction.response.send_message(embed=ui.help_embed(), view=ui.help_view(uid), ephemeral=True)
    elif act == "helpt":   # 도움말 주제 바꾸기
        topic = (interaction.data.get("values") or ["start"])[0]
        await interaction.response.edit_message(embed=ui.help_embed(topic), view=ui.help_view(uid, topic))
    else:
        await interaction.response.send_message("알 수 없는 메뉴예요.", ephemeral=True)


async def ask_reset(interaction: discord.Interaction):
    uid = interaction.user.id
    run = await get_run(uid, "adventure")
    if not run:
        await interaction.response.send_message("진행 중인 모험이 없어요.", ephemeral=True)
        return
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="정말 초기화하기", style=discord.ButtonStyle.danger, custom_id=f"pm:{uid}:resetok"))
    view.add_item(discord.ui.Button(label="취소", style=discord.ButtonStyle.secondary, custom_id=f"pm:{uid}:resetno"))
    view.stop()
    await interaction.response.send_message(
        f"⚠️ 모험을 처음부터 다시 할까요? 지금 진행({A.summary_line(run)}, 파티·박스 포켓몬, 가방, 돈)이 **모두 사라져요.** "
        "도감 기록은 남아요.", view=view, ephemeral=True)


# ---------- 게임 버튼 (pr:<슬롯>:<버전>:<동작>[:<값>]) ----------
def _buy(run: dict, arg: str):
    item, _, n = arg.rpartition(".")
    return A.buy(run, item, int(n or 1))


PLACE_OF = {"heal": "center", "gym": "gym", "league": "center"}   # 동작 → 필드에서 보여줄 장면

ADV_ACTIONS = {   # 모험 필드에서 하는 동작: (run, arg)
    "explore": lambda run, arg: A.explore(run, rng),
    "trainer": lambda run, arg: A.fight_trainer(run, rng),
    "gym": lambda run, arg: A.challenge_gym(run, rng),
    "league": lambda run, arg: A.challenge_league(run, rng),
    "next": lambda run, arg: A.next_challenger(run, rng),
    "legend": lambda run, arg: A.meet_legend(run, rng),
    "gift": lambda run, arg: A.take_gift(run, rng),
    "gift2": lambda run, arg: A.take_gift_choice(run, int(arg), rng),
    "heal": lambda run, arg: A.heal(run),
    "goto": lambda run, arg: A.move(run, arg, rng),
    "buy": _buy,
    "dep": lambda run, arg: A.deposit(run, int(arg)),
    "wd": lambda run, arg: A.withdraw(run, int(arg)),
    "lead": lambda run, arg: A.set_lead(run, int(arg)),
}


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
        if act in ("starter", "new", "region", "hero", "heropick"):
            if run and run["phase"] in ACTIVE:
                await show(interaction, run, _main(slot, name, run))   # 이미 진행 중인 게임이 있으면 그 화면으로
                return
            if act in ("hero", "heropick"):   # 모험 시작 2단계: 주인공 고르기 (메뉴 / 다음·이전 버튼)
                hero = H.valid((interaction.data.get("values") or [arg])[0] if act == "hero" else arg)
                file = await heroes_file(hero)
                content, embeds, view = ui.hero_screen(slot, hero, image=file is not None)
                await interaction.response.edit_message(content=content or None, embeds=embeds, view=view,
                                                        attachments=[file] if file else [])
                sprites.prefetch(sids=ui.REGIONS["관동"], backs=ui.REGIONS["관동"])
                return
            if act == "region":   # 모험 시작 3단계: 스타팅 고르기 (다음 버튼 / 다른 지방 메뉴)
                region = (interaction.data.get("values") or ["관동"])[0]
                region = region if region in ui.REGIONS else "관동"
                file = await starters_file(region)
                content, embeds, view = ui.adventure_start_screen(slot, region, H.valid(arg), image=file is not None)
                await interaction.response.edit_message(content=content or None, embeds=embeds, view=view,
                                                        attachments=[file] if file else [])
                sprites.prefetch(backs=ui.REGIONS[region])
                return
            if act == "new":   # 데일리·챌린지가 끝난 화면의 버튼
                await interaction.response.edit_message(view=None)
                return
            arg, _, hero = arg.partition(".")   # 모험 스타팅 버튼: "<종>.<주인공>"
            sid = int(arg or (interaction.data.get("values") or ["0"])[0])
            if mode == "adventure":
                if sid not in A.STARTERS:
                    return await notify_failure(interaction, "고를 수 없는 포켓몬이에요.")
                run = A.new_adventure(sid, rng, name)
                run["hero"] = H.valid(hero)
            else:
                seed = period_of(mode)
                if storage.has_result(mode, seed, uid):
                    return await notify_failure(interaction, "이번 기간에는 이미 도전했어요.")
                if sid not in (E.daily_starters(seed) if mode == "daily" else E.challenge_starters(seed)):
                    return await notify_failure(interaction, "고를 수 없는 포켓몬이에요.")
                run = E.new_run(sid, rng, mode, seed)
            run["ver"] = 1
            storage.cache_run(uid, mode, run)
            record_dex(uid, run)
            await show(interaction, run, _main(slot, name, run))
            _bg(storage.save_run(uid, mode, run), "게임 저장")
            log.info("새 게임(%s): %s → %s", mode, user, sid)
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
        adv = mode == "adventure"
        if adv:
            run["name"] = name   # 랭킹에 보일 이름
        # --- 메뉴 열기 (게임 상태는 그대로) ---
        if act in ("bagcat", "shopcat", "martcat"):   # 종류 고르기 (선택 메뉴)
            arg = (interaction.data.get("values") or [""])[0]
            act = act[:-3]
        elif act in ("wd", "lead"):   # 선택 메뉴 (PC에서 데려오기, 맨 앞 포켓몬)
            arg = (interaction.data.get("values") or [""])[0]
        menus = {
            "quit": lambda image: ui.quit_screen(slot, name, run, image),
            "bag": lambda image: ui.bag_screen(slot, name, run, arg or None, image),
            "swmenu": lambda image: ui.switch_screen(slot, name, run, image),
            "shop": lambda image: ui.shop_screen(slot, name, run, arg or None, image),
            "mart": lambda image: ui.mart_screen(slot, name, run, arg or None, image),
            "go": lambda image: ui.move_screen(slot, name, run, image),
            "pc": lambda image: ui.pc_screen(slot, name, run, int(arg) if arg.lstrip("-").isdigit() else 0, image),
            "back": _main(slot, name, run),
        }
        field_only = not A.in_league(run) if adv else False
        if act == "bag" and phase not in ("battle", "reward", "field"):
            act = "back"
        if act in menus:
            if act == "swmenu" and (phase != "battle" or len(E.alive(run)) < 2):
                act = "back"
            if act == "shop" and (adv or phase != "reward" or not E.shop_open(run)):
                act = "back"
            if act == "quit" and adv:
                act = "back"
            if act in ("mart", "go", "pc") and not (adv and phase == "field" and field_only):
                act = "back"
            if act == "mart" and not A.loc(run).get("mart"):
                act = "back"
            if act == "pc" and not A.has_center(run):
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
        if act == "itemt" and phase in ("battle", "reward", "field"):
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
        if adv and phase == "battle" and (run.get("battle") or {}).get("intro") and act != "fight":
            await show(interaction, run, _main(slot, name, run))   # 트레이너 등장 중에는 승부 버튼만
            return
        stay = None   # 바뀐 뒤 보여줄 메뉴 (없으면 기본 화면)
        loc_before = run.get("loc")
        if phase == "field":   # 배틀 결과는 필드에서 한 번 보여 주고 다음 동작에서 지운다
            run.pop("result", None)
        shop_cat = ui._shop_cat(arg) if act == "buy" and arg in E.ITEMS else None
        try:
            if adv and phase == "field" and A.in_league(run) and act not in ("next", "itemt", "itemm", "forget",
                                                                             "noforget"):
                raise ValueError("in league")
            if adv and act == "quitok":
                raise ValueError("no quit in adventure")
            if adv and phase == "field" and act in ADV_ACTIONS:
                ADV_ACTIONS[act](run, arg)
                if act in PLACE_OF:   # 센터에서 쉬면 센터 안, 체육관에 도전하면 체육관 안 장면
                    run["place"] = "home" if A.loc(run).get("home") else PLACE_OF[act]
                elif act not in ("buy", "dep", "wd", "lead"):
                    run.pop("place", None)
                if act == "buy":
                    stay, shop_cat = "mart", ui._mart_cat(arg.rpartition(".")[0])
                elif act in ("dep", "wd"):
                    stay = "pc"
            elif adv and act == "fight" and phase == "battle" and (run.get("battle") or {}).get("intro"):
                run["battle"].pop("intro")   # 트레이너 등장 → 포켓몬 배틀
            elif adv and act == "flee" and phase == "battle":
                A.flee(run)
            elif act == "quitok":
                run["log"] = ["🏳️ 게임을 포기했다."]
                run["phase"] = "over"
            elif act == "move" and phase == "battle":
                E.take_turn(run, int(arg), rng)
            elif act == "sw" and phase in ("battle", "switch"):
                E.switch(run, int(arg), rng)
            elif act == "ball" and phase == "battle":
                E.throw_ball(run, arg, rng)
            elif act == "itemt" and phase in ("battle", "reward", "field"):
                item, t = arg.rsplit(".", 1)
                E.use_item(run, item, int(t), rng)
            elif act == "itemm" and phase in ("battle", "reward", "field"):
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
                E.resolve_replace(run, int(arg), rng)
            elif act == "relnew" and phase == "replace":
                E.resolve_replace(run, None, rng)
            else:
                await show(interaction, run, _main(slot, name, run))
                return
        except (ValueError, IndexError, KeyError) as ex:
            log.info("안 되는 동작 %s (%s): %s", act, arg, ex)
            msg = str(ex) if str(ex).startswith("배지") else "지금은 그걸 할 수 없어요. 화면을 다시 확인해 주세요."
            if act == "ball" and not E.can_catch(run):
                msg = "다른 트레이너의 포켓몬은 잡을 수 없어요!"
            await notify_failure(interaction, msg)
            return

        run["ver"] = run.get("ver", 0) + 1
        if run.get("loc") != loc_before:   # 지고 센터로 돌아가는 등 장소가 바뀌면 바깥 장면
            run.pop("place", None)
        record_dex(uid, run)
        if run["phase"] != "field":
            stay = None
        if stay == "shop":
            await show(interaction, run, lambda image: ui.shop_screen(slot, name, run, shop_cat, image))
        elif stay == "mart":
            await show(interaction, run, lambda image: ui.mart_screen(slot, name, run, shop_cat, image))
        elif stay == "pc":
            await show(interaction, run, lambda image: ui.pc_screen(slot, name, run, 0, image))
        else:
            await show(interaction, run, _main(slot, name, run))

        if run["phase"] in ("over", "clear"):
            cleared = run["wave"] if run["phase"] == "clear" else run["wave"] - 1
            storage.cache_run(uid, mode, None)
            if mode != "adventure":   # 기록은 바로 메모리에 (다시 도전 못 하게)
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


async def menu_file(user) -> discord.File | None:
    """메뉴 카드 그림 (user가 없으면 누구나 보는 공용 패널)"""
    try:
        day, week = today_key(), week_key()
        rule, mono = E.weekly_rules(week)
        info = {"weekly": E.RULES[rule].split(":")[0] + (f" ({D.TYPE_KO[mono]})" if mono else ""),
                "daily": "하루 한 번 도전", "public": user is None}
        if user is not None:
            run = await get_run(user.id, "adventure")
            done = storage.has_result("daily", day, user.id)
            info.update(name=user.display_name, run=run, dex=len(storage.dex(user.id)),
                        daily=f"오늘 완료 · {done['wave']}웨이브" if done else "오늘 도전 가능")
            if run:
                await sprites.ensure(sids=_party_sids(run), timeout=1.0)
        png = await asyncio.to_thread(scene.menu, info, sprites.get_sprite)
        return discord.File(io.BytesIO(png), filename=ui.MENU_FILE)
    except Exception as ex:
        log.warning("메뉴 그림 실패: %s", short_error(ex))
        return None


@bot.tree.command(name="메뉴", description="포켓몬 메뉴 (모험·데일리·챌린지·도감·기록·초기화)")
async def menu(interaction: discord.Interaction):
    file = await menu_file(interaction.user)
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(embed=ui.menu_embed(image=file is not None),
                                            view=ui.menu_view(interaction.user.id), ephemeral=True, **kwargs)


@bot.tree.command(name="세팅", description="(관리자) 이 채널에 누구나 쓰는 게임 버튼 패널을 올려요")
@app_commands.default_permissions(manage_guild=True)
async def setup_panel(interaction: discord.Interaction):
    file = await menu_file(None)
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(embed=ui.menu_embed(public=True, image=file is not None),
                                            view=ui.menu_view(0), **kwargs)


@bot.tree.command(name="스타팅", description="오박사에게 포켓몬을 받아 관동 모험을 시작해요 (하던 모험이 있으면 이어서)")
async def start(interaction: discord.Interaction):
    await start_game(interaction, "adventure")


@bot.tree.command(name="주인공", description="모험의 주인공을 역대 주인공 중에서 바꿔요")
@app_commands.describe(주인공="바꿀 주인공")
@app_commands.choices(주인공=[app_commands.Choice(name=f"{n} ({g}세대 · {game})", value=k) for k, n, g, game in H.HEROES])
async def hero_cmd(interaction: discord.Interaction, 주인공: app_commands.Choice[str]):
    uid = interaction.user.id
    async with storage.lock(uid):
        run = await get_run(uid, "adventure")
        if not run:
            await interaction.response.send_message("아직 모험을 시작하지 않았어요. `/스타팅`에서 주인공과 스타팅을 골라 보세요!",
                                                    ephemeral=True)
            return
        run["hero"] = H.valid(주인공.value)
        storage.cache_run(uid, "adventure", run)
        _bg(storage.save_run(uid, "adventure", run), "게임 저장")
    file = await heroes_file(run["hero"])
    kwargs = {"file": file} if file else {}
    await interaction.response.send_message(josa(f"주인공을 **{H.NAMES[run['hero']]}**(으)로 바꿨어요!"), ephemeral=True, **kwargs)


@bot.tree.command(name="도움말", description="게임 방법과 명령어 안내")
async def help_cmd(interaction: discord.Interaction):
    await menu_action(interaction, "help")


@bot.tree.command(name="초기화", description="관동 모험을 처음부터 다시 시작해요 (확인 버튼이 나와요)")
async def reset(interaction: discord.Interaction):
    await ask_reset(interaction)


@bot.tree.command(name="데일리", description="오늘의 데일리 도전 (모두 같은 조건, 하루 한 번)")
async def daily(interaction: discord.Interaction):
    await start_game(interaction, "daily")


@bot.tree.command(name="챌린지", description="이번 주 챌린지 (특별 규칙, 주에 한 번)")
async def challenge(interaction: discord.Interaction):
    await start_game(interaction, "challenge")


@bot.tree.command(name="이어하기", description="진행 중인 게임 화면을 다시 불러와요")
@app_commands.describe(종류="불러올 게임 (비워 두면 진행 중인 게임 하나)")
@app_commands.choices(종류=[app_commands.Choice(name="모험", value="adventure"),
                          app_commands.Choice(name="데일리", value="daily"),
                          app_commands.Choice(name="주간 챌린지", value="challenge")])
async def resume(interaction: discord.Interaction, 종류: app_commands.Choice[str] | None = None):
    uid = interaction.user.id
    modes = [종류.value] if 종류 else ui.MODES
    for mode in modes:
        run = await get_run(uid, mode)
        if run and run["phase"] in ACTIVE:
            await show(interaction, run, _main(ui.slot_of(uid, mode), interaction.user.display_name, run), send=True)
            return
    await interaction.response.send_message("진행 중인 게임이 없어요. `/메뉴`에서 시작해 보세요!", ephemeral=True)


@bot.tree.command(name="내포켓몬", description="진행 중인 게임의 파티를 보고, 한 마리씩 자세히 볼 수 있어요")
async def my_pokemon(interaction: discord.Interaction):
    uid = interaction.user.id
    for mode in ui.MODES:
        run = await get_run(uid, mode)
        if run and run["phase"] in ACTIVE:
            slot = ui.slot_of(uid, mode)
            await show(interaction, run, lambda image: ui.party_screen(slot, interaction.user.display_name, run, image),
                       send=True)
            return
    await interaction.response.send_message("진행 중인 게임이 없어요. `/메뉴`에서 시작해 보세요!", ephemeral=True)


@bot.tree.command(name="도감", description="지금까지 잡은 포켓몬 도감을 봐요")
async def dex_cmd(interaction: discord.Interaction):
    await show_dex(interaction, interaction.user, 1, 0, send=True)


async def send_records(interaction: discord.Interaction, ephemeral: bool = False):
    me = interaction.user.id
    embeds = [ui.adventure_board(storage.adventure_rows(), me)]
    day, week = today_key(), week_key()
    embeds.append(ui.period_board_embed(f"📅 오늘의 데일리 · {day}", storage.period_board("daily", day), me))
    rule, mono = E.weekly_rules(week)
    embeds.append(ui.period_board_embed(
        f"🏆 주간 챌린지 · {week}", storage.period_board("challenge", week), me,
        "규칙: " + E.RULES[rule] + (f" ({D.TYPE_KO[mono]})" if mono else "")))
    await interaction.response.send_message(embeds=embeds, ephemeral=ephemeral)


@bot.tree.command(name="기록", description="모험 랭킹(배지·챔피언·도감)과 오늘의 데일리·이번 주 챌린지 랭킹")
async def records(interaction: discord.Interaction):
    await send_records(interaction)


async def main():
    """Render 무료 플랜의 공유 IP가 디스코드에 잠깐 막히면(429) 로그인이 실패해요.
    그때 바로 꺼지지 않고 포트를 연 채로 기다렸다가 다시 로그인해요."""
    discord.utils.setup_logging(root=True)
    await start_health_server()
    delay = 30
    async with bot:
        while True:
            try:
                await bot.login(TOKEN)
                break
            except discord.HTTPException as e:
                if e.status != 429:
                    raise
                log.warning("디스코드 로그인이 잠시 막혔어요 (429). %d초 뒤에 다시 시도해요.", delay)
                await bot.http.close()   # 실패한 로그인의 연결을 닫는다 (안 닫으면 'Unclosed client session'이 쌓인다)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 600)
        await bot.connect()


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN 환경변수를 설정해 주세요 (.env 파일 참고)")
    asyncio.run(main())
