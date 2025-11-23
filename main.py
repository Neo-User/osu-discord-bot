import discord
from discord import app_commands
from discord.ext import commands
from ossapi import Ossapi
import os
from dotenv import load_dotenv

load_dotenv(override=True) # .env 파일 읽어오기

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") # 코드에서 비밀번호 사라짐!
OSU_CLIENT_ID = os.getenv("OSU_CLIENT_ID")
OSU_CLIENT_SECRET = os.getenv("OSU_CLIENT_SECRET")

# ==========================================
# 2. osu! API 및 봇 초기화
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
# 3. 명령어 구현 (/osu) - 이모지 최적화 버전
# ==========================================
@bot.tree.command(name="osu", description="osu! 유저의 상세 프로필을 조회합니다.")
@app_commands.describe(username="검색할 유저 닉네임")
async def osu_slash(interaction: discord.Interaction, username: str):
    await interaction.response.defer()

    try:
        # 1. 데이터 가져오기
        user = osu_api.user(username, mode="osu", key="username")
        stats = user.statistics

        # 2. 데이터 전처리 (None 값 처리 등)
        # 랭크가 없으면(휴면 유저) 0 대신 "Unranked" 표시
        g_rank = f"#{stats.global_rank:,}" if stats.global_rank else "Unranked"
        c_rank = f"#{stats.country_rank:,}" if stats.country_rank else "Unranked"
        
        # [색상 변환 코드]
        # 유저가 설정한 프로필 색상이 있으면 그것을 쓰고, 없으면 기본 핑크색(0xff66aa)을 사용
        if user.profile_colour:
            # "#RRGGBB" 문자열에서 '#'을 빼고 16진수 숫자로 변환
            embed_color = int(user.profile_colour.replace("#", ""), 16)
        else:
            embed_color = 0xff66aa
                # 플레이 시간 (초 -> 시간 변환)
        play_hours = stats.play_time / 3600

        # 3. 임베드 생성
        # 국가 코드를 소문자로 바꿔서 디스코드 국기 이모지 적용
        flag = f":flag_{user.country_code.lower()}:"
        
        embed = discord.Embed(
            title=f"{flag}  {user.username}",
            url=f"https://osu.ppy.sh/users/{user.id}",
            description=f"**Global:** `{g_rank}`  |  **Country:** `{c_rank}`",
            color=0x42f5ef
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
        embed.add_field(name="🏆 Rank Counts", value=ranks_str, inline=False)

        # 5. 푸터
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        embed.timestamp = interaction.created_at

        await interaction.followup.send(embed=embed)

    except ValueError:
        await interaction.followup.send(f"**{username}** 유저를 찾을 수 없습니다.")
    except Exception as e:
        await interaction.followup.send(f"오류 발생: {e}")

# 봇 실행
bot.run(DISCORD_TOKEN)