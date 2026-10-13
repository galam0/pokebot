import os

import aiohttp
import aiosqlite
import discord
from aiohttp import web
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # 개발 중 명령어를 즉시 반영하고 싶을 때만 설정
DB_PATH = os.getenv("DB_PATH", "pokebot.db")

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

SPRITE_BASE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"


# ---------- PokeAPI ----------
_info_cache: dict[int, dict] = {}


async def get_info(species_id: int) -> dict:
    """한국어 이름과 이미지 URL을 가져온다. 실패해도 봇이 죽지 않도록 폴백 처리."""
    if species_id in _info_cache:
        return _info_cache[species_id]

    name = f"#{species_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://pokeapi.co/api/v2/pokemon-species/{species_id}",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                data = await resp.json()
        name = next(
            (n["name"] for n in data["names"] if n["language"]["name"] == "ko"),
            data["name"],
        )
    except Exception:
        pass  # 이름만 번호로 표시하고 계속 진행

    info = {
        "name": name,
        "image": f"{SPRITE_BASE}/other/official-artwork/{species_id}.png",
    }
    if not name.startswith("#"):
        _info_cache[species_id] = info
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


class GenSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="지방을 골라주세요",
            options=[discord.SelectOption(label=g, value=g) for g in STARTERS],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ids = STARTERS[self.values[0]]
        infos = [await get_info(i) for i in ids]

        embeds = [
            discord.Embed(title=info["name"], color=discord.Color.blurple()).set_thumbnail(
                url=info["image"]
            )
            for info in infos
        ]
        view = StarterView(interaction.user.id, ids, infos)
        await interaction.edit_original_response(
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
        await interaction.response.defer()

        # 중복 선택 방지 (버튼을 연타하거나 창을 여러 개 연 경우)
        if await has_any_pokemon(interaction.user.id):
            await interaction.edit_original_response(
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
        await interaction.edit_original_response(content=None, embeds=[embed], view=None)


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
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = PokeBot()


@bot.tree.command(name="시작", description="스타팅 포켓몬을 골라 모험을 시작해요")
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
            "아직 파트너가 없어요. `/시작`으로 스타팅 포켓몬을 골라보세요!", ephemeral=True
        )
        return

    await interaction.response.defer()
    info = await get_info(row["species_id"])
    name = row["nickname"] or info["name"]

    embed = discord.Embed(title=name, color=discord.Color.gold())
    embed.add_field(name="레벨", value=f"Lv.{row['level']}")
    embed.add_field(name="경험치", value=str(row["exp"]))
    embed.add_field(name="친밀도", value=f"{row['friendship']} / 255")
    embed.set_image(url=info["image"])
    embed.set_footer(text=f"{interaction.user.display_name} 트레이너의 파트너")
    await interaction.followup.send(embed=embed)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN 환경변수를 설정해 주세요 (.env 파일 참고)")
    bot.run(TOKEN)
