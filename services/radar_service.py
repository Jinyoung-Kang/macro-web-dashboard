# services/radar_service.py
import streamlit as st
import requests
import json
import pandas as pd
from services.ls_service import get_ls_token

LS_BASE_URL = "https://openapi.ls-sec.co.kr:8080"

@st.cache_data(ttl=60, show_spinner=False)
def fetch_investor_top_stocks(market_type="1", investor_type="1", trade_type="1"):
    """ [당일 실시간] 투자자별 매매 상위 스캐닝 (t1664) """
    token, err = get_ls_token()
    if err or not token: 
        return None, f"토큰 오류: {err}"

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
                # svalue: 순매수금액, price: 현재가, diff: 등락률
                df['svalue'] = pd.to_numeric(df.get('value', df.get('svalue', 0)), errors='coerce')
                df['price'] = pd.to_numeric(df.get('price', 0), errors='coerce')
                df['diff'] = pd.to_numeric(df.get('diff', 0), errors='coerce')
                return df, None
            return pd.DataFrame(), "수급 조건에 부합하는 데이터가 없습니다."
        return None, f"API 호출 실패 (HTTP {resp.status_code})"
    except Exception as e: 
        return None, f"통신 예외: {str(e)}"
