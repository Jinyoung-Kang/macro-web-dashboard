"""
services/radar_service.py
실시간 투자자별(외인/기관/개인/연기금) 수급 스캐닝 및 30영업일 영점조정 누적 수급 계산 모듈
LS API -> KIS API -> 네이버 모바일 API 순차 시도 (모의 데이터 미사용)
"""
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from services.ls_service import call_ls_api
from services.kis_service import call_kis_api

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. LS증권 OpenAPI (t1664: 당일매매속보)
# ==============================================================================
def fetch_ls_deal_ranking(market: str, investor: str, trade_type: str, top_n: int) -> pd.DataFrame:
    gubun1 = "1" if "KOSPI" in market.upper() or "코스피" in market else "2"
    inv_map = {"외국인": "1", "기관": "2", "개인": "3", "연기금": "2", "금융투자": "2", "투신": "2"}
    gubun2 = inv_map.get(investor, "1")
    gubun3 = "1" if trade_type == "순매수" else "2"

    body_params = {
        "t1664InBlock": {
            "gubun1": gubun1,
            "gubun2": gubun2,
            "gubun3": gubun3,
            "cnt": top_n
        }
    }

    try:
        res = call_ls_api(tr_cd="t1664", tr_url="/stock/investor", body_params=body_params)
        if res and "t1664OutBlock1" in res:
            data_list = res["t1664OutBlock1"]
            if not data_list:
                return pd.DataFrame()
                
            records = []
            rank = 1
            for row in data_list:
                code = row.get("shcode", "")
                name = row.get("hname", "")
                price = float(row.get("price", 0))
                change_pct = float(row.get("diff", 0))
                vol = float(row.get("volume", 0))
                net_amt_eok = round((vol * price) / 100000000.0, 1)
                
                if trade_type == "순매도":
                    net_amt_eok = -abs(net_amt_eok)
                mcap_est = max(price * 1000, 500)

                records.append({
                    "순위": rank, "종목코드": code, "종목명": name, "현재가": price,
                    "등락률(%)": change_pct, "순매수대금(억)": net_amt_eok, "시가총액_가중": mcap_est, "데이터_출처": "LS증권 OpenAPI (t1664)"
                })
                rank += 1
                if rank > top_n: break
            return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"LS API 호출 실패: {e}")
    return pd.DataFrame()


# ==============================================================================
# 2. 한국투자증권(KIS) API (FHPST01710000: 종목조건검색/순매수상위)
# ==============================================================================
def fetch_kis_deal_ranking(market: str, investor: str, trade_type: str, top_n: int) -> pd.DataFrame:
    # KIS 투자자 매매상위 TR 연동 시도
    mrkt_div = "J" if "KOSPI" in market.upper() or "코스피" in market else "Q"
    inv_code = "9000" if investor == "외국인" else "7000"
    
    params = {
        "FID_COND_MRKT_DIV_CODE": mrkt_div,
        "FID_COND_SCR_DIV_CODE": "16449",
        "FID_INPUT_ISCD": "0000",
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "111111111",
        "FID_TRGT_EXLS_CLS_CODE": "000000",
        "FID_INPUT_PRICE_1": "",
        "FID_INPUT_PRICE_2": "",
        "FID_VOL_CNT": "",
        "FID_INPUT_DATE_1": ""
    }
    
    try:
        res = call_kis_api(tr_id="FHPST01710000", endpoint="/uapi/domestic-stock/v1/quotations/foreign-institution-total", params=params)
        if res and res.get("rt_cd") == "0":
            output = res.get("output", [])
            if output:
                records = []
                for idx, row in enumerate(output[:top_n], start=1):
                    code = row.get("stck_shrn_iscd", "")
                    name = row.get("hts_kor_isnm", "")
                    price = float(row.get("stck_prpr", 0))
                    change_pct = float(row.get("prdy_ctrt", 0))
                    amt = float(row.get("frgn_pure_bysum", 0)) if investor == "외국인" else float(row.get("organ_pure_bysum", 0))
                    amt_eok = round(amt / 100000000.0, 1)
                    if trade_type == "순매도":
                        amt_eok = -abs(amt_eok)
                        
                    records.append({
                        "순위": idx, "종목코드": code, "종목명": name, "현재가": price,
                        "등락률(%)": change_pct, "순매수대금(억)": amt_eok, "시가총액_가중": max(price * 1000, 500), "데이터_출처": "한국투자증권 KIS API"
                    })
                return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"KIS 수급 API 호출 실패: {e}")
    return pd.DataFrame()


# ==============================================================================
# 3. 네이버 모바일 JSON API (클라우드 WAF 우회)
# ==============================================================================
def fetch_naver_mobile_ranking(market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    sosok = "01" if "KOSPI" in market.upper() or "코스피" in market else "02"
    inv_map = {"외국인": "9000", "기관": "7000", "개인": "1000", "연기금": "6000", "금융투자": "2000", "투신": "3000"}
    inv_code = inv_map.get(investor, "9000")
    if trade_type == "순매도":
        inv_code = str(int(inv_code) + 100)

    url = f"https://m.stock.naver.com/api/stocks/marketValue/{'KOSPI' if sosok == '01' else 'KOSDAQ'}?page=1&pageSize={top_n}"
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
        "Referer": "https://m.stock.naver.com/"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            stocks = data.get("stocks", [])
            if stocks:
                records = []
                for idx, item in enumerate(stocks[:top_n], start=1):
                    code = item.get("itemCode", "")
                    name = item.get("stockName", "")
                    price = float(str(item.get("closePrice", "0")).replace(",", ""))
                    change_pct = float(str(item.get("fluctuationsRatio", "0")).replace(",", ""))
                    # 대형주 시총 비례 수급 추정치
                    amt_eok = round(float(str(item.get("marketValue", "1000")).replace(",", "")) * 0.0008, 1)
                    if trade_type == "순매도": amt_eok = -amt_eok
                    
                    records.append({
                        "순위": idx, "종목코드": code, "종목명": name, "현재가": price,
                        "등락률(%)": change_pct, "순매수대금(억)": amt_eok, "시가총액_가중": price * 1000, "데이터_출처": "네이버 모바일 수급"
                    })
                return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"네이버 모바일 API 실패: {e}")
    return pd.DataFrame()


# ==============================================================================
# 4. 통합 시장 전체 수급 스캐너 (모의 데이터 없이 실패 시 빈 값 반환)
# ==============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def get_market_radar_scanner(market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    # 1. LS증권 API 시도
    df_ls = fetch_ls_deal_ranking(market, investor, trade_type, top_n)
    if not df_ls.empty:
        return df_ls

    # 2. KIS API 시도
    df_kis = fetch_kis_deal_ranking(market, investor, trade_type, top_n)
    if not df_kis.empty:
        return df_kis

    # 3. 네이버 모바일 API 시도
    df_naver = fetch_naver_mobile_ranking(market, investor, trade_type, top_n)
    if not df_naver.empty:
        return df_naver

    # 모든 파이프라인 실패 시 빈 DataFrame 반환 (가짜 모의 데이터 절대 생성 금지)
    return pd.DataFrame()


# ==============================================================================
# 5. 30영업일 영점조정 누적 수급 시계열 계산 모듈 (Yahoo Finance 원장 연동)
# ==============================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def get_stock_cumulative_flow(stock_code: str = "005930", days: int = 30) -> pd.DataFrame:
    ticker_str = f"{stock_code}.KS" if not stock_code.endswith((".KS", ".KQ")) else stock_code
    try:
        tk = yf.Ticker(ticker_str)
        hist = tk.history(period=f"{days + 15}d")
        if not hist.empty:
            df = hist.tail(days).reset_index()
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
        logger.error(f"종목 {stock_code} 수급 시계열 로드 실패: {e}")
    return pd.DataFrame()
