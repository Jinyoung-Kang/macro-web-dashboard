# views/radar_view.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from services.radar_service import fetch_investor_top_stocks, fetch_kis_ticker_investor_trend
from services.kis_service import fetch_kis_kospi_index

def render_radar_view():
    st.title("📡 정밀 수급 레이더 (Flow Radar)")
    st.caption("LS증권(실시간 시장 스캐닝)과 KIS증권(종목 정밀 시계열) 정식 API를 활용한 무결성 수급 분석")

    with st.spinner("시장 지표 동기화 중..."):
        kospi_data, _ = fetch_kis_kospi_index()
    if kospi_data:
        st.markdown(f"**현재 코스피 지수:** `{kospi_data['price']:,.2f} pt` (전일비 {kospi_data['diff']:+.2f} pt / {kospi_data['rate']:+.2f}%)")
    
    st.divider()

    tab1, tab2 = st.tabs([
        "⚡ 실시간 시장 수급 레이더 (LS API)", 
        "🔍 개별 종목 수급 정밀 분석 (KIS API)"
    ])

    # ==========================================
    # [Tab 1] 실시간 당일 레이더
    # ==========================================
    with tab1:
        st.markdown("#### ⚙️ 시장 스캐닝 설정")
        col1, col2, col3 = st.columns(3)
        with col1:
            market = st.selectbox("조회 시장", ["코스피", "코스닥"], index=0, key="t1_m")
            ls_market = "1" if market == "코스피" else "2"
        with col2:
            investor = st.selectbox("투자자 주체", ["외국인", "기관", "개인"], index=0, key="t1_i")
            ls_investor = "1" if investor == "외국인" else "2" if investor == "기관" else "3"
        with col3:
            trade_type = st.selectbox("매매 동향", ["순매수 (자금 유입)", "순매도 (자금 이탈)"], index=0, key="t1_t")
            clean_trade = "순매수" if "순매수" in trade_type else "순매도"
            ls_trade = "1" if clean_trade == "순매수" else "2"

        with st.spinner("당일 실시간 수급 스캐닝 중..."):
            df_day, err_day = fetch_investor_top_stocks(ls_market, ls_investor, ls_trade)
        
        if err_day:
            st.error(err_day)
        elif df_day is None or df_day.empty or df_day['svalue'].abs().sum() == 0:
            st.warning("⚠️ **장 마감/주말 상태:** 현재 실시간 데이터가 0으로 초기화되었습니다. 평일 정규장(09:00~15:30)에 정상 작동합니다. 과거 수급 분석은 **[개별 종목 정밀 분석]** 탭을 이용하십시오.")
        else:
            plot_df = df_day.copy()
            plot_df['plot_value'] = plot_df['svalue'].fillna(0).abs()
            plot_df = plot_df[plot_df['plot_value'] > 0]

            if not plot_df.empty:
                fig = px.treemap(
                    plot_df,
                    path=[px.Constant(f"{market} {investor} Top 50"), 'hname'],
                    values='plot_value',
                    color='diff',
                    custom_data=['svalue'],
                    color_continuous_scale=['#3B82F6', '#94A3B8', '#EF4444'],
                    color_continuous_midpoint=0,
                )
                fig.update_traces(
                    texttemplate="<b>%{label}</b><br>%{customdata[0]:,.0f}백만<br>%{color:+.2f}%",
                    hovertemplate="<b>%{label}</b><br>순금액: %{customdata[0]:,.0f} 백만원<br>등락률: %{color:+.2f}%<extra></extra>"
                )
                fig.update_layout(height=500, margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig, use_container_width=True)

            disp_df = df_day[['rank', 'hname', 'price', 'diff', 'svalue']].copy()
            disp_df.columns = ['순위', '종목명', '종가(원)', '등락률(%)', '당일 금액(백만원)']
            disp_df['종가(원)'] = disp_df['종가(원)'].map('{:,.0f}'.format)
            disp_df['등락률(%)'] = disp_df['등락률(%)'].map('{:+.2f}%'.format)
            disp_df['당일 금액(백만원)'] = disp_df['당일 금액(백만원)'].map('{:,.0f}'.format)
            st.dataframe(disp_df, use_container_width=True, hide_index=True)

    # ==========================================
    # [Tab 2] 개별 종목 수급 시계열 (KIS API)
    # ==========================================
    with tab2:
        st.markdown("#### 🔍 종목 정밀 추적")
        st.caption("특정 종목의 최근 30영업일 투자자별 순매수 수량(주) 및 주가 변동을 분석합니다.")
        
        c1, c2 = st.columns([2, 1])
        with c1:
            target_code = st.text_input("조회할 종목코드 (6자리)", value="005930")
        with c2:
            st.write("")
            analyze_btn = st.button("차트 분석 실행", type="primary", use_container_width=True)
            
        if target_code:
            with st.spinner("해당 종목의 30일 시계열 데이터를 불러오는 중..."):
                df_ticker, err_ticker = fetch_kis_ticker_investor_trend(target_code.strip())
            
            if err_ticker:
                st.error(err_ticker)
            elif df_ticker is not None and not df_ticker.empty:
                # 콤보 차트 생성 (주가 선형 + 수급 막대형)
                fig_t = make_subplots(specs=[[{"secondary_y": True}]])
                
                # 외인, 기관, 개인 수급을 누적(Bar)으로 표현
                fig_t.add_trace(go.Bar(x=df_ticker['date'], y=df_ticker['foreign'], name="외국인 순매수", marker_color="#3B82F6"), secondary_y=False)
                fig_t.add_trace(go.Bar(x=df_ticker['date'], y=df_ticker['inst'], name="기관 순매수", marker_color="#F97316"), secondary_y=False)
                fig_t.add_trace(go.Bar(x=df_ticker['date'], y=df_ticker['retail'], name="개인 순매수", marker_color="#10B981"), secondary_y=False)
                
                # 주가 추이를 꺾은선으로 중첩
                fig_t.add_trace(go.Scatter(x=df_ticker['date'], y=df_ticker['close'], mode="lines+markers", name="종가(우축)", line=dict(color="#EF4444", width=2)), secondary_y=True)

                fig_t.update_layout(
                    height=500,
                    barmode="group",
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                fig_t.update_yaxes(title_text="순매수 수량 (주)", secondary_y=False)
                fig_t.update_yaxes(title_text="주가 (원)", secondary_y=True)
                
                st.plotly_chart(fig_t, use_container_width=True)

                # 상세 표 출력
                st.markdown("##### 📋 일자별 상세 수급 내역 (단위: 주)")
                disp_ticker = df_ticker.sort_values('date', ascending=False).copy()
                disp_ticker['date'] = disp_ticker['date'].dt.strftime('%Y-%m-%d')
                disp_ticker.columns = ['일자', '종가(원)', '외국인 순매수(주)', '기관 순매수(주)', '개인 순매수(주)']
                
                for c in disp_ticker.columns[1:]:
                    disp_ticker[c] = disp_ticker[c].map('{:,.0f}'.format)
                st.dataframe(disp_ticker, use_container_width=True, hide_index=True)
