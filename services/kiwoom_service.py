# services/kiwoom_service.py
import streamlit as st
import requests
import json

BASE_URL = "https://api.kiwoom.com"

@st.cache_data(ttl=3600, show_spinner=False)
def get_kiwoom_token():
    """
    키움증권 REST API OAuth 2.0 접근 토큰(Access Token)을 발급받습니다.
    """
    app_key = st.secrets.get("kiwoom_api", {}).get("app_key")
    app_secret = st.secrets.get("kiwoom_api", {}).get("app_secret")

    if not app_key or not app_secret:
        return None, "secrets.toml에 [kiwoom_api] app_key 또는 app_secret이 설정되지 않았습니다."

    url = f"{BASE_URL}/oauth2/token"
    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "secretkey": app_secret
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if resp.status_code == 200:
            token_data = resp.json()
            access_token = token_data.get("access_token") or token_data.get("token")
            return access_token, None
        else:
            return None, f"토큰 발급 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"통신 예외: {str(e)}"

def fetch_kiwoom_stock_quote(shcode: str = "005930"):
    """
    키움증권 국내 주식 현재가 시세를 조회합니다.
    """
    token, err = get_kiwoom_token()
    if err or not token:
        return None, err

    app_key = st.secrets.get("kiwoom_api", {}).get("app_key")
    app_secret = st.secrets.get("kiwoom_api", {}).get("app_secret")

    url = f"{BASE_URL}/api/v1/stock/market-data/current-price"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecretkey": app_secret,
        "tr_id": "FHKST01010100"
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": shcode.strip()
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            res_json = resp.json()
            output = res_json.get("output", res_json.get("output1", {}))
            if output:
                return output, None
            return None, f"응답 데이터 누락: {res_json}"
        else:
            return None, f"시세 조회 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"통신 예외: {str(e)}"

@st.cache_data(ttl=15, show_spinner=False)
def fetch_kiwoom_kospi_index():
    """
    키움증권 코스피 실시간 업종/지수 시세를 조회합니다.
    (업종코드: 0001 또는 001)
    """
    token, err = get_kiwoom_token()
    if err or not token:
        return None, err

    app_key = st.secrets.get("kiwoom_api", {}).get("app_key")
    app_secret = st.secrets.get("kiwoom_api", {}).get("app_secret")

    url = f"{BASE_URL}/api/v1/stock/market-data/index-price"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecretkey": app_secret,
        "tr_id": "FHKUP03500100"
    }
    params = {
        "fid_cond_mrkt_div_code": "U",
        "fid_input_iscd": "0001"
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        if resp.status_code == 200:
            res_json = resp.json()
            out = res_json.get("output", {})
            if out:
                price = float(out.get("bstp_nmix_prpr", out.get("price", 0)))
                diff = float(out.get("bstp_nmix_prdy_vrss", out.get("change", 0)))
                rate = float(out.get("bstp_nmix_prdy_cttr", out.get("diff", 0)))
                sign = str(out.get("prdy_vrss_sign", "3"))

                if sign in ["4", "5"]:
                    diff = -abs(diff)
                    rate = -abs(rate)
                elif sign in ["1", "2"]:
                    diff = abs(diff)
                    rate = abs(rate)

                prev_price = price - diff
                return {
                    "price": price,
                    "prev_price": prev_price,
                    "diff": diff,
                    "rate": rate,
                    "hname": out.get("hts_kor_isnm", "코스피 종합지수")
                }, None
            return None, f"지수 응답 데이터 누락: {res_json}"
        else:
            return None, f"지수 조회 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"통신 예외: {str(e)}"
