# services/cot_service.py
import pandas as pd
import requests
import streamlit as st

@st.cache_data(ttl=3600*12, show_spinner=False)
def fetch_cftc_cot_legacy(contract_code: str, limit: int = 300):
    """
    CFTC Legacy COT (Futures Only) API 호출
    - contract_code: 자산군 고유 코드
    - limit: 조회할 과거 주(Week) 데이터 수 (최대 1000)
    """
    url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    params = {
        "cftc_contract_market_code": contract_code,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": limit
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                return pd.DataFrame(), "해당 자산의 COT 데이터를 찾을 수 없습니다."
            
            df = pd.DataFrame(data)
            
            # 날짜 및 수치 데이터 형변환
            df['date'] = pd.to_datetime(df['report_date_as_yyyy_mm_dd']).dt.tz_localize(None)
            df['long'] = pd.to_numeric(df.get('noncomm_positions_long_all', 0), errors='coerce').fillna(0)
            df['short'] = pd.to_numeric(df.get('noncomm_positions_short_all', 0), errors='coerce').fillna(0)
            
            # 순포지션 (Net Position) = Long - Short 계산
            df['net_position'] = df['long'] - df['short']
            
            return df[['date', 'long', 'short', 'net_position']], None
            
        return pd.DataFrame(), f"CFTC API 호출 실패 (HTTP {resp.status_code})"
    except Exception as e:
        return pd.DataFrame(), f"API 통신 예외 발생: {str(e)}"
