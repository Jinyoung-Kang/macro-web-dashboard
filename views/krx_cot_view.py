"""
views/krx_cot_view.py
🇰🇷 국내 파생상품 수급 & COT 한국판 대시보드 뷰
KOSPI 200 선물, 미결제약정(OI), 베이시스, 투자자별 포지션 분석
"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from config import KRX_AUTH_KEY
from services.krx_service import get_krx_futures_history, get_krx_investor_derivatives_summary
from services.ai_service import ask_investment_agent

def render_krx_cot_view():
    st.markdown("""
    <div style="padding: 12px 0 20px 0;">
        <h2 style="margin:0; font-weight: 700; color: #F0F6FC;">
            🇰🇷 국내 파생상품 수급 & COT 한국판
        </h2>
        <p style="margin: 4px 0 0 0; color: #8B949E; font-size: 0.92rem;">
            KRX KOSPI 200 선물, 미결제약정(Open Interest) 4대 국면, 시장 베이시스 및 스마트머니(외국인) 포지션 분석
        </p>
    </div>
    """, unsafe_allow_html=True)

    if not KRX_AUTH_KEY:
        st.info("💡 **KRX OPEN API 인증키가 미등록 상태입니다.** 현재 KODEX 200 기반 프록시 시뮬레이션 모드로 작동 중입니다. 정밀한 원장 데이터를 연동하려면 `.streamlit/secrets.toml`에 `[krx] api_key = '...'`를 추가하세요.")

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        lookback_days = st.selectbox(
            "조회 기간 (영업일)",
            options=[20, 40, 60, 90],
            index=1,
            help="선물 시계열 및 미결제약정 누적 추적 기간을 선택합니다."
        )
    with c2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.caption("🟢 장마감 확정 데이터 기준 (KRX Data Marketplace)")
    with c3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 데이터 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    df_hist = get_krx_futures_history(days=lookback_days)
    df_investors = get_krx_investor_derivatives_summary()

    if df_hist.empty:
        st.warning("⚠️ 파생상품 시계열 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
        return

    latest = df_hist.iloc[-1]
    prev = df_hist.iloc[-2] if len(df_hist) > 1 else latest

    # 메트릭스 카드
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(
            label="KOSPI 200 선물 최근월물",
            value=f"{latest['Futures_Close']:,.2f} pt",
            delta=f"{latest['Change_Pct']:+.2f}%"
        )
    with m2:
        oi_delta = latest["Open_Interest"] - prev["Open_Interest"]
        st.metric(
            label="미결제약정 (Open Interest)",
            value=f"{int(latest['Open_Interest']):,} 계약",
            delta=f"{int(oi_delta):+,} 계약"
        )
    with m3:
        basis_state = "콘탱고 (정배열)" if latest["Market_Basis"] >= 0 else "백워데이션 (역배열)"
        st.metric(
            label="시장 베이시스 (Basis)",
            value=f"{latest['Market_Basis']:+.2f} pt",
            delta=basis_state,
            delta_color="normal" if latest["Market_Basis"] >= 0 else "inverse"
        )
    with m4:
        st.metric(
            label="파생 수급 국면 (Phase)",
            value=latest["Market_Phase"].split(" ")[0] + " " + latest["Market_Phase"].split(" ")[1],
            delta=f"COT Index {latest['COT_OI_Index']:.1f}%"
        )

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # 복합 차트
    st.markdown("#### 📈 KOSPI 200 선물 가격 & 미결제약정(OI) 추이")
    
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.55, 0.25, 0.20],
        subplot_titles=(
            "KOSPI 200 선물 지수 vs 미결제약정 시계열",
            "시장 베이시스 (Market Basis = 선물 - 이론가/현물)",
            "일별 거래량 (Volume)"
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_hist["Date"],
            y=df_hist["Futures_Close"],
            name="선물 종가 (pt)",
            line=dict(color="#58A6FF", width=2.5),
            mode="lines+markers"
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=df_hist["Date"],
            y=df_hist["Open_Interest"],
            name="미결제약정 (OI)",
            line=dict(color="#E3B341", width=2, dash="dot"),
            yaxis="y2"
        ),
        row=1, col=1
    )

    basis_colors = ["#238636" if b >= 0 else "#DA3633" for b in df_hist["Market_Basis"]]
    fig.add_trace(
        go.Bar(
            x=df_hist["Date"],
            y=df_hist["Market_Basis"],
            name="시장 베이시스",
            marker_color=basis_colors
        ),
        row=2, col=1
    )

    fig.add_trace(
        go.Bar(
            x=df_hist["Date"],
            y=df_hist["Volume"],
            name="거래량",
            marker_color="#8B949E"
        ),
        row=3, col=1
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0D1117",
        plot_bgcolor="#161B22",
        height=720,
        margin=dict(l=40, r=40, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified"
    )
    
    fig.update_yaxes(title_text="선물 지수 (pt)", row=1, col=1, gridcolor="#21262D")
    fig.update_yaxes(title_text="베이시스", row=2, col=1, gridcolor="#21262D")
    fig.update_yaxes(title_text="계약 수", row=3, col=1, gridcolor="#21262D")

    st.plotly_chart(fig, use_container_width=True)

    # 국면 매트릭스 & 포지션 테이블
    col_left, col_right = st.columns([1.2, 1])

    with col_left:
        st.markdown("#### 🧭 미결제약정(OI) 4대 국면 진단 매트릭스")
        st.markdown("""
        <div style="background-color:#161B22; border:1px solid #30363D; border-radius:8px; padding:16px; font-size:0.88rem;">
            <table style="width:100%; text-align:left; border-collapse: collapse; color:#C9D1D9;">
                <tr style="border-bottom: 1px solid #30363D; color:#8B949E;">
                    <th style="padding:6px;">구분</th>
                    <th style="padding:6px;">선물 가격</th>
                    <th style="padding:6px;">미결제약정</th>
                    <th style="padding:6px;">시장 함의</th>
                </tr>
                <tr style="border-bottom: 1px solid #21262D; background-color: rgba(35, 134, 54, 0.15);">
                    <td style="padding:8px; font-weight:bold; color:#3FB950;">신규 롱 진입</td>
                    <td>상승 (▲)</td>
                    <td>증가 (▲)</td>
                    <td>강한 상승 추세 확산 (스마트머니 롱 베팅)</td>
                </tr>
                <tr style="border-bottom: 1px solid #21262D; background-color: rgba(218, 54, 51, 0.15);">
                    <td style="padding:8px; font-weight:bold; color:#F85149;">신규 숏 진입</td>
                    <td>하락 (▼)</td>
                    <td>증가 (▲)</td>
                    <td>강한 하락 압력 확산 (신규 숏 포지션 누적)</td>
                </tr>
                <tr style="border-bottom: 1px solid #21262D; background-color: rgba(227, 179, 65, 0.15);">
                    <td style="padding:8px; font-weight:bold; color:#D29922;">숏 커버링</td>
                    <td>상승 (▲)</td>
                    <td>감소 (▼)</td>
                    <td>공매도/숏 포지션 환매수로 인한 일시적 반등</td>
                </tr>
                <tr style="background-color: rgba(139, 148, 158, 0.15);">
                    <td style="padding:8px; font-weight:bold; color:#8B949E;">롱 청산</td>
                    <td>하락 (▼)</td>
                    <td>감소 (▼)</td>
                    <td>기존 롱 포지션 손절/차익실현, 바닥 다지기 가능성</td>
                </tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="margin-top:12px; padding:12px; border-left:4px solid #58A6FF; background-color:#161B22; border-radius:4px;">
            <div style="font-weight:600; color:#58A6FF;">현재 국면 진단 결과:</div>
            <div style="font-size:0.95rem; color:#F0F6FC; margin-top:3px;">
                👉 <strong>{latest['Market_Phase']}</strong> (최근 영업일 변동: 가격 {latest['Change_Pct']:+.2f}%, OI {latest['OI_Change']:+,.0f}계약)
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_right:
        st.markdown("#### 🏛️ 투자 주체별 선물 누적 수급 (추정)")
        st.dataframe(
            df_investors,
            use_container_width=True,
            hide_index=True,
            column_config={
                "당일 순매수 (계약)": st.column_config.NumberColumn(format="%+d"),
                "5일 누적 순매수 (계약)": st.column_config.NumberColumn(format="%+d"),
                "20일 누적 순매수 (계약)": st.column_config.NumberColumn(format="%+d"),
            }
        )

    # AI 브리핑
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 🤖 AI 파생 수급 & 스마트머니 종합 진단")

    if st.button("🧠 현재 파생 수급 기반 투자 가설 & 포지션 AI 검증", use_container_width=True):
        with st.spinner("한국 파생시장(KOSPI 200 선물, 베이시스, OI 국면) 데이터를 분석하여 AI 리포트를 생성하고 있습니다..."):
            prompt = f"""
            [국내 파생시장 실시간 수급 및 한국판 COT 진단]
            - KOSPI 200 선물 최근월물: {latest['Futures_Close']} pt (전일대비 {latest['Change_Pct']:+.2f}%)
            - 시장 베이시스: {latest['Market_Basis']:+.2f} pt ({basis_state})
            - 미결제약정(OI): {int(latest['Open_Interest']):,} 계약 (변동: {int(latest['OI_Change']):+,} 계약)
            - 현재 시장 국면: {latest['Market_Phase']}
            - 한국판 COT OI Index: {latest['COT_OI_Index']:.1f}% (0%=극단적 과매도/바닥, 100%=극단적 과열/천장)

            위 파생 수급 데이터를 기반으로 다음을 냉정하고 비판적으로 분석하라:
            1. 현재 선물 베이시스와 미결제약정 변화가 시사하는 코스피 현물 시장의 단기 방향성.
            2. 숏스퀴즈 가능성 또는 롱 트랩(상승 함정) 위험도 평가.
            3. 매크로 투자자가 취해야 할 실전 포트폴리오 리밸런싱 전략.
            """
            analysis_result = ask_investment_agent(prompt)
            st.markdown(f"""
            <div style="background-color:#161B22; border:1px solid #30363D; border-radius:8px; padding:18px; margin-top:10px; color:#C9D1D9; line-height:1.65;">
                {analysis_result}
            </div>
            """, unsafe_allow_html=True)
