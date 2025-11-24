import os
import discord
import asyncio
from discord.ext import commands
from ossapi import Ossapi
from dotenv import load_dotenv

# 1. 환경 변수 로드
load_dotenv(override=True)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OSU_CLIENT_ID = os.getenv("OSU_CLIENT_ID")
OSU_CLIENT_SECRET = os.getenv("OSU_CLIENT_SECRET")

# 2. 봇 클래스 정의
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='?', intents=intents)

        # 3. osu! API 연결 (봇 전체에서 공유하기 위해 self에 저장)
        try:
            self.osu_api = Ossapi(OSU_CLIENT_ID, OSU_CLIENT_SECRET)
            print("osu! API 연결 성공")
        except Exception as e:
            print(f"osu! API 연결 실패: {e}")
            self.osu_api = None

    async def setup_hook(self):
        # 4. Cogs 폴더의 파일들을 로드 (직원 출근)
        if os.path.exists('./cogs'):
            for filename in os.listdir('./cogs'):
                if filename.endswith('.py'):
                    try:
                        await self.load_extension(f'cogs.{filename[:-3]}')
                        print(f"Cog 로드 완료: {filename}")
                    except Exception as e:
                        print(f"Cog 로드 실패 ({filename}): {e}")
        
        # 5. 슬래시 명령어 동기화
        await self.tree.sync()
        print("슬래시 명령어 동기화 완료")

bot = MyBot()

@bot.event
async def on_ready():
    print("-----------------------------------------")
    print(f"로그인 성공! 봇 이름: {bot.user.name} (ID: {bot.user.id})")
    print("이제 디스코드에서 /osu 명령어를 써보세요!")
    print("-----------------------------------------")

# 봇 실행
bot.run(DISCORD_TOKEN)