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
    """Streamlit Secrets 및 환경변수 안전 로드"""
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
    """KIS OAuth 2.0 Access Token 발급 및 캐싱"""
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
    """KIS API GET 공통 호출기"""
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
def fetch_kis_kospi_index() -> dict:
    """
    한국투자증권(KIS) API를 사용하여 코스피 업종(지수) 현재가를 조회
    (views/macro_view.py, services/macro_service.py 연동용)
    """
    # KIS 국내 주식 업종 현재가 TR_ID: FHPUP02100000
    # 업종코드(ISCD): "0001" (KOSPI)
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",  # 업종
        "FID_INPUT_ISCD": "0001"        # 코스피 종합지수
    }
    
    res = call_kis_api(tr_id="FHPUP02100000", endpoint="/uapi/domestic-stock/v1/quotations/inquire-index-price", params=params)
    
    if res and res.get("rt_cd") == "0":
        output = res.get("output", {})
        if output:
            try:
                # 현재가(지수), 전일대비부호, 전일대비율
                current_idx = float(output.get("bstp_nmix_prpr", "0"))
                change_pct = float(output.get("bstp_nmix_prdy_ctrt", "0"))
                return {
                    "price": current_idx,
                    "change_pct": change_pct
                }
            except Exception as e:
                logger.warning(f"KIS 지수 파싱 오류: {e}")
                
    # 실패 또는 미응답 시 빈 딕셔너리 반환
    return {}
