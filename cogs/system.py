import discord
from discord.ext import commands

class System(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # [긴급] 슬래시 명령어 강제 동기화 (!sync)
    @commands.command(name="sync")
    async def sync(self, ctx):
        await ctx.send("슬래시 명령어를 동기화하는 중입니다...")
        
        try:
            synced = await self.bot.tree.sync() # 동기화 실행
            await ctx.send(f"**{len(synced)}개**의 슬래시 명령어가 등록되었습니다!\n잠시 후 `/`를 입력해서 확인해보세요.")
            print(f"명령어 동기화 완료: {len(synced)}개")
        except Exception as e:
            await ctx.send(f"동기화 실패: {e}")

# 메인 파일에서 이 파일을 로드할 때 실행되는 함수
async def setup(bot):
    await bot.add_cog(System(bot))