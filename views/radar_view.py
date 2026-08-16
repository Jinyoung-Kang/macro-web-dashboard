# views/radar_view.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from services.radar_service import (
    fetch_investor_top_stocks,
    fetch_pykrx_period_top_stocks,
    fetch_pykrx_market_trend
)
from services.kis_service import fetch_kis_kospi_index

def render_treemap_and_table(df, market_label, investor_label, trade_type):
    if df is None or df.empty or df['svalue'].abs().sum() == 0:
        st.warning("표시할 유효한 수급 데이터가 없습니다.")
        return

    plot_df = df.copy()
    plot_df['plot_value'] = plot_df['svalue'].fillna(0).abs()
    plot_df = plot_df[plot_df['plot_value'] > 0]

    if not plot_df.empty:
        fig = px.treemap(
            plot_df,
            path=[px.Constant(f"{market_label} {investor_label} Top 50"), 'hname'],
            values='plot_value',
            color='diff',
            custom_data=['svalue'],
            color_continuous_scale=['#3B82F6', '#94A3B8', '#EF4444'],
            color_continuous_midpoint=0,
        )
        fig.update_traces(
            texttemplate="<b>%{label}</b><br>%{customdata[0]:,.0f}백만<br>%{color:+.2f}%",
            hovertemplate="<b>%{label}</b><br>순매수: %{customdata[0]:,.0f} 백만원<br>등락률: %{color:+.2f}%<extra></extra>"
        )
        fig.update_layout(height=500, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader(f"📋 {market_label} {investor_label} Top 50 랭킹표")
    disp_df = df[['rank', 'hname', 'price', 'diff', 'svalue']].copy()
    disp_df.columns = ['순위', '종목명', '종가(원)', '등락률(%)', '순매수금액(백만원)']
    disp_df['종가(원)'] = disp_df['종가(원)'].map('{:,.0f}'.format)
    disp_df['등락률(%)'] = disp_df['등락률(%)'].map('{:+.2f}%'.format)
    disp_df['순매수금액(백만원)'] = disp_df['순매수금액(백만원)'].map('{:,.0f}'.format)
    st.dataframe(disp_df, use_container_width=True, hide_index=True)


def render_radar_view():
    st.title("📡 외인/기관/개인 수급 레이더")
    st.caption("실시간 OpenAPI 및 한국거래소(KRX) 데이터를 융합하여 주체별 자금 흐름을 다각도로 분석합니다.")

    with st.spinner("시장 데이터 동기화 중..."):
        kospi_data, _ = fetch_kis_kospi_index()
    if kospi_data:
        st.markdown(f"**현재 코스피 지수:** `{kospi_data['price']:,.2f} pt` (전일비 {kospi_data['diff']:+.2f} pt / {kospi_data['rate']:+.2f}%)")

    st.divider()

    # 공통 설정
    col1, col2, col3 = st.columns(3)
    with col1:
        market = st.selectbox("조회 시장", ["코스피", "코스닥"], index=0)
        pykrx_market = "KOSPI" if market == "코스피" else "KOSDAQ"
        ls_market = "1" if market == "코스피" else "2"
    with col2:
        investor = st.selectbox("투자자 주체", ["외국인", "기관", "개인"], index=0)
        ls_investor = "1" if investor == "외국인" else "2" if investor == "기관" else "3"
    with col3:
        trade_type = st.selectbox("매매 동향", ["순매수 (자금 유입)", "순매도 (자금 이탈)"], index=0)
        clean_trade = "순매수" if "순매수" in trade_type else "순매도"
        ls_trade = "1" if clean_trade == "순매수" else "2"

    st.write("")

    tab1, tab2, tab3 = st.tabs([
        "⚡ 실시간 당일 레이더", 
        "📅 기간 누적 수급 레이더 (KRX)", 
        "📈 시장 전체 일별 수급 추이 (KRX)"
    ])

    # Tab 1: 당일 실시간
    with tab1:
        st.markdown("#### 🗺️ 당일 실시간 수급 집중도 (장중 전용)")
        with st.spinner("당일 실시간 수급 스캐닝 중..."):
            df_day, err_day = fetch_investor_top_stocks(ls_market, ls_investor, ls_trade)
        if err_day:
            st.error(err_day)
        elif df_day is None or df_day.empty or df_day['svalue'].abs().sum() == 0:
            st.warning("⚠️ **장 마감 및 주말 상태 안내**\n\n현재는 정규장 운영 시간이 아니므로 실시간 데이터가 0입니다. **[기간 누적]** 또는 **[일별 추이]** 탭에서 최근 수급 데이터를 확인하세요.")
        else:
            render_treemap_and_table(df_day, market, investor, clean_trade)

    # Tab 2: 기간 누적 (Pykrx)
    with tab2:
        period_days = st.radio("누적 조회 기간", [3, 5, 10, 20, 60], index=1, format_func=lambda x: f"최근 {x}일 누적", horizontal=True)
        st.markdown(f"#### 🗺️ 최근 {period_days}일 누적 수급 집중도 (Top 50)")
        with st.spinner(f"KRX 최근 {period_days}일 누적 데이터를 연산 중입니다..."):
            df_period, err_period = fetch_pykrx_period_top_stocks(pykrx_market, investor, clean_trade, days=period_days)
        if err_period:
            st.error(err_period)
        else:
            render_treemap_and_table(df_period, market, investor, clean_trade)

    # Tab 3: 시장 전체 일별 수급 추이 (Pykrx)
    with tab3:
        st.markdown(f"#### 📈 {market} 일별 3대 주체 순매수 금액 추이 (최근 30거래일)")
        with st.spinner("KRX 시장 시계열 데이터를 집계 중입니다..."):
            df_trend, err_trend = fetch_pykrx_market_trend(pykrx_market, days=30)
        
        if err_trend:
            st.error(err_trend)
        elif df_trend is not None and not df_trend.empty:
            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(x=df_trend['date'], y=df_trend['foreign'], mode='lines+markers', name='외국인', line=dict(color='#3B82F6', width=2)))
            fig_trend.add_trace(go.Scatter(x=df_trend['date'], y=df_trend['inst'], mode='lines+markers', name='기관', line=dict(color='#F97316', width=2)))
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
            disp_trend = df_trend.sort_values('date', ascending=False).copy()
            disp_trend['date'] = disp_trend['date'].dt.strftime('%Y-%m-%d')
            disp_trend.columns = ['일자', '외국인 순매수', '기관 순매수', '개인 순매수']
            for c in ['외국인 순매수', '기관 순매수', '개인 순매수']:
                disp_trend[c] = disp_trend[c].map('{:,.0f}'.format)
            st.dataframe(disp_trend, use_container_width=True, hide_index=True)
