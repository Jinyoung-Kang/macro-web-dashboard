"""
services/ls_service.py
LS증권 OPEN API 통신 엔진 및 토큰 관리 모듈
"""
import os
import time
import logging
import requests
import streamlit as st

logger = logging.getLogger(__name__)

def get_secret(key_path: str, default: str = "") -> str:
    """Streamlit Secrets (중첩 섹션 및 단일 키 지원) 및 환경변수 안전 로드"""
    try:
        if hasattr(st, "secrets") and st.secrets:
            keys = key_path.split(".")
            val = st.secrets
            found = True
            for k in keys:
                if hasattr(val, "get") and val.get(k) is not None:
                    val = val.get(k)
                elif hasattr(val, "__getitem__") and k in val:
                    val = val[k]
                else:
                    found = False
                    break
            if found and val is not None:
                return str(val).strip()

            leaf = keys[-1]
            if hasattr(st.secrets, "get") and st.secrets.get(leaf) is not None:
                return str(st.secrets.get(leaf)).strip()
            if hasattr(st.secrets, "get") and st.secrets.get(leaf.upper()) is not None:
                return str(st.secrets.get(leaf.upper())).strip()
    except Exception:
        pass
    return os.environ.get(key_path, os.environ.get(key_path.replace(".", "_").upper(), default))


LS_APP_KEY = get_secret("ls.app_key", get_secret("LS_APP_KEY", ""))
LS_APP_SECRET = get_secret("ls.app_secret", get_secret("LS_APP_SECRET", ""))
LS_BASE_URL = "https://openapi.ls-sec.co.kr:8080"

@st.cache_data(ttl=18000, show_spinner=False)
def get_ls_access_token() -> str:
    """LS증권 OAuth 2.0 Access Token 발급 및 캐싱"""
    app_key = get_secret("ls.app_key", get_secret("LS_APP_KEY", ""))
    app_secret = get_secret("ls.app_secret", get_secret("LS_APP_SECRET", ""))
    
    if not app_key or not app_secret:
        return ""

    url = f"{LS_BASE_URL}/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    payload = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecretkey": app_secret,
        "scope": "oob"
    }

    try:
        res = requests.post(url, headers=headers, data=payload, timeout=8)
        if res.status_code == 200:
            data = res.json()
            return data.get("access_token", "")
    except Exception as e:
        logger.warning(f"LS API Token 발급 실패: {e}")
    return ""


def call_ls_api(tr_cd: str, tr_url: str, body_params: dict) -> dict:
    """LS증권 TR 실행 공통 함수"""
    token = get_ls_access_token()
    app_key = get_secret("ls.app_key", get_secret("LS_APP_KEY", ""))
    
    if not token or not app_key:
        return {}

    url = f"{LS_BASE_URL}{tr_url}"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "tr_cd": tr_cd,
        "tr_cont": "N",
        "tr_cont_key": "",
        "mac_address": ""
    }

    try:
        res = requests.post(url, headers=headers, json=body_params, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.warning(f"LS TR ({tr_cd}) 호출 실패: {e}")
    return {}
