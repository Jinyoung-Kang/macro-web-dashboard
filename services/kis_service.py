# services/kis_service.py
import streamlit as st
import requests
import json

BASE_URL = "https://openapi.koreainvestment.com:9443"

@st.cache_data(ttl=3600, show_spinner=False)
def get_kis_token():
    app_key = st.secrets.get("kis_api", {}).get("app_key")
    app_secret = st.secrets.get("kis_api", {}).get("app_secret")

    if not app_key or not app_secret:
        return None, "secrets.toml에 [kis_api] app_key 또는 app_secret이 설정되지 않았습니다."

    url = f"{BASE_URL}/oauth2/tokenP"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if resp.status_code == 200:
            token_data = resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return None, f"토큰 발급 실패 (응답 데이터 이상): {token_data}"
            return access_token, None
        else:
            return None, f"토큰 발급 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"통신 예외 발생: {str(e)}"

def fetch_kis_kospi_index():
    token, err = get_kis_token()
    if err or not token:
        return None, f"토큰 오류: {err}"

    app_key = st.secrets.get("kis_api", {}).get("app_key")
    app_secret = st.secrets.get("kis_api", {}).get("app_secret")

    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHPUP02100000",
        "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": "0001"       
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        if resp.status_code == 200:
            res_json = resp.json()
            out = res_json.get("output", {})
            if out:
                price = float(out.get("bstp_nmix_prpr", 0))
                diff = float(out.get("bstp_nmix_prdy_vrss", 0))
                # 오타 수정: bstp_nmix_prdy_cttr -> bstp_nmix_prdy_ctrt
                rate = float(out.get("bstp_nmix_prdy_ctrt", 0))
                sign = str(out.get("prdy_vrss_sign", "3"))

                if sign in ["4", "5"]:
                    diff = -abs(diff)
                    rate = -abs(rate)
                elif sign in ["1", "2"]:
                    diff = abs(diff)
                    rate = abs(rate)
                else:
                    diff = 0.0
                    rate = 0.0

                prev_price = price - diff
                return {
                    "price": price,
                    "prev_price": prev_price,
                    "diff": diff,
                    "rate": rate,
                    "hname": out.get("hts_kor_isnm", "코스피 종합지수")
                }, None
            return None, f"응답 데이터 누락: {res_json}"
        else:
            return None, f"지수 조회 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"통신 예외: {str(e)}"

def fetch_kis_stock_quote(shcode: str = "005930"):
    token, err = get_kis_token()
    if err or not token:
        return None, err

    app_key = st.secrets.get("kis_api", {}).get("app_key")
    app_secret = st.secrets.get("kis_api", {}).get("app_secret")

    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01010100",
        "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": shcode.strip()
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            res_json = resp.json()
            output = res_json.get("output", {})
            if output:
                return output, None
            return None, f"응답 데이터 누락: {res_json}"
        else:
            return None, f"시세 조회 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"통신 예외: {str(e)}"
