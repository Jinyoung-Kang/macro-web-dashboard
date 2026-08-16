# services/radar_service.py
import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
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
            "mgubun": market_type, "vagubun": "1", "bdgubun": trade_type, "cdgubun": investor_type, 
            "cnt": 50 # t1664는 cnt 허용
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
def fetch_period_investor_top_stocks(market_type="1", investor_type="1", trade_type="1", days=5):
    """ [Tab 2] 특정 기간 누적 투자자별 매매 상위 (t1665) """
    token, err = get_ls_token()
    if err or not token: return None, f"토큰 오류: {err}"

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    fdt = start_dt.strftime("%Y%m%d")
    tdt = end_dt.strftime("%Y%m%d")

    url = f"{LS_BASE_URL}/stock/investor"
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {token}", "tr_cd": "t1665", "tr_cont": "N", "tr_cont_key": ""}
    
    # 🚨 FIX: HTTP 500 원인이었던 'cnt' 파라미터 삭제 (서버에서 미지원)
    payload = {
        "t1665InBlock": {
            "mgubun": market_type, "vagubun": "1", "bdgubun": trade_type, "cdgubun": investor_type,
            "fdt": fdt, "tdt": tdt
        }
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if resp.status_code == 200:
            out_block = resp.json().get("t1665OutBlock1", [])
            if out_block:
                df = pd.DataFrame(out_block)
                df['svalue'] = pd.to_numeric(df.get('value', df.get('svalue', 0)), errors='coerce')
                df['price'] = pd.to_numeric(df.get('price', 0), errors='coerce')
                df['diff'] = pd.to_numeric(df.get('diff', 0), errors='coerce')
                
                # API단에서 cnt를 지원하지 않으므로, Pandas 연산 후 상위 50개만 슬라이싱
                df = df.head(50)
                return df, None
            return pd.DataFrame(), "해당 기간의 수급 데이터가 없습니다."
        return None, f"API 호출 실패 (HTTP {resp.status_code}): {resp.text}"
    except Exception as e: return None, f"통신 예외: {str(e)}"

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_market_investor_trend(market_type="1"):
    """ [Tab 3] 시장 전체 투자자별 일별 매매 동향 추이 (t1615) """
    token, err = get_ls_token()
    if err or not token: return None, f"토큰 오류: {err}"

    url = f"{LS_BASE_URL}/stock/investor"
    headers = {"Content-Type": "application/json; charset=utf-8", "authorization": f"Bearer {token}", "tr_cd": "t1615", "tr_cont": "N", "tr_cont_key": ""}
    payload = {
        "t1615InBlock": {
            "gubun1": "2",        # 2: 일자별
            "gubun2": market_type,# 1: 코스피, 2: 코스닥
            "gubun3": "2",        # 2: 금액(백만원)
            "date": ""            # 공란: 최근 일자부터 연속
        }
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if resp.status_code == 200:
            out_block = resp.json().get("t1615OutBlock1", [])
            if out_block:
                df = pd.DataFrame(out_block)
                
                # 🚨 FIX: API 응답에 따라 date 필드를 동적 매핑 (KeyError 방지)
                date_col = 'date' if 'date' in df.columns else ('date1' if 'date1' in df.columns else None)
                if not date_col:
                    return pd.DataFrame(), "응답에 날짜 필드가 누락되었습니다."

                df['date_dt'] = pd.to_datetime(df[date_col], format='%Y%m%d', errors='coerce')
                
                # .get()을 활용해 혹시 모를 특정 주체 누락(KeyError) 완벽 방어
                df['foreign'] = df.get('sv_08', 0).apply(_safe_float)
                df['inst'] = df.get('sv_17', 0).apply(_safe_float)
                df['retail'] = df.get('sv_14', 0).apply(_safe_float)
                
                df = df.dropna(subset=['date_dt']).sort_values('date_dt').reset_index(drop=True)
                df['date'] = df['date_dt'] # 뷰와의 호환성을 위해 date 컬럼 복원
                
                return df[['date', 'foreign', 'inst', 'retail']], None
            return pd.DataFrame(), "수급 추이 데이터가 없습니다."
        return None, f"API 호출 실패 (HTTP {resp.status_code})"
    except Exception as e: return None, f"통신 예외: {str(e)}"
