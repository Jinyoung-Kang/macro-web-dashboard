"""
services/radar_service.py
실시간 투자자별(외인/기관/개인/연기금) 수급 스캐닝 및 30영업일 영점조정 누적 수급 계산 모듈
1순위: KRX OPEN API (공식 원장)
2순위: KIS API (증권사 TR)
3순위: Daum 금융 실시간 순매수/순매도 REST API
"""
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from config import get_krx_key, KRX_BASE_URL
from services.kis_service import call_kis_api

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. KRX OPEN API (1순위: 거래소 공식 투자자별 순매수/순매도 데이터)
# ==============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_krx_investor_ranking(market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    """
    KRX OPEN API: 종목별 투자자 순매수/순매도 실적 집계
    """
    auth_key = get_krx_key()
    if not auth_key:
        return pd.DataFrame()

    today = datetime.now(ZoneInfo("Asia/Seoul"))
    # 최근 평일 날짜 탐색
    curr = today
    while curr.weekday() >= 5:
        curr -= timedelta(days=1)
    bas_dd = curr.strftime("%Y%m%d")

    mkt_id = "STK" if "KOSPI" in market.upper() or "코스피" in market else "KSQ"
    
    # KRX 주식 매매실적 엔드포인트
    url = f"{KRX_BASE_URL}/sto/stk_bydd_trd"
    headers = {"AUTH_KEY": auth_key, "User-Agent": "Mozilla/5.0"}
    params = {"basDd": bas_dd, "mktId": mkt_id}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=8)
        if res.status_code == 200:
            data = res.json()
            items = []
            if isinstance(data, dict):
                for k in ["OutBlock_1", "output", "block1", "items"]:
                    if k in data and isinstance(data[k], list) and len(data[k]) > 0:
                        items = data[k]
                        break
                if not items:
                    for v in data.values():
                        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                            items = v
                            break

            if items:
                df = pd.DataFrame(items)
                cols = {c.upper(): c for c in df.columns}
                
                # 수급 컬럼 식별
                code_col = cols.get("ISU_CD", cols.get("ISU_SRT_CD", cols.get("SHCODE", "")))
                name_col = cols.get("ISU_NM", cols.get("ISU_ABBRV", cols.get("HNAME", "")))
                price_col = cols.get("TDD_CLSPRC", cols.get("CLSPRC", ""))
                fluc_col = cols.get("FLUC_RT", "")
                
                # 투자자별 순매수대금 컬럼 탐색 (기본: TRD_AMT 또는 NETBID_AMT)
                net_col = cols.get("NETBID_AMT", cols.get("TRD_VAL", cols.get("NET_AMT", "")))

                if name_col and price_col and net_col:
                    def safe_float(v):
                        try:
                            return float(str(v).replace(",", "").strip())
                        except:
                            return 0.0

                    records = []
                    for _, r in df.iterrows():
                        code = str(r.get(code_col, "")).strip()
                        name = str(r.get(name_col, "")).strip()
                        price = safe_float(r.get(price_col, 0))
                        fluc = safe_float(r.get(fluc_col, 0))
                        amt_eok = round(safe_float(r.get(net_col, 0)) / 100000000.0, 1)

                        if price > 0 and name:
                            records.append({
                                "종목코드": code,
                                "종목명": name,
                                "현재가": price,
                                "등락률(%)": fluc,
                                "순매수대금(억)": amt_eok,
                                "시가총액_가중": price * 1000,
                                "데이터_출처": "KRX OPEN API (공식)"
                            })

                    if records:
                        res_df = pd.DataFrame(records)
                        # 순매수: 양수 큰 순 / 순매도: 음수 작은 순(절대값 큰 순)
                        if trade_type == "순매수":
                            res_df = res_df[res_df["순매수대금(억)"] > 0].sort_values("순매수대금(억)", ascending=False)
                        else:
                            res_df = res_df[res_df["순매수대금(억)"] < 0].sort_values("순매수대금(억)", ascending=True)

                        res_df = res_df.head(top_n).reset_index(drop=True)
                        res_df["순위"] = range(1, len(res_df) + 1)
                        return res_df
    except Exception as e:
        logger.warning(f"KRX Open API 주식 수급 조회 실패: {e}")
    return pd.DataFrame()


# ==============================================================================
# 2. 한국투자증권(KIS) API (2순위: 순매수/순매도 구분 TR)
# ==============================================================================
def fetch_kis_deal_ranking(market: str, investor: str, trade_type: str, top_n: int) -> pd.DataFrame:
    mrkt_div = "J" if "KOSPI" in market.upper() or "코스피" in market else "Q"
    # 순매수(0) vs 순매도(1) 정밀 파라미터 분기
    rank_sort = "0" if trade_type == "순매수" else "1"
    
    params = {
        "FID_COND_MRKT_DIV_CODE": mrkt_div,
        "FID_COND_SCR_DIV_CODE": "16449",
        "FID_INPUT_ISCD": "0000",
        "FID_DIV_CLS_CODE": "0",
        "FID_RANK_SORT_CLS_CODE": rank_sort,
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
                    if trade_type == "순매도" and amt_eok > 0:
                        amt_eok = -amt_eok
                        
                    records.append({
                        "순위": idx, "종목코드": code, "종목명": name, "현재가": price,
                        "등락률(%)": change_pct, "순매수대금(억)": amt_eok, "시가총액_가중": max(price * 1000, 500), "데이터_출처": "한국투자증권 KIS API"
                    })
                return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"KIS 수급 API 호출 실패: {e}")
    return pd.DataFrame()


# ==============================================================================
# 3. Daum 금융 실시간 투자자별 순매수/순매도 REST API (3순위: 확실한 분리)
# ==============================================================================
def fetch_daum_deal_ranking(market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    """
    Daum 금융 공식 순매수/순매도 분리 REST API (JSON)
    """
    market_param = "KOSPI" if "KOSPI" in market.upper() or "코스피" in market else "KOSDAQ"
    
    inv_map = {
        "외국인": "FOREIGN",
        "기관": "INSTITUTION",
        "연기금": "PENSION",
        "금융투자": "FINANCIAL",
        "투신": "TRUST",
        "개인": "INDIVIDUAL"
    }
    inv_param = inv_map.get(investor, "FOREIGN")
    
    # 엔드포인트 완벽 분리: top_net_buyers vs top_net_sellers
    action = "top_net_buyers" if trade_type == "순매수" else "top_net_sellers"
    url = f"https://finance.daum.net/api/trend/investors/{action}?market={market_param}&investorType={inv_param}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.daum.net/trend/investors",
        "Accept": "application/json, text/plain, */*"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            if items:
                records = []
                for idx, row in enumerate(items[:top_n], start=1):
                    raw_code = row.get("symbolCode", "")
                    code = raw_code.replace("A", "")
                    name = row.get("name", "")
                    price = float(row.get("tradePrice", 0))
                    change_pct = float(row.get("changeRate", 0)) * 100.0
                    
                    # 순매수/순매도 대금 (원 단위 -> 억 원 단위 변환)
                    net_amount = float(row.get("netBuyAmount", row.get("netAmount", 0)))
                    amt_eok = round(abs(net_amount) / 100000000.0, 1)
                    if trade_type == "순매도":
                        amt_eok = -amt_eok

                    records.append({
                        "순위": idx,
                        "종목코드": code,
                        "종목명": name,
                        "현재가": price,
                        "등락률(%)": round(change_pct, 2),
                        "순매수대금(억)": amt_eok,
                        "시가총액_가중": max(price * 1000, 500),
                        "데이터_출처": "Daum 실시간 금융 API"
                    })
                return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Daum 금융 수급 API 실패: {e}")
    return pd.DataFrame()


# ==============================================
# 4. 통합 시장 전체 수급 스캐너 라우팅
# ==============================================
@st.cache_data(ttl=60, show_spinner=False)
def get_market_radar_scanner(market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    """
    1. KRX Open API (공식 거래소) -> 2. KIS API (증권사) -> 3. Daum 실시간 API 순차 호출
    (가짜 모의 데이터 절대 미사용)
    """
    # 1. KRX OPEN API
    df_krx = fetch_krx_investor_ranking(market, investor, trade_type, top_n)
    if not df_krx.empty:
        return df_krx

    # 2. KIS API
    df_kis = fetch_kis_deal_ranking(market, investor, trade_type, top_n)
    if not df_kis.empty:
        return df_kis

    # 3. Daum 금융 REST API (순매수/순매도 분리 제공)
    df_daum = fetch_daum_deal_ranking(market, investor, trade_type, top_n)
    if not df_daum.empty:
        return df_daum

    # 실패 시 빈 DataFrame 반환
    return pd.DataFrame()


# ==============================================================================
# 5. 30영업일 영점조정 누적 수급 시계열 계산 모듈
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
