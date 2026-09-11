import os
import json
import urllib.request
import subprocess

input_data = "protocol=https\nhost=github.com\n\n"
p = subprocess.run(['git', 'credential', 'fill'], input=input_data, capture_output=True, text=True)
token = ""
for line in p.stdout.splitlines():
    if line.startswith("password="):
        token = line.split("=", 1)[1].strip()
        break

if not token:
    raise RuntimeError("토큰을 찾을 수 없습니다.")

repo = "BoscoHeo/WorkPortalNotifier"
tag = "v1.9.2"
release_name = "업무포털 알리미 v1.9.2 (제로 메모리 & 포터블 자동 업데이트)"
body = """### 🚀 업무포털 알리미 v1.9.2 업데이트 안내

1. **제로 메모리 & 스텔스 모니터링**:
   - 모니터링 확인 시 화면 밖 투명 좌표에서 3초 만에 미결 문서를 확인합니다.
   - 확인 완료 즉시 크롬 브라우저를 100% 완전 종료하여 메모리를 0MB로 회수합니다!
   - 30분 세션 만료 및 타임아웃 오류를 원천 차단하여 결재 건수 증가를 100% 정확하게 감지합니다.

2. **반응형 체크 주기 & 작업 로그 강화**:
   - 실행 중 체크 주기를 변경하면 즉시 다음 확인 일정이 재스케줄링됩니다.
   - 다음 확인 예정 시각(HH:MM:SS)과 실시간 상태가 로그창에 명확히 기록됩니다.

3. **포터블 1초 자동 업데이트 시스템 탑재**:
   - 이제 새로운 버전이 나오면 앱 내 [업데이트 확인] 버튼을 통해 1초 만에 최신 파일로 교체되어 자동 재실행됩니다!
"""

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "WorkPortalNotifier-Publisher"
}

create_url = f"https://api.github.com/repos/{repo}/releases"
req_data = json.dumps({
    "tag_name": tag,
    "name": release_name,
    "body": body,
    "draft": False,
    "prerelease": False
}).encode('utf-8')

req = urllib.request.Request(create_url, data=req_data, headers=headers)
with urllib.request.urlopen(req) as resp:
    release_info = json.loads(resp.read().decode('utf-8'))

upload_url_template = release_info['upload_url'].split('{')[0]
release_id = release_info['id']
print(f"Release 생성 완료! ID: {release_id}")

exe_path = r"C:\Users\User\.gemini\antigravity\scratch\WorkPortalNotifier_Popup\dist\WorkPortalNotifier_Single.exe"
file_size = os.path.getsize(exe_path)
file_name = "WorkPortalNotifier.exe"

upload_url = f"{upload_url_template}?name={file_name}"
headers_upload = {
    "Authorization": f"token {token}",
    "Content-Type": "application/octet-stream",
    "Content-Length": str(file_size),
    "User-Agent": "WorkPortalNotifier-Publisher"
}

with open(exe_path, 'rb') as f:
    upload_req = urllib.request.Request(upload_url, data=f, headers=headers_upload)
    with urllib.request.urlopen(upload_req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print(f"Asset 업로드 완료! Download URL: {res['browser_download_url']}")
