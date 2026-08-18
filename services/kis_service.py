"""
services/kis_service.py
한국투자증권(KIS) Open API 통신 엔진 및 토큰 관리 모듈
"""
import os
import logging
import requests
import streamlit as st

logger = logging.getLogger(__name__)

def get_secret(key_path: str, default: str = "") -> str:
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


KIS_APP_KEY = get_secret("kis.app_key", get_secret("KIS_APP_KEY", ""))
KIS_APP_SECRET = get_secret("kis.app_secret", get_secret("KIS_APP_SECRET", ""))
KIS_CANO = get_secret("kis.cano", get_secret("KIS_CANO", ""))
KIS_ACNT_PRDT_CD = get_secret("kis.acnt_prdt_cd", get_secret("KIS_ACNT_PRDT_CD", "01"))
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"

@st.cache_data(ttl=21600, show_spinner=False)
def get_kis_access_token() -> str:
    app_key = get_secret("kis.app_key", get_secret("KIS_APP_KEY", ""))
    app_secret = get_secret("kis.app_secret", get_secret("KIS_APP_SECRET", ""))
    
    if not app_key or not app_secret:
        return ""

    url = f"{KIS_BASE_URL}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }

    try:
        res = requests.post(url, json=payload, timeout=8)
        if res.status_code == 200:
            data = res.json()
            return data.get("access_token", "")
    except Exception as e:
        logger.warning(f"KIS Token 발급 실패: {e}")
    return ""


def call_kis_api(tr_id: str, endpoint: str, params: dict) -> dict:
    token = get_kis_access_token()
    app_key = get_secret("kis.app_key", get_secret("KIS_APP_KEY", ""))
    app_secret = get_secret("kis.app_secret", get_secret("KIS_APP_SECRET", ""))

    if not token or not app_key:
        return {}

    url = f"{KIS_BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
        "custtype": "P"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.warning(f"KIS API ({tr_id}) 호출 실패: {e}")
    return {}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_kis_kospi_index() -> tuple:
    """
    한국투자증권(KIS) API를 사용하여 코스피 지수를 조회
    (튜플 반환으로 macro_service의 unpacking 에러 완전 차단)
    """
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",  
        "FID_INPUT_ISCD": "0001"        
    }
    
    res = call_kis_api(tr_id="FHPUP02100000", endpoint="/uapi/domestic-stock/v1/quotations/inquire-index-price", params=params)
    
    if res and res.get("rt_cd") == "0":
        output = res.get("output", {})
        if output:
            try:
                current_idx = float(output.get("bstp_nmix_prpr", "0"))
                change_pct = float(output.get("bstp_nmix_prdy_ctrt", "0"))
                sign = "+" if change_pct > 0 else ""
                formatted = f"{current_idx:,.2f} ({sign}{change_pct:.2f}%)"
                return formatted, current_idx
            except Exception as e:
                logger.warning(f"KIS 지수 파싱 오류: {e}")
                
    return "", 0.0
