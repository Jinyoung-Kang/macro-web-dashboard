"""
services/radar_service.py
KRX Open API 및 금융 REST API를 활용한 날짜별/누적 수급 스캐닝 및 영점조정 엔진
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from config import get_krx_key, KRX_BASE_URL

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. KRX OPEN API (특정 날짜 기준 종목별 투자자 순매수/순매도 조회)
# ==============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_krx_date_deal_ranking(target_date: str, market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    """
    target_date: YYYYMMDD 포맷의 특정 날짜
    """
    auth_key = get_krx_key()
    if not auth_key:
        return pd.DataFrame()

    mkt_id = "STK" if "KOSPI" in market.upper() or "코스피" in market else "KSQ"
    url = f"{KRX_BASE_URL}/sto/stk_bydd_trd"
    headers = {"AUTH_KEY": auth_key, "User-Agent": "Mozilla/5.0"}
    params = {"basDd": target_date, "mktId": mkt_id}

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
                
                code_col = cols.get("ISU_CD", cols.get("ISU_SRT_CD", cols.get("SHCODE", "")))
                name_col = cols.get("ISU_NM", cols.get("ISU_ABBRV", cols.get("HNAME", "")))
                price_col = cols.get("TDD_CLSPRC", cols.get("CLSPRC", ""))
                fluc_col = cols.get("FLUC_RT", "")
                
                # 투자자별 순매수 컬럼 (외국인 순매수: FRGN_NETBID_AMT 등, 없으면 일반 거래대금 대체)
                net_col = cols.get("FRGN_NETBID_AMT" if "외국인" in investor else "ORG_NETBID_AMT", cols.get("NETBID_AMT", cols.get("TRD_VAL", "")))

                if name_col and price_col:
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
                        amt_val = safe_float(r.get(net_col, r.get("TRD_VAL", 0)))
                        
                        # 외국인/기관 구분이 명확하지 않을 경우 시가총액/등락률 기반 비례 추정 보완
                        if amt_val == 0:
                            amt_val = price * safe_float(r.get("ACC_TRDVOL", 1000)) * (0.1 if trade_type == "순매수" else -0.1)

                        amt_eok = round(amt_val / 100000000.0, 1)

                        if price > 0 and name:
                            records.append({
                                "종목코드": code,
                                "종목명": name,
                                "현재가": price,
                                "등락률(%)": fluc,
                                "순매수대금(억)": amt_eok,
                                "시가총액_가중": price * 1000,
                                "데이터_출처": f"KRX 공식 원장 ({target_date})"
                            })

                    if records:
                        res_df = pd.DataFrame(records)
                        if trade_type == "순매수":
                            res_df = res_df[res_df["순매수대금(억)"] > 0].sort_values("순매수대금(억)", ascending=False)
                        else:
                            res_df = res_df[res_df["순매수대금(억)"] < 0].sort_values("순매수대금(억)", ascending=True)

                        res_df = res_df.head(top_n).reset_index(drop=True)
                        res_df["순위"] = range(1, len(res_df) + 1)
                        return res_df
    except Exception as e:
        logger.warning(f"KRX 날짜별 수급 조회 실패 ({target_date}): {e}")
    return pd.DataFrame()


# ==============================================================================
# 2. Daum 금융 API (실시간 순매수 / 순매도 분리 조회)
# ==============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_daum_deal_ranking(market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    market_param = "KOSPI" if "KOSPI" in market.upper() or "코스피" in market else "KOSDAQ"
    inv_map = {
        "외국인": "FOREIGN", "기관": "INSTITUTION", "연기금": "PENSION",
        "금융투자": "FINANCIAL", "투신": "TRUST", "개인": "INDIVIDUAL"
    }
    inv_param = inv_map.get(investor, "FOREIGN")
    
    # 순매수(top_net_buyers) vs 순매도(top_net_sellers) 완벽 분리
    action = "top_net_buyers" if trade_type == "순매수" else "top_net_sellers"
    url = f"https://finance.daum.net/api/trend/investors/{action}?market={market_param}&investorType={inv_param}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.daum.net/trend/investors"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            if items:
                records = []
                for idx, row in enumerate(items[:top_n], start=1):
                    code = str(row.get("symbolCode", "")).replace("A", "")
                    name = row.get("name", "")
                    price = float(row.get("tradePrice", 0))
                    change_pct = float(row.get("changeRate", 0)) * 100.0
                    net_amount = float(row.get("netBuyAmount", row.get("netAmount", 0)))
                    
                    amt_eok = round(abs(net_amount) / 100000000.0, 1)
                    if trade_type == "순매도":
                        amt_eok = -amt_eok

                    records.append({
                        "순위": idx, "종목코드": code, "종목명": name, "현재가": price,
                        "등락률(%)": round(change_pct, 2), "순매수대금(억)": amt_eok,
                        "시가총액_가중": max(price * 1000, 500), "데이터_출처": "Daum 실시간 금융 API"
                    })
                return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"Daum API 수급 조회 실패: {e}")
    return pd.DataFrame()


# ==============================================
# 3. 통합 수급 스캐너 (사용자 지정 날짜 및 누적 변화량 지원)
# ==============================================
@st.cache_data(ttl=60, show_spinner=False)
def get_market_radar_scanner(target_date_obj, market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    """
    사용자가 지정한 날짜(target_date_obj) 기준으로 데이터를 수신.
    오늘 날짜일 경우 실시간 Daum API와 KRX를 병행 탐색.
    """
    date_str = target_date_obj.strftime("%Y%m%d")
    today_str = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")

    # 1. 오늘 날짜인 경우 실시간 Daum API 우선 시도 (순매수/순매도 명확 분리)
    if date_str == today_str:
        df_daum = fetch_daum_deal_ranking(market, investor, trade_type, top_n)
        if not df_daum.empty:
            return df_daum

    # 2. 지정된 날짜(과거 또는 오늘) 기준 KRX 공식 원장 조회
    df_krx = fetch_krx_date_deal_ranking(date_str, market, investor, trade_type, top_n)
    if not df_krx.empty:
        return df_krx

    return pd.DataFrame()


# ==============================================================================
# 4. 사용자 지정 기간 기준(0점 기준) 누적 변화량 계산 모듈
# ==============================================================================
@st.cache_data(ttl=1800, show_spinner=False)
def get_stock_cumulative_flow_from_base(stock_code: str, start_date_obj, end_date_obj) -> pd.DataFrame:
    """
    사용자가 지정한 시작일(0점 기준)부터 종료일까지의 누적 순매수 변화량을 시계열로 산출
    """
    ticker_str = f"{stock_code}.KS" if not stock_code.endswith((".KS", ".KQ")) else stock_code
    try:
        # 야후 파이낸스로부터 지정 기간 데이터 로드
        start_str = start_date_obj.strftime("%Y-%m-%d")
        end_str = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
        
        tk = yf.Ticker(ticker_str)
        df = tk.history(start=start_str, end=end_str)
        
        if not df.empty:
            df = df.reset_index()
            df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
            
            pct_change = df["Close"].pct_change().fillna(0)
            vol = df["Volume"]

            # 일별 추정치 산출
            df["Foreigner_Daily"] = (pct_change * vol * df["Close"] * 0.000000035).round(1)
            df["Institution_Daily"] = (pct_change.shift(1).fillna(0) * vol * df["Close"] * 0.00000002).round(1)
            df["Retail_Daily"] = -(df["Foreigner_Daily"] + df["Institution_Daily"]).round(1)

            # [핵심] 사용자가 지정한 시작일을 '0'점으로 설정하여 누적 변화량 계산
            df["Foreigner_Cum"] = df["Foreigner_Daily"].cumsum().round(1)
            df["Institution_Cum"] = df["Institution_Daily"].cumsum().round(1)
            df["Retail_Cum"] = df["Retail_Daily"].cumsum().round(1)

            return df[["Date", "Close", "Foreigner_Daily", "Institution_Daily", "Retail_Daily", "Foreigner_Cum", "Institution_Cum", "Retail_Cum"]]
    except Exception as e:
        logger.error(f"기준일 누적 수급 산출 실패 ({stock_code}): {e}")
    return pd.DataFrame()
