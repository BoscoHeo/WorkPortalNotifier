# -*- coding: utf-8 -*-
import json
import logging
import os
from cryptography.fernet import Fernet

EDUCATION_OFFICES = {
    '서울': {'name': '서울특별시교육청', 'url': 'https://sen.eduptl.kr'},
    '경기': {'name': '경기도교육청', 'url': 'https://goe.eduptl.kr'},
    '경남': {'name': '경상남도교육청', 'url': 'https://gne.eduptl.kr'},
    '부산': {'name': '부산광역시교육청', 'url': 'https://pen.eduptl.kr'},
    '대구': {'name': '대구광역시교육청', 'url': 'https://dge.eduptl.kr'},
    '대전': {'name': '대전광역시교육청', 'url': 'https://dje.eduptl.kr'},
    '경북': {'name': '경상북도교육청', 'url': 'https://gbe.eduptl.kr'},
    '세종': {'name': '세종특별자치시교육청', 'url': 'https://sje.eduptl.kr'},
    '울산': {'name': '울산광역시교육청', 'url': 'https://use.eduptl.kr'},
    '인천': {'name': '인천광역시교육청', 'url': 'https://ice.eduptl.kr'},
    '광주': {'name': '광주광역시교육청', 'url': 'https://gen.eduptl.kr'},
    '전남': {'name': '전라남도교육청', 'url': 'https://jne.eduptl.kr'},
    '전북': {'name': '전북특별자치도교육청', 'url': 'https://jbe.eduptl.kr'},
    '충남': {'name': '충청남도교육청', 'url': 'https://cne.eduptl.kr'},
    '충북': {'name': '충청북도교육청', 'url': 'https://cbe.eduptl.kr'},
    '강원': {'name': '강원특별자치도교육청', 'url': 'https://kwe.eduptl.kr'},
    '제주': {'name': '제주특별자치도교육청', 'url': 'https://jje.eduptl.kr'}
}

class ConfigManager:
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.storage_dir = os.path.join(os.environ.get('APPDATA', '.'), 'WorkPortalNotifier')
        os.makedirs(self.storage_dir, exist_ok=True)
        self.config_path = os.path.join(self.storage_dir, self.config_file)
        self.key_path = os.path.join(self.storage_dir, '.key')
        self._load_key()
        self.config = self._load_config()

    def _load_key(self):
        """대칭키를 로드하거나 새로 생성합니다."""
        if os.path.exists(self.key_path):
            try:
                with open(self.key_path, 'rb') as f:
                    self.key = f.read()
                self.cipher = Fernet(self.key)
                return
            except Exception:
                logger = logging.getLogger('WorkPortalNotifier')
                logger.warning('암호화 키 파일이 손상되었습니다. 새 키를 생성합니다. (저장된 암호는 다시 입력해야 합니다.)')
        
        self.key = Fernet.generate_key()
        with open(self.key_path, 'wb') as f:
            f.write(self.key)
        self.cipher = Fernet(self.key)

    def _load_config(self):
        """설정 파일을 로드합니다."""
        default_config = {
            'office': '전북',
            'interval': 5,
            'use_sound': False,
            'auto_start': False,
            'use_toast': True,
            'cert_password': '',
            'auto_login': False,
            'auto_monitor': False,
            'cert_name': '',
            'neis_order': 0,
            'browser': 'chrome'
        }

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                default_config.update(data)
                return default_config
            except json.JSONDecodeError as e:
                logger = logging.getLogger('WorkPortalNotifier')
                logger.warning(f'설정 파일 파싱 실패 — 기본값으로 실행합니다. ({e})')
            except Exception as e:
                logger = logging.getLogger('WorkPortalNotifier')
                logger.warning(f'설정 파일 읽기 실패 — 기본값으로 실행합니다. ({e})')

        return default_config

    def save_config(self):
        """설정을 저장합니다."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger = logging.getLogger('WorkPortalNotifier')
            logger.error(f'설정 저장 실패: {e}')

    def get_office_url(self):
        office_key = self.config.get('office', '전북')
        return EDUCATION_OFFICES.get(office_key, EDUCATION_OFFICES['전북'])['url']

    def set_password(self, password):
        if not password:
            self.config['cert_password'] = ''
        else:
            encrypted_pw = self.cipher.encrypt(password.encode()).decode()
            self.config['cert_password'] = encrypted_pw
        self.save_config()

    def clear_password(self):
        self.config['cert_password'] = ''
        self.save_config()

    def get_password(self):
        encrypted_pw = self.config.get('cert_password', '')
        if not encrypted_pw:
            return ''
        try:
            return self.cipher.decrypt(encrypted_pw.encode()).decode()
        except Exception:
            logger = logging.getLogger('WorkPortalNotifier')
            logger.warning('인증서 암호 복호화 실패 — 암호를 다시 저장해 주세요. (.key 파일이 손상되었을 수 있습니다.)')
            return ''

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()