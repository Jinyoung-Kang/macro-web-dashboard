# app.py
import streamlit as st

# 페이지 기본 설정
st.set_page_config(page_title="Macro & AI Dashboard", layout="wide", page_icon="🌐")

# UI 모듈 임포트
from views.macro_view import render_macro_view
from views.liquidity_view import render_liquidity_view
from views.radar_view import render_radar_view
from views.cot_view import render_cot_view
from views.sector_view import render_sector_view
from views.sec_view import render_sec_view
from views.consensus_view import render_consensus_view
from views.ai_test_view import render_ai_test_view

# 시간 및 업데이트 주기 관련
from datetime import datetime
import pytz

def main():
    # Sidebar 네비게이션
    st.sidebar.title("🌐 Dashboard Menu")
    menu = st.sidebar.radio(
        "메뉴 선택",
        [
            "거시경제 매크로 지표", 
            "연준 순유동성 (Net Liquidity)", 
            "글로벌 자산 레이더", 
            "COT 투기세력 포지션",
            "섹터별 S&P500 현황",
            "주요 기관들의 포트폴리오",
            "기관 13F Money 교집합 분석",
            "AI API 통합 & Failover 테스트"
        ]
    )

    st.sidebar.divider()
    st.sidebar.info("💡 **Tip**: 왼쪽 메뉴를 클릭하여 다양한 거시경제 및 AI 분석 화면을 탐색하세요.")

    now_kst = datetime.now(pytz.timezone('Asia/Seoul'))
    now_str_kst = now_kst.strftime("%Y-%m-%d %H:%M:%S")
    refresh_interval = 60

    # 메뉴 라우팅
    if menu == "거시경제 매크로 지표":
        render_macro_view(now_str_kst, refresh_interval)
    elif menu == "연준 순유동성 (Net Liquidity)":
        render_liquidity_view()
    elif menu == "글로벌 자산 레이더":
        render_radar_view()
    elif menu == "COT 투기세력 포지션":
        render_cot_view()
    elif menu == "섹터별 S&P500 현황":
        render_sector_view()
    elif menu == "주요 기관들의 포트폴리오":
        render_sec_view()
    elif menu == "기관 13F Money 교집합 분석":
        render_consensus_view()
    elif menu == "AI API 통합 & Failover 테스트":
        render_ai_test_view()
    else:
        st.error("알 수 없는 메뉴입니다.")

if __name__ == "__main__":
    main()
