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
from views.ls_test_view import render_ls_test_view
from views.kis_test_view import render_kis_test_view  # 한국투자증권 뷰 임포트

# SSL 경고 비활성화
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Global Macro & 13F Dashboard", layout="wide")

# ==========================================
# 0. 간이 인증 (비밀번호 잠금) 시스템
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
# 1. 사이드바 네비게이션 & 갱신 설정
# ==========================================
st.sidebar.header("🧭 대시보드 메뉴")
menu_selection = st.sidebar.radio(
    "이동할 메뉴를 선택하세요",
    [
        "📊 거시경제 매크로 지표", 
        "💧 연준 순유동성 트래커",
        "🔄 섹터 & 자산군 로테이션",
        "📑 기관 13F 포트폴리오 분석", 
        "🎯 기관 13F Money 교집합",
        "🧪 LS증권 API 테스트",
        "🧪 한국투자증권 API 테스트"
    ],
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
# 2. 공통 헤더 시계 및 메뉴 렌더링
# ==========================================
kst_tz = ZoneInfo("Asia/Seoul")
now_kst = datetime.now(kst_tz)
now_str_kst = now_kst.strftime('%Y-%m-%d %H:%M:%S')

components.html(LIVE_CLOCK_HTML, height=45)

if menu_selection == "📊 거시경제 매크로 지표":
    render_macro_view(now_str_kst, refresh_interval)
elif menu_selection == "💧 연준 순유동성 트래커":
    render_liquidity_view()
elif menu_selection == "🔄 섹터 & 자산군 로테이션":
    render_sector_view()
elif menu_selection == "📑 기관 13F 포트폴리오 분석":
    render_sec_view()
elif menu_selection == "🎯 기관 13F Money 교집합":
    render_consensus_view()
elif menu_selection == "🧪 LS증권 API 테스트":
    render_ls_test_view()
elif menu_selection == "🧪 한국투자증권 API 테스트":
    render_kis_test_view()
