# views/radar_view.py
import streamlit as st
import pandas as pd
import plotly.express as px
from services.radar_service import fetch_investor_top_stocks
from services.kis_service import fetch_kis_kospi_index

def render_radar_view():
    st.title("📡 실시간 외인/기관 수급 레이더")
    st.caption("LS증권 및 한국투자증권 API를 교차 활용하여 당일 실시간 자금 유입 핵심 주도주를 스캐닝합니다.")

    # 1. 상단 KIS API 재활용 (시장 지표 확인)
    with st.spinner("시장 데이터 로딩 중..."):
        kospi_data, _ = fetch_kis_kospi_index()
    
    if kospi_data:
        st.markdown(f"**현재 코스피 지수:** `{kospi_data['price']:,.2f} pt` (전일비 {kospi_data['diff']:+.2f} pt / {kospi_data['rate']:+.2f}%)")
    
    st.divider()

    # 2. 레이더 컨트롤 패널
    col1, col2, col3 = st.columns(3)
    with col1:
        market = st.selectbox("조회 시장", ["코스피", "코스닥"], index=0)
        market_val = "1" if market == "코스피" else "2"
    with col2:
        investor = st.selectbox("투자자 주체", ["외국인", "기관", "개인"], index=0)
        investor_val = "1" if investor == "외국인" else "2" if investor == "기관" else "3"
    with col3:
        trade_type = st.selectbox("매매 동향", ["순매수 (자금 유입)", "순매도 (자금 이탈)"], index=0)
        trade_val = "1" if "순매수" in trade_type else "2"

    # 3. LS API 수급 스캐닝 호출
    with st.spinner("실시간 수급 데이터를 스캐닝 중입니다..."):
        df, err = fetch_investor_top_stocks(market_val, investor_val, trade_val)

    if err:
        st.error(f"데이터 스캐닝 실패: {err}")
        return
    
    if df is None or df.empty:
        st.warning("현재 기준 해당 조건의 수급 데이터가 잡히지 않습니다.")
        return

    # 4. 수급 히트맵 (Treemap) 렌더링
    st.subheader("🗺️ 실시간 수급 집중도 히트맵 (Top 50)")
    st.caption("박스의 크기는 '자금 규모(순매수/순매도 금액)'이며, 색상은 당일 '등락률(%)'을 의미합니다. (초록: 하락 / 빨강: 상승)")
    
    # ⚠️ Plotly Treemap 에러 방지 처리: values 파라미터에는 양수만 허용됨
    plot_df = df.copy()
    # 결측치를 0으로 채우고 절대값 처리하여 그리기용 변수 생성
    plot_df['plot_value'] = plot_df['svalue'].fillna(0).abs() 
    # 박스 크기가 0이하인 유령 데이터 필터링
    plot_df = plot_df[plot_df['plot_value'] > 0]

    if plot_df.empty:
        st.info("차트로 시각화할 수 있는 유효한 거래 금액 데이터가 없습니다.")
    else:
        # 트리맵 시각화 (한국 주식 색상: 상승=Red, 하락=Blue계열)
        fig = px.treemap(
            plot_df,
            path=[px.Constant(f"{market} Top 50"), 'hname'], # 루트 계층을 명확히 주어 렌더링 안정성 확보
            values='plot_value',
            color='diff',
            custom_data=['svalue'], # 원본 부호가 살아있는 데이터를 custom_data로 주입
            color_continuous_scale=['#3B82F6', '#94A3B8', '#EF4444'], # Blue -> Gray -> Red
            color_continuous_midpoint=0,
        )
        
        # UI 레이블에 plot_value(양수) 대신 custom_data(원본)를 노출하도록 수정
        fig.update_traces(
            texttemplate="<b>%{label}</b><br>%{customdata[0]:,.0f}백만<br>%{color:+.2f}%",
            hovertemplate="<b>%{label}</b><br>금액: %{customdata[0]:,.0f} 백만원<br>등락률: %{color:+.2f}%<extra></extra>"
        )
        
        fig.update_layout(
            height=500,
            margin=dict(l=10, r=10, t=30, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)

    # 5. 상세 데이터 테이블
    st.subheader(f"📋 {market} {investor} Top 50 랭킹표")
    
    # 존재하는 컬럼만 추출하여 KeyError 방지
    available_cols = [col for col in ['rank', 'hname', 'price', 'diff', 'svalue'] if col in df.columns]
    disp_df = df[available_cols].copy()
    
    # 컬럼 이름 변경
    new_col_names = []
    if 'rank' in available_cols: new_col_names.append('순위')
    if 'hname' in available_cols: new_col_names.append('종목명')
    if 'price' in available_cols: new_col_names.append('현재가(원)')
    if 'diff' in available_cols: new_col_names.append('등락률(%)')
    if 'svalue' in available_cols: new_col_names.append('금액(백만원)')
    
    disp_df.columns = new_col_names
    
    # 테이블 UI 포맷팅
    if '현재가(원)' in disp_df.columns:
        disp_df['현재가(원)'] = disp_df['현재가(원)'].map('{:,.0f}'.format)
    if '등락률(%)' in disp_df.columns:
        disp_df['등락률(%)'] = disp_df['등락률(%)'].map('{:+.2f}%'.format)
    if '금액(백만원)' in disp_df.columns:
        disp_df['금액(백만원)'] = disp_df['금액(백만원)'].map('{:,.0f}'.format)
    
    st.dataframe(disp_df, use_container_width=True, hide_index=True)
