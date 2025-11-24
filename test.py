# ==========================================
# 4. 최근 기록 명령어 (?recent, ?rs, /recent) - [완성형]
# ==========================================
@bot.hybrid_command(name="recent", aliases=['rs', 'r'], description="유저의 가장 최근 플레이 기록을 조회합니다.")
@app_commands.describe(username="닉네임 (비워두면 내 기록, @멘션하면 친구 기록)")
async def recent(ctx, username: str = None):
    await ctx.defer()

    target_username = None

    # [1] 닉네임 대상 찾기
    if username:
        if username.startswith("<@") and username.endswith(">"):
            user_id_str = ''.join(filter(str.isdigit, username))
            cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (int(user_id_str),))
            result = cursor.fetchone()
            if result: target_username = result[0]
            else:
                await ctx.send(f"❌ 해당 유저는 계정을 연동하지 않았습니다.")
                return
        else:
            target_username = username
    else:
        cursor.execute("SELECT osu_username FROM users WHERE discord_id = ?", (ctx.author.id,))
        result = cursor.fetchone()
        if result: target_username = result[0]
        else:
            await ctx.send("⚠️ 연동된 계정이 없습니다. `?link 닉네임`을 먼저 하거나 `?rs 닉네임`을 입력하세요.")
            return

    try:
        # 1. 유저 및 기록 가져오기
        user = osu_api.user(target_username, mode="osu", key="username")
        scores = osu_api.user_scores(user.id, type="recent", include_fails=True, limit=1)

        if not scores:
            await ctx.send(f"❌ **{user.username}** 님의 최근 기록이 없습니다.")
            return

        score = scores[0]
        beatmap = score.beatmap
        beatmapset = score.beatmapset
        
        # 통계 데이터 추출 (오류 방지)
        hits = score.statistics
        c300 = getattr(hits, "count_300", getattr(hits, "great", 0))
        c100 = getattr(hits, "count_100", getattr(hits, "ok", 0))
        c50  = getattr(hits, "count_50",  getattr(hits, "meh", 0))
        miss = getattr(hits, "count_miss", getattr(hits, "miss", 0))

        # 2. If FC PP 및 맵 스탯 계산
        if_fc_pp = None
        current_pp = score.pp if score.pp else 0
        
        # 맵 정보 변수 미리 가져오기
        bpm = beatmap.bpm
        total_length = beatmap.total_length
        ar = beatmap.ar
        od = beatmap.accuracy # API에서는 od를 accuracy라고 부름
        cs = beatmap.cs
        hp = beatmap.drain

        # 모드 적용 (DT/HT에 따른 시간/BPM 변환)
        mods_str = f"+{score.mods}" if score.mods else ""
        mods_list = str(score.mods).split(" ") if score.mods else [] # 모드 리스트화
        
        if "DT" in str(score.mods) or "NC" in str(score.mods):
            bpm *= 1.5
            total_length /= 1.5
        elif "HT" in str(score.mods):
            bpm *= 0.75
            total_length /= 0.75

        # 맵 길이 분:초 변환
        m, s = divmod(int(total_length), 60)
        time_str = f"{m}:{s:02d}"

        try:
            map_url = f"https://osu.ppy.sh/osu/{beatmap.id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(map_url) as resp:
                    if resp.status == 200:
                        map_content = await resp.read()
                        rosu_map = rosu_pp_py.Beatmap(bytes=map_content)
                        mods_value = score.mods.value if score.mods else 0

                        # FC 여부 판단 (미스가 없고, 최대 콤보에서 5개 이하로 빠졌을 때)
                        is_fc = miss == 0 and (score.max_combo >= beatmap.max_combo - 7)

                        if not is_fc:
                            # FC가 아닐 때만 If FC 계산
                            perf_fc = rosu_pp_py.Performance(
                                accuracy=score.accuracy * 100,
                                mods=mods_value,
                                misses=0,
                                combo=beatmap.max_combo
                            ).calculate(rosu_map)
                            if_fc_pp = perf_fc.pp

        except Exception as calc_error:
            print(f"계산 오류: {calc_error}")
            is_fc = miss == 0 # 계산 실패 시 단순 미스 0개면 FC로 간주

        # 3. 출력 문자열 포맷팅 (요청하신 부분!)
        
        # A. PP 표시 로직
        if is_fc:
            # 풀콤보일 때: "300pp FC"
            pp_display = f"**{current_pp:.0f}pp FC**"
        else:
            # 풀콤보 아닐 때: "174pp ➔ 200pp for 97.67% FC"
            if if_fc_pp:
                pp_display = f"**{current_pp:.0f}pp** ➔ **{if_fc_pp:.0f}pp** for **{score.accuracy * 100:.2f}% FC**"
            else:
                pp_display = f"**{current_pp:.0f}pp** (Calc Fail)"

        # B. 랭크 이모지
        rank_emoji = {
            "XH": "⚪ SS", "X": "🟡 SS", "SH": "⚪ S", "S": "🟡 S",
            "A": "🟢 A", "B": "🔵 B", "C": "🟣 C", "D": "🔴 D", "F": "💀 Fail"
        }.get(str(score.rank), str(score.rank))

        # C. 색상 (서포터 or 기본)
        if user.profile_colour:
            embed_color = int(user.profile_colour.replace("#", ""), 16)
        else:
            embed_color = 0xff66aa

        # 4. 임베드 생성
        embed = discord.Embed(
            title=f"{beatmapset.title} [{beatmap.version}] {mods_str}",
            url=score.beatmap.url,
            description=pp_display, # 계산된 PP 문자열 적용
            color=embed_color
        )
        
        embed.set_author(name=f"{user.username} 님의 최근 플레이", icon_url=user.avatar_url)
        embed.set_thumbnail(url=beatmapset.covers.list)

        # 5. Score Info (콤보/최대콤보 적용)
        # 요청: 콤보/최대콤보 이렇게 출력
        combo_str = f"**{score.max_combo:,}x** / {beatmap.max_combo:,}x"
        acc_str = f"{score.accuracy * 100:.2f}%"
        
        info_value = f"{rank_emoji} │ **{acc_str}** │ {combo_str}"
        embed.add_field(name="Score Info", value=info_value, inline=False)

        # 6. Hit Details
        hit_str = f"300: `{c300}`  100: `{c100}`  50: `{c50}`  Miss: `{miss}`"
        embed.add_field(name="Hit Details", value=hit_str, inline=False)

        # 7. Map Stats (요청: 길이, BPM, AR, OD, HP, CS 추가)
        # 소수점 1자리까지만 깔끔하게 표시
        map_stats_str = (
            f"⏱️ `{time_str}`  BPM: `{bpm:.0f}`  "
            f"CS: `{cs:.1f}`  AR: `{ar:.1f}`  OD: `{od:.1f}`  HP: `{hp:.1f}`"
        )
        embed.add_field(name="Map Stats", value=map_stats_str, inline=False)

        # 8. Time (오른쪽 아래 Timestamp로 이동)
        if score.ended_at:
            embed.timestamp = score.ended_at
        else:
            embed.timestamp = discord.utils.utcnow()
            
        embed.set_footer(text=f"Played by {user.username}") # Footer 텍스트도 깔끔하게

        await ctx.send(embed=embed)

    except ValueError:
        await ctx.send(f"**{target_username}** 유저를 찾을 수 없습니다.")
    except Exception as e:
        import traceback
        traceback.print_exc() # 에러 발생 시 콘솔에 자세히 출력
        await ctx.send(f"오류 발생: {e}")