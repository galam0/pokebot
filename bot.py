import logging
import os

import aiohttp
import aiosqlite
import discord
from aiohttp import web
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = os.getenv("DB_PATH", "pokebot.db")

# print 대신 logging 사용 → Render 로그에 바로 찍혀요
log = logging.getLogger("pokebot")

BUSY_MSG = "디스코드 연결이 잠시 불안정해요. 잠깐 뒤에 다시 시도해 주세요."


def short_error(error: Exception) -> str:
    """Cloudflare 차단 시 HTML 페이지 전체가 로그에 찍히지 않도록 첫 줄만 남긴다."""
    return str(error).split("\n", 1)[0][:200]


# 참고: Render 무료 플랜의 공유 IP는 디스코드의 '응답 나중에 수정' 경로
# (defer 후 edit_original_response / followup)가 Cloudflare에 막히는 일이 있어요.
# 그래서 모든 응답을 interaction.response.* 로 '즉시' 보내고, defer는 쓰지 않아요.
# 디스코드는 3초 안에 응답해야 하므로 클릭 시점에는 외부 API를 부르지 않아요.


async def notify_failure(interaction: discord.Interaction):
    """처리에 실패했을 때 사용자에게 안내한다. 이것도 막혔으면 조용히 넘어간다."""
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(BUSY_MSG, ephemeral=True)
    except Exception:
        pass

# 세대별 스타팅 포켓몬 (전국도감 번호: 풀, 불꽃, 물 순서)
STARTERS = {
    "1세대 · 관동": [1, 4, 7],
    "2세대 · 성도": [152, 155, 158],
    "3세대 · 호연": [252, 255, 258],
    "4세대 · 신오": [387, 390, 393],
    "5세대 · 하나": [495, 498, 501],
    "6세대 · 칼로스": [650, 653, 656],
    "7세대 · 알로라": [722, 725, 728],
    "8세대 · 가라르": [810, 813, 816],
    "9세대 · 팔데아": [906, 909, 912],
}

# 스타팅 포켓몬 한국어 이름 (클릭할 때 PokeAPI를 기다리지 않도록 미리 넣어둠)
KO_NAMES = {
    1: "이상해씨", 4: "파이리", 7: "꼬부기",
    152: "치코리타", 155: "브케인", 158: "리아코",
    252: "나무지기", 255: "아차모", 258: "물짱이",
    387: "모부기", 390: "불꽃숭이", 393: "팽도리",
    495: "주리비얀", 498: "뚜꾸리", 501: "수댕이",
    650: "도치마론", 653: "푸호꼬", 656: "개구마르",
    722: "나몰빼미", 725: "냐오불", 728: "누리공",
    810: "흥나숭", 813: "염버니", 816: "울머기",
    906: "나오하", 909: "뜨아거", 912: "꾸왁스",
}

SPRITE_BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"


# ---------- PokeAPI ----------
_info_cache: dict[int, dict] = {}


def info_now(species_id: int) -> dict:
    """네트워크 없이 바로 쓸 수 있는 정보 (캐시 → 고정 이름 → 번호)."""
    if species_id in _info_cache:
        return _info_cache[species_id]
    return {
        "name": KO_NAMES.get(species_id, f"#{species_id}"),
        "image": f"{SPRITE_BASE}/other/official-artwork/{species_id}.png",
    }


async def get_info(species_id: int) -> dict:
    """한국어 이름과 이미지 URL. 진화 후 포켓몬처럼 고정 목록에 없으면 PokeAPI에서 가져온다."""
    info = info_now(species_id)
    if species_id in _info_cache or species_id in KO_NAMES:
        return info
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://pokeapi.co/api/v2/pokemon-species/{species_id}",
                timeout=aiohttp.ClientTimeout(total=2),  # 디스코드 3초 제한 안에 끝나도록
            ) as resp:
                data = await resp.json()
        info["name"] = next(
            (n["name"] for n in data["names"] if n["language"]["name"] == "ko"),
            data["name"],
        )
        _info_cache[species_id] = info
    except Exception:
        pass  # 이름만 번호로 표시하고 계속 진행
    return info


# ---------- DB ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pokemon (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                species_id INTEGER NOT NULL,
                nickname TEXT,
                level INTEGER NOT NULL DEFAULT 5,
                exp INTEGER NOT NULL DEFAULT 0,
                friendship INTEGER NOT NULL DEFAULT 70,
                is_partner INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def get_partner(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM pokemon WHERE owner_id = ? AND is_partner = 1 LIMIT 1",
            (user_id,),
        )
        return await cur.fetchone()


async def has_any_pokemon(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM pokemon WHERE owner_id = ? LIMIT 1", (user_id,)
        )
        return await cur.fetchone() is not None


async def create_starter(user_id: int, species_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO pokemon (owner_id, species_id) VALUES (?, ?)",
            (user_id, species_id),
        )
        await db.commit()


# ---------- 경험치 ----------
# 스타팅 포켓몬은 본가 게임에서 모두 '중간 느림(Medium Slow)' 성장 그룹이에요.
# DB의 exp는 '현재 레벨에서 모은 경험치'예요.
MAX_LEVEL = 100


def total_exp(level: int) -> int:
    """Medium Slow: 레벨 n까지 필요한 누적 경험치 = 6/5·n³ − 15n² + 100n − 140"""
    return max(0, (6 * level**3) // 5 - 15 * level**2 + 100 * level - 140)


def exp_to_next(level: int) -> int:
    """현재 레벨에서 다음 레벨까지 필요한 경험치"""
    if level >= MAX_LEVEL:
        return 0
    return total_exp(level + 1) - total_exp(level)


def exp_bar(current: int, need: int, width: int = 10) -> str:
    if need <= 0:
        return "▰" * width
    filled = min(width, current * width // need)
    return "▰" * filled + "▱" * (width - filled)


# ---------- UI ----------
class OwnerView(discord.ui.View):
    """명령어를 실행한 본인만 조작할 수 있는 View"""

    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "본인이 연 선택창만 사용할 수 있어요.", ephemeral=True
            )
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        log.warning("선택창 처리 실패 (%s): %s", type(item).__name__, short_error(error))
        await notify_failure(interaction)


class GenSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="지방을 골라주세요",
            options=[discord.SelectOption(label=g, value=g) for g in STARTERS],
        )

    async def callback(self, interaction: discord.Interaction):
        ids = STARTERS[self.values[0]]
        infos = [info_now(i) for i in ids]

        embeds = [
            discord.Embed(title=info["name"], color=discord.Color.blurple()).set_thumbnail(
                url=info["image"]
            )
            for info in infos
        ]
        view = StarterView(interaction.user.id, ids, infos)
        await interaction.response.edit_message(
            content=f"**{self.values[0]}** 스타팅 포켓몬이에요. 함께할 파트너를 골라주세요!",
            embeds=embeds,
            view=view,
        )


class GenView(OwnerView):
    def __init__(self, owner_id: int):
        super().__init__(owner_id)
        self.add_item(GenSelect())


class StarterButton(discord.ui.Button):
    def __init__(self, species_id: int, info: dict):
        super().__init__(label=info["name"], style=discord.ButtonStyle.primary)
        self.species_id = species_id
        self.info = info

    async def callback(self, interaction: discord.Interaction):
        # 중복 선택 방지 (버튼을 연타하거나 창을 여러 개 연 경우)
        if await has_any_pokemon(interaction.user.id):
            await interaction.response.edit_message(
                content="이미 파트너 포켓몬이 있어요!", embeds=[], view=None
            )
            return

        await create_starter(interaction.user.id, self.species_id)
        embed = discord.Embed(
            title=f"{self.info['name']}, 너로 정했다!",
            description=f"{interaction.user.display_name} 트레이너의 첫 파트너가 되었어요.\n`/내포켓몬`으로 상태를 확인해 보세요.",
            color=discord.Color.green(),
        )
        embed.set_image(url=self.info["image"])
        await interaction.response.edit_message(content=None, embeds=[embed], view=None)


class StarterView(OwnerView):
    def __init__(self, owner_id: int, ids: list[int], infos: list[dict]):
        super().__init__(owner_id)
        for species_id, info in zip(ids, infos):
            self.add_item(StarterButton(species_id, info))


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
        await init_db()

    # 전역 등록은 반영이 느려서, 봇이 들어가 있는 서버마다 '서버 전용'으로 등록해요.
    # → 어느 서버든 몇 초 안에 명령어가 생겨요.
    async def sync_guild(self, guild: discord.abc.Snowflake) -> int:
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        return len(synced)

    async def on_ready(self):
        log.info("로그인: %s / 서버 %d곳", self.user, len(self.guilds))
        if getattr(self, "_synced", False):  # 재연결 때마다 다시 하지 않음
            return
        self._synced = True
        for guild in self.guilds:
            try:
                count = await self.sync_guild(guild)
                log.info("명령어 %d개 동기화: %s", count, guild.name)
            except Exception as e:  # 한 서버가 실패해도 나머지는 계속
                log.warning("명령어 동기화 실패 (%s): %s", guild.name, short_error(e))

    async def on_guild_join(self, guild: discord.Guild):
        try:
            count = await self.sync_guild(guild)
            log.info("새 서버 참가: %s → 명령어 %d개 등록", guild.name, count)
        except Exception as e:
            log.warning("새 서버 명령어 등록 실패 (%s): %s", guild.name, short_error(e))


bot = PokeBot()


@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    cmd = interaction.command.name if interaction.command else "?"
    log.warning("/%s 처리 실패: %s", cmd, short_error(getattr(error, "original", error)))
    await notify_failure(interaction)


@bot.tree.command(name="스타팅", description="스타팅 포켓몬을 골라 모험을 시작해요")
async def start(interaction: discord.Interaction):
    if await has_any_pokemon(interaction.user.id):
        await interaction.response.send_message(
            "이미 파트너 포켓몬이 있어요! `/내포켓몬`으로 확인해 보세요.", ephemeral=True
        )
        return
    await interaction.response.send_message(
        "어느 지방의 스타팅 포켓몬과 함께할까요?",
        view=GenView(interaction.user.id),
        ephemeral=True,
    )


@bot.tree.command(name="내포켓몬", description="내 파트너 포켓몬의 상태를 확인해요")
async def my_pokemon(interaction: discord.Interaction):
    row = await get_partner(interaction.user.id)
    if row is None:
        await interaction.response.send_message(
            "아직 파트너가 없어요. `/스타팅`으로 스타팅 포켓몬을 골라보세요!", ephemeral=True
        )
        return

    info = await get_info(row["species_id"])
    name = row["nickname"] or info["name"]

    embed = discord.Embed(title=name, color=discord.Color.gold())
    level, exp = row["level"], row["exp"]
    need = exp_to_next(level)
    embed.add_field(name="레벨", value=f"Lv.{level}")
    embed.add_field(name="친밀도", value=f"{row['friendship']} / 255")
    if need:
        exp_text = f"{exp_bar(exp, need)}\n{exp} / {need}  ·  레벨업까지 **{need - exp}** 남음"
    else:
        exp_text = "최고 레벨이에요!"
    embed.add_field(name=f"경험치 (Lv.{level} → {level + 1})" if need else "경험치", value=exp_text, inline=False)
    embed.set_image(url=info["image"])
    embed.set_footer(text=f"{interaction.user.display_name} 트레이너의 파트너")
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN 환경변수를 설정해 주세요 (.env 파일 참고)")
    bot.run(TOKEN, root_logger=True)  # pokebot 로그도 discord 로그와 같이 출력
