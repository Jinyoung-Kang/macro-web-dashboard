# services/radar_service.py
import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import sys

# ==========================================
# 🚨 [HOTFIX] pykrx 라이브러리 Python 3.12+ 호환성 패치
# pkg_resources 모듈이 없는 최신 환경에서 pykrx가 뻗는 것을 방지하기 위해 가짜 모듈을 주입합니다.
# ==========================================
try:
    import pkg_resources
except ImportError:
    import types
    mock_pkg = types.ModuleType('pkg_resources')
    mock_pkg.get_distribution = lambda x: type('MockDist', (object,), {'version': 'unknown'})()
    sys.modules['pkg_resources'] = mock_pkg

from pykrx import stock
from services.ls_service import get_ls_token

LS_BASE_URL = "https://openapi.ls-sec.co.kr:8080"

# ==========================================
# 1. 당일 실시간 수급 스캐닝 (LS증권 t1664)
# ==========================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_investor_top_stocks(market_type="1", investor_type="1", trade_type="1"):
    """ 당일 장중 실시간 투자자별 매매 상위 50 """
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
                df['svalue'] = pd.to_numeric(df.get('value', df.get('svalue', 0)), errors='coerce')
                df['price'] = pd.to_numeric(df.get('price', 0), errors='coerce')
                df['diff'] = pd.to_numeric(df.get('diff', 0), errors='coerce')
                return df, None
            return pd.DataFrame(), "수급 데이터가 없습니다."
        return None, f"API 호출 실패 (HTTP {resp.status_code})"
    except Exception as e: 
        return None, f"통신 예외: {str(e)}"

# ==========================================
# 2. 최근 N일 누적 수급 랭킹 (Pykrx / KRX)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pykrx_period_top_stocks(market="KOSPI", investor="외국인", trade_type="순매수", days=5):
    """
    최근 N일간 누적 순매수/순매도 Top 50 종목 집계
    - market: "KOSPI", "KOSDAQ"
    - investor: "외국인", "기관합계", "개인"
    - trade_type: "순매수", "순매도"
    """
    try:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days * 2) 
        
        fdt = start_dt.strftime("%Y%m%d")
        tdt = end_dt.strftime("%Y%m%d")

        df = stock.get_market_net_purchases_of_equities_by_ticker(fdt, tdt, market)
        if df is None or df.empty:
            return pd.DataFrame(), "KRX 수급 데이터를 불러올 수 없습니다."

        target_col = investor
        if target_col not in df.columns:
            if investor == "외국인": target_col = "외국인합계"
            elif investor == "기관": target_col = "기관합계"
            elif investor == "개인": target_col = "개인"

        df['svalue'] = df[target_col] / 1000000

        ascending = True if trade_type == "순매도" else False
        df_sorted = df.sort_values(by='svalue', ascending=ascending).head(50).copy()

        ticker_list = df_sorted.index.tolist()
        result_rows = []
        
        for rank, ticker in enumerate(ticker_list, start=1):
            hname = stock.get_market_ticker_name(ticker)
            val = df_sorted.loc[ticker, 'svalue']
            
            ohlcv = stock.get_market_ohlcv_by_date(start_dt.strftime("%Y%m%d"), tdt, ticker)
            if len(ohlcv) >= 2:
                close = float(ohlcv['종가'].iloc[-1])
                prev_close = float(ohlcv['종가'].iloc[-2])
                diff_rate = ((close - prev_close) / prev_close) * 100
            elif len(ohlcv) == 1:
                close = float(ohlcv['종가'].iloc[-1])
                diff_rate = 0.0
            else:
                close, diff_rate = 0.0, 0.0

            result_rows.append({
                "rank": rank,
                "shcode": ticker,
                "hname": hname,
                "price": close,
                "diff": diff_rate,
                "svalue": val
            })

        return pd.DataFrame(result_rows), None
    except Exception as e:
        return None, f"KRX 기간 데이터 연산 오류: {str(e)}"

# ==========================================
# 3. 시장 전체 일별 수급 추이 (Pykrx / KRX)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_pykrx_market_trend(market="KOSPI", days=30):
    """ 최근 N거래일 코스피/코스닥 시장 전체 투자자별 일별 순매수 추이 """
    try:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days * 2)
        
        fdt = start_dt.strftime("%Y%m%d")
        tdt = end_dt.strftime("%Y%m%d")

        df = stock.get_market_net_purchases_of_equities_by_date(fdt, tdt, market)
        if df is None or df.empty:
            return pd.DataFrame(), "시장 수급 추이 데이터가 없습니다."

        df_res = pd.DataFrame()
        df_res['date'] = df.index
        df_res['foreign'] = df.get('외국인합계', 0) / 1000000
        df_res['inst'] = df.get('기관합계', 0) / 1000000
        df_res['retail'] = df.get('개인', 0) / 1000000
        
        df_res = df_res.tail(days).reset_index(drop=True)
        return df_res, None
    except Exception as e:
        return None, f"시장 시계열 연산 오류: {str(e)}"
