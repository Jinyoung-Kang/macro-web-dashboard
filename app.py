import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Global Macro Web Dashboard", layout="wide")

# ==========================================
# 0. 간이 인증 (비밀번호 잠금) 시스템
# ==========================================
def check_password():
    """올바른 비밀번호가 입력되었는지 검증하고 세션 상태를 유지합니다."""
    # Secrets에 설정된 비밀번호 가져오기 (없을 경우 기본 비밀번호 대체)
    correct_password = st.secrets.get("auth", {}).get("password", "na0930@")

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        # 로그인 UI
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

# 인증 실패 시 아래 메인 코드 실행 중단
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
# 2. 매크로 지표 정의 및 데이터 수집
# ==========================================
MACRO_CATEGORIES = {
    "💵 통화 및 환율": {
        "달러 인덱스 (DXY)": "DX-Y.NYB",
        "원/달러 (USD/KRW)": "KRW=X",
        "달러/엔 (USD/JPY)": "JPY=X",
        "엔/원 100엔당 (JPY/KRW)": "JPYKRW=X"
    },
    "🏛️ 미국 국채 금리": {
        "미국채 2년물 금리(%)": "2YY=F",
        "미국채 10년물 금리(%)": "^TNX",
        "미국채 30년물 금리(%)": "^TYX"
    },
    "🛢️ 원자재": {
        "WTI 원유 ($)": "CL=F",
        "브렌트유 ($)": "BZ=F",
        "금 선물 ($)": "GC=F"
    },
    "📈 주가지수 및 선물": {
        "S&P 500": "^GSPC",
        "S&P 500 선물 (ES)": "ES=F",
        "나스닥 100": "^NDX",
        "나스닥 선물 (NQ)": "NQ=F",
        "VIX 변동성 지수": "^VIX"
    }
}

now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

@st.cache_data(ttl=30, show_spinner=False)
def fetch_ticker_data(symbol, period="5d"):
    try:
        t = yf.Ticker(symbol)
        return t.history(period=period)
    except Exception:
        return None

collected_data = {}

for cat_name, tickers in MACRO_CATEGORIES.items():
    collected_data[cat_name] = []
    for name, ticker_symbol in tickers.items():
        hist = fetch_ticker_data(ticker_symbol, period="5d")
        
        if hist is not None and len(hist) >= 2:
            curr_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2]
            delta = curr_price - prev_price
            pct_change = (delta / prev_price) * 100
            
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

lines = [
    "📌 [글로벌 매크로 지표 브리핑]",
    f"⏱ 기준 시각: {now_str}",
    "※ 변동 기준: 직전 거래일 종가 대비 (+, - 수치 및 %)",
    "=" * 55
]
for cat_name, items in collected_data.items():
    lines.append(f"\n{cat_name}")
    lines.append("-" * 45)
    for item in items:
        if item["status"] == "ok":
            lines.append(f"• {item['name']:<20} : {item['price_str']:>9} (전일: {item['prev_str']:>9}) | 전일비 {item['delta_str']}")
        else:
            lines.append(f"• {item['name']:<20} : {item['price_str']:>9} | {item['delta_str']}")
lines.append("\n" + "=" * 55)
report_text = "\n".join(lines)

# ==========================================
# 3. 헤더 영역
# ==========================================
header_left, header_right = st.columns([3, 1])

with header_left:
    st.title("📊 Global Macro Dashboard")
    st.caption(f"최근 데이터 갱신 시각: {now_str} (갱신 주기: {refresh_interval}초)")

with header_right:
    st.write("")
    with st.popover("📋 텍스트 브리핑 보기 / 복사", use_container_width=True):
        st.markdown("**현재 시세 텍스트 브리핑**")
        st.caption("우측 상단 복사 아이콘(📋)을 눌러 즉시 복사하세요.")
        st.code(report_text, language="text")

st.divider()

# ==========================================
# 4. 메인 시세 요약 카드 렌더링
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
# 5. 개별 지표 상세 차트
# ==========================================
st.subheader("지표별 기간별 단독 차트")

ALL_TICKERS = {}
for cat in MACRO_CATEGORIES.values():
    ALL_TICKERS.update(cat)

c1, c2 = st.columns([2, 1])
with c1:
    selected_name = st.selectbox("조회할 단일 지표 선택", list(ALL_TICKERS.keys()))
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
            name=selected_name,
            line=dict(color='#0066FF', width=2)
        ))
        fig.update_layout(
            title=f"{selected_name} ({selected_symbol}) 상세 차트",
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
# 6. 다중 지표 오버레이 비교 차트
# ==========================================
st.subheader("🔀 다중 지표 오버레이 비교 차트")

col_comp1, col_comp2, col_comp3 = st.columns([2, 1, 1])

with col_comp1:
    multi_selected = st.multiselect(
        "비교할 지표 선택 (다중 선택 가능)",
        options=list(ALL_TICKERS.keys()),
        default=["원/달러 (USD/KRW)", "달러 인덱스 (DXY)"]
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
                name=name,
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
