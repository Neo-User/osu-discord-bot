import os
from dotenv import load_dotenv, find_dotenv

print("=== 환경 변수 진단 시작 ===")

# 1. 현재 작업 경로 확인
cwd = os.getcwd()
print(f"1. 현재 작업 폴더: {cwd}")

# 2. .env 파일 존재 여부 확인
env_path = find_dotenv()
if env_path:
    print(f"2. .env 파일 발견 위치: {env_path}")
else:
    print("❌ 2. .env 파일을 찾을 수 없습니다! 파일명이나 위치를 확인하세요.")
    exit()

# 3. 강제 로드 (override=True: 기존 캐시 무시하고 덮어쓰기)
load_dotenv(override=True)
print("3. .env 파일 로드 시도 완료")

# 4. 값 확인 (보안을 위해 일부만 출력)
token = os.getenv("DISCORD_TOKEN")
osu_id = os.getenv("OSU_CLIENT_ID")

if token:
    print(f"✅ DISCORD_TOKEN 로드 성공! (앞 5자리: {token[:5]}...)")
else:
    print("❌ DISCORD_TOKEN이 None입니다. .env 파일 내부 변수명 오타를 확인하세요.")

if osu_id:
    print(f"✅ OSU_CLIENT_ID 로드 성공! (값: {osu_id})")
else:
    print("❌ OSU_CLIENT_ID가 None입니다.")

print("=== 진단 종료 ===")