# services/radar_service.py
import streamlit as st
import requests
import json
import pandas as pd
from services.ls_service import get_ls_token

# LS증권 REST API 도메인
LS_BASE_URL = "https://openapi.ls-sec.co.kr:8080"

@st.cache_data(ttl=60, show_spinner=False)
def fetch_investor_top_stocks(market_type="1", investor_type="1", trade_type="1"):
    """
    LS증권 API (t1664) - 투자자별 순매수/순매도 상위 종목 스캐닝
    - market_type: "1"(코스피), "2"(코스닥)
    - investor_type: "1"(외국인), "2"(기관), "3"(개인)
    - trade_type: "1"(순매수), "2"(순매도)
    """
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
    
    # API 명세서 기준 InBlock 파라미터 조합
    payload = {
        "t1664InBlock": {
            "mgubun": market_type,
            "vagubun": "1",  # 0: 수량, 1: 금액 (자금 유입을 봐야 하므로 무조건 금액)
            "bdgubun": trade_type,
            "cdgubun": investor_type,
            "cnt": 50        # 최대 50종목 추출
        }
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if resp.status_code == 200:
            res_json = resp.json()
            out_block = res_json.get("t1664OutBlock1", [])
            
            if out_block:
                df = pd.DataFrame(out_block)
                
                # API 실제 응답 필드명에 맞게 매핑 ('value' 가 순매수금액)
                if 'value' in df.columns:
                    df['svalue'] = pd.to_numeric(df['value'], errors='coerce')
                else:
                    df['svalue'] = 0.0
                    
                if 'price' in df.columns:
                    df['price'] = pd.to_numeric(df['price'], errors='coerce')
                else:
                    df['price'] = 0.0
                    
                if 'diff' in df.columns:
                    df['diff'] = pd.to_numeric(df['diff'], errors='coerce')
                else:
                    df['diff'] = 0.0
                
                return df, None
            else:
                return pd.DataFrame(), "수급 조건에 부합하는 데이터가 없습니다."
        else:
            return None, f"API 호출 실패 (HTTP {resp.status_code})"
    except Exception as e:
        return None, f"통신 예외: {str(e)}"
