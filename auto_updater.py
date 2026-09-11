# -*- coding: utf-8 -*-
"""
업무포털 알리미 - 포터블 단일 실행 파일 자동 업데이트 엔진
- GitHub Releases 최신 버전 비동기 감지
- 백그라운드 다운로드 (진행률 콜백 지원)
- 1초 바통터치 스크립트(updater.bat)를 통한 무중단 파일 교체 및 자동 재실행
"""

import os
import sys
import json
import time
import urllib.request
import subprocess
from PySide6.QtCore import QThread, Signal

class UpdateCheckThread(QThread):
    """백그라운드에서 GitHub 최신 릴리즈 버전을 확인하는 스레드"""
    update_available = Signal(str, str, str)  # latest_tag, release_notes, download_url
    no_update = Signal()
    check_failed = Signal(str)

    def __init__(self, current_version, repo_name):
        super().__init__()
        self.current_version = current_version.strip()
        self.repo_name = repo_name.strip()

    def run(self):
        try:
            api_url = f"https://api.github.com/repos/{self.repo_name}/releases/latest"
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "WorkPortalNotifier-Updater"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            latest_tag = data.get('tag_name', '').strip()
            body = data.get('body', '')

            # .exe 첨부파일(Asset) URL 탐색
            download_url = ""
            for asset in data.get('assets', []):
                name = asset.get('name', '')
                if name.lower().endswith('.exe'):
                    download_url = asset.get('browser_download_url', '')
                    break

            if not latest_tag or not download_url:
                self.no_update.emit()
                return

            if self._is_newer(latest_tag, self.current_version):
                self.update_available.emit(latest_tag, body, download_url)
            else:
                self.no_update.emit()

        except Exception as e:
            self.check_failed.emit(str(e))

    def _is_newer(self, latest, current):
        """v1.9.2 vs v1.9.1 버전 비교"""
        def parse_v(v):
            nums = []
            for part in v.lstrip('v').split('-')[0].split('.'):
                try:
                    nums.append(int(part))
                except ValueError:
                    pass
            return nums

        l_nums = parse_v(latest)
        c_nums = parse_v(current)
        return l_nums > c_nums


class DownloadUpdateThread(QThread):
    """최신 실행 파일을 임시 폴더에 다운로드하는 스레드"""
    progress = Signal(int)
    download_finished = Signal(str)
    download_failed = Signal(str)

    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url

    def run(self):
        try:
            temp_dir = os.environ.get('TEMP', os.path.dirname(os.path.abspath(__file__)))
            temp_exe = os.path.join(temp_dir, f"WorkPortalNotifier_update_{int(time.time())}.exe")

            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "WorkPortalNotifier-Updater"}
            )

            with urllib.request.urlopen(req, timeout=60) as resp:
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                block_size = 65536

                with open(temp_exe, 'wb') as f:
                    while True:
                        chunk = resp.read(block_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress.emit(percent)

            self.download_finished.emit(temp_exe)

        except Exception as e:
            self.download_failed.emit(str(e))


class AutoUpdater:
    """자동 업데이트 실행 및 프로세스 교체 관리자"""

    @staticmethod
    def apply_update_and_restart(temp_new_exe_path):
        """
        1초 무중단 바통터치 기법:
        1. 임시 배치 파일(updater.bat) 생성
        2. 기존 앱 프로세스 종료 대기 -> 새 exe로 덮어쓰기 -> 새 exe 실행 -> bat 자가 삭제
        3. 현재 프로세스 즉시 종료
        """
        if getattr(sys, 'frozen', False):
            current_exe = os.path.abspath(sys.executable)
        else:
            current_exe = os.path.abspath(__file__)

        temp_dir = os.environ.get('TEMP', os.path.dirname(current_exe))
        bat_path = os.path.join(temp_dir, f"update_worker_{int(time.time())}.bat")

        bat_content = f"""@echo off
chcp 65001 > nul
echo [WorkPortalNotifier] 최신 버전으로 교체 중입니다...
timeout /t 2 /nobreak > nul

:REPLACE_LOOP
copy /y "{temp_new_exe_path}" "{current_exe}" > nul
if errorlevel 1 (
    timeout /t 1 /nobreak > nul
    goto REPLACE_LOOP
)

del /f /q "{temp_new_exe_path}" > nul

echo [WorkPortalNotifier] 최신 버전으로 자동 재실행합니다!
start "" "{current_exe}"

del /f /q "%~f0" > nul
exit
"""
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)

        subprocess.Popen(
            ['cmd.exe', '/c', bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            close_fds=True
        )

        sys.exit(0)
