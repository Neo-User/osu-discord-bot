import os
import discord
import sqlite3
import rosu_pp_py
import aiohttp
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

# ==========================================
# 4. 최근 기록 명령어 (?recent, ?rs, /recent)
# ==========================================
@bot.hybrid_command(name="recent", aliases=['rs', 'r'], description="유저의 가장 최근 플레이 기록을 조회합니다.")
@app_commands.describe(username="닉네임 (비워두면 내 기록, @멘션하면 친구 기록)")
async def recent(ctx, username: str = None):
    # '생각 중...' 상태 표시 (슬래시 커맨드 타임아웃 방지)
    await ctx.defer()

    target_username = None

    # [1] 검색할 대상(닉네임) 찾기 로직
    if username:
        # 1-1. 멘션인 경우 (@친구)
        if username.startswith("<@") and username.endswith(">"):
            # 멘션에서 숫자 ID만 추출
            user_id_str = ''.join(filter(str.isdigit, username))
            # DB에서 친구가 연동한 osu! 닉네임 검색
            cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (int(user_id_str),))
            result = cursor.fetchone()
            
            if result: 
                target_username = result[0]
            else:
                await ctx.send(f"해당 유저는 계정을 연동하지 않았습니다.")
                return
        # 1-2. 직접 닉네임을 입력한 경우
        else:
            target_username = username
    else:
        # 1-3. 입력이 없는 경우 (내 정보 조회)
        cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (ctx.author.id,))
        result = cursor.fetchone()
        if result: 
            target_username = result[0]
        else:
            await ctx.send("연동된 계정이 없습니다. `?link 닉네임`을 먼저 하거나 `?rs 닉네임`을 입력하세요.")
            return

    try:
        # 2. osu! API로 유저 정보 및 최근 기록 가져오기
        user = osu_api.user(target_username, mode="osu", key="username")
        # include_fails=True: 클리어 실패(폭사)한 기록도 가져옴
        scores = osu_api.user_scores(user.id, type="recent", include_fails=True, limit=1)

        if not scores:
            await ctx.send(f"**{user.username}** 님의 최근 기록이 없습니다.")
            return

        score = scores[0]
        beatmap = score.beatmap
        beatmapset = score.beatmapset
        
        # 3. 비트맵 정보 안전하게 가져오기 (값이 None이면 0으로 처리)
        bpm = beatmap.bpm if beatmap.bpm else 0
        total_length = beatmap.total_length if beatmap.total_length else 0
        ar = beatmap.ar if beatmap.ar else 0
        od = beatmap.accuracy if beatmap.accuracy else 0
        cs = beatmap.cs if beatmap.cs else 0
        hp = beatmap.drain if beatmap.drain else 0

        # 4. 활성화된 모드(Mods) 이름 추출 및 리스트 생성
        active_mods = []
        
        if score.mods:
            # Lazer 클라이언트 (리스트 형태) 대응
            if isinstance(score.mods, list):
                for m in score.mods:
                    if hasattr(m, 'acronym'):
                        active_mods.append(str(m.acronym))
                    else:
                        active_mods.append(str(m))
            # Legacy 클라이언트 (문자열 형태) 대응
            else:
                active_mods = str(score.mods).split(" ")

        # 모드 이름을 문자열로 합침 (예: "+HDDT")
        mods_str = "+" + "".join(active_mods) if active_mods else ""

        # 5. DT/HT/NC 모드에 따른 BPM 및 곡 길이 재계산
        calc_bpm = bpm
        calc_length = total_length
        
        if "DT" in active_mods or "NC" in active_mods:
            calc_bpm *= 1.5
            calc_length /= 1.5
        elif "HT" in active_mods:
            calc_bpm *= 0.75
            calc_length /= 0.75

        # 곡 길이를 '분:초' 형식으로 변환
        m, s = divmod(int(calc_length), 60)
        time_str = f"{m}:{s:02d}"

        # ---------------------------------------------------------
        # [중요] 변수 미리 초기화 (계산 에러 시 UnboundLocalError 방지)
        # ---------------------------------------------------------
        if_fc_pp = None
        current_pp = score.pp if score.pp else 0
        real_max_combo = beatmap.max_combo # API에서 제공하는 최대 콤보 (없을 수 있음)
        is_fc = False # 풀콤보 여부 기본값
        
        try:
            # 비트맵 파일 다운로드 (메모리 상에서 처리)
            map_url = f"https://osu.ppy.sh/osu/{beatmap.id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(map_url) as resp:
                    if resp.status == 200:
                        map_content = await resp.read()
                        rosu_map = rosu_pp_py.Beatmap(bytes=map_content)
                        
                        # rosu-pp 계산을 위한 모드 비트마스크 변환
                        # (문자열 모드 이름을 숫자로 변환)
                        mods_value = 0
                        mod_bits = {
                            "NF": 1, "EZ": 2, "TD": 4, "HD": 8, "HR": 16, 
                            "SD": 32, "DT": 64, "RX": 128, "HT": 256, "NC": 576, 
                            "FL": 1024, "SO": 4096
                        }
                        for mod_name in active_mods:
                            if mod_name in mod_bits:
                                mods_value += mod_bits[mod_name]

                        # ---------------------------------------------------------
                        # rosu-pp를 사용하여 맵의 실제 최대 콤보 계산
                        # (API가 None을 줄 때를 대비해 직접 계산)
                        # ---------------------------------------------------------
                        if real_max_combo is None:
                            diff_attrs = rosu_pp_py.Difficulty(mods=mods_value).calculate(rosu_map)
                            real_max_combo = int(diff_attrs.max_combo)
                        
                        # 안전장치: 콤보 값이 여전히 없으면 99999로 설정하여 에러 방지
                        check_combo = real_max_combo if real_max_combo else 99999
                        
                        # 미스 개수 가져오기 (None이면 0)
                        miss_count = getattr(score.statistics, "count_miss", 0)
                        if miss_count is None: miss_count = 0
                        
                        # 풀콤보(FC) 여부 판단: 미스가 0개이고, 최대 콤보에서 7개 이내로 차이날 때
                        is_fc = miss_count == 0 and (score.max_combo >= check_combo - 7)

                        # FC가 아닐 경우, '만약 풀콤보였다면(If FC)'의 PP 계산
                        if not is_fc:
                            perf_fc = rosu_pp_py.Performance(
                                accuracy=score.accuracy * 100,
                                mods=mods_value,
                                misses=0,
                                combo=check_combo
                            ).calculate(rosu_map)
                            if_fc_pp = perf_fc.pp

        except Exception as calc_error:
            # 계산 실패 시 콘솔에 에러 출력 (봇 멈춤 방지)
            print(f"계산 오류: {calc_error}")
            
            # 계산 실패 시 최소한의 FC 판단 (단순 미스 0개 여부)
            miss_check = getattr(score.statistics, "count_miss", 0)
            if miss_check is None: miss_check = 0
            is_fc = miss_check == 0
            pass

        # ---------------------------------------------------------
        # 6. [수정됨] 결과 메시지 포맷팅 (Fail / FC / 일반 구분)
        # ---------------------------------------------------------

        # 랭크 문자열 미리 가져오기 ("Grade.F" -> "F")
        raw_rank = getattr(score.rank, "name", str(score.rank)).replace("Grade.", "")

        # [진행도 계산용] 전체 노트 수 계산
        # rosu-pp 맵 데이터가 있으면 그걸 쓰고, 없으면 API 기본값 사용
        if 'rosu_map' in locals():
            total_objects = rosu_map.n_circles + rosu_map.n_sliders + rosu_map.n_spinners
        else:
            total_objects = beatmap.count_circles + beatmap.count_sliders + beatmap.count_spinners

        # [진행도 계산용] 내가 친 노트 수 계산 (순서를 위로 당김)
        hits = score.statistics
        c300 = getattr(hits, "count_300", getattr(hits, "great", 0))
        if c300 is None: c300 = 0
        c100 = getattr(hits, "count_100", getattr(hits, "ok", 0))
        if c100 is None: c100 = 0
        c50  = getattr(hits, "count_50",  getattr(hits, "meh", 0))
        if c50 is None: c50 = 0
        miss = getattr(hits, "count_miss", getattr(hits, "miss", 0))
        if miss is None: miss = 0
        
        current_objects = c300 + c100 + c50 + miss

        # PP 및 상태 메시지 결정
        if raw_rank == "F":
            # [죽은 기록일 때]
            # 진행률 퍼센트 계산
            progress = (current_objects / total_objects * 100) if total_objects > 0 else 0
            
            # If FC 정보가 있으면 같이 표시
            if if_fc_pp:
                pp_display = f"**Failed @ {progress:.1f}%** (If FC: **{if_fc_pp:.0f}pp**)"
            else:
                pp_display = f"**Failed @ {progress:.1f}%**"
                
        elif is_fc:
            # [풀콤보일 때]
            pp_display = f"**{current_pp:.0f}pp FC**"
            
        else:
            # [클리어는 했으나 풀콤이 아닐 때]
            if if_fc_pp:
                pp_display = f"**{current_pp:.0f}pp** ➔ **{if_fc_pp:.0f}pp** for **{score.accuracy * 100:.2f}% FC**"
            else:
                pp_display = f"**{current_pp:.0f}pp**"

        # 랭크 이모지/텍스트 매핑
        rank_map = {
            "XH": "SSH", "X":  "SS", 
            "SH": "SH",  "S":  "S", 
            "A":  "A",   "B":  "B", "C": "C", "D": "D", 
            "F":  "Fail" 
        }
        rank_display = rank_map.get(raw_rank, raw_rank)

        # 유저 프로필 색상 적용
        if user.profile_colour:
            embed_color = int(user.profile_colour.replace("#", ""), 16)
        else:
            embed_color = 0xff66aa

        # 임베드 생성
        embed = discord.Embed(
            title=f"{beatmapset.title} [{beatmap.version}] {mods_str}",
            url=score.beatmap.url,
            description=pp_display,
            color=embed_color
        )
        
        embed.set_author(name=f"{user.username} 님의 최근 플레이", icon_url=user.avatar_url)
        embed.set_thumbnail(url=beatmapset.covers.list)

        # [점수 정보] (랭크 | 정확도 | 콤보/최대콤보)
        # 계산된 최대 콤보가 없으면 현재 콤보를 대신 표시
        final_max_combo = real_max_combo if real_max_combo else score.max_combo

        # [수정됨] 풀콤보(is_fc)일 때만 현재 콤보를 굵게(**) 표시
        if is_fc:
            combo_str = f"**{score.max_combo:,}x** / {final_max_combo:,}x"
        else:
            combo_str = f"{score.max_combo:,}x / {final_max_combo:,}x"

        acc_str = f"{score.accuracy * 100:.2f}%"

        info_value = f"**{rank_display}** │ **{acc_str}** │ {combo_str}"
        embed.add_field(name="Score Info", value=info_value, inline=False)

        # [판정 상세 정보] (300 / 100 / 50 / Miss)
        # 값이 None일 경우 0으로 안전하게 처리
        hits = score.statistics
        c300 = getattr(hits, "count_300", getattr(hits, "great", 0))
        if c300 is None: c300 = 0
        c100 = getattr(hits, "count_100", getattr(hits, "ok", 0))
        if c100 is None: c100 = 0
        c50  = getattr(hits, "count_50",  getattr(hits, "meh", 0))
        if c50 is None: c50 = 0
        miss = getattr(hits, "count_miss", getattr(hits, "miss", 0))
        if miss is None: miss = 0

        hit_str = f"300: **{c300}** 100: **{c100}** 50: **{c50}** Miss: **{miss}**"
        embed.add_field(name="Hit Details", value=hit_str, inline=False)

        # [비트맵 상세 스탯] (길이, BPM, CS, AR, OD, HP)
        map_stats_str = (
            f"Length: `{time_str}`  BPM: `{calc_bpm:.0f}`  "
            f"CS: `{cs:.1f}`  AR: `{ar:.1f}`  OD: `{od:.1f}`  HP: `{hp:.1f}`"
        )
        embed.add_field(name="Map Stats", value=map_stats_str, inline=False)

        # [플레이 시각] (우측 하단 타임스탬프)
        if score.ended_at:
            embed.timestamp = score.ended_at
        else:
            embed.timestamp = discord.utils.utcnow()
            
        embed.set_footer(text=f"Played by {user.username}")

        # 결과 전송
        await ctx.send(embed=embed)

    except ValueError:
        # 유저를 찾지 못했을 때
        await ctx.send(f"**{target_username}** 유저를 찾을 수 없습니다.")
    except Exception as e:
        # 기타 모든 에러 발생 시 상세 내용 출력
        import traceback
        traceback.print_exc()
        await ctx.send(f"오류 발생: {e}")
# 봇 실행
bot.run(DISCORD_TOKEN)