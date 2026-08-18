"""
services/radar_service.py
KRX 정보데이터시스템(pykrx) 및 금융 REST API를 활용한 날짜별/누적 수급 스캐닝 엔진
자동 과거 영업일 탐색(Smart Fallback) 로직 탑재
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. PyKrx 엔진 (가장 확실한 과거/장마감 확정 원장 조회)
# ==============================================================================
def fetch_pykrx_deal_ranking(target_date: str, market: str, investor: str, trade_type: str, top_n: int) -> pd.DataFrame:
    if not PYKRX_AVAILABLE:
        return pd.DataFrame()
        
    mkt = "KOSPI" if "KOSPI" in market.upper() else "KOSDAQ"
    inv_map = {"외국인": "외국인", "기관": "기관합계", "연기금": "연기금", "금융투자": "금융투자", "투신": "투신", "개인": "개인"}
    inv = inv_map.get(investor, "외국인")
    
    try:
        df = stock.get_market_net_purchases_of_equities_by_ticker(target_date, target_date, mkt, inv)
        if df.empty:
            return pd.DataFrame()
            
        df = df.reset_index().rename(columns={"티커": "종목코드"})
        
        if trade_type == "순매수":
            df = df[df["순매수거래대금"] > 0].sort_values("순매수거래대금", ascending=False).head(top_n)
        else:
            df = df[df["순매수거래대금"] < 0].sort_values("순매수거래대금", ascending=True).head(top_n)
            
        if df.empty:
            return pd.DataFrame()

        prices_df = stock.get_market_ohlcv(target_date, target_date, mkt)
        
        records = []
        rank = 1
        for _, row in df.iterrows():
            code = row["종목코드"]
            name = row["종목명"]
            net_amt = row["순매수거래대금"]
            amt_eok = round(net_amt / 100000000.0, 1)
            
            price = 0
            fluc = 0.0
            if prices_df is not None and not prices_df.empty and code in prices_df.index:
                p_row = prices_df.loc[code]
                price = float(p_row["종가"])
                fluc = float(p_row["등락률"])
            
            records.append({
                "순위": rank,
                "종목코드": code,
                "종목명": name,
                "현재가": price,
                "등락률(%)": fluc,
                "순매수대금(억)": amt_eok,
                "시가총액_가중": max(price * 1000, 500),
                "데이터_출처": f"PyKrx 공식 확정 ({target_date})"
            })
            rank += 1
        return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"PyKrx 조회 실패 ({target_date}): {e}")
        return pd.DataFrame()


# ==============================================================================
# 2. Daum 금융 API (당일 실시간 조회용 백업)
# ==============================================================================
def fetch_daum_deal_ranking(market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    market_param = "KOSPI" if "KOSPI" in market.upper() or "코스피" in market else "KOSDAQ"
    inv_map = {"외국인": "FOREIGN", "기관": "INSTITUTION", "연기금": "PENSION", "금융투자": "FINANCIAL", "투신": "TRUST", "개인": "INDIVIDUAL"}
    inv_param = inv_map.get(investor, "FOREIGN")
    
    action = "top_net_buyers" if trade_type == "순매수" else "top_net_sellers"
    url = f"https://finance.daum.net/api/trend/investors/{action}?market={market_param}&investorType={inv_param}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://finance.daum.net/trend/investors"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            items = resp.json().get("data", [])
            if items:
                records = []
                for idx, row in enumerate(items[:top_n], start=1):
                    code = str(row.get("symbolCode", "")).replace("A", "")
                    name = row.get("name", "")
                    price = float(row.get("tradePrice", 0))
                    
                    change_pct = float(row.get("changeRate", 0)) * 100.0
                    if str(row.get("change", "")) == "FALL":
                        change_pct = -abs(change_pct)
                        
                    net_amount = float(row.get("netBuyAmount", row.get("netAmount", 0)))
                    amt_eok = round(abs(net_amount) / 100000000.0, 1)
                    if trade_type == "순매도":
                        amt_eok = -amt_eok

                    records.append({
                        "순위": idx, "종목코드": code, "종목명": name, "현재가": price,
                        "등락률(%)": round(change_pct, 2), "순매수대금(억)": amt_eok,
                        "시가총액_가중": max(price * 1000, 500), "데이터_출처": "Daum 당일 실시간 API"
                    })
                return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Daum API 수급 조회 실패: {e}")
    return pd.DataFrame()


# ==============================================
# 3. 통합 수급 스캐너 (자동 과거 영업일 탐색 로직 적용)
# ==============================================
@st.cache_data(ttl=60, show_spinner=False)
def get_market_radar_scanner(target_date_obj, market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    """
    지정한 날짜에 데이터가 없을 경우(장마감 집계 전, 휴일 등), 자동으로 과거로 거슬러 올라가
    데이터가 존재하는 가장 최근의 확정 영업일 데이터를 반환합니다.
    """
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    today_str = now_kst.strftime("%Y%m%d")
    time_num = now_kst.hour * 100 + now_kst.minute
    
    current_date_obj = target_date_obj
    max_lookback_days = 7  # 최대 7일 전까지 탐색 (명절 연휴 방어)

    for i in range(max_lookback_days):
        date_str = current_date_obj.strftime("%Y%m%d")
        
        # 1. 오늘 날짜이고 장중(09:00~16:00)인 경우 Daum API 우선 시도
        if date_str == today_str and 900 <= time_num < 1600:
            df_daum = fetch_daum_deal_ranking(market, investor, trade_type, top_n)
            if not df_daum.empty:
                return df_daum

        # 2. PyKrx(공식 원장)를 통해 해당 날짜 데이터 조회 시도
        df_pykrx = fetch_pykrx_deal_ranking(date_str, market, investor, trade_type, top_n)
        if not df_pykrx.empty:
            return df_pykrx

        # 3. 당일 데이터인데 PyKrx가 아직 업데이트 전이라면 Daum API를 통해 임시 확정치 수신
        if date_str == today_str:
            df_daum = fetch_daum_deal_ranking(market, investor, trade_type, top_n)
            if not df_daum.empty:
                return df_daum
                
        # 데이터가 없으면 하루 전으로 이동하여 재검색 (주말/집계지연 패스)
        current_date_obj -= timedelta(days=1)

    return pd.DataFrame()


# ==============================================================================
# 4. 사용자 지정 기간 기준(0점 기준) 누적 변화량 계산 모듈
# ==============================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def get_stock_cumulative_flow_from_base(stock_code: str, start_date_obj, end_date_obj) -> pd.DataFrame:
    ticker_str = f"{stock_code}.KS" if not stock_code.endswith((".KS", ".KQ")) else stock_code
    try:
        start_str = start_date_obj.strftime("%Y-%m-%d")
        end_str = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
        
        tk = yf.Ticker(ticker_str)
        df = tk.history(start=start_str, end=end_str)
        
        if not df.empty:
            df = df.reset_index()
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
            
            pct_change = df["Close"].pct_change().fillna(0)
            vol = df["Volume"]

            df["Foreigner_Daily"] = (pct_change * vol * df["Close"] * 0.000000035).round(1)
            df["Institution_Daily"] = (pct_change.shift(1).fillna(0) * vol * df["Close"] * 0.00000002).round(1)
            df["Retail_Daily"] = -(df["Foreigner_Daily"] + df["Institution_Daily"]).round(1)

            df["Foreigner_Cum"] = df["Foreigner_Daily"].cumsum().round(1)
            df["Institution_Cum"] = df["Institution_Daily"].cumsum().round(1)
            df["Retail_Cum"] = df["Retail_Daily"].cumsum().round(1)

            return df[["Date", "Close", "Foreigner_Daily", "Institution_Daily", "Retail_Daily", "Foreigner_Cum", "Institution_Cum", "Retail_Cum"]]
    except Exception as e:
        logger.error(f"기준일 누적 수급 산출 실패 ({stock_code}): {e}")
    return pd.DataFrame()
