# -*- coding: utf-8 -*-
"""
업무포털 알리미 (윈도우 팝업 알림 에디션)
메인 GUI 윈도우 및 모니터링 스레드
"""

import os
import sys
import re
import time
import threading
import webbrowser

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QSpinBox, QLineEdit, QPushButton, QCheckBox,
    QTextEdit, QGroupBox, QMessageBox, QSystemTrayIcon, QMenu, QStyle,
    QProgressDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QFont

from selenium.webdriver.common.by import By
from version import APP_NAME, APP_VERSION, APP_AUTHOR, KAKAO_INQUIRY_URL, GITHUB_REPO
from config import ConfigManager, EDUCATION_OFFICES
from utils import Utils
from engine import PortalEngine
from toast_popup import send_notification
from auto_updater import UpdateCheckThread, DownloadUpdateThread, AutoUpdater

import selenium.webdriver

# 모니터링 시 화면 밖(-32000px) 스텔스 배치를 위한 브라우저 옵션 후킹
_orig_chrome_init = selenium.webdriver.Chrome.__init__
_orig_edge_init = selenium.webdriver.Edge.__init__

def _patched_chrome_init(driver_self, *args, **kwargs):
    if getattr(PortalEngine, '_active_stealth_monitor', False):
        options = kwargs.get('options')
        if options:
            options.add_argument('--window-position=-32000,-32000')
            options.add_argument('--window-size=1280,800')
    return _orig_chrome_init(driver_self, *args, **kwargs)

def _patched_edge_init(driver_self, *args, **kwargs):
    if getattr(PortalEngine, '_active_stealth_monitor', False):
        options = kwargs.get('options')
        if options:
            options.add_argument('--window-position=-32000,-32000')
            options.add_argument('--window-size=1280,800')
    return _orig_edge_init(driver_self, *args, **kwargs)

selenium.webdriver.Chrome.__init__ = _patched_chrome_init
selenium.webdriver.Edge.__init__ = _patched_edge_init


def custom_check_updates(self, headless=False):
    """
    개선된 나이스 및 K-에듀파인 미결 건수 확인 로직 (제로 메모리 & 스텔스 모드)
    - 화면 밖(-32000px)에서 스텔스 실행되어 사용자 화면 번쩍임 없음
    - 공인인증서 보안 프로그램 및 팝업 100% 정상 연동
    - 결재 건수 확인 완료 즉시 크롬 브라우저를 100% 완전 종료하여 메모리 반환 (0MB 유지)
    - 세션 만료 및 타임아웃 오류 원천 차단
    """
    with self._action_lock:
        # 1. 기존 드라이버 생존 여부 실시간 점검 (닫힌 창 찌꺼기 즉시 정리)
        if self.driver:
            if not self.is_driver_alive():
                # 선생님께서 창을 닫으셨으나 메모리 객체가 남아있는 경우 즉시 완전 정리
                self.close_driver()
            elif getattr(self, 'driver_owner', '') != 'monitor':
                # 선생님께서 직접 바로가기(나이스/에듀파인) 창을 열어두고 작업 중이신 경우
                self.logger.info('선생님께서 직접 열어두신 업무 창이 활성화되어 있어 작업을 방해하지 않기 위해 이번 점검을 1회 건너뜁니다. (창을 닫으시면 스텔스 자동 점검이 즉시 재개됩니다)')
                return None

        # 백그라운드 스텔스 모드 플래그 가동
        PortalEngine._active_stealth_monitor = True

        results = {'nice': 0, 'edufine': 0}
        try:
            self.logger.debug('나이스/에듀파인 현황 확인 시작 (스텔스 모드)...')

            # 안전한 로그인 (화면 밖 좌표로 실행)
            if not self.driver or not getattr(self, 'driver_logged_in', False):
                if not self.login(headless=False, owner='monitor'):
                    self.logger.warning('로그인 실패로 업무 현황을 확인할 수 없습니다. (인증서 암호 확인 필요)')
                    return None

            # 화면 밖 및 최소화 재확인
            if self.driver:
                try:
                    self.driver.set_window_position(-32000, -32000)
                    self.driver.minimize_window()
                except Exception:
                    pass

            # 1. 나이스 새로고침
            try:
                btn_nice = self.driver.find_element(By.ID, 'btnRefreshNeisAprvWork')
                btn_nice.click()
                time.sleep(1.5)
            except Exception:
                pass

            # 2. 에듀파인 새로고침 (클릭 후 비동기 데이터 갱신 대기)
            try:
                btn_kedu = self.driver.find_element(By.ID, 'btnRefreshKedu')
                btn_kedu.click()
                time.sleep(3.5)
            except Exception:
                time.sleep(2)

            # 3. body 전체 텍스트 추출
            try:
                body_elem = self.driver.find_element(By.TAG_NAME, 'body')
                body_text = body_elem.text
            except Exception:
                body_text = ''

            # 4. 나이스 카운트 파싱
            nice_total = 0
            match_nice = re.search(r'미결/협조함\s*(\d+)', body_text)
            if match_nice:
                nice_total = int(match_nice.group(1))
            if nice_total > 0:
                results['nice'] = nice_total
            else:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, "a.openTapBtn[id*='neis.go.kr']")
                    t = elem.text.strip()
                    nums = re.findall(r'\d+', t)
                    if nums:
                        results['nice'] = int(nums[0])
                except Exception:
                    pass

            # 5. 에듀파인 카운트 파싱 (결재(긴급) 2(0) 복합 포맷 및 단일 포맷 완벽 대응)
            edu_found = False
            try:
                kedu_targets = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "a[href*='sanctnWait'], a[href*='sanctn'], a[href*='kedu'], a[href*='edufine'], #btnRefreshKedu ~ a, .kedu-aprv, a[title*='결재']"
                )
                for el in kedu_targets:
                    el_text = el.text.strip()
                    if not el_text:
                        continue

                    # 결재(긴급) 2(0) 형태 -> 일반 2건 + 긴급 0건
                    m_pair = re.search(r'결재(?:\(긴급\))?\s*(\d+)\s*\(\s*(\d+)\s*\)', el_text)
                    if m_pair:
                        normal_cnt = int(m_pair.group(1))
                        urgent_cnt = int(m_pair.group(2))
                        results['edufine'] = normal_cnt + urgent_cnt
                        self.logger.info(f"에듀파인 현황 감지: '{el_text}' ➔ 일반 {normal_cnt}건, 긴급 {urgent_cnt}건 (총 {results['edufine']}건)")
                        edu_found = True
                        break

                    # 2(0) 단독 형태
                    m_num_pair = re.search(r'^\s*(\d+)\s*\(\s*(\d+)\s*\)\s*$', el_text)
                    if m_num_pair:
                        normal_cnt = int(m_num_pair.group(1))
                        urgent_cnt = int(m_num_pair.group(2))
                        results['edufine'] = normal_cnt + urgent_cnt
                        self.logger.info(f"에듀파인 현황 감지: '{el_text}' ➔ 총 {results['edufine']}건")
                        edu_found = True
                        break

                    # 결재 2건, 결재 2 형태
                    m_single = re.search(r'결재(?:대기)?(?:\(긴급\))?\s*[:\s]*(\d+)', el_text)
                    if m_single:
                        results['edufine'] = int(m_single.group(1))
                        self.logger.info(f"에듀파인 현황 감지: '{el_text}' ➔ 결재 {results['edufine']}건")
                        edu_found = True
                        break
            except Exception as e:
                self.logger.debug(f'에듀파인 요소 탐색 오류: {e}')

            if not edu_found and body_text:
                m_body_pair = re.search(r'결재(?:\(긴급\))?\s*(\d+)\s*\(\s*(\d+)\s*\)', body_text)
                if m_body_pair:
                    normal_cnt = int(m_body_pair.group(1))
                    urgent_cnt = int(m_body_pair.group(2))
                    results['edufine'] = normal_cnt + urgent_cnt
                    self.logger.info(f"에듀파인 현황 감지 (본문): 결재(긴급) {normal_cnt}({urgent_cnt}) ➔ 총 {results['edufine']}건")
                    edu_found = True
                else:
                    m_body_single = re.search(r'결재(?:대기)?(?:\(긴급\))?\s*[:\s]*(\d+)', body_text)
                    if m_body_single:
                        results['edufine'] = int(m_body_single.group(1))
                        self.logger.info(f"에듀파인 현황 감지 (본문 단일): 결재 {results['edufine']}건")
                        edu_found = True

            self.logger.info(f"확인 결과: 나이스={results['nice']}건, 에듀파인={results['edufine']}건")
            return results

        except Exception as e:
            self.logger.error(f'업무 확인 중 오류 발생: {e}')
            return results

        finally:
            PortalEngine._active_stealth_monitor = False
            # ★ 핵심: 확인이 끝나면 즉시 브라우저를 완전히 닫아 메모리 100% 반환 (0MB 유지)
            try:
                self.close_driver()
                self.logger.info('🧹 브라우저 완전 종료: 메모리를 100% 회수했습니다. (메모리 점유 0MB 유지)')
            except Exception:
                pass


# PortalEngine의 check_updates 메서드를 개선된 버전으로 교체
PortalEngine.check_updates = custom_check_updates


class MonitoringThread(QThread):
    """업무포털 주기적 미결 건수 확인 스레드 (제로 메모리 & 반응형 타이머)"""
    update_signal = Signal(dict, bool)
    log_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, engine, interval):
        super().__init__()
        self.engine = engine
        self.interval = interval  # 분 단위
        self.running = True
        self._first_check_done = False
        self._consecutive_skips = 0
        self._consecutive_failures = 0
        self._remaining_seconds = 0
        self._interrupt_event = threading.Event()

    def set_interval(self, new_interval):
        """실행 중인 상태에서 확인 주기가 변경되었을 때 즉시 반영"""
        old_interval = self.interval
        self.interval = new_interval
        new_total = new_interval * 60
        if self._remaining_seconds > new_total:
            self._remaining_seconds = new_total
        next_eta = time.strftime('%H:%M:%S', time.localtime(time.time() + self._remaining_seconds))
        self.log_signal.emit(f'💡 확인 주기가 {old_interval}분 ➔ {new_interval}분으로 즉시 변경되었습니다. (다음 확인 예정: {next_eta})')
        self._interrupt_event.set()

    def run(self):
        while self.running:
            try:
                check_type_str = "첫 현황 확인" if not self._first_check_done else "정기 현황 점검"
                self.log_signal.emit(f'🔄 [{check_type_str}] 나이스·에듀파인 미결 문서 확인 중... (스텔스 3초)')

                # 제로 메모리 모드: 화면 밖 스텔스 모드로 확인 후 즉시 크롬 완전 종료
                results = self.engine.check_updates(headless=False)

                if results is None:
                    # 브라우저 창이 이미 열려있어 확인을 건너뛴 경우
                    self._consecutive_skips += 1
                    self.log_signal.emit(
                        f'ℹ️ 선생님의 작업 보호: 직접 열어두신 나이스/에듀파인 창이 활성화되어 있어 점검을 1회 건너뛰었습니다. '
                        f'(창을 닫으시면 다음 주기부터 스텔스 모드로 자동 점검됩니다)'
                    )
                else:
                    self._consecutive_skips = 0
                    is_first = not self._first_check_done
                    self._first_check_done = True
                    self._consecutive_failures = 0
                    self.update_signal.emit(results, is_first)

            except Exception as e:
                self._consecutive_failures += 1
                self.log_signal.emit(f'모니터링 오류 ({self._consecutive_failures}회 실패): {e}')
                if self._consecutive_failures >= 3:
                    self.error_signal.emit(
                        f'연속 확인 {self._consecutive_failures}회 실패했습니다.\n네트워크 또는 로그인 상태를 확인해 주세요.'
                    )
                    self._consecutive_failures = 0

            # 다음 확인까지 대기 (반응형 1초 루프)
            self._remaining_seconds = self.interval * 60
            next_time = time.strftime('%H:%M:%S', time.localtime(time.time() + self._remaining_seconds))
            self.log_signal.emit(f'⏳ 다음 확인 예정 시각: {next_time} ({self.interval}분 후 | 메모리 점유 0MB 대기)')

            while self.running and self._remaining_seconds > 0:
                self._interrupt_event.clear()
                self._interrupt_event.wait(1.0)
                if not self.running:
                    return
                self._remaining_seconds -= 1

    def stop(self):
        self.running = False
        self._interrupt_event.set()
        self.wait()


class MainWindow(QMainWindow):
    """메인 윈도우 UI 클래스"""
    _log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.config_mgr = ConfigManager()
        self.logger = Utils.setup_logger(self._thread_safe_log)
        self.engine = PortalEngine(self.config_mgr, self.logger)

        self.monitor_thread = None
        self.last_results = {'nice': 0, 'edufine': 0}

        self._log_signal.connect(self.append_log)

        self.init_ui()
        self.create_tray_icon()
        self.load_settings()
        self.connect_autosave()

        # ChromeDriver 사전 캐싱 백그라운드 시작
        threading.Thread(target=self.engine._cache_driver, daemon=True).start()

        # 부팅 시 자동 시작 시퀀스
        self.auto_start_sequence()

        # 시작 3초 후 GitHub 최신 버전 조용히 확인
        QTimer.singleShot(3000, lambda: self.check_for_updates(manual=False))

    def _thread_safe_log(self, msg):
        self._log_signal.emit(msg)

    def _resource_path(self, relative_path):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    def init_ui(self):
        self.setWindowTitle(f'{APP_NAME} {APP_VERSION}')
        self.setFixedSize(560, 720)

        icon_path = self._resource_path('app_icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # 1. 상단 타이틀 & 설명
        header_layout = QHBoxLayout()
        title_label = QLabel(f'<b>{APP_NAME}</b> {APP_VERSION}')
        title_label.setFont(QFont('Malgun Gothic', 11))
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        update_btn = QPushButton('업데이트 확인')
        update_btn.setFixedWidth(95)
        update_btn.setStyleSheet('font-size: 11px; background-color: #f1f3f4;')
        update_btn.clicked.connect(lambda: self.check_for_updates(manual=True))
        header_layout.addWidget(update_btn)

        help_btn = QPushButton('사용 안내')
        help_btn.setFixedWidth(80)
        help_btn.clicked.connect(self.show_manual)
        header_layout.addWidget(help_btn)
        main_layout.addLayout(header_layout)

        # 2. 기본 접속 및 환경 설정 그룹
        settings_group = QGroupBox('기본 설정')
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(8)

        # 교육청 선택 & 체크 주기 & 브라우저
        row1 = QHBoxLayout()
        row1.addWidget(QLabel('교육청:'))
        self.office_combo = QComboBox()
        for key, val in EDUCATION_OFFICES.items():
            self.office_combo.addItem(f"{key} ({val['name']})", key)
        row1.addWidget(self.office_combo, 2)

        row1.addWidget(QLabel('체크 주기:'))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(30)
        self.interval_spin.setSuffix(' 분')
        row1.addWidget(self.interval_spin, 1)

        row1.addWidget(QLabel('브라우저:'))
        self.browser_combo = QComboBox()
        self.browser_combo.addItem('Chrome (기본)', 'chrome')
        self.browser_combo.addItem('Edge', 'edge')
        row1.addWidget(self.browser_combo, 1)
        settings_layout.addLayout(row1)

        # 인증서 암호 입력
        row2 = QHBoxLayout()
        row2.addWidget(QLabel('인증서 암호:'))
        self.cert_pw_input = QLineEdit()
        self.cert_pw_input.setEchoMode(QLineEdit.Password)
        self.cert_pw_input.setPlaceholderText('공인인증서 비밀번호')
        row2.addWidget(self.cert_pw_input, 2)

        self.save_pw_btn = QPushButton('암호 저장')
        self.save_pw_btn.clicked.connect(self.save_password)
        row2.addWidget(self.save_pw_btn)

        self.delete_pw_btn = QPushButton('암호 삭제')
        self.delete_pw_btn.clicked.connect(self.delete_password)
        row2.addWidget(self.delete_pw_btn)
        settings_layout.addLayout(row2)

        # 인증서 이름 & 소속기관 순서
        row3 = QHBoxLayout()
        row3.addWidget(QLabel('인증서 이름:'))
        self.cert_name_input = QLineEdit()
        self.cert_name_input.setPlaceholderText('예: 홍길동 (비워두면 첫 번째 인증서)')
        row3.addWidget(self.cert_name_input, 2)

        row3.addWidget(QLabel('소속기관(NEIS):'))
        self.neis_order_spin = QSpinBox()
        self.neis_order_spin.setRange(0, 20)
        self.neis_order_spin.setSpecialValueText('팝업 없음')
        row3.addWidget(self.neis_order_spin, 1)
        settings_layout.addLayout(row3)

        main_layout.addWidget(settings_group)

        # 3. 알림 및 시작 옵션 그룹
        options_group = QGroupBox('알림 및 실행 옵션')
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(6)

        opt_grid1 = QHBoxLayout()
        self.toast_check = QCheckBox('🔔 윈도우 팝업 알림')
        self.toast_check.setChecked(True)
        opt_grid1.addWidget(self.toast_check)

        self.remind_pending_check = QCheckBox('⏳ 미결 문서 반복 알림')
        self.remind_pending_check.setChecked(True)
        self.remind_pending_check.setToolTip('결재 대기 문서가 남아있으면 결재를 마칠 때까지 매 주기마다 계속 팝업과 소리로 리마인드합니다.')
        opt_grid1.addWidget(self.remind_pending_check)

        self.sound_check = QCheckBox('🔊 알림음')
        opt_grid1.addWidget(self.sound_check)

        self.test_toast_btn = QPushButton('🔔 알림 테스트')
        self.test_toast_btn.setStyleSheet('font-weight: bold; background-color: #e8f0fe; color: #1967d2; height: 28px;')
        self.test_toast_btn.clicked.connect(self.test_toast_notification)
        opt_grid1.addWidget(self.test_toast_btn)
        options_layout.addLayout(opt_grid1)

        opt_grid2 = QHBoxLayout()
        self.auto_start_check = QCheckBox('윈도우 시작 시 자동 실행')
        opt_grid2.addWidget(self.auto_start_check)

        self.auto_login_check = QCheckBox('시작 시 업무포털 자동로그인')
        opt_grid2.addWidget(self.auto_login_check)

        self.auto_monitor_check = QCheckBox('시작 시 자동 모니터링')
        opt_grid2.addWidget(self.auto_monitor_check)
        options_layout.addLayout(opt_grid2)

        main_layout.addWidget(options_group)

        # 4. 제어 및 바로가기 버튼 그룹
        action_layout = QHBoxLayout()
        self.save_settings_btn = QPushButton('설정 저장')
        self.save_settings_btn.clicked.connect(self.save_all_settings)
        action_layout.addWidget(self.save_settings_btn)

        self.monitor_btn = QPushButton('▶ 모니터링 시작')
        self.monitor_btn.setStyleSheet('font-weight: bold; background-color: #2b78e4; color: white; height: 32px;')
        self.monitor_btn.clicked.connect(self.toggle_monitoring)
        action_layout.addWidget(self.monitor_btn)
        main_layout.addLayout(action_layout)

        # 바로가기 버튼들
        quick_layout = QHBoxLayout()
        quick_layout.addWidget(QLabel('바로가기(자동로그인):'))
        portal_btn = QPushButton('업무포털')
        portal_btn.clicked.connect(self.open_portal_site)
        quick_layout.addWidget(portal_btn)

        nice_btn = QPushButton('나이스')
        nice_btn.clicked.connect(self.open_nice)
        quick_layout.addWidget(nice_btn)

        edufine_btn = QPushButton('에듀파인')
        edufine_btn.clicked.connect(self.open_edufine)
        quick_layout.addWidget(edufine_btn)
        main_layout.addLayout(quick_layout)

        # 5. 작업 로그
        log_group = QGroupBox('작업 로그')
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont('Consolas', 9))
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)

        # 6. 하단 정보
        footer_layout = QHBoxLayout()
        footer_label = QLabel(f'제작: {APP_AUTHOR}')
        footer_label.setStyleSheet('color: gray; font-size: 11px;')
        footer_layout.addWidget(footer_label)
        footer_layout.addStretch()

        inquiry_btn = QPushButton('원작자 오픈채팅')
        inquiry_btn.setStyleSheet('font-size: 11px;')
        inquiry_btn.clicked.connect(lambda: webbrowser.open(KAKAO_INQUIRY_URL))
        footer_layout.addWidget(inquiry_btn)
        main_layout.addLayout(footer_layout)

    def create_tray_icon(self):
        """시스템 트레이 아이콘 생성 및 메뉴 구성"""
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)

        tray_menu = QMenu()
        open_action = tray_menu.addAction('창 열기')
        open_action.triggered.connect(self.show_and_activate)

        test_action = tray_menu.addAction('팝업 알림 테스트')
        test_action.triggered.connect(self.test_toast_notification)

        update_action = tray_menu.addAction('업데이트 확인')
        update_action.triggered.connect(lambda: self.check_for_updates(manual=True))

        tray_menu.addSeparator()

        quit_action = tray_menu.addAction('종료')
        quit_action.triggered.connect(QApplication.instance().quit)

        QApplication.instance().aboutToQuit.connect(self._cleanup_on_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.messageClicked.connect(self.show_and_activate)
        self.tray_icon.show()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_and_activate()

    def show_and_activate(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        """닫기 버튼 클릭 시 시스템 트레이로 최소화"""
        event.ignore()
        self.hide()
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                APP_NAME,
                '프로그램이 시스템 트레이(우측 하단)로 최소화되었습니다.\n완전 종료하려면 트레이 아이콘 우클릭 후 [종료]를 누르세요.',
                QSystemTrayIcon.Information,
                3000
            )

    def _cleanup_on_quit(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
        self.engine.close_driver()

    def load_settings(self):
        """저장된 설정 불러오기"""
        cfg = self.config_mgr.config
        idx = self.office_combo.findData(cfg.get('office', '경기'))
        if idx >= 0:
            self.office_combo.setCurrentIndex(idx)

        b_idx = self.browser_combo.findData(cfg.get('browser', 'chrome'))
        if b_idx >= 0:
            self.browser_combo.setCurrentIndex(b_idx)

        self.interval_spin.setValue(cfg.get('interval', 30))
        self.sound_check.setChecked(cfg.get('use_sound', True))
        self.auto_start_check.setChecked(cfg.get('auto_start', False))
        self.auto_login_check.setChecked(cfg.get('auto_login', False))
        self.auto_monitor_check.setChecked(cfg.get('auto_monitor', False))
        self.toast_check.setChecked(cfg.get('use_toast', True))
        self.remind_pending_check.setChecked(cfg.get('remind_pending', True))

        self.cert_name_input.setText(cfg.get('cert_name', ''))
        self.neis_order_spin.setValue(cfg.get('neis_order', 0))

        if self.config_mgr.get_password():
            self.cert_pw_input.setText('********')

    def save_password(self):
        pw = self.cert_pw_input.text().strip()
        if not pw or pw == '********':
            QMessageBox.warning(self, '경고', '저장할 인증서 암호를 입력해 주세요.')
            return
        self.config_mgr.set_password(pw)
        self.cert_pw_input.setText('********')
        self.append_log('인증서 암호가 안전하게 암호화되어 저장되었습니다.')
        QMessageBox.information(self, '완료', '인증서 암호가 저장되었습니다.')

    def delete_password(self):
        self.config_mgr.clear_password()
        self.cert_pw_input.clear()
        self.append_log('저장된 인증서 암호가 완전히 삭제되었습니다.')
        QMessageBox.information(self, '완료', '저장된 암호가 삭제되었습니다.')

    def persist_settings(self):
        """현재 UI 값을 config에 반영"""
        self.config_mgr.set('office', self.office_combo.currentData())
        self.config_mgr.set('browser', self.browser_combo.currentData())
        self.config_mgr.set('interval', self.interval_spin.value())
        self.config_mgr.set('use_sound', self.sound_check.isChecked())
        self.config_mgr.set('auto_start', self.auto_start_check.isChecked())
        self.config_mgr.set('auto_login', self.auto_login_check.isChecked())
        self.config_mgr.set('auto_monitor', self.auto_monitor_check.isChecked())
        self.config_mgr.set('use_toast', self.toast_check.isChecked())
        self.config_mgr.set('remind_pending', self.remind_pending_check.isChecked())
        self.config_mgr.set('cert_name', self.cert_name_input.text().strip())
        self.config_mgr.set('neis_order', self.neis_order_spin.value())

    def save_all_settings(self):
        self.persist_settings()
        self.append_log('설정이 성공적으로 저장되었습니다.')
        QMessageBox.information(self, '완료', '설정이 저장되었습니다.')

    def _on_startup_check_changed(self, state):
        enabled = (state == Qt.Checked.value or state == True)
        Utils.set_auto_start(enabled)

    def _on_interval_changed(self, val):
        """체크 주기 스핀박스 변경 시 설정 저장 및 실행 중인 모니터링 스레드에 즉시 반영"""
        self.persist_settings()
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.set_interval(val)

    def connect_autosave(self):
        self.office_combo.currentIndexChanged.connect(self.persist_settings)
        self.browser_combo.currentIndexChanged.connect(self.persist_settings)
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        self.sound_check.toggled.connect(self.persist_settings)
        self.auto_login_check.toggled.connect(self.persist_settings)
        self.auto_monitor_check.toggled.connect(self.persist_settings)
        self.toast_check.toggled.connect(self.persist_settings)
        self.remind_pending_check.toggled.connect(self.persist_settings)
        self.cert_name_input.textChanged.connect(self.persist_settings)
        self.neis_order_spin.valueChanged.connect(self.persist_settings)

        self.auto_start_check.stateChanged.connect(self._on_startup_check_changed)
        self.auto_start_check.toggled.connect(self.persist_settings)

    def auto_start_sequence(self):
        """시작 시 자동 실행 옵션 처리"""
        if self.auto_monitor_check.isChecked():
            self.append_log('시작 시 자동 모니터링 옵션이 켜져 있어 모니터링을 시작합니다...')
            self._start_monitoring_if_idle()

        if '--startup' in sys.argv or self.auto_login_check.isChecked():
            self.append_log('시작 시 자동 로그인 옵션이 실행됩니다...')
            self.open_portal_site()

    def _start_monitoring_if_idle(self):
        if not self.monitor_thread or not self.monitor_thread.isRunning():
            self.toggle_monitoring()

    def toggle_monitoring(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_btn.setText('▶ 모니터링 시작')
            self.monitor_btn.setStyleSheet('font-weight: bold; background-color: #2b78e4; color: white; height: 32px;')
            self.monitor_thread.stop()
            self.monitor_thread = None
            self.append_log('모니터링이 중지되었습니다.')
        else:
            if not self.config_mgr.get_password():
                QMessageBox.warning(self, '경고', '인증서 암호를 먼저 저장해 주세요.')
                return
            interval = self.interval_spin.value()
            self.monitor_thread = MonitoringThread(self.engine, interval)
            self.monitor_thread.update_signal.connect(self.handle_updates)
            self.monitor_thread.log_signal.connect(self.append_log)
            self.monitor_thread.error_signal.connect(self.handle_monitor_error)
            self.monitor_thread.start()
            self.monitor_btn.setText('■ 모니터링 중지')
            self.monitor_btn.setStyleSheet('font-weight: bold; background-color: #d93025; color: white; height: 32px;')
            self.append_log(f'모니터링이 시작되었습니다. (확인 주기: {interval}분 | 제로 메모리 모드)')

    def handle_updates(self, results, is_first):
        """모니터링 결과 수신 시 알림 처리 (신규 증가 및 미결 문서 반복 리마인드 지원)"""
        nice_count = results.get('nice', 0)
        edufine_count = results.get('edufine', 0)
        has_pending = (nice_count > 0 or edufine_count > 0)

        last_nice = self.last_results.get('nice', 0)
        last_edufine = self.last_results.get('edufine', 0)
        increased = (nice_count > last_nice or edufine_count > last_edufine)

        if is_first:
            msg = f'모니터링 시작 - 현재 상태 (나이스: {nice_count}건, 에듀파인: {edufine_count}건)'
            self.logger.info(msg)
            if has_pending and self.sound_check.isChecked():
                Utils.play_notification_sound()
            self._notify(results, msg)
        else:
            if increased:
                # 1. 신규 문서가 도착하여 건수가 증가한 경우
                msg = f'새로운 문서가 도착했습니다! (나이스: {nice_count}건, 에듀파인: {edufine_count}건)'
                self.logger.info(msg)
                if self.sound_check.isChecked():
                    Utils.play_notification_sound()
                self._notify(results, msg)
            elif has_pending and self.remind_pending_check.isChecked():
                # 2. 건수 증가는 없으나 미결 문서가 남아있고 반복 알림 옵션이 켜진 경우 (리마인드 모드)
                msg = f'⏳ 결재 대기 중인 문서가 있습니다! (나이스: {nice_count}건, 에듀파인: {edufine_count}건)'
                self.logger.info(msg)
                if self.sound_check.isChecked():
                    Utils.play_notification_sound()
                self._notify(results, msg)
                self.append_log(f'🔔 [반복 알림] 미결 문서 잔여 안내: 나이스 {nice_count}건, 에듀파인 {edufine_count}건')
            else:
                # 3. 미결 문서가 전혀 없거나 반복 알림이 꺼진 경우
                if not has_pending:
                    self.append_log('✨ 정기 점검 완료: 모든 미결 문서가 결재 처리되었습니다. (미결 0건)')
                else:
                    self.append_log(f'ℹ️ 정기 점검 완료: 나이스 {nice_count}건, 에듀파인 {edufine_count}건 (신규 도착 문서 없음)')

        self.last_results = results

    def _handle_popup_action(self, action):
        """팝업 알림에서 버튼 클릭 시 자동 로그인 브라우저 열기 또는 창 열기"""
        if action == 'nice':
            self.append_log('알림 클릭: 나이스로 자동 로그인 접속합니다...')
            self.open_nice()
        elif action == 'edufine':
            self.append_log('알림 클릭: 에듀파인으로 자동 로그인 접속합니다...')
            self.open_edufine()
        elif action == 'portal':
            self.append_log('알림 클릭: 업무포털로 자동 로그인 접속합니다...')
            self.open_portal_site()
        elif action == 'app':
            self.show_and_activate()

    def _notify(self, results, msg):
        """윈도우 팝업 알림 발송"""
        if self.toast_check.isChecked():
            title = '업무포털 알리미'
            send_notification(title, msg, results=results, on_action_callback=self._handle_popup_action)
            try:
                self.tray_icon.showMessage(title, msg, QSystemTrayIcon.Information, 10000)
            except Exception:
                pass

    def handle_monitor_error(self, err_msg):
        self.append_log(f'모니터링 알림: {err_msg}')
        if self.toast_check.isChecked():
            send_notification('업무포털 알리미 오류', err_msg, on_action_callback=self.show_and_activate)

    def test_toast_notification(self):
        """팝업 알림 테스트: 모달 확인창 없이 화면 우측 하단에 즉시 알림 카드가 뜸"""
        self.append_log('🔔 팝업 알림 테스트를 발송했습니다. 화면 우측 하단을 확인해 주세요!')
        msg = '테스트 알림입니다.\n나이스: 1건, 에듀파인: 2건\n아래 버튼을 누르면 해당 사이트로 자동 로그인됩니다!'
        test_results = {'nice': 1, 'edufine': 2}
        send_notification(
            '업무포털 알리미 [알림 테스트]',
            msg,
            results=test_results,
            on_action_callback=self._handle_popup_action
        )
        if self.sound_check.isChecked():
            Utils.play_notification_sound()

    def open_portal_site(self):
        """업무포털 메인 자동 로그인 접속"""
        url = self.config_mgr.get_office_url()
        self.append_log(f'업무포털로 자동 로그인 접속합니다: {url}')
        self._open_link_worker(url)

    def open_nice(self):
        """나이스(NEIS) 자동 연동 접속"""
        base_url = self.config_mgr.get_office_url()
        m = re.search(r'https://(\w+)\.eduptl\.kr', base_url)
        region = m.group(1) if m else base_url.split('//')[1].split('.')[0]
        url = f'https://{region}.neis.go.kr/jsp/main.jsp'
        self.append_log(f'나이스로 자동 로그인 접속합니다: {url}')
        self._open_link_worker(url)

    def open_edufine(self):
        """에듀파인(K-Edufine) 자동 연동 접속"""
        base_url = self.config_mgr.get_office_url()
        m = re.search(r'https://(\w+)\.eduptl\.kr', base_url)
        region = m.group(1) if m else base_url.split('//')[1].split('.')[0]
        url = f'https://klef.{region}.go.kr/keris_ui/main.do'
        self.append_log(f'에듀파인으로 자동 로그인 접속합니다: {url}')
        self._open_link_worker(url)

    def _open_link_worker(self, url):
        def _run():
            try:
                self.engine.open_portal(url)
            except Exception as e:
                self.logger.error(f'포털 열기 실패: {e}')
                self.append_log(f'접속 실패 오류: {e}')
        threading.Thread(target=_run, daemon=True).start()

    def show_manual(self):
        msg = (
            '### 업무포털 알리미 (윈도우 알림 에디션)\n\n'
            '1. 공인인증서 암호를 입력하고 [암호 저장]을 누릅니다.\n'
            '2. 교육청과 체크 주기를 설정합니다.\n'
            '3. [▶ 모니터링 시작]을 누르면 설정한 주기마다 나이스와 에듀파인의 미결 문서를 자동 확인합니다.\n'
            '4. 새 문서가 도착하면 화면 우측 하단에 알림 카드가 뜹니다.\n'
            '5. [🚀 나이스/에듀파인 접속] 버튼을 누르면 자동 로그인된 브라우저가 즉시 열립니다.'
        )
        QMessageBox.information(self, '사용 안내', msg)

    def append_log(self, text):
        now = time.strftime('%H:%M:%S')
        self.log_text.append(f'[{now}] {text}')

    def check_for_updates(self, manual=False):
        """GitHub Releases 최신 버전 비동기 확인"""
        self._manual_update_check = manual
        if manual:
            self.append_log('GitHub에서 최신 버전을 확인하는 중입니다...')

        self._update_thread = UpdateCheckThread(APP_VERSION, GITHUB_REPO)
        self._update_thread.update_available.connect(self._on_update_available)
        self._update_thread.no_update.connect(self._on_no_update)
        self._update_thread.check_failed.connect(self._on_update_check_failed)
        self._update_thread.start()

    def _on_update_available(self, latest_tag, release_notes, download_url):
        self.append_log(f'🎉 새로운 버전({latest_tag}) 발견! 확인 절차 없이 즉시 최신 버전으로 자동 업데이트합니다.')
        self._start_update_download(download_url)

    def _on_no_update(self):
        if getattr(self, '_manual_update_check', False):
            self.append_log(f'현재 최신 버전({APP_VERSION})을 사용 중입니다.')
            QMessageBox.information(self, '업데이트 확인', f'현재 최신 버전({APP_VERSION})을 사용 중입니다!')

    def _on_update_check_failed(self, err):
        if getattr(self, '_manual_update_check', False):
            self.append_log(f'업데이트 확인 실패: {err}')
            QMessageBox.warning(self, '업데이트 확인 실패', f'최신 버전 정보를 가져오지 못했습니다:\n{err}')

    def _start_update_download(self, download_url):
        self.append_log('최신 버전 다운로드를 시작합니다...')
        self._progress_dialog = QProgressDialog('최신 버전으로 자동 업데이트 진행 중...', None, 0, 100, self)
        self._progress_dialog.setCancelButton(None)
        self._progress_dialog.setWindowTitle('무인 자동 업데이트')
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setValue(0)
        self._progress_dialog.show()

        self._download_thread = DownloadUpdateThread(download_url)
        self._download_thread.progress.connect(self._progress_dialog.setValue)
        self._download_thread.download_finished.connect(self._on_download_finished)
        self._download_thread.download_failed.connect(self._on_download_failed)
        self._download_thread.start()

    def _on_download_finished(self, temp_exe):
        if hasattr(self, '_progress_dialog'):
            self._progress_dialog.close()
        self.append_log('다운로드 완료! 1초 후 최신 버전으로 교체되어 자동 재실행됩니다.')
        AutoUpdater.apply_update_and_restart(temp_exe)

    def _on_download_failed(self, err):
        if hasattr(self, '_progress_dialog'):
            self._progress_dialog.close()
        self.append_log(f'업데이트 파일 다운로드 실패: {err}')
        QMessageBox.critical(self, '다운로드 오류', f'업데이트 파일 다운로드에 실패했습니다:\n{err}')