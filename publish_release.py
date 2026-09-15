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
tag = "v1.9.5"
release_name = "업무포털 알리미 v1.9.5 (예/아니오 확인 없는 100% 무인 자동 업데이트 탑재)"
body = """### 🚀 업무포털 알리미 v1.9.5 업데이트 안내

1. **예/아니오 확인 없는 100% 무인 자동 업데이트**:
   - 새 버전이 감지되면 사용자에게 묻지 않고 즉시 최신 버전으로 조용히 교체 및 자동 재실행합니다.
   - 선생님들의 번거로운 클릭 절차를 완전히 제거하여 항상 최신 버전을 유지합니다.

2. **미결 문서 반복 알림(리마인드 모드)**:
   - 미결 문서가 남아있으면 결재를 완료할 때까지 매 주기마다 계속 팝업과 소리로 리마인드합니다.

3. **유령 브라우저 감지 버그 완벽 차단 & 제로 메모리 스텔스 모니터링**:
   - 바로가기 브라우저를 닫은 후에도 정상 점검이 지속되며, 확인 시에만 크롬이 실행된 후 즉각 완전 종료됩니다.
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
