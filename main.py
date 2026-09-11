# -*- coding: utf-8 -*-
import sys
import os
import time

# Selenium 및 브라우저 드라이버 (Chrome, Edge) 전체 번들링 보장
try:
    import selenium.webdriver.chrome.webdriver
    import selenium.webdriver.chrome.service
    import selenium.webdriver.chrome.options
    import selenium.webdriver.edge.webdriver
    import selenium.webdriver.edge.service
    import selenium.webdriver.edge.options
    import webdriver_manager.chrome
    import webdriver_manager.microsoft
except ImportError:
    pass

# 기존 업무포털알리미\_internal 폴더가 있다면 해당 라이브러리를 자동으로 인식하도록 sys.path에 추가
possible_internal_paths = [
    os.path.join(os.path.dirname(__file__), '_internal'),
    r'C:\Users\User\Downloads\업무포털알리미\_internal'
]
for p in possible_internal_paths:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

def main():
    if '--startup' in sys.argv:
        print('부팅 자동 실행 감지: 15초 후 실행을 시작합니다...')
        time.sleep(15)

    try:
        from PySide6.QtWidgets import QApplication
        from gui import MainWindow

        app = QApplication(sys.argv)
        # 창을 닫아도 시스템 트레이에서 계속 상주하도록 설정
        app.setQuitOnLastWindowClosed(False)

        window = MainWindow()
        window.show()

        sys.exit(app.exec())

    except ImportError as e:
        msg = f'필수 라이브러리가 없습니다: {e}\n\npip install -r requirements.txt 를 실행해 주세요.'
        print(msg)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, '실행 오류', 16)
        except Exception:
            pass

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        crash_dir = os.path.join(os.environ.get('APPDATA', '.'), 'WorkPortalNotifier')
        os.makedirs(crash_dir, exist_ok=True)
        crash_path = os.path.join(crash_dir, 'crash_report.txt')
        with open(crash_path, 'w', encoding='utf-8') as f:
            f.write(str(e) + '\n')
            f.write(error_msg)
        print(f'Application crashed. See {crash_path} for details.')
        print(error_msg)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f'오류가 발생했습니다:\n{e}\n\n상세 내용은 다음 파일을 확인해 주세요:\n{crash_path}',
                '오류',
                16
            )
        except Exception:
            pass

if __name__ == '__main__':
    main()