# views/liquidity_view.py
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from services.liquidity_service import get_net_liquidity_data

def render_liquidity_view():
    st.title("🏢 연준 순유동성 트래커 (Fed Net Liquidity Tracker)")
    st.caption("연준 총자산에서 재무부 일반계좌(TGA)와 역레포(ON RRP)를 차감한 실제 금융시장 가용 유동성을 모니터링합니다.")

    with st.spinner("연준(Fed) 및 재무부 유동성 데이터를 분석 중입니다..."):
        df, metrics = get_net_liquidity_data()

    if df is None or not metrics:
        st.error("유동성 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
        return

    # 1. 상단 핵심 지표 요약 메트릭 카드
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "현재 연준 순유동성",
        f"${metrics['net_liq_t']:.3f} T",
        delta=f"{metrics['net_liq_1w_delta']:+.1f} B (1주)",
        help="연준 총자산 - TGA 잔고 - 역레포 잔고"
    )
    m1.caption(f"1개월 변동: `{metrics['net_liq_1m_delta']:+.1f} B` | 연초비: `{metrics['net_liq_ytd_delta']:+.1f} B`")

    m2.metric(
        "연준 총자산 (WALCL)",
        f"${metrics['walcl_t']:.3f} T",
        help="연준 대차대조표 총자산 규모 (양적긴축 QT 진행 척도)"
    )
    m2.caption(f"기준일: {metrics['latest_date']}")

    m3.metric(
        "재무부 일반계좌 (TGA)",
        f"${metrics['tga_b']:,.1f} B",
        help="미국 재무부의 국고 계좌 잔고. 정부가 지출하면 유동성 방출(+), 국채 발행으로 채우면 유동성 흡수(-)"
    )
    m3.caption(f"약 ${metrics['tga_b']/1000.0:.2f} T")

    m4.metric(
        "역레포 잔고 (ON RRP)",
        f"${metrics['rrp_b']:,.1f} B",
        help="시중 MMF 등이 연준에 맡긴 잉여 자금. 잔고가 줄어들면 시중 유동성 공급(+)"
    )
    m4.caption(f"약 ${metrics['rrp_b']/1000.0:.2f} T")

    st.divider()

    # 2. 탭별 상세 시각화
    tab1, tab2, tab3 = st.tabs([
        "📈 순유동성 vs 증시 지수 오버레이",
        "📊 순유동성 3대 구성요소 추이",
        "📖 연준 순유동성 작동 원리 & 가이드"
    ])

    # TAB 1: 오버레이 비교 차트
    with tab1:
        st.markdown("#### ⚙️ 오버레이 차트 조건 설정")
        col_c1, col_c2 = st.columns([1, 1])
        with col_c1:
            index_choice = st.selectbox("비교할 주가지수 선택", ["S&P 500 (^GSPC)", "나스닥 100 (^NDX)"], index=0)
            index_col = "SP500" if "S&P 500" in index_choice else "NASDAQ"
        with col_c2:
            period_choice = st.selectbox("조회 기간 선택", ["1년", "2년", "3년", "5년", "전체 (2020~)"], index=1)

        # 기간 필터링
        now = pd.Timestamp.now()
        if period_choice == "1년":
            sub_df = df[df.index >= (now - pd.DateOffset(years=1))]
        elif period_choice == "2년":
            sub_df = df[df.index >= (now - pd.DateOffset(years=2))]
        elif period_choice == "3년":
            sub_df = df[df.index >= (now - pd.DateOffset(years=3))]
        elif period_choice == "5년":
            sub_df = df[df.index >= (now - pd.DateOffset(years=5))]
        else:
            sub_df = df

        # 상관계수 계산
        valid_corr_df = sub_df.dropna(subset=['Net_Liquidity_T', index_col])
        corr_val = valid_corr_df['Net_Liquidity_T'].corr(valid_corr_df[index_col]) if len(valid_corr_df) > 10 else 0

        st.info(f"💡 선택 기간(`{period_choice}`) 동안 **연준 순유동성**과 **{index_choice}** 간의 상관계수는 **`{corr_val:.2f}`** 입니다. (1.0에 가까울수록 강한 양의 상관관계)", icon="ℹ️")

        fig_overlay = go.Figure()
        # 좌측 Y축: 순유동성
        fig_overlay.add_trace(go.Scatter(
            x=sub_df.index,
            y=sub_df['Net_Liquidity_T'],
            mode='lines',
            name='연준 순유동성 ($T)',
            line=dict(color='#00D2FF', width=2.5),
            fill='tozeroy',
            fillcolor='rgba(0, 210, 255, 0.08)'
        ))
        # 우측 Y축: 주가지수
        if index_col in sub_df.columns:
            fig_overlay.add_trace(go.Scatter(
                x=sub_df.index,
                y=sub_df[index_col],
                mode='lines',
                name=index_choice,
                line=dict(color='#FFA726', width=2),
                yaxis='y2'
            ))

        fig_overlay.update_layout(
            title=f"연준 순유동성 vs {index_choice} 동행 추이 ({period_choice})",
            xaxis_title="일자",
            yaxis=dict(
                title=dict(text="순유동성 ($T)", font=dict(color="#00D2FF")),
                tickfont=dict(color="#00D2FF")
            ),
            yaxis2=dict(
                title=dict(text=index_choice, font=dict(color="#FFA726")),
                tickfont=dict(color="#FFA726"),
                overlaying="y",
                side="right"
            ),
            hovermode="x unified",
            margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_overlay, use_container_width=True)

    # TAB 2: 구성요소 개별 분해 추이
    with tab2:
        st.markdown("#### 📊 순유동성 3대 구성요소 추이 ($T, 조 달러 기준)")
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Scatter(x=sub_df.index, y=sub_df['WALCL_T'], mode='lines', name='연준 총자산 (WALCL)', line=dict(color='#3B82F6', width=2)))
        fig_comp.add_trace(go.Scatter(x=sub_df.index, y=sub_df['TGA_T'], mode='lines', name='재무부 TGA 잔고', line=dict(color='#EF4444', width=2)))
        fig_comp.add_trace(go.Scatter(x=sub_df.index, y=sub_df['RRP_T'], mode='lines', name='역레포(ON RRP) 잔고', line=dict(color='#8B5CF6', width=2)))
        fig_comp.add_trace(go.Scatter(x=sub_df.index, y=sub_df['Net_Liquidity_T'], mode='lines', name='최종 순유동성 (합산)', line=dict(color='#10B981', width=3, dash='dot')))

        fig_comp.update_layout(
            title=f"연준 순유동성 구성 항목 분해 추이 ({period_choice})",
            xaxis_title="일자",
            yaxis_title="금액 ($T, 조 달러)",
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    # TAB 3: 해석 가이드 & 메커니즘
    with tab3:
        st.markdown("#### 📚 연준 순유동성(Net Liquidity)이란?")
        st.markdown("""
        전통적으로 시장은 연준의 기준금리에 주목하지만, **중기 증시(S&P 500 / 나스닥)의 밸류에이션과 방향성을 결정하는 실질적인 힘은 :blue-background['실제 시스템에 풀려 있는 달러 유동성의 크기']**입니다.

        연준 순유동성은 다음 공식으로 산출됩니다:
        """)
        st.latex(r"\text{Net Liquidity} = \text{Fed Total Assets (총자산)} - \text{TGA (재무부 국고)} - \text{ON RRP (역레포 잔고)}")

        st.markdown("---")
        st.markdown("#### 🔍 3대 핵심 변수의 메커니즘")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("##### 🏛️  1. 연준 총자산 (WALCL)")
            st.markdown("• :blue[**증가 시 **]: 양적완화(QE)로 시중에 직접 달러 공급 ➔ :green[**유동성 증가 (+)**]")
            st.markdown("• :blue[**감소 시 **]: 양적긴축(QT)으로 만기 채권 미재투자 ➔ :red[**유동성 흡수 (-)**]")

        with c2:
            st.markdown("##### 🏦 2. 재무부 일반계좌 (TGA)")
            st.markdown("• :blue[**잔고 증가 **]: 정부가 국채를 발행해 시장 돈을 흡수 ➔ :red[**유동성 감소 (-)**]")
            st.markdown("• :blue[**잔고 감소 **]: 정부가 재정 지출 및 보조금 집행 ➔ :green[**시장에 달러 방출 (+)**]")

        with c3:
            st.markdown("##### 🔄 3. 역레포 잔고 (ON RRP)")
            st.markdown("• :blue[**잔고 증가 **]: MMF가 돈을 굴릴 곳이 없어 연준에 예치 ➔ :red[**유동성 잠김 (-)**]")
            st.markdown("• :blue[**잔고 감소 **]: 예치금을 빼서 국채 매수 및 시중 투자 ➔ :green[**유동성 방출 (+)**]")

        st.markdown("---")
        st.markdown("#### 🎯 실전 투자 체크포인트")
        st.markdown("1. :green[**순유동성 증가 국면**] : 주식 시장의 밸류에이션(PER) 확장 및 성장주/테크주 랠리 가능성 고조.")
        st.markdown("2. :red[**순유동성 정체/감소 국면**] : 지수 상단 제한, 변동성 확대 및 방어주/현금 비중 확대 전략 유리.")
        st.markdown("3. :orange[**TGA 재충전 구간 주의**] : 부채한도 협상 타결 직후 재무부가 대규모 국채를 발행할 때 증시 단기 조정 압력 빈번.")
