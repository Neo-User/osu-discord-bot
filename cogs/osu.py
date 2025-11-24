import discord
import sqlite3
import rosu_pp_py
import aiohttp
import os
from discord import app_commands
from discord.ext import commands

class Osu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # 1. DB 연결 (Cog가 로드될 때 실행)
        self.conn = sqlite3.connect("osu_bot.db")
        self.cursor = self.conn.cursor()
        
        # 테이블 생성
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER PRIMARY KEY,
                osu_username TEXT
            )
        """)
        self.conn.commit()

    # 봇이 꺼지거나 Cog가 언로드될 때 DB 연결 종료
    def cog_unload(self):
        self.conn.close()

    # ==========================================
    # 계정 연동 명령어 (?link, /link)
    # ==========================================
    @commands.hybrid_command(name="link", description="내 디스코드 계정과 osu! 닉네임을 연결합니다.")
    @app_commands.describe(username="연동할 osu! 닉네임")
    async def link(self, ctx, username: str):
        await ctx.defer()

        try:
            # main.py에 있는 osu_api를 가져와서 사용
            user = self.bot.osu_api.user(username, mode="osu", key="username")
            
            # DB에 저장
            self.cursor.execute("REPLACE INTO users (discord_id, osu_username) VALUES (?, ?)", (ctx.author.id, user.username))
            self.conn.commit()
            
            await ctx.send(f"**{ctx.author.display_name}**님의 계정이 osu! 닉네임 **'{user.username}'**으로 연동되었습니다!")
        
        except ValueError:
            await ctx.send("해당 닉네임의 osu! 유저를 찾을 수 없습니다.")
        except Exception as e:
            await ctx.send(f"오류 발생: {e}")

    # ==========================================
    # 프로필 조회 명령어 (/osu)
    # ==========================================
    @commands.hybrid_command(name="osu", aliases=['u'], description="osu! 프로필을 조회합니다.")
    @app_commands.describe(username="닉네임 (비워두면 내 정보, @멘션하면 친구 정보)")
    async def osu(self, ctx, username: str = None):
        await ctx.defer()
        target_username = None

        # [1] 닉네임 확인 로직
        if username:
            if username.startswith("<@") and username.endswith(">"):
                user_id_str = ''.join(filter(str.isdigit, username))
                self.cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (int(user_id_str),))
                result = self.cursor.fetchone()
                if result:
                    target_username = result[0]
                else:
                    await ctx.send(f"해당 유저는 아직 봇에 계정을 연동하지 않았습니다.")
                    return
            else:
                target_username = username
        else:
            self.cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (ctx.author.id,))
            result = self.cursor.fetchone()
            if result:
                target_username = result[0]
            else:
                await ctx.send("연동된 계정이 없습니다. `?link 닉네임`을 먼저 하거나 `?osu 닉네임`을 입력하세요.")
                return

        try:
            # API 호출
            user = self.bot.osu_api.user(target_username, mode="osu", key="username")
            stats = user.statistics

            # 데이터 가공
            g_rank = f"#{stats.global_rank:,}" if stats.global_rank else "Unranked"
            c_rank = f"#{stats.country_rank:,}" if stats.country_rank else "Unranked"
            play_hours = stats.play_time / 3600
            flag = f":flag_{user.country_code.lower()}:"
            
            embed = discord.Embed(
                title=f"{flag}  {user.username}",
                url=f"https://osu.ppy.sh/users/{user.id}",
                description=f"**Global:** `{g_rank}`  |  **Country:** `{c_rank}`",
                color=0xff66aa
            )

            embed.set_thumbnail(url=user.avatar_url)
            embed.set_image(url=user.cover_url)

            embed.add_field(name="Performance", value=f"**{stats.pp:,.0f}pp**", inline=True)
            embed.add_field(name="Accuracy", value=f"**{stats.hit_accuracy:.2f}%**", inline=True)
            embed.add_field(name="Max Combo", value=f"**{stats.maximum_combo:,}x**", inline=True)
            embed.add_field(name="Play Count", value=f"**{stats.play_count:,}**", inline=True)
            embed.add_field(name="Play Time", value=f"**{play_hours:,.1f}시간**", inline=True)
            embed.add_field(name="Level", value=f"**Lv.{stats.level.current} ({stats.level.progress}%)**", inline=True)

            ranks_str = (
                f"**SSH:** `{stats.grade_counts.ssh}` **SS:** `{stats.grade_counts.ss}` "
                f"**SH:** `{stats.grade_counts.sh}` **S:** `{stats.grade_counts.s}` **A:** `{stats.grade_counts.a}`"
            )
            embed.add_field(name="Rank Counts", value=ranks_str, inline=False)
            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            embed.timestamp = ctx.message.created_at if ctx.message else discord.utils.utcnow()

            await ctx.send(embed=embed)

        except ValueError:
            await ctx.followup.send(f"**{target_username}** 유저를 찾을 수 없습니다.")
        except Exception as e:
            await ctx.followup.send(f"오류 발생: {e}")

    # ==========================================
    # 최근 기록 명령어 (?recent, /recent)
    # ==========================================
    @commands.hybrid_command(name="recent", aliases=['rs', 'r'], description="유저의 가장 최근 플레이 기록을 조회합니다.")
    @app_commands.describe(username="닉네임 (비워두면 내 기록, @멘션하면 친구 기록)")
    async def recent(self, ctx, username: str = None):
        await ctx.defer()
        target_username = None

        # [1] 닉네임 확인
        if username:
            if username.startswith("<@") and username.endswith(">"):
                user_id_str = ''.join(filter(str.isdigit, username))
                self.cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (int(user_id_str),))
                result = self.cursor.fetchone()
                if result: target_username = result[0]
                else:
                    await ctx.send(f"해당 유저는 계정을 연동하지 않았습니다.")
                    return
            else:
                target_username = username
        else:
            self.cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (ctx.author.id,))
            result = self.cursor.fetchone()
            if result: target_username = result[0]
            else:
                await ctx.send("연동된 계정이 없습니다. `?link 닉네임`을 먼저 하거나 `?rs 닉네임`을 입력하세요.")
                return

        try:
            user = self.bot.osu_api.user(target_username, mode="osu", key="username")
            scores = self.bot.osu_api.user_scores(user.id, type="recent", include_fails=True, limit=1)

            if not scores:
                await ctx.send(f"**{user.username}** 님의 최근 기록이 없습니다.")
                return

            score = scores[0]
            beatmap = score.beatmap
            beatmapset = score.beatmapset
            
            # 비트맵 정보 안전 처리
            bpm = beatmap.bpm if beatmap.bpm else 0
            total_length = beatmap.total_length if beatmap.total_length else 0
            ar = beatmap.ar if beatmap.ar else 0
            od = beatmap.accuracy if beatmap.accuracy else 0
            cs = beatmap.cs if beatmap.cs else 0
            hp = beatmap.drain if beatmap.drain else 0

            # 모드 처리
            active_mods = []
            if score.mods:
                if isinstance(score.mods, list):
                    for m in score.mods:
                        if hasattr(m, 'acronym'): active_mods.append(str(m.acronym))
                        else: active_mods.append(str(m))
                else:
                    active_mods = str(score.mods).split(" ")

            mods_str = "+" + "".join(active_mods) if active_mods else ""

            # DT/HT/NC 계산
            calc_bpm = bpm
            calc_length = total_length
            if "DT" in active_mods or "NC" in active_mods:
                calc_bpm *= 1.5
                calc_length /= 1.5
            elif "HT" in active_mods:
                calc_bpm *= 0.75
                calc_length /= 0.75

            m, s = divmod(int(calc_length), 60)
            time_str = f"{m}:{s:02d}"

            # PP 계산 로직
            if_fc_pp = None
            current_pp = score.pp if score.pp else 0
            real_max_combo = beatmap.max_combo
            is_fc = False
            
            try:
                map_url = f"https://osu.ppy.sh/osu/{beatmap.id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(map_url) as resp:
                        if resp.status == 200:
                            map_content = await resp.read()
                            rosu_map = rosu_pp_py.Beatmap(bytes=map_content)
                            
                            mods_value = 0
                            mod_bits = {"NF": 1, "EZ": 2, "TD": 4, "HD": 8, "HR": 16, "SD": 32, "DT": 64, "RX": 128, "HT": 256, "NC": 576, "FL": 1024, "SO": 4096}
                            for mod_name in active_mods:
                                if mod_name in mod_bits: mods_value += mod_bits[mod_name]

                            if real_max_combo is None:
                                diff_attrs = rosu_pp_py.Difficulty(mods=mods_value).calculate(rosu_map)
                                real_max_combo = int(diff_attrs.max_combo)
                            
                            check_combo = real_max_combo if real_max_combo else 99999
                            miss_count = getattr(score.statistics, "count_miss", 0) or 0
                            is_fc = miss_count == 0 and (score.max_combo >= check_combo - 7)

                            if not is_fc:
                                perf_fc = rosu_pp_py.Performance(accuracy=score.accuracy * 100, mods=mods_value, misses=0, combo=check_combo).calculate(rosu_map)
                                if_fc_pp = perf_fc.pp

            except Exception as calc_error:
                print(f"계산 오류: {calc_error}")
                miss_check = getattr(score.statistics, "count_miss", 0) or 0
                is_fc = miss_check == 0

            # 결과 메시지 포맷팅
            raw_rank = getattr(score.rank, "name", str(score.rank)).replace("Grade.", "")
            
            # 노트 수 계산
            if 'rosu_map' in locals():
                total_objects = rosu_map.n_circles + rosu_map.n_sliders + rosu_map.n_spinners
            else:
                total_objects = beatmap.count_circles + beatmap.count_sliders + beatmap.count_spinners

            hits = score.statistics
            c300 = getattr(hits, "count_300", getattr(hits, "great", 0)) or 0
            c100 = getattr(hits, "count_100", getattr(hits, "ok", 0)) or 0
            c50  = getattr(hits, "count_50",  getattr(hits, "meh", 0)) or 0
            miss = getattr(hits, "count_miss", getattr(hits, "miss", 0)) or 0
            current_objects = c300 + c100 + c50 + miss

            if raw_rank == "F":
                progress = (current_objects / total_objects * 100) if total_objects > 0 else 0
                if if_fc_pp: pp_display = f"**Failed @ {progress:.1f}%** (If FC: **{if_fc_pp:.0f}pp**)"
                else: pp_display = f"**Failed @ {progress:.1f}%**"
            elif is_fc:
                pp_display = f"**{current_pp:.0f}pp FC**"
            else:
                if if_fc_pp: pp_display = f"**{current_pp:.0f}pp** ➔ **{if_fc_pp:.0f}pp** for **{score.accuracy * 100:.2f}% FC**"
                else: pp_display = f"**{current_pp:.0f}pp**"

            rank_map = {"XH": "SSH", "X": "SS", "SH": "SH", "S": "S", "A": "A", "B": "B", "C": "C", "D": "D", "F": "Fail"}
            rank_display = rank_map.get(raw_rank, raw_rank)

            if user.profile_colour: embed_color = int(user.profile_colour.replace("#", ""), 16)
            else: embed_color = 0xff66aa

            embed = discord.Embed(title=f"{beatmapset.title} [{beatmap.version}] {mods_str}", url=score.beatmap.url, description=pp_display, color=embed_color)
            embed.set_author(name=f"{user.username} 님의 최근 플레이", icon_url=user.avatar_url)
            embed.set_thumbnail(url=beatmapset.covers.list)

            final_max_combo = real_max_combo if real_max_combo else score.max_combo
            combo_str = f"**{score.max_combo:,}x** / {final_max_combo:,}x" if is_fc else f"{score.max_combo:,}x / {final_max_combo:,}x"
            
            info_value = f"**{rank_display}** │ **{score.accuracy * 100:.2f}%** │ {combo_str}"
            embed.add_field(name="Score Info", value=info_value, inline=False)
            
            hit_str = f"300: **{c300}** 100: **{c100}** 50: **{c50}** Miss: **{miss}**"
            embed.add_field(name="Hit Details", value=hit_str, inline=False)
            
            map_stats_str = f"Length: `{time_str}`  BPM: `{calc_bpm:.0f}`  CS: `{cs:.1f}`  AR: `{ar:.1f}`  OD: `{od:.1f}`  HP: `{hp:.1f}`"
            embed.add_field(name="Map Stats", value=map_stats_str, inline=False)
            
            embed.timestamp = score.ended_at if score.ended_at else discord.utils.utcnow()
            embed.set_footer(text=f"Played by {user.username}")

            await ctx.send(embed=embed)

        except ValueError:
            await ctx.followup.send(f"**{target_username}** 유저를 찾을 수 없습니다.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            await ctx.followup.send(f"오류 발생: {e}")

# Cog 로드 함수
async def setup(bot):
    await bot.add_cog(Osu(bot))