# app.py
import streamlit as st
import streamlit.components.v1 as components
import urllib3
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

from config import LIVE_CLOCK_HTML
from views.macro_view import render_macro_view
from views.sec_view import render_sec_view
from views.consensus_view import render_consensus_view
from views.sector_view import render_sector_view
from views.liquidity_view import render_liquidity_view
from views.radar_view import render_radar_view
from views.cot_view import render_cot_view

# SSL 경고 비활성화
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 페이지 기본 설정
st.set_page_config(page_title="Global Macro & 13F Dashboard", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 0. 커스텀 CSS 주입 (모던 UI & 메뉴 간격 조정)
# ==========================================
st.markdown("""
<style>
    /* 사이드바 라디오 메뉴 디자인 모던화 */
    section[data-testid="stSidebar"] div.stRadio > div[role="radiogroup"] > label {
        padding: 12px 15px !important;       /* 메뉴 내부 여백 (위아래 12px, 좌우 15px) */
        margin-bottom: 8px !important;       /* 메뉴 간의 간격 띄우기 */
        border-radius: 8px !important;       /* 모서리 둥글게 */
        background-color: rgba(128, 128, 128, 0.05) !important; /* 은은한 배경색 */
        transition: all 0.2s ease-in-out !important; /* 부드러운 애니메이션 효과 */
        cursor: pointer;
    }
    
    /* 마우스 호버(올렸을 때) 액션 */
    section[data-testid="stSidebar"] div.stRadio > div[role="radiogroup"] > label:hover {
        background-color: rgba(128, 128, 128, 0.15) !important; /* 배경색 진하게 */
        transform: translateX(4px); /* 살짝 오른쪽으로 밀리는 입체감 */
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. 간이 인증 (비밀번호 잠금) 시스템
# ==========================================
def check_password():
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
# 2. 사이드바 네비게이션 & 갱신 설정
# ==========================================
st.sidebar.markdown("## 대시보드 메뉴")
st.sidebar.caption("글로벌 매크로 및 시장 수급 정밀 분석 시스템")

# 직관적이고 깔끔한 형태의 라디오 버튼 UI 적용
menu_selection = st.sidebar.radio(
    "이동할 메뉴를 선택하세요",
    [
        "📊 거시경제 매크로 지표", 
        "🏢 연준 순유동성 트래커",
        "🔄 섹터 & 자산군 로테이션",
        "📑 기관 13F 포트폴리오 분석", 
        "🎯 기관 13F Money 교집합",
        "🏛️ 글로벌 스마트머니 (COT)",
        "📡 외국인/기관 수급 레이더 (코스피)"        
    ],
    index=0,
    label_visibility="collapsed"
)

st.sidebar.divider()
st.sidebar.markdown("#### 🔄 데이터 갱신 설정")

# 수동 강제 새로고침 버튼 (API 캐시 메모리 완전 초기화)
if st.sidebar.button("데이터 수동 새로고침 🚀", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# 기존 자동 새로고침 로직 유지
auto_refresh_enabled = st.sidebar.checkbox("실시간 자동 새로고침 활성화", value=False)
refresh_interval = st.sidebar.selectbox(
    "새로고침 주기",
    options=[10, 30, 60, 120, 300],
    index=2,
    format_func=lambda x: f"{x}초 간격"
)

if auto_refresh_enabled:
    st_autorefresh(interval=refresh_interval * 1000, key="datarefresh")

st.sidebar.divider()
if st.sidebar.button("로그아웃", use_container_width=True):
    st.session_state.authenticated = False
    st.rerun()

st.sidebar.caption("© 2026 Macro Web Dashboard v2.3")

# ==========================================
# 3. 공통 헤더 시계 및 메뉴 렌더링
# ==========================================
kst_tz = ZoneInfo("Asia/Seoul")
now_kst = datetime.now(kst_tz)
now_str_kst = now_kst.strftime('%Y-%m-%d %H:%M:%S')

components.html(LIVE_CLOCK_HTML, height=45)

if menu_selection == "📊 거시경제 매크로 지표":
    render_macro_view(now_str_kst, refresh_interval)
elif menu_selection == "🏢 연준 순유동성 트래커":
    render_liquidity_view()
elif menu_selection == "🔄 섹터 & 자산군 로테이션":
    render_sector_view()
elif menu_selection == "📑 기관 13F 포트폴리오 분석":
    render_sec_view()
elif menu_selection == "🎯 기관 13F Money 교집합":
    render_consensus_view()
elif menu_selection == "🏛️ 글로벌 스마트머니 (COT)":  
    render_cot_view()
elif menu_selection == "📡 외국인/기관 수급 레이더 (코스피)":
    render_radar_view()
