"""
app.py
Macro & Market Intelligence Web Dashboard - 메인 엔트리포인트
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import APP_PASSWORD
from views.macro_view import render_macro_view
from views.liquidity_view import render_liquidity_view
from views.sector_view import render_sector_view
from views.sec_view import render_sec_view
from views.consensus_view import render_consensus_view
from views.cot_view import render_cot_view
from views.krx_cot_view import render_krx_cot_view
from views.radar_view import render_radar_view
from views.ai_test_view import render_ai_test_view

# ==============================================================================
# 1. 페이지 기본 설정 & 커스텀 CSS 테마
# ==============================================================================
st.set_page_config(
    page_title="Macro Intelligence Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

CUSTOM_CSS = """
<style>
    /* 다크 핀테크 테마 배경 */
    .stApp {
        background-color: #0D1117;
        color: #C9D1D9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* 사이드바 스타일링 */
    section[data-testid="stSidebar"] {
        background-color: #161B22;
        border-right: 1px solid #30363D;
    }
    
    /* 메트릭 카드 컨테이너 */
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 14px 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    }
    
    div[data-testid="stMetricLabel"] {
        color: #8B949E;
        font-size: 0.85rem;
        font-weight: 500;
    }
    
    div[data-testid="stMetricValue"] {
        color: #F0F6FC;
        font-size: 1.45rem;
        font-weight: 700;
    }

    /* 버튼 스타일 */
    .stButton>button {
        background-color: #21262D;
        color: #C9D1D9;
        border: 1px solid #30363D;
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    .stButton>button:hover {
        background-color: #30363D;
        border-color: #8B949E;
        color: #F0F6FC;
    }

    /* 테이블 테두리 */
    div[data-testid="stDataFrame"] {
        border: 1px solid #30363D;
        border-radius: 8px;
        background-color: #161B22;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ==============================================================================
# 2. 간이 보안 인증 (Session State)
# ==============================================================================
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div style='text-align: center; padding-bottom: 20px;'>
            <h2 style='color:#F0F6FC;'>🔒 Macro Dashboard Access</h2>
            <p style='color:#8B949E;'>시스템 접속을 위한 접근 비밀번호를 입력하십시오.</p>
        </div>
        """, unsafe_allow_html=True)
        pwd = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Enter Password...")
        if st.button("로그인", use_container_width=True):
            if pwd == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")
    return False

if not check_password():
    st.stop()

# ==============================================================================
# 3. 사이드바 네비게이션 & 글로벌 컨트롤
# ==============================================================================
with st.sidebar:
    st.markdown("""
    <div style="padding: 10px 0 15px 0;">
        <h3 style="margin:0; color:#58A6FF; font-weight:700;">📊 Macro Insight</h3>
        <p style="margin:2px 0 0 0; color:#8B949E; font-size:0.82rem;">Global Multi-Asset Intelligence</p>
    </div>
    """, unsafe_allow_html=True)

    menu = st.radio(
        "Navigation",
        options=[
            "📊 거시경제 매크로 지표",
            "🏢 연준 순유동성 트래커",
            "🔄 섹터 & 자산군 로테이션",
            "📑 기관 13F 포트폴리오",
            "🎯 기관 13F Money 교집합",
            "🏛️ 글로벌 스마트머니 (COT)",
            "🇰🇷 국내 파생 & 스마트머니 (KRX)",
            "📡 수급 레이더 (코스피)",
            "🤖 AI 엔진 & Failover 테스트"
        ],
        index=6  # 기본 선택을 신규 기능으로 지정
    )

    st.markdown("---")
    
    # 자동 갱신 인터벌
    refresh_rate = st.selectbox(
        "⏱️ 자동 새로고침 주기",
        options=[0, 60, 300, 600],
        format_func=lambda x: "비활성화 (수동)" if x == 0 else f"{x}초 간격",
        index=0
    )
    if refresh_rate > 0:
        st_autorefresh(interval=refresh_rate * 1000, key="global_autorefresh")

    st.markdown("---")
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# ==============================================================================
# 4. 라우팅 처리
# ==============================================================================
if menu == "📊 거시경제 매크로 지표":
    render_macro_view()
elif menu == "🏢 연준 순유동성 트래커":
    render_liquidity_view()
elif menu == "🔄 섹터 & 자산군 로테이션":
    render_sector_view()
elif menu == "📑 기관 13F 포트폴리오":
    render_sec_view()
elif menu == "🎯 기관 13F Money 교집합":
    render_consensus_view()
elif menu == "🏛️ 글로벌 스마트머니 (COT)":
    render_cot_view()
elif menu == "🇰🇷 국내 파생 & 스마트머니 (KRX)":
    render_krx_cot_view()
elif menu == "📡 수급 레이더 (코스피)":
    render_radar_view()
elif menu == "🤖 AI 엔진 & Failover 테스트":
    render_ai_test_view()
