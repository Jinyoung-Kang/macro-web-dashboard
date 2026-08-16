# services/liquidity_service.py
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from services.macro_service import fetch_fred_series, fetch_ticker_data

@st.cache_data(ttl=1800, show_spinner=False)
def get_net_liquidity_data():
    """
    FRED와 Yahoo Finance에서 데이터를 수집하여 연준 순유동성과 증시 지표를 결합합니다.
    - WALCL (Fed Total Assets, $ Millions)
    - WTREGEN (Treasury General Account, $ Millions)
    - RRPONTSYD (Overnight Reverse Repo, $ Billions)
    """
    # 1. FRED 시계열 수집
    walcl_df = fetch_fred_series("WALCL")
    tga_df = fetch_fred_series("WTREGEN")
    rrp_df = fetch_fred_series("RRPONTSYD")

    # 2. 증시 지수 수집
    sp500_df = fetch_ticker_data("^GSPC", period="5y")
    nasdaq_df = fetch_ticker_data("^NDX", period="5y")

    if walcl_df is None or tga_df is None or rrp_df is None:
        return None, None

    # 인덱스 타임존 통일 및 날짜 정규화
    def clean_index(df):
        d = df.copy()
        if d.index.tz is not None:
            d.index = d.index.tz_localize(None)
        d.index = pd.to_datetime(d.index).normalize()
        return d

    walcl = clean_index(walcl_df)
    tga = clean_index(tga_df)
    rrp = clean_index(rrp_df)

    # 3. 데이터프레임 병합 및 단위 통일 ($ Billions 기준)
    merged = pd.DataFrame(index=pd.date_range(start="2020-01-01", end=datetime.now(), freq='D'))
    merged['WALCL_B'] = walcl['WALCL'] / 1000.0  # 백만$ -> 십억$(B)
    merged['TGA_B'] = tga['WTREGEN'] / 1000.0     # 백만$ -> 십억$(B)
    merged['RRP_B'] = rrp['RRPONTSYD']            # 이미 십억$(B) 단위

    # 결측치 전방 보간 (주간 발표 데이터와 일간 데이터 정합성 유지)
    merged = merged.ffill().dropna()

    # 순유동성 연산 (단위: $T, 조 달러)
    merged['Net_Liquidity_B'] = merged['WALCL_B'] - merged['TGA_B'] - merged['RRP_B']
    merged['Net_Liquidity_T'] = merged['Net_Liquidity_B'] / 1000.0
    merged['WALCL_T'] = merged['WALCL_B'] / 1000.0
    merged['TGA_T'] = merged['TGA_B'] / 1000.0
    merged['RRP_T'] = merged['RRP_B'] / 1000.0

    # 증시 데이터 결합
    if sp500_df is not None and not sp500_df.empty:
        sp_clean = clean_index(sp500_df)
        merged['SP500'] = sp_clean['Close']
    if nasdaq_df is not None and not nasdaq_df.empty:
        nq_clean = clean_index(nasdaq_df)
        merged['NASDAQ'] = nq_clean['Close']

    merged = merged.ffill().dropna(subset=['Net_Liquidity_T'])

    # 4. 주요 요약 메트릭 계산
    latest = merged.iloc[-1]
    prev_1w = merged.iloc[-8] if len(merged) >= 8 else merged.iloc[0]
    prev_1m = merged.iloc[-31] if len(merged) >= 31 else merged.iloc[0]

    curr_year = datetime.now().year
    ytd_df = merged[merged.index.year == curr_year]
    prev_ytd = ytd_df.iloc[0] if not ytd_df.empty else merged.iloc[0]

    metrics = {
        "latest_date": merged.index[-1].strftime('%Y-%m-%d'),
        "net_liq_t": latest['Net_Liquidity_T'],
        "net_liq_1w_delta": (latest['Net_Liquidity_T'] - prev_1w['Net_Liquidity_T']) * 1000.0,  # $B 단위 증감
        "net_liq_1m_delta": (latest['Net_Liquidity_T'] - prev_1m['Net_Liquidity_T']) * 1000.0,
        "net_liq_ytd_delta": (latest['Net_Liquidity_T'] - prev_ytd['Net_Liquidity_T']) * 1000.0,
        "walcl_t": latest['WALCL_T'],
        "tga_b": latest['TGA_B'],
        "rrp_b": latest['RRP_B'],
        "sp500": latest.get('SP500', 0),
        "sp500_1m_pct": ((latest['SP500'] - prev_1m['SP500']) / prev_1m['SP500'] * 100.0) if 'SP500' in latest else 0
    }

    return merged, metrics
