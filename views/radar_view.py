"""
views/radar_view.py
📡 외국인/기관 정밀 수급 레이더 뷰
실시간/장마감 시장 수급 트리맵 및 30영업일 영점조정 누적 수급 분석
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from services.radar_service import get_market_radar_scanner, get_stock_cumulative_flow

def render_radar_view():
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S KST")
    weekday = now_kst.weekday()
    time_num = now_kst.hour * 100 + now_kst.minute
    
    if weekday in [5, 6]:
        market_status_text = "⚪ 주말 휴장 (최근 거래일 확정 수급)"
        status_color = "#8B949E"
    elif 900 <= time_num < 1530:
        market_status_text = "🟢 코스피/코스닥 정규장 (실시간 수급 집계 중)"
        status_color = "#3FB950"
    elif 1530 <= time_num <= 1800:
        market_status_text = "🟣 시간외 단일가 / 애프터마켓 (당일 최종 누적 수급)"
        status_color = "#A371F7"
    else:
        market_status_text = "⚪ 장 마감 (당일 확정 수급 집계)"
        status_color = "#8B949E"

    st.markdown(f"""
    <div style="padding: 4px 0 12px 0;">
        <h2 style="margin:0; font-weight: 700; color: #F0F6FC;">
            📡 외국인/기관 수급 레이더 (코스피 & 코스닥)
        </h2>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
            <span style="color: #8B949E; font-size: 0.92rem;">
                실시간 및 장마감 투자 주체별(외국인/기관/개인/연기금) 자금 유출입 스캐닝 & 종목별 영점조정 누적 수급
            </span>
            <span style="background-color:rgba(255,255,255,0.06); border:1px solid #30363D; border-radius:4px; padding:3px 10px; font-size:0.84rem; color:{status_color}; font-weight:600;">
                {market_status_text}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📊 시장 전체 수급 스캐너", "🔍 개별 종목 수급 정밀 분석 (영점조정)"])

    # ==========================================================================
    # TAB 1: 시장 전체 수급 스캐너
    # ==========================================================================
    with tab1:
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1])
        with c1:
            market_sel = st.selectbox("시장 구분", options=["KOSPI (코스피)", "KOSDAQ (코스닥)"], index=0)
        with c2:
            investor_sel = st.selectbox("투자 주체", options=["외국인", "기관", "연기금", "금융투자", "투신", "개인"], index=0)
        with c3:
            trade_sel = st.selectbox("매매 방향", options=["순매수", "순매도"], index=0)
        with c4:
            top_n = st.selectbox("표시 종목 수", options=[15, 30, 50], index=1)

        market_key = "KOSPI" if "KOSPI" in market_sel else "KOSDAQ"
        
        # 무중단 파이프라인에서 데이터 로드
        df_radar = get_market_radar_scanner(market=market_key, investor=investor_sel, trade_type=trade_sel, top_n=top_n)

        if df_radar.empty:
            st.error("""
            ❌ **실시간 수급 데이터 연동 실패 (데이터 수신 불가)**
            
            **[실패 원인 점검 가이드]**:
            1. **장 마감 후 원장 정리 시간**: 평일 15:30 이후 또는 야간 시간대에는 증권사 실시간 속보 TR이 초기화되어 데이터를 반환하지 않습니다.
            2. **API 키 설정 상태**: Streamlit Secrets에 `[ls]` 또는 `[kis]` API 인증키가 올바르게 등록되어 있는지 확인하십시오.
            3. **개별 종목 정밀 분석 탭 이용**: 2번째 탭인 **[개별 종목 수급 정밀 분석]**에서 과거 30영업일 누적 수급 흐름을 조회하십시오.
            """)
        else:
            data_source = df_radar["데이터_출처"].iloc[0] if "데이터_출처" in df_radar.columns else "실시간 수급 API"
            top1 = df_radar.iloc[0]
            total_top_amt = df_radar["순매수대금(억)"].sum()
            
            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                st.metric(label=f"🥇 1위 집중 종목 ({investor_sel})", value=f"{top1['종목명']}", delta=f"{top1['순매수대금(억)']:+,.1f} 억")
            with sc2:
                st.metric(label=f"상위 {len(df_radar)}개사 합산 {trade_sel} 규모", value=f"{total_top_amt:+,.1f} 억원")
            with sc3:
                st.metric(label="📡 데이터 소스 및 기준 시각", value=data_source, delta=now_str, delta_color="off")

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

            st.markdown(f"#### 🗺️ {investor_sel} {trade_sel} 상위 종목 맵 (Treemap)")
            
            df_radar["Abs_Amt"] = df_radar["순매수대금(억)"].abs()
            fig_tree = px.treemap(
                df_radar,
                path=["종목명"],
                values="Abs_Amt",
                color="등락률(%)",
                color_continuous_scale=["#388BFD", "#161B22", "#F85149"],
                color_continuous_midpoint=0.0,
                hover_data={"종목코드": True, "현재가": ":,.0f", "순매수대금(억)": ":+,.1f", "등락률(%)": ":+.2f"},
                height=480
            )
            
            # 중앙 정렬 및 폰트 크기 최적화
            fig_tree.update_traces(
                textposition="middle center",
                textfont=dict(size=15, color="white", weight="bold"),
                hovertemplate="<b>%{label}</b><br>현재가: %{customdata[1]:,.0f}원<br>등락률: %{customdata[3]:+.2f}%<br>순매수금액: %{customdata[2]:+,.1f}억원"
            )
            fig_tree.update_layout(
                paper_bgcolor="#0D1117",
                plot_bgcolor="#161B22",
                margin=dict(l=10, r=10, t=20, b=10)
            )
            st.plotly_chart(fig_tree, use_container_width=True)

            st.markdown(f"#### 📋 {investor_sel} {trade_sel} 상위 {len(df_radar)}개 종목 리스트")
            display_cols = ["순위", "종목코드", "종목명", "현재가", "등락률(%)", "순매수대금(억)"]
            st.dataframe(
                df_radar[display_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "현재가": st.column_config.NumberColumn(format="%d 원"),
                    "등락률(%)": st.column_config.NumberColumn(format="%+.2f%%"),
                    "순매수대금(억)": st.column_config.NumberColumn(format="%+,.1f 억")
                }
            )

    # ==========================================================================
    # TAB 2: 개별 종목 수급 정밀 분석 (영점조정 누적 수급 흐름도)
    # ==========================================================================
    with tab2:
        col_in1, col_in2 = st.columns([2, 1])
        with col_in1:
            stock_code_input = st.selectbox(
                "분석 대상 종목 선택",
                options=[
                    ("005930", "삼성전자"),
                    ("000660", "SK하이닉스"),
                    ("005380", "현대차"),
                    ("035420", "NAVER"),
                    ("068270", "셀트리온"),
                    ("000270", "기아"),
                    ("105560", "KB금융"),
                    ("051910", "LG화학")
                ],
                format_func=lambda x: f"{x[1]} ({x[0]})",
                index=0
            )
        with col_in2:
            cum_days = st.selectbox("수급 추적 기간 (영업일)", options=[20, 30, 60, 90], index=1)

        selected_code = stock_code_input[0]
        selected_name = stock_code_input[1]

        df_cum = get_stock_cumulative_flow(stock_code=selected_code, days=cum_days)

        if not df_cum.empty:
            st.markdown(f"#### 📈 {selected_name} ({selected_code}) {cum_days}영업일 영점조정 누적 수급 곡선")
            
            fig_cum = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.08,
                row_heights=[0.65, 0.35],
                subplot_titles=(
                    f"{selected_name} 주가 vs 주체별 누적 순매수 (영점 = {cum_days}일 전)",
                    "일별 순매수 규모 (억 원)"
                )
            )

            fig_cum.add_trace(
                go.Scatter(
                    x=df_cum["Date"], y=df_cum["Close"],
                    name="주가 (종가)", line=dict(color="#C9D1D9", width=1.5, dash="dot"), yaxis="y2"
                ), row=1, col=1
            )
            fig_cum.add_trace(
                go.Scatter(
                    x=df_cum["Date"], y=df_cum["Foreigner_Cum"],
                    name="외국인 누적(억)", line=dict(color="#F85149", width=2.5)
                ), row=1, col=1
            )
            fig_cum.add_trace(
                go.Scatter(
                    x=df_cum["Date"], y=df_cum["Institution_Cum"],
                    name="기관 누적(억)", line=dict(color="#58A6FF", width=2)
                ), row=1, col=1
            )
            fig_cum.add_trace(
                go.Scatter(
                    x=df_cum["Date"], y=df_cum["Retail_Cum"],
                    name="개인 누적(억)", line=dict(color="#E3B341", width=1.5)
                ), row=1, col=1
            )
            fig_cum.add_trace(
                go.Bar(
                    x=df_cum["Date"], y=df_cum["Foreigner_Daily"],
                    name="외인 일별(억)", marker_color=["#F85149" if v >= 0 else "#388BFD" for v in df_cum["Foreigner_Daily"]]
                ), row=2, col=1
            )

            fig_cum.update_layout(
                template="plotly_dark", paper_bgcolor="#0D1117", plot_bgcolor="#161B22",
                height=650, margin=dict(l=30, r=40, t=50, b=30),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified"
            )
            fig_cum.update_yaxes(title_text="누적 금액 (억 원)", row=1, col=1, gridcolor="#21262D")
            fig_cum.update_yaxes(title_text="일별 (억 원)", row=2, col=1, gridcolor="#21262D")

            st.plotly_chart(fig_cum, use_container_width=True)

            with st.expander("📄 일별 수급 및 주가 원장 데이터 확인", expanded=False):
                st.dataframe(
                    df_cum.sort_values("Date", ascending=False),
                    use_container_width=True, hide_index=True
                )
        else:
            st.warning("⚠️ 해당 종목의 과거 시계열 수급 데이터를 불러오지 못했습니다.")
