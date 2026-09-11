# -*- coding: utf-8 -*-
import os
import sys
import winsound
import winreg
import logging
from logging.handlers import RotatingFileHandler

class Utils:
    @staticmethod
    def play_notification_sound():
        """새 알림이 있을 때 비프음을 재생합니다."""
        try:
            winsound.Beep(1000, 500)
        except Exception:
            pass

    @staticmethod
    def set_auto_start(enabled=True, launcher_path='', app_name='WorkPortalNotifier'):
        """윈도우 시작 시 자동 실행 레지스트리를 등록/삭제합니다."""
        key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
        if launcher_path and os.path.isfile(launcher_path):
            app_path = os.path.realpath(launcher_path)
        else:
            app_path = os.path.realpath(sys.argv[0])
            if app_path.endswith('.py'):
                bat_path = os.path.join(os.path.dirname(app_path), 'run.bat')
                if os.path.exists(bat_path):
                    app_path = bat_path

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    cmd = f'"{app_path}" --startup'
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                    except FileNotFoundError:
                        pass
        except Exception as e:
            print(f'Error setting auto-start: {e}')

    @staticmethod
    def setup_logger(log_callback=None):
        """애플리케이션 전용 로거를 설정합니다."""
        logger = logging.getLogger('WorkPortalNotifier')
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if logger.handlers:
            for h in logger.handlers:
                if hasattr(h, '_wpa_callback'):
                    h.log_callback = log_callback
            return logger

        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        class CallbackHandler(logging.Handler):
            def __init__(self, callback=None):
                super().__init__()
                self.log_callback = callback
                self._wpa_callback = True

            def emit(self, record):
                try:
                    msg = self.format(record)
                    if self.log_callback:
                        self.log_callback(msg)
                except Exception:
                    pass

        cb_handler = CallbackHandler(log_callback)
        cb_handler.setFormatter(formatter)
        logger.addHandler(cb_handler)

        log_dir = os.path.join(os.environ.get('APPDATA', '.'), 'WorkPortalNotifier')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'app.log'),
            maxBytes=5242880,
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger