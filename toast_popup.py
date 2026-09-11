# -*- coding: utf-8 -*-
"""
우측 하단 스마트 플로팅 팝업 카드 (원클릭 자동 로그인 지원)
듀얼 모니터 완벽 지원: 사용자가 보고 있는 모니터의 우측 하단에 최상위로 100% 확실하게 표시됩니다.
"""

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QGraphicsDropShadowEffect, QApplication
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QCursor, QGuiApplication

class NotificationPopup(QWidget):
    def __init__(self, title, message, results=None, on_action_callback=None, duration_secs=0):
        # 최상위 플로팅 윈도우 플래그
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.results = results or {'nice': 0, 'edufine': 0}
        self.on_action_callback = on_action_callback
        self.duration_secs = duration_secs

        self.init_ui(title, message)
        self.position_at_bottom_right()

        if self.duration_secs > 0:
            self.timer = QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.close)
            self.timer.start(self.duration_secs * 1000)
        else:
            self.timer = None

    def init_ui(self, title, message):
        nice_count = self.results.get('nice', 0)
        edufine_count = self.results.get('edufine', 0)

        container = QWidget(self)
        container.setObjectName('container')
        container.setStyleSheet('''
            #container {
                background-color: #ffffff;
                border: 2px solid #2b78e4;
                border-radius: 10px;
            }
        ''')

        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # 1. 헤더 (아이콘 + 제목 + 닫기버튼)
        header = QHBoxLayout()
        title_lbl = QLabel(f'🔔 <b>{title}</b>')
        title_lbl.setFont(QFont('Malgun Gothic', 11, QFont.Bold))
        title_lbl.setStyleSheet('color: #1a56b0;')
        header.addWidget(title_lbl)
        header.addStretch()

        close_btn = QPushButton('×')
        close_btn.setFixedSize(24, 24)
        close_btn.setToolTip('알림 닫기')
        close_btn.setStyleSheet('''
            QPushButton {
                border: none;
                font-size: 20px;
                font-weight: bold;
                color: #888888;
                background: transparent;
            }
            QPushButton:hover {
                color: #d93025;
            }
        ''')
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # 2. 본문 메시지
        msg_lbl = QLabel(message)
        msg_lbl.setFont(QFont('Malgun Gothic', 10))
        msg_lbl.setStyleSheet('color: #222222; line-height: 140%;')
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        # 3. 상황별 스마트 자동로그인 액션 버튼 그룹
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        if edufine_count > 0 and nice_count == 0:
            edu_btn = QPushButton(f'🚀 에듀파인 접속 ({edufine_count}건)')
            edu_btn.setFont(QFont('Malgun Gothic', 9, QFont.Bold))
            edu_btn.setStyleSheet('''
                QPushButton {
                    background-color: #0f9d58;
                    color: white;
                    border: none;
                    padding: 8px 14px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #0b8043; }
            ''')
            edu_btn.clicked.connect(lambda: self.handle_action('edufine'))
            btn_layout.addWidget(edu_btn)

        elif nice_count > 0 and edufine_count == 0:
            nice_btn = QPushButton(f'🚀 나이스 접속 ({nice_count}건)')
            nice_btn.setFont(QFont('Malgun Gothic', 9, QFont.Bold))
            nice_btn.setStyleSheet('''
                QPushButton {
                    background-color: #2b78e4;
                    color: white;
                    border: none;
                    padding: 8px 14px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #1c5fbd; }
            ''')
            nice_btn.clicked.connect(lambda: self.handle_action('nice'))
            btn_layout.addWidget(nice_btn)

        elif nice_count > 0 and edufine_count > 0:
            nice_btn = QPushButton(f'나이스 ({nice_count}건)')
            nice_btn.setFont(QFont('Malgun Gothic', 9, QFont.Bold))
            nice_btn.setStyleSheet('''
                QPushButton {
                    background-color: #2b78e4;
                    color: white;
                    border: none;
                    padding: 8px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #1c5fbd; }
            ''')
            nice_btn.clicked.connect(lambda: self.handle_action('nice'))
            btn_layout.addWidget(nice_btn)

            edu_btn = QPushButton(f'에듀파인 ({edufine_count}건)')
            edu_btn.setFont(QFont('Malgun Gothic', 9, QFont.Bold))
            edu_btn.setStyleSheet('''
                QPushButton {
                    background-color: #0f9d58;
                    color: white;
                    border: none;
                    padding: 8px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #0b8043; }
            ''')
            edu_btn.clicked.connect(lambda: self.handle_action('edufine'))
            btn_layout.addWidget(edu_btn)

        else:
            portal_btn = QPushButton('업무포털 접속')
            portal_btn.setFont(QFont('Malgun Gothic', 9, QFont.Bold))
            portal_btn.setStyleSheet('''
                QPushButton {
                    background-color: #2b78e4;
                    color: white;
                    border: none;
                    padding: 8px 14px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #1c5fbd; }
            ''')
            portal_btn.clicked.connect(lambda: self.handle_action('portal'))
            btn_layout.addWidget(portal_btn)

        app_btn = QPushButton('프로그램 창')
        app_btn.setFont(QFont('Malgun Gothic', 9))
        app_btn.setStyleSheet('''
            QPushButton {
                background-color: #f1f3f4;
                color: #333333;
                border: 1px solid #dadce0;
                padding: 8px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #e8eaed; }
        ''')
        app_btn.clicked.connect(lambda: self.handle_action('app'))
        btn_layout.addWidget(app_btn)

        layout.addLayout(btn_layout)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(container)

        self.setFixedWidth(400)
        self.adjustSize()

    def position_at_bottom_right(self):
        """현재 마우스가 위치한 모니터(선생님이 보고 계신 화면)의 우측 하단에 정확히 배치"""
        screen = QGuiApplication.screenAt(QCursor.pos())
        if not screen:
            screen = QApplication.primaryScreen()
        if not screen:
            return

        geo = screen.availableGeometry()
        x = geo.right() - self.width() - 20
        y = geo.bottom() - self.height() - 20
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 알림 카드를 클릭하면 프로그램 창 열기
            self.handle_action('app')

    def handle_action(self, action_name):
        if self.on_action_callback:
            self.on_action_callback(action_name)
        self.close()

# 전역 팝업 참조 유지 (가비지 컬렉션 방지)
_active_popups = []

def send_notification(title, message, results=None, on_action_callback=None, duration_secs=0):
    """
    화면 우측 하단 스마트 플로팅 카드 팝업 + 윈도우 네이티브 토스트
    """
    global _active_popups

    try:
        popup = NotificationPopup(title, message, results, on_action_callback, duration_secs)
        _active_popups.append(popup)
        popup.show()
        popup.raise_()
        popup.activateWindow()
        popup.destroyed.connect(lambda: _active_popups.remove(popup) if popup in _active_popups else None)
    except Exception as e:
        print(f'Floating popup error: {e}')

    # Windows 10/11 네이티브 알림 센터 토스트 알림도 동시 발송
    try:
        from winotify import Notification
        toast = Notification(
            app_id='업무포털 알리미',
            title=title,
            msg=message
        )
        toast.show()
    except Exception as e:
        print(f'Winotify error: {e}')