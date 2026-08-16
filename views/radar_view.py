# views/radar_view.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from services.radar_service import (
    fetch_investor_top_stocks, 
    fetch_period_investor_top_stocks, 
    fetch_market_investor_trend
)
from services.kis_service import fetch_kis_kospi_index

def format_treemap_and_table(df, market, investor, trade_type, is_period=False):
    """ 트리맵과 테이블을 렌더링하는 공통 헬퍼 함수 """
    if df.empty or df['svalue'].abs().sum() == 0:
        if not is_period:
            st.warning("⚠️ **장 마감 및 주말 상태 안내**\n\n현재 당일 실시간 수급 데이터가 0으로 초기화되었습니다. 평일 장중에만 정상 표출됩니다. (※ '기간별 누적' 탭이나 '시장 수급 추이' 탭을 이용해 과거 데이터를 확인하세요.)")
        else:
            st.warning("선택한 기간의 유효한 수급 데이터가 없습니다.")
        return

    plot_df = df.copy()
    plot_df['plot_value'] = plot_df['svalue'].fillna(0).abs() 
    plot_df = plot_df[plot_df['plot_value'] > 0]

    if not plot_df.empty:
        fig = px.treemap(
            plot_df,
            path=[px.Constant(f"{market} {investor} Top 50"), 'hname'],
            values='plot_value',
            color='diff',
            custom_data=['svalue', 'diff'],
            color_continuous_scale=['#3B82F6', '#94A3B8', '#EF4444'], 
            color_continuous_midpoint=0,
        )
        fig.update_traces(
            texttemplate="<b>%{label}</b><br>%{customdata[0]:,.0f}백만<br>%{color:+.2f}%",
            hovertemplate="<b>%{label}</b><br>금액: %{customdata[0]:,.0f} 백만원<br>등락률: %{color:+.2f}%<extra></extra>"
        )
        fig.update_layout(height=500, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    # 데이터 테이블
    st.subheader(f"📋 {market} {investor} Top 50 랭킹표")
    available_cols = [col for col in ['rank', 'hname', 'price', 'diff', 'svalue'] if col in df.columns]
    disp_df = df[available_cols].copy()
    
    col_map = {'rank': '순위', 'hname': '종목명', 'price': '현재가(원)', 'diff': '등락률(%)', 'svalue': '금액(백만원)'}
    disp_df.rename(columns=col_map, inplace=True)
    
    if '현재가(원)' in disp_df.columns: disp_df['현재가(원)'] = disp_df['현재가(원)'].map('{:,.0f}'.format)
    if '등락률(%)' in disp_df.columns: disp_df['등락률(%)'] = disp_df['등락률(%)'].map('{:+.2f}%'.format)
    if '금액(백만원)' in disp_df.columns: disp_df['금액(백만원)'] = disp_df['금액(백만원)'].map('{:,.0f}'.format)
    
    st.dataframe(disp_df, use_container_width=True, hide_index=True)


def render_radar_view():
    st.title("📡 외인/기관/개인 수급 레이더")
    st.caption("시장 주체별 핵심 주도주 스캐닝 및 일별 자금 유입/이탈 추이를 분석합니다.")

    # 1. 상단 KIS API 마켓 인덱스
    with st.spinner("시장 데이터 로딩 중..."):
        kospi_data, _ = fetch_kis_kospi_index()
    if kospi_data:
        st.markdown(f"**현재 코스피 지수:** `{kospi_data['price']:,.2f} pt` (전일비 {kospi_data['diff']:+.2f} pt / {kospi_data['rate']:+.2f}%)")
    
    st.divider()

    # 2. 공통 설정 패널
    st.markdown("#### ⚙️ 기본 설정")
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

    st.write("")

    # 3. 3단 탭 구성
    tab1, tab2, tab3 = st.tabs([
        "⚡ 실시간 당일 레이더", 
        "📅 기간 누적 수급 레이더", 
        "📈 시장 전체 일별 수급 추이"
    ])

    # [Tab 1] 당일 실시간
    with tab1:
        st.markdown(f"#### 🗺️ 당일 실시간 수급 집중도 (Top 50)")
        with st.spinner("당일 실시간 수급 데이터를 스캐닝 중입니다..."):
            df_day, err_day = fetch_investor_top_stocks(market_val, investor_val, trade_val)
        if err_day: st.error(err_day)
        elif df_day is not None:
            format_treemap_and_table(df_day, market, investor, trade_type, is_period=False)

    # [Tab 2] 기간 누적
    with tab2:
        period_days = st.radio("누적 조회 기간", [3, 5, 10, 20, 60], index=1, format_func=lambda x: f"최근 {x}일", horizontal=True)
        st.markdown(f"#### 🗺️ 최근 {period_days}일 누적 수급 집중도 (Top 50)")
        
        with st.spinner(f"최근 {period_days}일 누적 데이터를 연산 중입니다..."):
            df_period, err_per = fetch_period_investor_top_stocks(market_val, investor_val, trade_val, days=period_days)
        if err_per: st.error(err_per)
        elif df_period is not None:
            format_treemap_and_table(df_period, market, investor, trade_type, is_period=True)

    # [Tab 3] 시장 전체 일별 수급 추이
    with tab3:
        st.markdown(f"#### 📈 {market} 일별 3대 주체 누적 순매수 금액 추이")
        st.caption("최근 거래일 기준 코스피/코스닥 시장 전체의 외국인, 기관, 개인 순매수 금액(단위: 백만원) 라인 차트입니다.")
        
        with st.spinner("시장 일별 수급 동향을 불러오는 중입니다..."):
            df_trend, err_trend = fetch_market_investor_trend(market_val)
            
        if err_trend: st.error(err_trend)
        elif df_trend is not None and not df_trend.empty:
            fig_trend = go.Figure()
            # 외인 (Blue)
            fig_trend.add_trace(go.Scatter(x=df_trend['date'], y=df_trend['foreign'], mode='lines+markers', name='외국인', line=dict(color='#3B82F6', width=2)))
            # 기관 (Orange)
            fig_trend.add_trace(go.Scatter(x=df_trend['date'], y=df_trend['inst'], mode='lines+markers', name='기관', line=dict(color='#F97316', width=2)))
            # 개인 (Green)
            fig_trend.add_trace(go.Scatter(x=df_trend['date'], y=df_trend['retail'], mode='lines+markers', name='개인', line=dict(color='#10B981', width=2)))
            
            fig_trend.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.7)
            fig_trend.update_layout(
                height=450,
                xaxis_title="일자", yaxis_title="순매수 금액 (백만원)",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_trend, use_container_width=True)
            
            st.markdown("##### 📋 일자별 상세 수급 데이터 (단위: 백만원)")
            # 날짜를 최신순으로 정렬 후 출력
            disp_trend = df_trend.sort_values('date', ascending=False).copy()
            disp_trend['date'] = disp_trend['date'].dt.strftime('%Y-%m-%d')
            disp_trend.columns = ['일자', '외국인 순매수', '기관 순매수', '개인 순매수']
            
            for col in ['외국인 순매수', '기관 순매수', '개인 순매수']:
                disp_trend[col] = disp_trend[col].map('{:,.0f}'.format)
                
            st.dataframe(disp_trend, use_container_width=True, hide_index=True)
        else:
            st.warning("해당 시장의 일별 수급 추이 데이터를 불러올 수 없습니다.")
