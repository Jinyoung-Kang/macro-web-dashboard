# services/macro_service.py
import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import io
import re
import os
from config import MACRO_CATEGORIES
from services.ls_service import fetch_kospi_index

@st.cache_data(ttl=30, show_spinner=False)
def fetch_ticker_data(symbol: str, period: str = "5d"):
    try:
        t = yf.Ticker(symbol)
        df = t.history(period=period)
        if df is not None and not df.empty:
            return df.dropna(subset=['Close'])
        return None
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fred_series(series_id: str):
    api_key = None
    try:
        if hasattr(st, "secrets") and "fred" in st.secrets:
            api_key = st.secrets["fred"].get("api_key")
    except Exception:
        pass

    if not api_key:
        api_key = os.environ.get("FRED_API_KEY")

    if api_key:
        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json"
            r = requests.get(url, timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json().get('observations', [])
                if data:
                    df = pd.DataFrame(data)[['date', 'value']]
                    df.rename(columns={'date': 'DATE', 'value': series_id}, inplace=True)
                    df['DATE'] = pd.to_datetime(df['DATE'])
                    df[series_id] = pd.to_numeric(df[series_id], errors='coerce')
                    df = df.dropna().set_index('DATE')
                    if not df.empty:
                        return df
        except Exception:
            pass

    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"https://fred.stlouisfed.org/series/{series_id}"
        }
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        if resp.status_code == 200 and series_id in resp.text:
            df = pd.read_csv(io.StringIO(resp.text))
            df['DATE'] = pd.to_datetime(df['DATE'])
            df[series_id] = pd.to_numeric(df[series_id], errors='coerce')
            df = df.dropna().set_index('DATE')
            if not df.empty:
                return df
    except Exception:
        pass
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fred_cp_spread():
    cp_df = fetch_fred_series("DCPF3M")
    tb_df = fetch_fred_series("DTB3")
    if tb_df is None or tb_df.empty:
        tb_df = fetch_fred_series("DGS3MO")

    if cp_df is not None and tb_df is not None and not cp_df.empty and not tb_df.empty:
        s_cp = cp_df.iloc[:, 0].copy()
        s_tb = tb_df.iloc[:, 0].copy()
        s_cp.index = pd.to_datetime(s_cp.index).normalize()
        s_tb.index = pd.to_datetime(s_tb.index).normalize()
        merged = pd.DataFrame({'CP': s_cp, 'TB': s_tb}).ffill().dropna()
        if not merged.empty and len(merged) >= 2:
            merged['CP_SPREAD'] = merged['CP'] - merged['TB']
            return merged
    return None

def clean_category_title(text: str) -> str:
    return re.sub(r':gray\[(.*)\]', r'\1', text)

def clean_item_briefing(text: str) -> str:
    return re.sub(r'\s*:gray\[.*\]', '', text).strip()

def clean_tag_ui(text: str) -> str:
    return re.sub(r':gray\[(.*)\]', r'\1', text)

def get_collected_macro_data():
    collected_data = {}
    rate_10y_curr, rate_10y_prev = None, None
    rate_2y_curr, rate_2y_prev = None, None

    for cat_name, tickers in MACRO_CATEGORIES.items():
        collected_data[cat_name] = []
        for name, ticker_symbol in tickers.items():
            display_name = name

            # 1. 코스피 지수는 LS증권 실시간 API 우선 호출
            if ticker_symbol == "^KS11":
                ls_kospi = fetch_kospi_index()
                if ls_kospi:
                    curr_price = ls_kospi['price']
                    prev_price = ls_kospi['prev_price']
                    delta = ls_kospi['diff']
                    pct_change = ls_kospi['rate']
                    display_name = "코스피 (KOSPI) :gray[[실시간 LS]]"

                    collected_data[cat_name].append({
                        "name": display_name,
                        "price_str": f"{curr_price:,.2f}",
                        "prev_str": f"{prev_price:,.2f}",
                        "delta_str": f"{delta:+.2f} ({pct_change:+.2f}%)",
                        "status": "ok"
                    })
                    continue

            # 2. 기타 지표 및 코스피 폴백: Yahoo Finance 호출
            hist = fetch_ticker_data(ticker_symbol, period="5d")
            if hist is not None and len(hist) >= 2:
                curr_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                delta = curr_price - prev_price
                pct_change = (delta / prev_price) * 100

                if ticker_symbol == "^TNX":
                    rate_10y_curr, rate_10y_prev = curr_price, prev_price
                elif ticker_symbol == "2YY=F":
                    rate_2y_curr, rate_2y_prev = curr_price, prev_price

                if "JPY/KRW" in name and curr_price < 50:
                    curr_price *= 100
                    prev_price *= 100
                    delta *= 100

                collected_data[cat_name].append({
                    "name": display_name,
                    "price_str": f"{curr_price:,.2f}",
                    "prev_str": f"{prev_price:,.2f}",
                    "delta_str": f"{delta:+.2f} ({pct_change:+.2f}%)",
                    "status": "ok"
                })
            elif hist is not None and len(hist) == 1:
                curr_price = hist['Close'].iloc[-1]
                collected_data[cat_name].append({
                    "name": display_name,
                    "price_str": f"{curr_price:,.2f}",
                    "prev_str": "N/A",
                    "delta_str": "N/A",
                    "status": "single"
                })
            else:
                collected_data[cat_name].append({
                    "name": display_name,
                    "price_str": "N/A",
                    "prev_str": "N/A",
                    "delta_str": "N/A",
                    "status": "fail"
                })

    return collected_data, rate_10y_curr, rate_10y_prev, rate_2y_curr, rate_2y_prev

def generate_briefing_text(collected_data, rate_10y_curr, rate_10y_prev, rate_2y_curr, rate_2y_prev, 
                           vix_hist, move_hist, hy_df, cp_spread_df, stlfsi_df, now_str_kst):
    lines = [
        "📌 [글로벌 매크로 지표 종합 브리핑]",
        f"⏱ 기준 시각: {now_str_kst} (KST)",
        "※ 변동 기준: 직전 거래일 종가 대비 (+, - 수치 및 %)",
        "=" * 55
    ]
    for cat_name, items in collected_data.items():
        lines.append(f"\n{clean_category_title(cat_name)}")
        lines.append("-" * 45)
        for item in items:
            clean_name = clean_item_briefing(item['name'])
            if item["status"] == "ok":
                lines.append(f"• {clean_name:<18} : {item['price_str']:>9} (전일: {item['prev_str']:>9}) | 전일비 {item['delta_str']}")
            else:
                lines.append(f"• {clean_name:<18} : {item['price_str']:>9} | {item['delta_str']}")

    if rate_10y_curr is not None and rate_2y_curr is not None:
        curr_spread = rate_10y_curr - rate_2y_curr
        prev_spread = rate_10y_prev - rate_2y_prev
        spread_delta = curr_spread - prev_spread
        lines.append("\n📊 주요 거시 스프레드 (15분 지연)")
        lines.append("-" * 45)
        lines.append(f"• 10Y-2Y 장단기 금리차    : {curr_spread:>8.2f}%p (전일: {prev_spread:>8.2f}%p) | 전일비 {spread_delta:+.2f}%p")

    lines.append("\n⚡ 신용, 은행권 및 시장 변동성 지표")
    lines.append("-" * 45)
    if vix_hist is not None and len(vix_hist) >= 2:
        v_c, v_p = vix_hist['Close'].iloc[-1], vix_hist['Close'].iloc[-2]
        lines.append(f"• CBOE VIX [15분 지연]    : {v_c:>8.2f} pt (전일: {v_p:>8.2f}) | 전일비 {v_c-v_p:+.2f} ({((v_c-v_p)/v_p)*100:+.2f}%)")
    if move_hist is not None and len(move_hist) >= 2:
        m_c, m_p = move_hist['Close'].iloc[-1], move_hist['Close'].iloc[-2]
        lines.append(f"• ICE BofA MOVE [지연/마감]: {m_c:>8.2f} pt (전일: {m_p:>8.2f}) | 전일비 {m_c-m_p:+.2f} ({((m_c-m_p)/m_p)*100:+.2f}%)")
    if hy_df is not None and len(hy_df) >= 2:
        h_c, h_p = hy_df['BAMLH0A0HYM2'].iloc[-1], hy_df['BAMLH0A0HYM2'].iloc[-2]
        h_dt = hy_df.index[-1].strftime('%m-%d')
        lines.append(f"• 하이일드 OAS [1일지연 {h_dt}]: {h_c:>8.2f}%p (전일: {h_p:>8.2f}%p) | 전일비 {h_c-h_p:+.2f}%p")
    if cp_spread_df is not None and len(cp_spread_df) >= 2:
        cp_c, cp_p = cp_spread_df['CP_SPREAD'].iloc[-1], cp_spread_df['CP_SPREAD'].iloc[-2]
        cp_dt = cp_spread_df.index[-1].strftime('%m-%d')
        lines.append(f"• 3M 금융 CP 스프레드 [1일지연 {cp_dt}]: {cp_c:>6.2f}%p (전일: {cp_p:>6.2f}%p) | 전일비 {cp_c-cp_p:+.2f}%p")
    if stlfsi_df is not None and len(stlfsi_df) >= 2:
        s_c, s_p = stlfsi_df['STLFSI4'].iloc[-1], stlfsi_df['STLFSI4'].iloc[-2]
        s_dt = stlfsi_df.index[-1].strftime('%m-%d')
        lines.append(f"• STLFSI4 스트레스지수 [주간 {s_dt}]: {s_c:>+6.2f} pt (전주: {s_p:>+6.2f} pt) | 전주비 {s_c-s_p:+.2f} pt")

    lines.append("\n" + "=" * 55)
    return "\n".join(lines)
