# services/radar_service.py
import streamlit as st
import pandas as pd
import requests
import json
from services.ls_service import get_ls_token
from services.kis_service import get_kis_token

LS_BASE_URL = "https://openapi.ls-sec.co.kr:8080"
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"

# ==========================================
# 1. 당일 실시간 수급 스캐닝 (LS증권 t1664)
# ==========================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_investor_top_stocks(market_type="1", investor_type="1", trade_type="1"):
    token, err = get_ls_token()
    if err or not token: 
        return None, f"LS증권 토큰 오류: {err}"

    url = f"{LS_BASE_URL}/stock/investor"
    headers = {
        "Content-Type": "application/json; charset=utf-8", 
        "authorization": f"Bearer {token}", 
        "tr_cd": "t1664", 
        "tr_cont": "N", 
        "tr_cont_key": ""
    }
    payload = {
        "t1664InBlock": {
            "mgubun": market_type, 
            "vagubun": "1", 
            "bdgubun": trade_type, 
            "cdgubun": investor_type, 
            "cnt": 50
        }
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if resp.status_code == 200:
            out_block = resp.json().get("t1664OutBlock1", [])
            if out_block:
                df = pd.DataFrame(out_block)
                df['svalue'] = pd.to_numeric(df.get('value', df.get('svalue', 0)), errors='coerce')
                df['price'] = pd.to_numeric(df.get('price', 0), errors='coerce')
                df['diff'] = pd.to_numeric(df.get('diff', 0), errors='coerce')
                return df, None
            return pd.DataFrame(), "수급 조건에 부합하는 데이터가 없습니다."
        return None, f"LS API 호출 실패 (HTTP {resp.status_code})"
    except Exception as e: 
        return None, f"통신 예외: {str(e)}"

# ==========================================
# 2. 개별 종목 수급 정밀 분석 (한국투자증권 FHKST01010900)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_kis_ticker_investor_trend(shcode: str):
    """ 특정 종목의 과거 30영업일 투자자별 순매수 수량 추이 조회 """
    token, err = get_kis_token()
    if err or not token: return None, f"KIS 토큰 오류: {err}"

    app_key = st.secrets.get("kis_api", {}).get("app_key")
    app_secret = st.secrets.get("kis_api", {}).get("app_secret")

    url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST01010900",
        "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": shcode.strip()
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            out_block = resp.json().get("output", [])
            if out_block:
                df = pd.DataFrame(out_block)
                
                df['date'] = pd.to_datetime(df['stck_bsop_date'], format='%Y%m%d', errors='coerce')
                df['close'] = pd.to_numeric(df['stck_clpr'], errors='coerce')
                df['foreign'] = pd.to_numeric(df['frgn_ntby_qty'], errors='coerce')
                df['inst'] = pd.to_numeric(df['orgn_ntby_qty'], errors='coerce')
                df['retail'] = pd.to_numeric(df['prsn_ntby_qty'], errors='coerce')
                
                df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
                return df[['date', 'close', 'foreign', 'inst', 'retail']], None
            return pd.DataFrame(), "해당 종목의 수급 데이터가 존재하지 않습니다."
        return None, f"KIS API 호출 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e:
        return None, f"통신 예외: {str(e)}"
