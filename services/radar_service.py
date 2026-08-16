# services/radar_service.py
import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
from services.ls_service import get_ls_token

LS_BASE_URL = "https://openapi.ls-sec.co.kr:8080"

def _safe_float(val):
    try:
        return float(val) if val else 0.0
    except:
        return 0.0

@st.cache_data(ttl=60, show_spinner=False)
def fetch_investor_top_stocks(market_type="1", investor_type="1", trade_type="1"):
    """ [Tab 1] 당일 실시간 투자자별 매매 상위 (t1664) """
    token, err = get_ls_token()
    if err or not token: return None, f"토큰 오류: {err}"

    url = f"{LS_BASE_URL}/stock/investor"
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {token}", "tr_cd": "t1664", "tr_cont": "N", "tr_cont_key": ""}
    payload = {
        "t1664InBlock": {
            "mgubun": market_type, "vagubun": "1", "bdgubun": trade_type, "cdgubun": investor_type, "cnt": 50
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
        return None, f"API 호출 실패 (HTTP {resp.status_code})"
    except Exception as e: return None, f"통신 예외: {str(e)}"

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_market_investor_trend(market_type="1"):
    """ [Tab 2] 시장 전체 투자자별 일별 매매 동향 추이 (t1615) """
    token, err = get_ls_token()
    if err or not token: return None, f"토큰 오류: {err}"

    url = f"{LS_BASE_URL}/stock/investor"
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {token}", "tr_cd": "t1615", "tr_cont": "N", "tr_cont_key": ""}
    payload = {
        "t1615InBlock": {
            "gubun1": "2",        # 2: 일자별
            "gubun2": market_type,# 1: 코스피, 2: 코스닥
            "gubun3": "2",        # 2: 금액(백만원)
            "date": ""            
        }
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if resp.status_code == 200:
            out_block = resp.json().get("t1615OutBlock1", [])
            if out_block:
                df = pd.DataFrame(out_block)
                
                # 🚨 FIX: 서버가 어떤 이름으로 날짜를 주든 무조건 찾아서 매핑하는 동적 탐색 로직
                date_col = None
                possible_date_cols = ['date', 'date1', 'dt', 'trdt', 'biz_dt', 'tmdt', 'tdate']
                for col in possible_date_cols:
                    if col in df.columns:
                        date_col = col
                        break
                
                # 그래도 필드가 없다면, 무엇이 반환되었는지 화면에 강제로 표출시켜 디버깅 유도
                if not date_col:
                    return pd.DataFrame(), f"날짜 필드 누락. 수신된 원본 컬럼명: {list(df.columns)}"

                df['date_dt'] = pd.to_datetime(df[date_col], format='%Y%m%d', errors='coerce')
                
                # 데이터 매핑
                df['foreign'] = df.get('sv_08', 0).apply(_safe_float)
                df['inst'] = df.get('sv_17', 0).apply(_safe_float)
                df['retail'] = df.get('sv_14', 0).apply(_safe_float)
                
                df = df.dropna(subset=['date_dt']).sort_values('date_dt').reset_index(drop=True)
                df['date'] = df['date_dt']
                
                return df[['date', 'foreign', 'inst', 'retail']], None
            return pd.DataFrame(), "수급 추이 데이터가 없습니다."
        return None, f"API 호출 실패 (HTTP {resp.status_code})"
    except Exception as e: return None, f"통신 예외: {str(e)}"
