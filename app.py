import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import requests
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Global Macro Web Dashboard", layout="wide")

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
            st.markdown("### 🔒 Global Macro Dashboard")
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
# 1. 사이드바: 갱신 설정 및 로그아웃
# ==========================================
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
# 2. 데이터 갱신 시각(KST) 및 매크로 지표 정의
# ==========================================
kst_tz = ZoneInfo("Asia/Seoul")
now_kst = datetime.now(kst_tz)
now_str_kst = now_kst.strftime('%Y-%m-%d %H:%M:%S')

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

# 텍스트 가공 헬퍼 함수
def clean_category_title(text: str) -> str:
    """카테고리명에서 마크다운 태그만 제거하고 '(지연 수준)'은 유지"""
    return re.sub(r':gray\[(.*?)\]', r'\1', text)

def clean_item_briefing(text: str) -> str:
    """텍스트 브리핑용: 개별 지표명에서 지연 수준 표기를 완전히 제거"""
    return re.sub(r'\s*:gray\[.*?\]', '', text).strip()

def clean_tag_ui(text: str) -> str:
    """UI 셀렉트박스/차트용: 마크다운 태그만 벗기고 텍스트는 유지"""
    return re.sub(r':gray\[(.*?)\]', r'\1', text)

# 텍스트 종합 브리핑 문자열 생성
lines = [
    "📌 [글로벌 매크로 지표 종합 브리핑]",
    f"⏱ 기준 시각: {now_str_kst} (KST)",
    "※ 변동 기준: 직전 거래일 종가 대비 (+, - 수치 및 %)",
    "=" * 55
]
for cat_name, items in collected_data.items():
    # 카테고리 헤더에는 지연 수준 유지 (예: 💵 통화 및 환율 (실시간))
    lines.append(f"\n{clean_category_title(cat_name)}")
    lines.append("-" * 45)
    for item in items:
        # 개별 지표명 옆의 지연 수준은 제거 (예: • 달러 인덱스 (DXY))
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

# ==========================================
# 3. 헤더 영역 (실시간 듀얼 디지털 시계 + KST 갱신 시각)
# ==========================================
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

# ==========================================
# 4. 메인 시세 요약 카드 렌더링 (지연 수준 표기 유지)
# ==========================================
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

# ==========================================
# 5. 10Y-2Y 장단기 금리차 핵심 해석 모델 & 실시간 분석
# ==========================================
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

spread_table_data = {
    "시장 상태": ["정상 (Normal)", "평탄화 (Flattening)", "역전 (Inversion) ⚠️"],
    "스프레드 수치": ["양수 (+)", "0에 수렴", "음수 (-)"],
    "시장의 심리 및 해석": [
        "장기 미래의 불확실성(프리미엄)으로 인해 장기 금리가 더 높음.",
        "미래 경기 성장이 둔화될 것이라는 우려가 커지기 시작함.",
        "현재 인플레이션을 잡기 위해 금리를 급격히 올렸으나, 미래 경기는 침체될 것으로 확신함."
    ],
    "경제적 귀결": [
        "경제의 점진적인 성장 및 안정적 확장",
        "경기 정점 통과 및 둔화 신호",
        "역사적으로 1~2년 내 경기 침체(Recession) 도래"
    ]
}
st.dataframe(pd.DataFrame(spread_table_data), use_container_width=True, hide_index=True)

# 10Y-2Y 과거 추이 차트
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
            x=df_spread.index,
            y=df_spread['Spread'],
            mode='lines',
            name='10Y-2Y 스프레드 (%p)',
            line=dict(color='#E02424', width=2),
            fill='tozeroy',
            fillcolor='rgba(224, 36, 36, 0.15)'
        ))
        fig_spread.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.8, annotation_text="기준선 (0%p 역전 경계)")
        fig_spread.update_layout(
            title=f"미국채 10Y - 2Y 스프레드 과거 추이 ({spread_period})",
            xaxis_title="일자",
            yaxis_title="스프레드 (%p)",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        st.plotly_chart(fig_spread, use_container_width=True)
    else:
        st.warning("스프레드 데이터를 병합하지 못했습니다.")
else:
    st.warning("차트 데이터를 불러오지 못했습니다.")

st.divider()

# ==========================================
# 6. 신용 리스크 및 시장 변동성 (Credit & Volatility) 전용 섹션
# ==========================================
st.subheader("⚡ 신용 리스크 및 시장 변동성 (Credit & Volatility)")
st.caption("주식·채권 시장의 가격 변동성과 기업 자금시장의 부도 위험(신용 스프레드)을 종합 모니터링합니다.")

col_v, col_m, col_h = st.columns(3)

# 1) VIX 카드
with col_v:
    if vix_hist is not None and len(vix_hist) >= 2:
        v_curr = vix_hist['Close'].iloc[-1]
        v_prev = vix_hist['Close'].iloc[-2]
        v_delta = v_curr - v_prev
        v_pct = (v_delta / v_prev) * 100
        
        if v_curr < 15:
            v_status, v_color = "안도 (Complacency)", "green"
        elif v_curr <= 20:
            v_status, v_color = "정상 (Normal)", "blue"
        elif v_curr <= 30:
            v_status, v_color = "경계 (Caution)", "orange"
        else:
            v_status, v_color = "공포 (Panic)", "red"
            
        st.metric(
            label="CBOE VIX (주식 변동성) :gray[[15분 지연]]",
            value=f"{v_curr:.2f}",
            delta=f"{v_delta:+.2f} ({v_pct:+.2f}%)",
            help="S&P 500 옵션 가격 기반 30일 변동성 기대치"
        )
        st.markdown(f"상태: :{v_color}[**{v_status}**] (전일: `{v_prev:.2f}`)")
    else:
        st.metric(label="CBOE VIX", value="로드 실패")

# 2) MOVE 카드
with col_m:
    if move_hist is not None and len(move_hist) >= 2:
        m_curr = move_hist['Close'].iloc[-1]
        m_prev = move_hist['Close'].iloc[-2]
        m_delta = m_curr - m_prev
        m_pct = (m_delta / m_prev) * 100
        
        if m_curr < 80:
            m_status, m_color = "안정 (Stable)", "green"
        elif m_curr <= 120:
            m_status, m_color = "정상 (Normal)", "blue"
        elif m_curr <= 140:
            m_status, m_color = "경계 (Caution)", "orange"
        else:
            m_status, m_color = "발작 / 위기 (Crisis)", "red"
            
        st.metric(
            label="ICE BofA MOVE (채권 변동성) :gray[[지연/마감]]",
            value=f"{m_curr:.2f}",
            delta=f"{m_delta:+.2f} ({m_pct:+.2f}%)",
            help="미국 국채 옵션 기반 금리 변동성 지수"
        )
        st.markdown(f"상태: :{m_color}[**{m_status}**] (전일: `{m_prev:.2f}`)")
    else:
        st.metric(label="ICE BofA MOVE", value="로드 실패")

# 3) 하이일드 스프레드 카드
with col_h:
    if hy_df is not None and len(hy_df) >= 2:
        h_curr = hy_df['BAMLH0A0HYM2'].iloc[-1]
        h_prev = hy_df['BAMLH0A0HYM2'].iloc[-2]
        h_date = hy_df.index[-1].strftime('%m-%d')
        h_delta = h_curr - h_prev
        
        if h_curr < 3.5:
            h_status, h_color = "완화 (Low Risk)", "green"
        elif h_curr <= 5.0:
            h_status, h_color = "정상 (Normal)", "blue"
        elif h_curr <= 7.0:
            h_status, h_color = "경계 (Stress)", "orange"
        else:
            h_status, h_color = "신용 위기 (Crisis)", "red"
            
        st.metric(
            label=f"하이일드 스프레드 (HY OAS) :gray[[1일 지연 {h_date} EOD]]",
            value=f"{h_curr:.2f} %p",
            delta=f"{h_delta:+.2f} %p",
            help="ICE BofA 미국 하이일드 채권 지수 옵션조정 스프레드 (FRED Daily)"
        )
        st.markdown(f"상태: :{h_color}[**{h_status}**] (직전: `{h_prev:.2f}%p`)")
    else:
        st.metric(label="하이일드 스프레드", value="로드 실패")

# 신용 & 변동성 해석 모델 테이블
st.markdown("#### 📖 신용 및 변동성 핵심 해석 기준표")
risk_model_table = {
    "지표명 (지연 수준)": [
        "CBOE VIX [15분 지연]", 
        "ICE BofA MOVE [지연/마감]", 
        "하이일드 스프레드 [1일 지연 EOD]"
    ],
    "정상 / 안정 범위": [
        "15 ~ 20 (15 미만: 과도한 낙관)", 
        "80 ~ 120 (80 미만: 금리 초안정)", 
        "3.5% ~ 5.0% (3.5% 미만: 유동성 풍부)"
    ],
    "위험 / 발작 임계치": [
        "30 이상 (패닉 / 급락 / 투매)", 
        "140 이상 (채권 발작 / 긴축 충격)", 
        "7.0% 이상 (본격 신용경색 / 경기침체)"
    ],
    "지표의 성격 및 핵심 해석": [
        "주식 시장의 단기 공포 측정기. 급등 시 주가 급락 및 투매 발생 신호.",
        "채권 시장의 공포 지수. 연준 통화정책 불확실성과 유동성 경색에 민감하게 반응.",
        "한계 기업의 부도 리스크 프리미엄. 경기 침체 진입 시 가장 먼저 급등하는 신용 선행 지표."
    ]
}
st.dataframe(pd.DataFrame(risk_model_table), use_container_width=True, hide_index=True)

# 변동성 & 신용 추이 차트 탭
st.markdown("#### 📈 위험 지표 상세 과거 추이")
risk_tab1, risk_tab2 = st.tabs(["📊 VIX & MOVE 변동성 지수 추이", "📉 하이일드 채권 스프레드 추이"])

with risk_tab1:
    vix_period = st.selectbox("변동성 지수 기간 선택", ["6mo", "1y", "2y", "5y", "max"], index=1, key="vix_period_sel")
    v_chart = fetch_ticker_data("^VIX", period=vix_period)
    m_chart = fetch_ticker_data("^MOVE", period=vix_period)
    
    if v_chart is not None and not v_chart.empty:
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Scatter(
            x=v_chart.index, y=v_chart['Close'], mode='lines', name='VIX (주식 변동성)',
            line=dict(color='#FF5722', width=2)
        ))
        
        if m_chart is not None and not m_chart.empty:
            fig_vol.add_trace(go.Scatter(
                x=m_chart.index, y=m_chart['Close'], mode='lines', name='MOVE (채권 변동성)',
                line=dict(color='#3F51B5', width=2), yaxis="y2"
            ))
            
        fig_vol.update_layout(
            title=f"VIX 및 MOVE 지수 비교 추이 ({vix_period})",
            xaxis_title="일자",
            yaxis=dict(
                title=dict(text="VIX (pt)", font=dict(color="#FF5722")),
                tickfont=dict(color="#FF5722")
            ),
            yaxis2=dict(
                title=dict(text="MOVE (pt)", font=dict(color="#3F51B5")),
                tickfont=dict(color="#3F51B5"),
                overlaying="y",
                side="right"
            ),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_vol, use_container_width=True)
    else:
        st.warning("변동성 지수 데이터를 불러오지 못했습니다.")

with risk_tab2:
    if hy_df is not None and not hy_df.empty:
        hy_period_years = st.selectbox("하이일드 기간 선택", [1, 2, 5, 10], index=2, format_func=lambda x: f"최근 {x}년")
        cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=hy_period_years)
        filtered_hy = hy_df[hy_df.index >= cutoff_date]
        
        fig_hy = go.Figure()
        fig_hy.add_trace(go.Scatter(
            x=filtered_hy.index, y=filtered_hy['BAMLH0A0HYM2'], mode='lines',
            name='US High Yield OAS (%p)', line=dict(color='#D32F2F', width=2),
            fill='tozeroy', fillcolor='rgba(211, 47, 47, 0.1)'
        ))
        fig_hy.add_hline(y=5.0, line_dash="dot", line_color="orange", annotation_text="경계선 (5.0%p)")
        fig_hy.add_hline(y=7.0, line_dash="dash", line_color="red", annotation_text="위기/침체선 (7.0%p)")
        fig_hy.update_layout(
            title=f"미국 하이일드 채권 스프레드 (HY OAS) 추이 (최근 {hy_period_years}년)",
            xaxis_title="일자",
            yaxis_title="스프레드 (%p)",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        st.plotly_chart(fig_hy, use_container_width=True)
    else:
        st.warning("하이일드 스프레드 데이터를 불러오지 못했습니다.")

st.divider()

# ==========================================
# 7. 개별 지표 상세 차트
# ==========================================
st.subheader("지표별 기간별 단독 차트")

ALL_TICKERS = {}
for cat in MACRO_CATEGORIES.values():
    ALL_TICKERS.update(cat)

c1, c2 = st.columns([2, 1])
with c1:
    selected_name = st.selectbox(
        "조회할 단일 지표 선택", 
        list(ALL_TICKERS.keys()),
        format_func=clean_tag_ui
    )
with c2:
    period = st.selectbox("조회 기간", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=3, key="single_period")

selected_symbol = ALL_TICKERS[selected_name]

try:
    df = fetch_ticker_data(selected_symbol, period=period)
    if df is not None and not df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df.index, 
            y=df['Close'], 
            mode='lines', 
            name=clean_tag_ui(selected_name),
            line=dict(color='#0066FF', width=2)
        ))
        fig.update_layout(
            title=f"{clean_tag_ui(selected_name)} ({selected_symbol}) 상세 차트",
            xaxis_title="일자",
            yaxis_title="수치/가격",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("데이터를 불러오지 못했습니다.")
except Exception:
    st.warning("차트 데이터를 불러오는 중 오류가 발생했습니다.")

st.divider()

# ==========================================
# 8. 다중 지표 오버레이 비교 차트
# ==========================================
st.subheader("🔀 다중 지표 오버레이 비교 차트")

col_comp1, col_comp2, col_comp3 = st.columns([2, 1, 1])

with col_comp1:
    multi_selected = st.multiselect(
        "비교할 지표 선택 (다중 선택 가능)",
        options=list(ALL_TICKERS.keys()),
        default=["원/달러 (USD/KRW) :gray[[실시간]]", "달러 인덱스 (DXY) :gray[[실시간]]"],
        format_func=clean_tag_ui
    )

with col_comp2:
    multi_period = st.selectbox(
        "비교 기간",
        options=["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
        index=3,
        key="multi_period"
    )

with col_comp3:
    norm_mode = st.radio(
        "비교 방식",
        options=["수익률/변동률(%) 기준", "실제 수치(절대값) 기준"],
        index=0
    )

if multi_selected:
    fig_multi = go.Figure()
    
    for name in multi_selected:
        sym = ALL_TICKERS[name]
        m_df = fetch_ticker_data(sym, period=multi_period)
        if m_df is not None and not m_df.empty:
            y_data = m_df['Close']
            
            if "JPY/KRW" in name and y_data.iloc[-1] < 50:
                y_data = y_data * 100
            
            if norm_mode == "수익률/변동률(%) 기준":
                base_val = y_data.iloc[0]
                if base_val != 0:
                    y_data = ((y_data - base_val) / base_val) * 100
                    y_title = "기준일 대비 누적 변동률 (%)"
                else:
                    y_title = "수치"
            else:
                y_title = "실제 수치 / 가격"

            fig_multi.add_trace(go.Scatter(
                x=m_df.index,
                y=y_data,
                mode='lines',
                name=clean_tag_ui(name),
                line=dict(width=2)
            ))

    fig_multi.update_layout(
        title=f"다중 지표 비교 추이 ({multi_period} 기준)",
        xaxis_title="일자",
        yaxis_title=y_title,
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    if norm_mode == "수익률/변동률(%) 기준":
        fig_multi.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.7)

    st.plotly_chart(fig_multi, use_container_width=True)
else:
    st.info("비교할 지표를 최소 1개 이상 선택해주세요.")
