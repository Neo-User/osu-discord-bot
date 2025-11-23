import os
import discord
import sqlite3
from discord import app_commands
from discord.ext import commands
from ossapi import Ossapi
from dotenv import load_dotenv

load_dotenv(override=True) # .env 파일 읽어오기

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") # 코드에서 비밀번호 사라짐!
OSU_CLIENT_ID = os.getenv("OSU_CLIENT_ID")
OSU_CLIENT_SECRET = os.getenv("OSU_CLIENT_SECRET")

conn = sqlite3.connect("osu_bot.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        discord_id INTEGER PRIMARY KEY,
        osu_username TEXT
    )
""")
conn.commit()

# ==========================================
# osu! API 및 봇 초기화
# ==========================================
try:
    osu_api = Ossapi(OSU_CLIENT_ID, OSU_CLIENT_SECRET)
    print("osu! API 연결 성공")
except Exception as e:
    print(f"osu! API 연결 실패: {e}")
    # osu 설정이 틀려도 봇은 켜지게 하기 위해 에러만 출력

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='?', intents=intents)

    async def setup_hook(self):
        # 슬래시 커맨드 서버 동기화
        await self.tree.sync()
        print("슬래시 명령어 동기화 완료")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"로그인 성공! 봇 이름: {bot.user.name} (ID: {bot.user.id})")
    print("이제 디스코드에서 /osu 명령어를 써보세요!")

# ==========================================
# [긴급] 슬래시 명령어 강제 동기화 (!sync)
# ==========================================
@bot.command(name="sync")
async def sync(ctx):
    # 이 명령어는 오직 봇 주인(본인)만 쓸 수 있게 하거나, 
    # 개발 중에는 그냥 아무나 쓸 수 있게 둡니다.
    await ctx.send("슬래시 명령어를 동기화하는 중입니다...")
    
    try:
        synced = await bot.tree.sync() # 동기화 실행
        await ctx.send(f"**{len(synced)}개**의 슬래시 명령어가 등록되었습니다!\n잠시 후 `/`를 입력해서 확인해보세요.")
        print(f"명령어 동기화 완료: {len(synced)}개")
    except Exception as e:
        await ctx.send(f"동기화 실패: {e}")

# ==========================================
# 계정 연동 명령어 (?link, /link)
# ==========================================
@bot.hybrid_command(name="link", description="내 디스코드 계정과 osu! 닉네임을 연결합니다.")
@app_commands.describe(username="연동할 osu! 닉네임")
async def link(ctx, username: str):
    # defer: 처리 중임을 알림 (슬래시/채팅 모두 대응)
    await ctx.defer()

    try:
        # 실제로 존재하는 유저인지 확인
        user = osu_api.user(username, mode="osu", key="username")
        
        # DB에 저장 (이미 있으면 덮어쓰기)
        cursor.execute("REPLACE INTO users (discord_id, osu_username) VALUES (?, ?)", (ctx.author.id, user.username))
        conn.commit()
        
        await ctx.send(f"**{ctx.author.display_name}**님의 계정이 osu! 닉네임 **'{user.username}'**으로 연동되었습니다!")
    
    except ValueError:
        await ctx.send("해당 닉네임의 osu! 유저를 찾을 수 없습니다.")
    except Exception as e:
        await ctx.send(f"오류 발생: {e}")

# ==========================================
# 명령어 구현 (/osu)
# ==========================================
@bot.hybrid_command(name="osu", aliases=['u'], description="osu! 프로필을 조회합니다.")
@app_commands.describe(username="닉네임 (비워두면 내 정보, @멘션하면 친구 정보)")
async def osu(ctx, username: str = None):
    await ctx.defer()

    target_username = None

    # [1] 닉네임 입력이 있을 때 (직접 입력 OR 멘션)
    if username:
        # 멘션인지 확인 (예: <@123456789>)
        if username.startswith("<@") and username.endswith(">"):
            # 멘션에서 숫자(ID)만 추출
            user_id_str = ''.join(filter(str.isdigit, username))
            target_id = int(user_id_str)
            
            # DB에서 친구 닉네임 찾기
            cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (target_id,))
            result = cursor.fetchone()
            
            if result:
                target_username = result[0]
            else:
                await ctx.send(f"해당 유저는 아직 봇에 계정을 연동하지 않았습니다.")
                return
        else:
            # 멘션이 아니면 그냥 닉네임으로 인식
            target_username = username
            
    # [2] 입력이 없을 때 (내 정보 조회)
    else:
        cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (ctx.author.id,))
        result = cursor.fetchone()
        if result:
            target_username = result[0]
        else:
            await ctx.send("연동된 계정이 없습니다. `?link 닉네임`을 먼저 하거나 `?osu 닉네임`을 입력하세요.")
            return
    try:
        # 1. 데이터 가져오기
        user = osu_api.user(target_username, mode="osu", key="username")
        stats = user.statistics

        # 2. 데이터 전처리 (None 값 처리 등)
        # 랭크가 없으면(휴면 유저) 0 대신 "Unranked" 표시
        g_rank = f"#{stats.global_rank:,}" if stats.global_rank else "Unranked"
        c_rank = f"#{stats.country_rank:,}" if stats.country_rank else "Unranked"
        play_hours = stats.play_time / 3600

        # 3. 임베드 생성
        # 국가 코드를 소문자로 바꿔서 디스코드 국기 이모지 적용
        flag = f":flag_{user.country_code.lower()}:"
        
        embed = discord.Embed(
            title=f"{flag}  {user.username}",
            url=f"https://osu.ppy.sh/users/{user.id}",
            description=f"**Global:** `{g_rank}`  |  **Country:** `{c_rank}`",
            color=0xff66aa
        )

        embed.set_thumbnail(url=user.avatar_url)
        embed.set_image(url=user.cover_url)

        # 4. 정보 필드 배치 (아이콘 + 굵은 글씨로 가독성 UP)
        # [실력 지표]
        embed.add_field(name="Performance", value=f"**{stats.pp:,.0f}pp**", inline=True)
        embed.add_field(name="Accuracy", value=f"**{stats.hit_accuracy:.2f}%**", inline=True)
        embed.add_field(name="Max Combo", value=f"**{stats.maximum_combo:,}x**", inline=True)

        # [성실성 지표]
        embed.add_field(name="Play Count", value=f"**{stats.play_count:,}**", inline=True)
        embed.add_field(name="Play Time", value=f"**{play_hours:,.1f}시간**", inline=True)
        embed.add_field(name="Level", value=f"**Lv.{stats.level.current} ({stats.level.progress}%)**", inline=True)

        # [랭크 달성 수] - 여기가 포인트! (SS, S 랭크 개수 보여주기)
        # 이모지가 너무 많아지지 않게 한 줄로 요약
        ranks_str = (
            f"**SSH:** `{stats.grade_counts.ssh}` "
            f"**SS:** `{stats.grade_counts.ss}` "
            f"**SH:** `{stats.grade_counts.sh}` "
            f"**S:** `{stats.grade_counts.s}` "
            f"**A:** `{stats.grade_counts.a}`"
        )
        embed.add_field(name="Rank Counts", value=ranks_str, inline=False)

        # 5. 푸터
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        embed.timestamp = ctx.message.created_at if ctx.message else discord.utils.utcnow()

        await ctx.send(embed=embed)

    except ValueError:
        await ctx.followup.send(f"**{target_username}** 유저를 찾을 수 없습니다.")
    except Exception as e:
        await ctx.followup.send(f"오류 발생: {e}")

# 봇 실행
bot.run(DISCORD_TOKEN)