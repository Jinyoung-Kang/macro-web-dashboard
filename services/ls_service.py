# services/ls_service.py
import streamlit as st
import requests
import json

BASE_URL = "https://openapi.ls-sec.co.kr:8080"

@st.cache_data(ttl=3600, show_spinner=False)
def get_ls_token():
    """
    LS증권 OPEN API OAuth 2.0 접근 토큰(Access Token)을 발급받습니다.
    """
    app_key = st.secrets.get("ls_api", {}).get("app_key")
    app_secret = st.secrets.get("ls_api", {}).get("app_secret")

    if not app_key or not app_secret:
        return None, "secrets.toml에 [ls_api] app_key 또는 app_secret이 설정되지 않았습니다."

    url = f"{BASE_URL}/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecretkey": app_secret,
        "scope": "oob"
    }

    try:
        resp = requests.post(url, headers=headers, data=payload, timeout=10)
        if resp.status_code == 200:
            token_data = resp.json()
            access_token = token_data.get("access_token")
            return access_token, None
        else:
            return None, f"토큰 발급 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"API 통신 오류: {str(e)}"

def fetch_stock_quote(shcode: str = "005930"):
    """
    국내 주식 현재가 시세(TR: t1102)를 실시간 조회합니다.
    """
    token, err = get_ls_token()
    if err or not token:
        return None, err

    url = f"{BASE_URL}/stock/market-data"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "tr_cd": "t1102",
        "tr_cont": "N",
        "tr_cont_key": ""
    }
    payload = {
        "t1102InBlock": {
            "shcode": shcode.strip()
        }
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            out_block = result.get("t1102OutBlock", {})
            if not out_block or not out_block.get("hname"):
                return None, f"종목 정보를 찾을 수 없습니다. (응답: {result})"
            return out_block, None
        else:
            return None, f"시세 조회 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"시세 통신 오류: {str(e)}"

@st.cache_data(ttl=15, show_spinner=False)
def fetch_kospi_index():
    """
    LS증권 업종 현재가(TR: t1511)를 호출하여 코스피 실시간 지수 데이터를 반환합니다.
    - upcode: 001 (코스피 종합)
    """
    token, err = get_ls_token()
    if err or not token:
        return None

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "tr_cd": "t1511",
        "tr_cont": "N",
        "tr_cont_key": ""
    }
    payload = {
        "t1511InBlock": {
            "upcode": "001"
        }
    }

    # /stock/sector 및 /stock/market-data 경로 순차 시도
    for path in ["/stock/sector", "/stock/market-data"]:
        try:
            url = f"{BASE_URL}{path}"
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=8)
            if resp.status_code == 200:
                data = resp.json().get("t1511OutBlock", {})
                raw_jisu = data.get("jisu") or data.get("pricejisu") or data.get("price")
                if raw_jisu is not None:
                    price = float(raw_jisu)
                    raw_change = float(data.get("change", 0))
                    raw_diff = float(data.get("diff", 0))
                    sign = str(data.get("sign", "3"))

                    # 하락/하한(4, 5) 부호 처리
                    if sign in ["4", "5"]:
                        diff = -abs(raw_change)
                        rate = -abs(raw_diff)
                    elif sign in ["1", "2"]:
                        diff = abs(raw_change)
                        rate = abs(raw_diff)
                    else:
                        diff = 0.0
                        rate = 0.0

                    prev_price = price - diff

                    if price > 0:
                        return {
                            "price": price,
                            "prev_price": prev_price,
                            "diff": diff,
                            "rate": rate,
                            "hname": data.get("hname", "코스피")
                        }
        except Exception:
            continue
    return None
