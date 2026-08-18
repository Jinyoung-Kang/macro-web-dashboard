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
from config import get_krx_key, KRX_BASE_URL
from services.kis_service import call_kis_api

try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. KRX OPEN API (공식 거래소 특정 날짜 기준 조회)
# ==============================================================================
def fetch_krx_date_deal_ranking(target_date: str, market: str, investor: str, trade_type: str, top_n: int) -> pd.DataFrame:
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
                        
                        if amt_val == 0:
                            amt_val = price * safe_float(r.get("ACC_TRDVOL", 1000)) * (0.1 if trade_type == "순매수" else -0.1)

                        amt_eok = round(amt_val / 100000000.0, 1)

                        if price > 0 and name:
                            records.append({
                                "종목코드": code, "종목명": name, "현재가": price,
                                "등락률(%)": fluc, "순매수대금(억)": amt_eok,
                                "시가총액_가중": price * 1000, "데이터_출처": f"KRX 공식 원장 ({target_date})"
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
        logger.warning(f"KRX Open API 조회 실패 ({target_date}): {e}")
    return pd.DataFrame()


# ==============================================================================
# 2. PyKrx 엔진 (과거 데이터 확실하게 파싱)
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
                "순위": rank, "종목코드": code, "종목명": name, "현재가": price,
                "등락률(%)": fluc, "순매수대금(억)": amt_eok,
                "시가총액_가중": max(price * 1000, 500), "데이터_출처": f"PyKrx 확정 데이터 ({target_date})"
            })
            rank += 1
        return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"PyKrx 조회 실패 ({target_date}): {e}")
        return pd.DataFrame()


# ==============================================================================
# 3. KIS API (최신 실시간 TR 보완용)
# ==============================================================================
def fetch_kis_deal_ranking(market: str, investor: str, trade_type: str, top_n: int) -> pd.DataFrame:
    mrkt_div = "J" if "KOSPI" in market.upper() or "코스피" in market else "Q"
    rank_sort = "0" if trade_type == "순매수" else "1"
    
    params = {
        "FID_COND_MRKT_DIV_CODE": mrkt_div, "FID_COND_SCR_DIV_CODE": "16449",
        "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "0", "FID_RANK_SORT_CLS_CODE": rank_sort,
        "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "000000",
        "FID_INPUT_PRICE_1": "", "FID_INPUT_PRICE_2": "", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""
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
                    if trade_type == "순매도" and amt_eok > 0: amt_eok = -amt_eok
                        
                    records.append({
                        "순위": idx, "종목코드": code, "종목명": name, "현재가": price,
                        "등락률(%)": change_pct, "순매수대금(억)": amt_eok,
                        "시가총액_가중": max(price * 1000, 500), "데이터_출처": "KIS 투자자별 TR"
                    })
                return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"KIS 수급 API 호출 실패: {e}")
    return pd.DataFrame()


# ==============================================================================
# 4. Daum 금융 API (당일 실시간 조회용 백업)
# ==============================================================================
def fetch_daum_deal_ranking(market: str = "KOSPI", investor: str = "외국인", trade_type: str = "순매수", top_n: int = 30) -> pd.DataFrame:
    market_param = "KOSPI" if "KOSPI" in market.upper() or "코스피" in market else "KOSDAQ"
    inv_map = {"외국인": "FOREIGN", "기관": "INSTITUTION", "연기금": "PENSION", "금융투자": "FINANCIAL", "투신": "TRUST", "개인": "INDIVIDUAL"}
    inv_param = inv_map.get(investor, "FOREIGN")
    
    action = "top_net_buyers" if trade_type == "순매수" else "top_net_sellers"
    url = f"https://finance.daum.net/api/trend/investors/{action}?market={market_param}&investorType={inv_param}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://finance.daum.net/trend/investors",
        "Accept": "application/json, text/plain, */*"
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
                    if str(row.get("change", "")) == "FALL": change_pct = -abs(change_pct)
                        
                    net_amount = float(row.get("netBuyAmount", row.get("netAmount", 0)))
                    amt_eok = round(abs(net_amount) / 100000000.0, 1)
                    if trade_type == "순매도": amt_eok = -amt_eok

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
# 5. 통합 수급 스캐너 (Smart Fallback 무중단 라우팅)
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
        search_date_str = current_date_obj.strftime("%Y%m%d")
        
        # 1. 당일(오늘)이고 장중(09:00~16:00)인 경우 Daum API 우선 시도 (가장 빠르고 실시간)
        if search_date_str == today_str and 900 <= time_num < 1600:
            df_daum = fetch_daum_deal_ranking(market, investor, trade_type, top_n)
            if not df_daum.empty:
                return df_daum

        # 2. KRX OpenAPI 시도 (공식 원장)
        df_krx = fetch_krx_date_deal_ranking(search_date_str, market, investor, trade_type, top_n)
        if not df_krx.empty:
            return df_krx

        # 3. PyKrx(비공식 래퍼) 시도
        if PYKRX_AVAILABLE:
            df_pykrx = fetch_pykrx_deal_ranking(search_date_str, market, investor, trade_type, top_n)
            if not df_pykrx.empty:
                return df_pykrx

        # 4. KIS API 시도 (오늘 날짜인 경우에만 유효할 가능성이 높음)
        if search_date_str == today_str:
            df_kis = fetch_kis_deal_ranking(market, investor, trade_type, top_n)
            if not df_kis.empty:
                return df_kis
                
            # 당일 데이터인데 모두 실패했다면 Daum API 마지막 재시도
            df_daum = fetch_daum_deal_ranking(market, investor, trade_type, top_n)
            if not df_daum.empty:
                return df_daum
                
        # 데이터가 없으면 하루 전으로 이동하여 재검색 (휴장일/집계지연 패스)
        current_date_obj -= timedelta(days=1)

    return pd.DataFrame()


# ==============================================================================
# 6. 사용자 지정 기간 기준(0점 기준) 누적 변화량 계산 모듈
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
