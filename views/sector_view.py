# views/sector_view.py
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from config import SECTOR_ETFS, ASSET_CLASS_ETFS
from services.sector_service import calculate_returns_matrix

def highlight_return(val):
    """
    수익률 수치에 따라 양수(초록색), 음수(빨간색), 0(회색) 텍스트 색상을 지정합니다.
    """
    try:
        num = float(val)
        if num > 0:
            return 'color: #10B981; font-weight: 600;'
        elif num < 0:
            return 'color: #EF4444; font-weight: 600;'
        return 'color: #94A3B8;'
    except (ValueError, TypeError):
        return ''

def render_sector_view():
    st.title("🔄 섹터 & 자산군 로테이션 맵 (Sector Momentum & Rotation)")
    st.caption("S&P 500 11대 섹터 및 글로벌 핵심 자산군의 단기/중기 자금 이동과 주도 섹터(공격 vs 방어)를 모니터링합니다.")

    with st.spinner("S&P 500 섹터 및 자산군 시세 데이터를 분석 중입니다..."):
        sector_df, sector_hist = calculate_returns_matrix(SECTOR_ETFS, benchmark_ticker="SPY")
        asset_df, asset_hist = calculate_returns_matrix(ASSET_CLASS_ETFS, benchmark_ticker="SPY")

    if sector_df is None or sector_df.empty:
        st.error("섹터 데이터를 불러오는 데 실패했습니다. 잠시 후 다시 시도해주세요.")
        return

    # 기준 거래일 추출
    latest_date_str = ""
    if sector_hist and "SPY" in sector_hist and not sector_hist["SPY"].empty:
        latest_date_str = sector_hist["SPY"].index[-1].strftime('%Y-%m-%d')
    elif asset_hist and "SPY" in asset_hist and not asset_hist["SPY"].empty:
        latest_date_str = asset_hist["SPY"].index[-1].strftime('%Y-%m-%d')

    # 1. 메인 핵심 요약 메트릭
    best_1m = sector_df.sort_values(by="1M", ascending=False).iloc[0]
    worst_1m = sector_df.sort_values(by="1M", ascending=True).iloc[0]
    best_ytd = sector_df.sort_values(by="YTD", ascending=False).iloc[0]

    m1, m2, m3 = st.columns(3)
    m1.metric("최근 1개월 1등 주도 섹터", f"{best_1m['name'].split()[0]} ({best_1m['ticker']})", f"{best_1m['1M']:+.2f}%")
    m2.metric("최근 1개월 최하위 섹터", f"{worst_1m['name'].split()[0]} ({worst_1m['ticker']})", f"{worst_1m['1M']:+.2f}%")
    m3.metric("올해(YTD) 1등 주도 섹터", f"{best_ytd['name'].split()[0]} ({best_ytd['ticker']})", f"{best_ytd['YTD']:+.2f}%")

    st.divider()

    # 2. 탭별 상세 시각화
    tab1, tab2, tab3 = st.tabs([
        "📊 11대 섹터 모멘텀 순위",
        "📈 섹터별 누적 수익률 추이",
        "🌐 글로벌 자산군(Asset Class) 로테이션"
    ])

    return_cols = ['1주(%)', '1개월(%)', '3개월(%)', '6개월(%)', '1년(%)', 'YTD(%)']

    # TAB 1: 11대 섹터 모멘텀 순위
    with tab1:
        st.markdown("#### ⚙️ 기간별 섹터 성과 순위")
        col_c1, col_c2 = st.columns([1, 1])
        with col_c1:
            period_sel = st.selectbox("조회 기간 선택", ["1W", "1M", "3M", "6M", "1Y", "YTD"], index=1, key="sector_period_sel")
        with col_c2:
            mode_sel = st.radio("표시 기준", ["단순 수익률 (%)", "S&P 500(SPY) 대비 초과성과 (Alpha %p)"], index=0, horizontal=True)

        target_col = period_sel if mode_sel == "단순 수익률 (%)" else f"{period_sel}_alpha"
        sorted_df = sector_df.sort_values(by=target_col, ascending=True).copy()

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=sorted_df[target_col],
            y=sorted_df['ticker'] + " (" + sorted_df['name'] + ")",
            orientation='h',
            marker=dict(
                color=['#EF4444' if v < 0 else '#10B981' for v in sorted_df[target_col]]
            ),
            text=sorted_df[target_col].apply(lambda x: f"{x:+.2f}%" if mode_sel == "단순 수익률 (%)" else f"{x:+.2f}%p"),
            textposition='outside',
            hovertemplate="<b>%{y}</b><br>성과: %{x:+.2f}%<extra></extra>"
        ))
        fig_bar.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.6)
        fig_bar.update_layout(
            height=460,
            title=f"11대 섹터 {period_sel} {mode_sel} 순위 (기준일: {latest_date_str})",
            xaxis_title="수익률 (%)" if mode_sel == "단순 수익률 (%)" else "초과성과 (%p)",
            yaxis_title="",
            margin=dict(l=20, r=50, t=40, b=20)
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown(f"#### 📋 11대 섹터 기간별 수익률 종합 매트릭스 :gray[(기준일: {latest_date_str})]")
        disp_df = sector_df[['ticker', 'name', 'type', '1W', '1M', '3M', '6M', '1Y', 'YTD']].copy()
        disp_df.columns = ['티커', '섹터명', '성격', '1주(%)', '1개월(%)', '3개월(%)', '6개월(%)', '1년(%)', 'YTD(%)']

        # 색상 및 서식 적용
        styled_disp = disp_df.style.format({c: '{:+.2f}%' for c in return_cols})
        if hasattr(styled_disp, 'map'):
            styled_disp = styled_disp.map(highlight_return, subset=return_cols)
        else:
            styled_disp = styled_disp.applymap(highlight_return, subset=return_cols)

        st.dataframe(styled_disp, use_container_width=True, hide_index=True)

    # TAB 2: 누적 수익률 추이 비교 차트
    with tab2:
        st.markdown("#### 📈 섹터별 상대 수익률 시계열 비교")
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            selected_tickers = st.multiselect(
                "비교할 섹터 선택 (다중 선택 가능)",
                options=list(SECTOR_ETFS.keys()),
                default=["XLK", "XLE", "XLF", "XLV"],
                format_func=lambda x: f"{x} - {SECTOR_ETFS[x]['name']}"
            )
        with col_t2:
            chart_period = st.selectbox("비교 기간", ["1mo", "3mo", "6mo", "1y", "2y"], index=2, key="sector_chart_p")

        if selected_tickers and sector_hist:
            fig_trend = go.Figure()
            if "SPY" in sector_hist:
                spy_s = sector_hist["SPY"].iloc[-130:] if chart_period == "6mo" else sector_hist["SPY"]
                spy_ret = ((spy_s - spy_s.iloc[0]) / spy_s.iloc[0]) * 100
                fig_trend.add_trace(go.Scatter(
                    x=spy_ret.index, y=spy_ret, mode='lines', name='S&P 500 (SPY)',
                    line=dict(color='white', width=2, dash='dash')
                ))

            colors = px.colors.qualitative.Plotly
            for idx, sym in enumerate(selected_tickers):
                if sym in sector_hist:
                    s = sector_hist[sym]
                    sub_s = s.iloc[-130:] if chart_period == "6mo" else s
                    norm_ret = ((sub_s - sub_s.iloc[0]) / sub_s.iloc[0]) * 100
                    fig_trend.add_trace(go.Scatter(
                        x=norm_ret.index, y=norm_ret, mode='lines',
                        name=f"{sym} ({SECTOR_ETFS[sym]['name'].split()[0]})",
                        line=dict(width=2.2, color=colors[idx % len(colors)])
                    ))

            fig_trend.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
            fig_trend.update_layout(
                title=f"선택 섹터 누적 변동률 (%) 비교 (기준: {chart_period})",
                xaxis_title="일자", yaxis_title="누적 수익률 (%)",
                hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_trend, use_container_width=True)

    # TAB 3: 글로벌 자산군 로테이션
    with tab3:
        if asset_df is not None and not asset_df.empty:
            st.markdown("#### 🌐 주식 · 채권 · 원자재 · 달러 자산군 모멘텀 순위")
            asset_period = st.selectbox("자산군 순위 기준 기간", ["1W", "1M", "3M", "6M", "1Y", "YTD"], index=1, key="asset_period_sel")
            sorted_asset = asset_df.sort_values(by=asset_period, ascending=True).copy()

            fig_asset = go.Figure(go.Bar(
                x=sorted_asset[asset_period],
                y=sorted_asset['name'] + " (" + sorted_asset['ticker'] + ")",
                orientation='h',
                marker=dict(
                    color=['#EF4444' if v < 0 else '#3B82F6' for v in sorted_asset[asset_period]]
                ),
                text=sorted_asset[asset_period].apply(lambda x: f"{x:+.2f}%"),
                textposition='outside',
                hovertemplate="<b>%{y}</b><br>수익률: %{x:+.2f}%<extra></extra>"
            ))
            fig_asset.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.6)
            fig_asset.update_layout(
                height=460,
                title=f"글로벌 주요 자산군 {asset_period} 수익률 순위 (기준일: {latest_date_str})",
                xaxis_title="수익률 (%)", yaxis_title="",
                margin=dict(l=20, r=50, t=40, b=20)
            )
            st.plotly_chart(fig_asset, use_container_width=True)

            st.markdown(f"#### 📋 자산군별 기간별 수익률표 :gray[(기준일: {latest_date_str})]")
            disp_asset = asset_df[['ticker', 'name', 'type', '1W', '1M', '3M', '6M', '1Y', 'YTD']].copy()
            disp_asset.columns = ['티커', '자산군 명칭', '카테고리', '1주(%)', '1개월(%)', '3개월(%)', '6개월(%)', '1년(%)', 'YTD(%)']

            # 색상 및 서식 적용
            styled_asset = disp_asset.style.format({c: '{:+.2f}%' for c in return_cols})
            if hasattr(styled_asset, 'map'):
                styled_asset = styled_asset.map(highlight_return, subset=return_cols)
            else:
                styled_asset = styled_asset.applymap(highlight_return, subset=return_cols)

            st.dataframe(styled_asset, use_container_width=True, hide_index=True)
