import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import requests
import io
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Global Macro & 13F Dashboard", layout="wide")

# ==========================================
# 0. 간이 인증 (비밀번호 잠금) 시스템
# ==========================================
def check_password():
    """올바른 비밀번호가 입력되었는지 검증하고 세션 상태를 유지합니다."""
    correct_password = st.secrets.get("auth", {}).get("password", "admin1234@")

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("### 🔒 Global Macro & 13F Dashboard")
            st.caption("인가된 사용자만 접근할 수 있습니다.")
            pwd_input = st.text_input("접속 비밀번호를 입력하세요", type="password")
            
            if st.button("로그인", type="primary", use_container_width=True):
                if pwd_input == correct_password:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("비밀번호가 올바르지 않습니다.")
        return False
    return True

if not check_password():
    st.stop()

# ==========================================
# 1. 사이드바 네비게이션 & 갱신 설정
# ==========================================
st.sidebar.header("🧭 대시보드 메뉴")
menu_selection = st.sidebar.radio(
    "이동할 메뉴를 선택하세요",
    ["📊 거시경제 매크로 지표", "📑 기관 13F 포트폴리오 분석"],
    index=0
)

st.sidebar.divider()
st.sidebar.header("⚙️ 갱신 설정")
auto_refresh_enabled = st.sidebar.checkbox("실시간 자동 새로고침 활성화", value=False)
refresh_interval = st.sidebar.selectbox(
    "새로고침 주기",
    options=[30, 60, 120, 300],
    index=2,
    format_func=lambda x: f"{x}초 간격"
)

if auto_refresh_enabled:
    st_autorefresh(interval=refresh_interval * 1000, key="datarefresh")

st.sidebar.divider()
if st.sidebar.button("로그아웃", use_container_width=True):
    st.session_state.authenticated = False
    st.rerun()

# ==========================================
# 2. 공통 시간대(KST) 및 헤더 시계
# ==========================================
kst_tz = ZoneInfo("Asia/Seoul")
now_kst = datetime.now(kst_tz)
now_str_kst = now_kst.strftime('%Y-%m-%d %H:%M:%S')

live_clock_html = """
<div style="
    display: flex; 
    flex-wrap: wrap;
    gap: 15px; 
    align-items: center; 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: rgba(255, 255, 255, 0.04); 
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px; 
    padding: 8px 14px; 
    color: #e0e0e0;
    font-size: 13.5px;
    margin-bottom: 5px;
">
    <div style="display: flex; align-items: center; gap: 6px;">
        <span>🇰🇷 <b>한국 (KST)</b></span>
        <span id="live-kst" style="font-family: monospace; font-weight: bold; color: #4da3ff; font-size: 14.5px;">--:--:--</span>
    </div>
    <div style="color: rgba(255, 255, 255, 0.25);">|</div>
    <div style="display: flex; align-items: center; gap: 6px;">
        <span>🗽 <b>뉴욕 (EST/EDT)</b></span>
        <span id="live-ny" style="font-family: monospace; font-weight: bold; color: #ffb74d; font-size: 14.5px;">--:--:--</span>
    </div>
</div>
<script>
function updateLiveClocks() {
    const now = new Date();
    const optKST = { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
    const optNY = { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
    
    document.getElementById('live-kst').innerText = new Intl.DateTimeFormat('ko-KR', optKST).format(now);
    document.getElementById('live-ny').innerText = new Intl.DateTimeFormat('ko-KR', optNY).format(now);
}
updateLiveClocks();
setInterval(updateLiveClocks, 1000);
</script>
"""

# ==============================================================================
# MENU 1: 거시경제 매크로 대시보드
# ==============================================================================
if menu_selection == "📊 거시경제 매크로 지표":
    MACRO_CATEGORIES = {
        "💵 통화 및 환율 :gray[(실시간)]": {
            "달러 인덱스 (DXY) :gray[[실시간]]": "DX-Y.NYB",
            "원/달러 (USD/KRW) :gray[[실시간]]": "KRW=X",
            "달러/엔 (USD/JPY) :gray[[실시간]]": "JPY=X",
            "엔/원 100엔당 (JPY/KRW) :gray[[실시간]]": "JPYKRW=X"
        },
        "🏛️ 미국 국채 금리 :gray[(15분 지연)]": {
            "미국채 2년물 금리(%) :gray[[15분 지연]]": "2YY=F",
            "미국채 10년물 금리(%) :gray[[15분 지연]]": "^TNX",
            "미국채 30년물 금리(%) :gray[[15분 지연]]": "^TYX"
        },
        "🛢️ 원자재 :gray[(15분 지연)]": {
            "WTI 원유 ($) :gray[[15분 지연]]": "CL=F",
            "브렌트유 ($) :gray[[15분 지연]]": "BZ=F",
            "금 선물 ($) :gray[[15분 지연]]": "GC=F"
        },
        "🇺🇸 미국 주가지수 및 선물 :gray[(15분 지연)]": {
            "S&P 500 :gray[[15분 지연]]": "^GSPC",
            "S&P 500 선물 (ES) :gray[[15분 지연]]": "ES=F",
            "나스닥 100 :gray[[15분 지연]]": "^NDX",
            "나스닥 선물 (NQ) :gray[[15분 지연]]": "NQ=F"
        },
        "🌏 아시아 주요 주가지수 :gray[(15분 지연)]": {
            "코스피 (KOSPI) :gray[[15분 지연]]": "^KS11",
            "닛케이 225 (Nikkei) :gray[[15분 지연]]": "^N225",
            "상하이 종합 (SSE) :gray[[15분 지연]]": "000001.SS",
            "항셍 지수 (HSI) :gray[[15분 지연]]": "^HSI"
        }
    }

    @st.cache_data(ttl=30, show_spinner=False)
    def fetch_ticker_data(symbol, period="5d"):
        try:
            t = yf.Ticker(symbol)
            df = t.history(period=period)
            if df is not None and not df.empty:
                return df.dropna(subset=['Close'])
            return None
        except Exception:
            return None

    @st.cache_data(ttl=3600, show_spinner=False)
    def fetch_fred_hy_spread():
        api_key = st.secrets.get("fred", {}).get("api_key", None)
        if api_key:
            try:
                url = f"https://api.stlouisfed.org/fred/series/observations?series_id=BAMLH0A0HYM2&api_key={api_key}&file_type=json"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json().get('observations', [])
                    if data:
                        df = pd.DataFrame(data)[['date', 'value']]
                        df.rename(columns={'date': 'DATE', 'value': 'BAMLH0A0HYM2'}, inplace=True)
                        df['DATE'] = pd.to_datetime(df['DATE'])
                        df['BAMLH0A0HYM2'] = pd.to_numeric(df['BAMLH0A0HYM2'], errors='coerce')
                        df = df.dropna().set_index('DATE')
                        if not df.empty:
                            return df
            except Exception:
                pass

        try:
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"
            }
            session = requests.Session()
            resp = session.get(url, headers=headers, timeout=10)
            if resp.status_code == 200 and "BAMLH0A0HYM2" in resp.text:
                df = pd.read_csv(io.StringIO(resp.text))
                df['DATE'] = pd.to_datetime(df['DATE'])
                df['BAMLH0A0HYM2'] = pd.to_numeric(df['BAMLH0A0HYM2'], errors='coerce')
                df = df.dropna().set_index('DATE')
                if not df.empty:
                    return df
        except Exception:
            pass
        return None

    collected_data = {}
    rate_10y_curr, rate_10y_prev = None, None
    rate_2y_curr, rate_2y_prev = None, None

    for cat_name, tickers in MACRO_CATEGORIES.items():
        collected_data[cat_name] = []
        for name, ticker_symbol in tickers.items():
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
                    "name": name,
                    "price_str": f"{curr_price:,.2f}",
                    "prev_str": f"{prev_price:,.2f}",
                    "delta_str": f"{delta:+.2f} ({pct_change:+.2f}%)",
                    "status": "ok"
                })
            elif hist is not None and len(hist) == 1:
                curr_price = hist['Close'].iloc[-1]
                collected_data[cat_name].append({
                    "name": name,
                    "price_str": f"{curr_price:,.2f}",
                    "prev_str": "N/A",
                    "delta_str": "N/A",
                    "status": "single"
                })
            else:
                collected_data[cat_name].append({"name": name, "price_str": "N/A", "prev_str": "N/A", "delta_str": "N/A", "status": "fail"})

    vix_hist = fetch_ticker_data("^VIX", period="1mo")
    move_hist = fetch_ticker_data("^MOVE", period="1mo")
    hy_df = fetch_fred_hy_spread()

    def clean_category_title(text: str) -> str:
        return re.sub(r':gray\[(.*)\]', r'\1', text)

    def clean_item_briefing(text: str) -> str:
        return re.sub(r'\s*:gray\[.*\]', '', text).strip()

    def clean_tag_ui(text: str) -> str:
        return re.sub(r':gray\[(.*)\]', r'\1', text)

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

    lines.append("\n⚡ 신용 및 시장 변동성 지표")
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

    lines.append("\n" + "=" * 55)
    report_text = "\n".join(lines)

    header_left, header_right = st.columns([3, 1])
    with header_left:
        st.title("📊 Global Macro Dashboard")
        components.html(live_clock_html, height=45)
        st.caption(f"최근 데이터 갱신 시각: {now_str_kst} (KST) | 갱신 주기: {refresh_interval}초")

    with header_right:
        st.write("")
        with st.popover("📋 텍스트 브리핑 보기 / 복사", use_container_width=True):
            st.markdown("**현재 시세 텍스트 종합 브리핑**")
            st.caption("우측 상단 복사 아이콘(📋)을 눌러 즉시 복사하세요.")
            st.code(report_text, language="text")

    st.divider()

    st.subheader("실시간/최근 시세 요약")
    st.info("💡 **변동 수치(+/-) 기준:** 각 지표 하단의 수치는 **직전 거래일 공식 종가(Previous Close) 대비 등락폭과 등락률(%)**입니다.", icon="ℹ️")

    for cat_name, items in collected_data.items():
        st.markdown(f"#### {cat_name}")
        cols = st.columns(len(items))
        for idx, item in enumerate(items):
            if item["status"] == "ok":
                cols[idx].metric(
                    label=item["name"],
                    value=item["price_str"],
                    delta=item["delta_str"],
                    help=f"직전 거래일 종가: {item['prev_str']}"
                )
                cols[idx].caption(f"전일 종가: `{item['prev_str']}`")
            elif item["status"] == "single":
                cols[idx].metric(label=item["name"], value=item["price_str"])
                cols[idx].caption("전일 데이터 없음")
            else:
                cols[idx].metric(label=item["name"], value="로드 실패")

    st.divider()

    # 장단기 금리차
    st.subheader("📊 10Y-2Y 장단기 금리차의 핵심 해석 모델")
    st.markdown("미국채 10년물(장기 금리)에서 2년물(단기 금리)을 뺀 값은 채권 시장에서 가장 주목하는 **경기 선행 지표**입니다.")
    st.code("스프레드(Spread) = 장기 금리(미래 경기 전망) - 단기 금리(현재 통화 정책)", language="text")

    if rate_10y_curr is not None and rate_2y_curr is not None:
        curr_spread = rate_10y_curr - rate_2y_curr
        prev_spread = rate_10y_prev - rate_2y_prev
        spread_delta = curr_spread - prev_spread
        
        if curr_spread < 0:
            status_title = "🚨 역전 (Inversion)"
            status_color = "red"
            status_desc = "현재 인플레이션을 잡기 위해 금리를 급격히 올렸으나, 미래 경기는 침체될 것으로 시장이 확신하고 있습니다. **(역사적으로 1~2년 내 경기 침체 Recession 도래)**"
        elif 0 <= curr_spread <= 0.2:
            status_title = "⚠️ 평탄화 (Flattening)"
            status_color = "orange"
            status_desc = "미래 경기 성장이 둔화될 것이라는 우려가 커지기 시작했습니다. **(경기 정점 통과 및 둔화 신호)**"
        else:
            status_title = "✅ 정상 (Normal)"
            status_color = "green"
            status_desc = "장기 미래의 불확실성(프리미엄)으로 인해 장기 금리가 더 높은 정상 상태입니다. **(경제의 점진적인 성장 및 확장)**"

        sc1, sc2 = st.columns([1, 2])
        with sc1:
            st.metric(
                label="현재 10Y - 2Y 스프레드 :gray[[15분 지연]]",
                value=f"{curr_spread:+.2f} %p",
                delta=f"{spread_delta:+.2f} %p (전일비)"
            )
            st.caption(f"10Y: `{rate_10y_curr:.2f}%` | 2Y: `{rate_2y_curr:.2f}%` (전일: `{prev_spread:+.2f}%p`)")
        with sc2:
            st.markdown(f"**현재 시장 진단:** :{status_color}[{status_title}]")
            st.write(status_desc)

    spread_period = st.selectbox("금리차 추이 기간 선택", ["6mo", "1y", "2y", "5y", "max"], index=2, key="spread_period_select")
    df_10y = fetch_ticker_data("^TNX", period=spread_period)
    df_2y = fetch_ticker_data("2YY=F", period=spread_period)

    if df_10y is not None and df_2y is not None and not df_10y.empty and not df_2y.empty:
        s_10y = df_10y['Close'].copy()
        s_2y = df_2y['Close'].copy()
        if s_10y.index.tz is not None:
            s_10y.index = s_10y.index.tz_localize(None)
        if s_2y.index.tz is not None:
            s_2y.index = s_2y.index.tz_localize(None)
        s_10y.index = s_10y.index.normalize()
        s_2y.index = s_2y.index.normalize()

        df_spread = pd.DataFrame({'10Y': s_10y, '2Y': s_2y}).ffill().dropna()
        df_spread['Spread'] = df_spread['10Y'] - df_spread['2Y']

        if not df_spread.empty:
            fig_spread = go.Figure()
            fig_spread.add_trace(go.Scatter(
                x=df_spread.index, y=df_spread['Spread'], mode='lines',
                name='10Y-2Y 스프레드 (%p)', line=dict(color='#E02424', width=2),
                fill='tozeroy', fillcolor='rgba(224, 36, 36, 0.15)'
            ))
            fig_spread.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.8, annotation_text="기준선 (0%p 역전 경계)")
            fig_spread.update_layout(
                title=f"미국채 10Y - 2Y 스프레드 과거 추이 ({spread_period})",
                xaxis_title="일자", yaxis_title="스프레드 (%p)", hovermode="x unified",
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_spread, use_container_width=True)

    st.divider()

    # 변동성 & 신용
    st.subheader("⚡ 신용 리스크 및 시장 변동성 (Credit & Volatility)")
    col_v, col_m, col_h = st.columns(3)

    with col_v:
        if vix_hist is not None and len(vix_hist) >= 2:
            v_curr = vix_hist['Close'].iloc[-1]
            v_prev = vix_hist['Close'].iloc[-2]
            v_delta = v_curr - v_prev
            v_pct = (v_delta / v_prev) * 100
            v_status, v_color = ("안도", "green") if v_curr < 15 else ("정상", "blue") if v_curr <= 20 else ("경계", "orange") if v_curr <= 30 else ("공포", "red")
            st.metric("CBOE VIX (주식 변동성) :gray[[15분 지연]]", f"{v_curr:.2f}", f"{v_delta:+.2f} ({v_pct:+.2f}%)")
            st.markdown(f"상태: :{v_color}[**{v_status}**] (전일: `{v_prev:.2f}`)")
        else:
            st.metric("CBOE VIX", "로드 실패")

    with col_m:
        if move_hist is not None and len(move_hist) >= 2:
            m_curr = move_hist['Close'].iloc[-1]
            m_prev = move_hist['Close'].iloc[-2]
            m_delta = m_curr - m_prev
            m_pct = (m_delta / m_prev) * 100
            m_status, m_color = ("안정", "green") if m_curr < 80 else ("정상", "blue") if m_curr <= 120 else ("경계", "orange") if m_curr <= 140 else ("위기", "red")
            st.metric("ICE BofA MOVE (채권 변동성) :gray[[지연/마감]]", f"{m_curr:.2f}", f"{m_delta:+.2f} ({m_pct:+.2f}%)")
            st.markdown(f"상태: :{m_color}[**{m_status}**] (전일: `{m_prev:.2f}`)")
        else:
            st.metric("ICE BofA MOVE", "로드 실패")

    with col_h:
        if hy_df is not None and len(hy_df) >= 2:
            h_curr = hy_df['BAMLH0A0HYM2'].iloc[-1]
            h_prev = hy_df['BAMLH0A0HYM2'].iloc[-2]
            h_date = hy_df.index[-1].strftime('%m-%d')
            h_delta = h_curr - h_prev
            h_status, h_color = ("완화", "green") if h_curr < 3.5 else ("정상", "blue") if h_curr <= 5.0 else ("경계", "orange") if h_curr <= 7.0 else ("위기", "red")
            st.metric(f"하이일드 스프레드 (HY OAS) :gray[[1일 지연 {h_date} EOD]]", f"{h_curr:.2f} %p", f"{h_delta:+.2f} %p")
            st.markdown(f"상태: :{h_color}[**{h_status}**] (직전: `{h_prev:.2f}%p`)")
        else:
            st.metric("하이일드 스프레드", "로드 실패")

    st.divider()

    # 단독 및 다중 차트
    st.subheader("지표별 기간별 단독 차트")
    ALL_TICKERS = {}
    for cat in MACRO_CATEGORIES.values():
        ALL_TICKERS.update(cat)

    c1, c2 = st.columns([2, 1])
    with c1:
        selected_name = st.selectbox("조회할 단일 지표 선택", list(ALL_TICKERS.keys()), format_func=clean_tag_ui)
    with c2:
        period = st.selectbox("조회 기간", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=3, key="single_period")

    selected_symbol = ALL_TICKERS[selected_name]
    df = fetch_ticker_data(selected_symbol, period=period)
    if df is not None and not df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name=clean_tag_ui(selected_name), line=dict(color='#0066FF', width=2)))
        fig.update_layout(title=f"{clean_tag_ui(selected_name)} ({selected_symbol}) 상세 차트", xaxis_title="일자", yaxis_title="수치/가격", hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

# ==============================================================================
# MENU 2: 기관 13F 포트폴리오 분석 (신규 기능)
# ==============================================================================
elif menu_selection == "📑 기관 13F 포트폴리오 분석":
    
    st.title("📑 대가들의 포트폴리오 (13F Holdings Analysis)")
    components.html(live_clock_html, height=45)
    st.caption("SEC EDGAR 공식 공시 데이터 기반 미국 주요 기관 투자자 포트폴리오 분석 & Gemini Pro AI 리포트")
    
    INSTITUTIONS = {
        "🇰🇷 국민연금 (National Pension Service)": {"cik": "0001608046", "desc": "글로벌 자산배분 및 미국 대형 우량주 중심 장기 투자"},
        "🇺🇸 버크셔 해서웨이 (Berkshire Hathaway)": {"cik": "0001067983", "desc": "워런 버핏의 가치투자 포트폴리오, 핵심 우량주 집중"},
        "🇺🇸 듀케인 패밀리 오피스 (Duquesne Family Office)": {"cik": "0001536411", "desc": "스탠리 드럭켄밀러의 탑다운 매크로 & AI 성장주 집중 베팅"},
        "🇺🇸 브리지워터 어소시에이츠 (Bridgewater)": {"cik": "0001350694", "desc": "레이 달리오 설립, 올웨더 및 글로벌 매크로 헤지펀드"},
        "🇺🇸 사이언 자산운용 (Scion Asset Management)": {"cik": "0001649339", "desc": "마이클 버리의 역발상 딥밸류 및 숏(풋옵션)/롱 전략"},
        "🇺🇸 블랙록 (BlackRock)": {"cik": "0002012383", "desc": "세계 최대 자산운용사, 광범위한 글로벌 자산군"},
        "🇺🇸 뱅가드 (Vanguard Group)": {"cik": "0000102909", "desc": "글로벌 인덱스 펀드의 거두, 시장 전체를 아우르는 포트폴리오"}
    }

    selected_inst_name = st.selectbox(
        "분석할 기관을 선택하세요",
        options=list(INSTITUTIONS.keys()),
        index=1  # 기본값: 버크셔 해서웨이
    )
    
    inst_info = INSTITUTIONS[selected_inst_name]
    st.info(f"💡 **기관 소개:** {inst_info['desc']} (SEC CIK: `{inst_info['cik']}`)", icon="ℹ️")

    # SEC EDGAR 13F 크롤링 및 파싱 함수
    @st.cache_data(ttl=86400, show_spinner=False)
    def fetch_sec_13f(cik: str):
        user_agent = st.secrets.get("sec", {}).get("user_agent", "MacroDashboard user@gmail.com")
        headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        
        try:
            # 1. 제출 내역 조회
            sub_url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            r = requests.get(sub_url, headers=headers, timeout=15)
            if r.status_code != 200:
                return None, f"SEC API 접근 실패 (상태 코드: {r.status_code})"
            
            sub_data = r.json()
            recent = sub_data.get('filings', {}).get('recent', {})
            forms = recent.get('form', [])
            
            # 최신 13F-HR 공시 찾기
            f_idx = None
            for idx, f in enumerate(forms):
                if f in ['13F-HR', '13F-HR/A']:
                    f_idx = idx
                    break
            
            if f_idx is None:
                return None, "최근 13F-HR 보고서를 찾을 수 없습니다."
            
            accession_number = recent['accessionNumber'][f_idx]
            report_date = recent['reportDate'][f_idx]
            filing_date = recent['filingDate'][f_idx]
            acc_clean = accession_number.replace('-', '')
            
            # 2. 13F Information Table XML 파일명 탐색
            dir_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/index.json"
            dir_resp = requests.get(dir_url, headers=headers, timeout=15)
            
            xml_filename = None
            if dir_resp.status_code == 200:
                dir_data = dir_resp.json()
                for item in dir_data.get('directory', {}).get('item', []):
                    name = item.get('name', '')
                    if name.endswith('.xml') and not name.startswith('primary') and '13f' in name.lower():
                        xml_filename = name
                        break
                if not xml_filename:
                    for item in dir_data.get('directory', {}).get('item', []):
                        name = item.get('name', '')
                        if name.endswith('.xml') and not name.startswith('primary'):
                            xml_filename = name
                            break
            
            # index.json 실패 시 index.htm 파싱
            if not xml_filename:
                htm_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession_number}-index.htm"
                htm_resp = requests.get(htm_url, headers=headers, timeout=15)
                if htm_resp.status_code == 200:
                    soup = BeautifulSoup(htm_resp.text, 'html.parser')
                    for row in soup.find_all('tr'):
                        text = row.get_text()
                        if 'INFORMATION TABLE' in text and '.xml' in text:
                            for link in row.find_all('a'):
                                if link.get('href', '').endswith('.xml'):
                                    xml_filename = link.get('href').split('/')[-1]
                                    break

            if not xml_filename:
                return None, "13F Information Table XML 파일을 찾을 수 없습니다."

            # 3. XML 다운로드 및 파싱
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_filename}"
            xml_resp = requests.get(xml_url, headers=headers, timeout=25)
            if xml_resp.status_code != 200:
                return None, f"XML 파일 다운로드 실패 (상태 코드: {xml_resp.status_code})"

            root = ET.fromstring(xml_resp.content)
            
            holdings = []
            for child in root:
                # 네임스페이스 제거 태그 매칭
                tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag_name.lower() in ['infotable', 'informationtable']:
                    row = {}
                    for elem in child:
                        t = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                        if t == 'nameOfIssuer':
                            row['name'] = elem.text
                        elif t == 'titleOfClass':
                            row['class'] = elem.text
                        elif t == 'cusip':
                            row['cusip'] = elem.text
                        elif t == 'value':
                            try:
                                row['value'] = float(elem.text)
                            except:
                                row['value'] = 0.0
                        elif t == 'shrsOrPrnAmt':
                            for sub in elem:
                                subt = sub.tag.split('}')[-1] if '}' in sub.tag else sub.tag
                                if subt == 'sshPrnamt':
                                    try:
                                        row['shares'] = float(sub.text)
                                    except:
                                        row['shares'] = 0.0
                        elif t == 'putCall':
                            row['putCall'] = elem.text
                    
                    if 'name' in row and row.get('value', 0) > 0:
                        holdings.append(row)

            if not holdings:
                return None, "파싱된 주식 보유 데이터가 없습니다."

            df = pd.DataFrame(holdings)
            
            # SEC 2023년 이후 규칙 (원 달러 vs 천 달러 단위 자동 보정)
            total_v = df['value'].sum()
            if total_v < 10000000 and len(df) > 10:  # 단위가 천 달러($'000)인 경우
                df['value'] = df['value'] * 1000

            # 동일 종목 합산
            df = df.groupby('name', as_index=False).agg({
                'value': 'sum',
                'shares': 'sum',
                'class': 'first',
                'cusip': 'first'
            })
            
            df = df.sort_values(by='value', ascending=False).reset_index(drop=True)
            df['weight'] = (df['value'] / df['value'].sum()) * 100

            meta = {
                "report_date": report_date,
                "filing_date": filing_date,
                "accession_number": accession_number,
                "total_aum": df['value'].sum(),
                "total_count": len(df),
                "top10_weight": df.head(10)['weight'].sum()
            }
            return (df, meta), None

        except Exception as e:
            return None, f"오류 발생: {str(e)}"

    with st.spinner("SEC EDGAR에서 최신 13F 공시 데이터를 수집 및 분석 중입니다..."):
        result, error = fetch_sec_13f(inst_info['cik'])

    if error:
        st.error(f"⚠️ {error}")
        st.caption("SEC API 일시적 지연이거나 User-Agent 헤더 규정 오류일 수 있습니다.")
    elif result:
        df_holdings, meta = result
        
        # 1. 메인 요약 메트릭 카드
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 운용자산 (AUM)", f"${meta['total_aum']/1e9:,.2f} B", help="13F 공시 대상 미국 주식 총 평가액")
        m2.metric("보유 종목 수", f"{meta['total_count']:,} 개")
        m3.metric("Top 10 집중도", f"{meta['top10_weight']:.1f} %", help="상위 10개 종목이 전체 포트폴리오에서 차지하는 비중")
        m4.metric("보고서 기준일 (QoQ)", meta['report_date'], help=f"공시 제출일: {meta['filing_date']}")

        st.divider()

        # 2. 포트폴리오 비중 시각화 (트리맵 & Top 10 바차트)
        st.subheader("📊 포트폴리오 비중 인터랙티브 시각화")
        tab_v1, tab_v2 = st.tabs(["🌳 포트폴리오 트리맵 (Treemap)", "📈 상위 10개 종목 비중"])
        
        with tab_v1:
            # 상위 50개 종목 트리맵
            df_tree = df_holdings.head(50).copy()
            df_tree['label'] = df_tree['name'] + "<br>" + df_tree['weight'].apply(lambda x: f"{x:.2f}%") + "<br>($" + (df_tree['value']/1e6).apply(lambda x: f"{x:,.1f}M") + ")"
            fig_tree = px.treemap(
                df_tree,
                path=['name'],
                values='value',
                title=f"{selected_inst_name} 주요 보유 종목 트리맵 (Top 50)",
                color='weight',
                color_continuous_scale='Blues'
            )
            fig_tree.update_traces(textinfo="label", textfont=dict(size=13))
            fig_tree.update_layout(margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_tree, use_container_width=True)

        with tab_v2:
            df_top10 = df_holdings.head(10).sort_values(by='weight', ascending=True)
            fig_bar = go.Figure(go.Bar(
                x=df_top10['weight'],
                y=df_top10['name'],
                orientation='h',
                marker=dict(color='#0066FF', opacity=0.85),
                text=df_top10['weight'].apply(lambda x: f"{x:.2f}%"),
                textposition='outside'
            ))
            fig_bar.update_layout(
                title=f"{selected_inst_name} 상위 Top 10 보유 비중",
                xaxis_title="포트폴리오 비중 (%)",
                yaxis_title="",
                margin=dict(l=20, r=40, t=40, b=20)
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # 3. 전체 보유 종목 상세 표
        st.subheader("📋 전체 보유 지분 상세 목록")
        df_display = df_holdings[['name', 'weight', 'value', 'shares', 'class', 'cusip']].copy()
        df_display.columns = ['종목명 (Issuer)', '비중 (%)', '평가액 ($)', '보유 주식수', '주식 종류', 'CUSIP']
        df_display['비중 (%)'] = df_display['비중 (%)'].map('{:.2f}%'.format)
        df_display['평가액 ($)'] = df_display['평가액 ($)'].map('${:,.0f}'.format)
        df_display['보유 주식수'] = df_display['보유 주식수'].map('{:,.0f}'.format)
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.divider()

        # 4. Gemini Pro AI 심층 전략 리포트 생성기
        st.subheader("🤖 Gemini Pro AI 심층 투자 전략 리포트")
        st.caption("정량적 13F 데이터셋을 Gemini Pro 모델에 전달하여 기관의 투자 철학과 거시경제 베팅 방향을 분석합니다.")

        # Gemini API 호출 함수 (REST 방식 직통 호출)
        def generate_gemini_report(inst_name: str, meta_data: dict, top_df: pd.DataFrame) -> str:
            gemini_key = st.secrets.get("gemini", {}).get("api_key", None)
            if not gemini_key:
                return "⚠️ Streamlit Secrets에 `[gemini] api_key`가 등록되지 않았습니다. Secrets에 API 키를 설정해주세요."

            top_holdings_str = "\n".join([
                f"- {row['name']}: 비중 {row['weight']:.2f}% (평가액: ${row['value']/1e6:,.1f}M, 주식수: {row['shares']:,.0f})"
                for _, row in top_df.head(15).iterrows()
            ])

            prompt = f"""
당신은 월스트리트 최고의 거시경제 펀드 전략가이자 헤지펀드 수석 애널리스트입니다.
아래 제공된 미국 SEC 13F 최신 공시 데이터를 바탕으로 **{inst_name}**의 이번 분기 포트폴리오를 심층 분석하고 전문적인 투자 전략 리포트를 작성해주세요.

[기관 및 포트폴리오 개요]
- 기관명: {inst_name}
- 공시 기준일: {meta_data['report_date']} (제출일: {meta_data['filing_date']})
- 총 운용자산(AUM): ${meta_data['total_aum']/1e9:,.2f} B (10억 달러 단위)
- 총 보유 종목 수: {meta_data['total_count']} 개
- Top 10 종목 집중도: {meta_data['top10_weight']:.1f}%

[상위 Top 15 보유 종목 현황]
{top_holdings_str}

[작성 요구사항]
다음 4가지 핵심 섹션으로 나누어 전문적이고 논리정연한 한국어로 작성해주세요:
1. 🎯 **이번 분기 핵심 포트폴리오 구조 및 집중도 평가**
   - 상위 종목 집중도({meta_data['top10_weight']:.1f}%)와 핵심 베팅 종목들의 성격 분석
2. 🏭 **주요 섹터/산업별 자산 배분 및 전략적 특징**
   - 빅테크, 금융, 에너지, 헬스케어, 소비재 등 포트폴리오가 가리키는 산업 방향성
3. 🌐 **거시경제(매크로) 환경과의 연계성 및 시사점**
   - 금리, 인플레이션, 경기 사이클과 관련하여 이 기관이 어떤 시나리오에 베팅하고 있는지 분석
4. 💡 **개인 투자자를 위한 실전 벤치마킹 포인트 & 주의점**
   - 13F 공시 시차를 감안한 투자 아이디어 및 리스크 요인

답변은 마크다운 헤더와 불릿 포인트를 활용하여 최고급 금융 리포트 양식으로 깔끔하게 작성해주세요.
"""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 4096
                }
            }
            try:
                resp = requests.post(url, json=payload, timeout=40)
                if resp.status_code == 200:
                    resp_json = resp.json()
                    candidates = resp_json.get('candidates', [])
                    if candidates:
                        return candidates[0]['content']['parts'][0]['text']
                    return "리포트를 생성하지 못했습니다. 응답 내용을 확인해주세요."
                else:
                    # gemini-2.5-pro 실패 시 gemini-2.5-flash로 폴백
                    fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                    resp_fb = requests.post(fallback_url, json=payload, timeout=40)
                    if resp_fb.status_code == 200:
                        return resp_fb.json()['candidates'][0]['content']['parts'][0]['text']
                    return f"Gemini API 호출 실패 (상태 코드: {resp.status_code}, 메시지: {resp.text})"
            except Exception as ex:
                return f"Gemini API 통신 중 오류 발생: {str(ex)}"

        if st.button("🚀 Gemini Pro 분석 리포트 생성", type="primary", use_container_width=True):
            with st.spinner("Gemini Pro가 13F 데이터를 정밀 분석하여 맞춤형 전략 리포트를 작성 중입니다..."):
                report_content = generate_gemini_report(selected_inst_name, meta, df_holdings)
                st.markdown(report_content)
