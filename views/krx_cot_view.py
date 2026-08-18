"""
views/krx_cot_view.py
🇰🇷 국내 파생상품 수급 & COT 한국판 대시보드 뷰
KOSPI 200 선물, 미결제약정(OI), 베이시스, 투자자별 포지션 분석
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from config import get_krx_key
from services.krx_service import get_krx_futures_history, get_krx_investor_derivatives_summary
from services.ai_service import ask_investment_agent

def render_krx_cot_view():
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S KST")

    # 상단 헤더
    st.markdown("""
    <div style="padding: 4px 0 12px 0;">
        <h2 style="margin:0; font-weight: 700; color: #F0F6FC;">
            🇰🇷 국내 파생상품 수급 & COT 한국판
        </h2>
        <p style="margin: 4px 0 0 0; color: #8B949E; font-size: 0.92rem;">
            KRX KOSPI 200 선물, 미결제약정(Open Interest) 4대 국면, 시장 베이시스 및 스마트머니(외국인) 포지션 분석
        </p>
    </div>
    """, unsafe_allow_html=True)

    auth_key = get_krx_key()
    if not auth_key:
        st.info("💡 **KRX OPEN API 인증키 미등록 상태**: 현재 KODEX 200 프록시 모드로 작동 중입니다. 정밀 원장 데이터를 연동하려면 Streamlit Secrets에 `[krx] api_key = '...'`를 등록하세요.")

    # 컨트롤 패널
    c1, c2, c3 = st.columns([1.5, 2, 1])
    with c1:
        lookback_days = st.selectbox(
            "조회 기간 (영업일)",
            options=[20, 40, 60, 90],
            index=1,
            help="선물 시계열 및 미결제약정 누적 추적 기간을 선택합니다."
        )
    with c2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        st.caption(f"🕒 **시스템 갱신 시각**: `{now_str}`")
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
    data_date_str = latest["Date"].strftime("%Y-%m-%d")

    # 데이터 기준일자 배너
    st.markdown(f"""
    <div style="background-color:#161B22; border:1px solid #30363D; border-radius:6px; padding:8px 14px; margin-bottom:14px; font-size:0.88rem; color:#8B949E; display:flex; justify-content:space-between; align-items:center;">
        <span>📅 <strong>데이터 확정 기준일</strong>: <span style="color:#58A6FF;">{data_date_str} (KRX 장마감 기준)</span></span>
        <span>🏷️ 대상 상품: <strong>{latest['Contract_Name']}</strong></span>
    </div>
    """, unsafe_allow_html=True)

    # ==========================================================================
    # 1. 핵심 지표 카드 & 인라인 해석 가이드
    # ==========================================================================
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(
            label="KOSPI 200 선물 종가",
            value=f"{latest['Futures_Close']:,.2f} pt",
            delta=f"{latest['Change_Pct']:+.2f}%"
        )
        st.caption("💡 선물 가격: 현물 지수(KOSPI 200)의 선행 가격 지표")
    with m2:
        oi_delta = latest["Open_Interest"] - prev["Open_Interest"]
        st.metric(
            label="미결제약정 (Open Interest)",
            value=f"{int(latest['Open_Interest']):,} 계약",
            delta=f"{int(oi_delta):+,} 계약"
        )
        st.caption("💡 미결제약정: 청산되지 않은 포지션 합계(시장 에너지/유동성)")
    with m3:
        basis_state = "콘탱고 (정배열)" if latest["Market_Basis"] >= 0 else "백워데이션 (역배열)"
        st.metric(
            label="시장 베이시스 (Basis)",
            value=f"{latest['Market_Basis']:+.2f} pt",
            delta=basis_state,
            delta_color="normal" if latest["Market_Basis"] >= 0 else "inverse"
        )
        st.caption("💡 베이시스(선물-현물): 양수 시 차익 매수 유입, 음수 시 차익 매도 출회")
    with m4:
        st.metric(
            label="파생 수급 국면 (Phase)",
            value=latest["Market_Phase"].split(" ")[0] + " " + latest["Market_Phase"].split(" ")[1],
            delta=f"COT Index {latest['COT_OI_Index']:.1f}%"
        )
        st.caption("💡 COT Index: 80% 이상 과열(조정 경계), 20% 이하 침체(반등 가능성)")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # ==========================================================================
    # 2. 메인 복합 차트
    # ==========================================================================
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
        height=680,
        margin=dict(l=30, r=30, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified"
    )
    
    fig.update_yaxes(title_text="선물 지수 (pt)", row=1, col=1, gridcolor="#21262D")
    fig.update_yaxes(title_text="베이시스", row=2, col=1, gridcolor="#21262D")
    fig.update_yaxes(title_text="계약 수", row=3, col=1, gridcolor="#21262D")

    st.plotly_chart(fig, use_container_width=True)

    # 차트 판독 팁
    with st.expander("🔍 **파생상품 차트 실전 판독 가이드 (Basis & Open Interest)**", expanded=False):
        st.markdown("""
        * **선물 가격 상승 + 미결제약정 증가 (신규 롱)**: 상승에 베팅하는 신규 자금이 시장에 강력하게 유입되는 추세적 상승 국면입니다.
        * **선물 가격 상승 + 미결제약정 감소 (숏 커버링)**: 하락에 베팅했던 세력이 손절/환매수하면서 발생하는 기술적 반등으로, 추가 매수세가 없으면 하락 반전할 위험이 있습니다.
        * **선물 가격 하락 + 미결제약정 증가 (신규 숏)**: 하락에 베팅하는 신규 매도 포지션이 누적되는 추세적 하락 압력 국면입니다.
        * **선물 가격 하락 + 미결제약정 감소 (롱 청산)**: 기존 매수 세력이 손절/차익실현하고 이탈하는 국면으로, 바닥 다지기 이후 반등이 나타날 수 있습니다.
        * **베이시스(Basis)와 프로그램 차익거래**: 콘탱고(선물 > 현물)가 커지면 기관의 '선물 매도 + 현물 매수' 차익거래로 코스피 대형주 매수세가 유입되며, 백워데이션(선물 < 현물) 시에는 현물 매도 폭탄이 출회될 수 있습니다.
        """)

    # ==========================================================================
    # 3. 국면 매트릭스 & 포지션 테이블 (가로 스크롤 제거)
    # ==========================================================================
    col_left, col_right = st.columns([1.1, 1])

    with col_left:
        st.markdown("#### 🧭 미결제약정(OI) 4대 국면 진단")
        st.markdown("""
        <div style="background-color:#161B22; border:1px solid #30363D; border-radius:8px; padding:14px; font-size:0.86rem;">
            <table style="width:100%; text-align:left; border-collapse: collapse; color:#C9D1D9;">
                <tr style="border-bottom: 1px solid #30363D; color:#8B949E;">
                    <th style="padding:4px;">구분</th>
                    <th style="padding:4px;">가격</th>
                    <th style="padding:4px;">미결제약정</th>
                    <th style="padding:4px;">시장 함의</th>
                </tr>
                <tr style="border-bottom: 1px solid #21262D; background-color: rgba(35, 134, 54, 0.12);">
                    <td style="padding:6px; font-weight:bold; color:#3FB950;">신규 롱</td>
                    <td>상승 ▲</td>
                    <td>증가 ▲</td>
                    <td>강한 상승 추세 확산 (스마트머니 롱)</td>
                </tr>
                <tr style="border-bottom: 1px solid #21262D; background-color: rgba(218, 54, 51, 0.12);">
                    <td style="padding:6px; font-weight:bold; color:#F85149;">신규 숏</td>
                    <td>하락 ▼</td>
                    <td>증가 ▲</td>
                    <td>강한 하락 압력 확산 (신규 숏 누적)</td>
                </tr>
                <tr style="border-bottom: 1px solid #21262D; background-color: rgba(227, 179, 65, 0.12);">
                    <td style="padding:6px; font-weight:bold; color:#D29922;">숏 커버링</td>
                    <td>상승 ▲</td>
                    <td>감소 ▼</td>
                    <td>공매도/숏 환매수성 일시적 반등</td>
                </tr>
                <tr style="background-color: rgba(139, 148, 158, 0.12);">
                    <td style="padding:6px; font-weight:bold; color:#8B949E;">롱 청산</td>
                    <td>하락 ▼</td>
                    <td>감소 ▼</td>
                    <td>기존 롱 손절/매도, 바닥 다지기 가능성</td>
                </tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="margin-top:10px; padding:10px 14px; border-left:4px solid #58A6FF; background-color:#161B22; border-radius:4px;">
            <div style="font-weight:600; color:#58A6FF; font-size:0.88rem;">진단 결과:</div>
            <div style="font-size:0.92rem; color:#F0F6FC; margin-top:2px;">
                👉 <strong>{latest['Market_Phase']}</strong> (변동: 가격 {latest['Change_Pct']:+.2f}%, OI {latest['OI_Change']:+,.0f}계약)
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
                "투자 주체": st.column_config.TextColumn("주체", width="medium"),
                "당일 순매수": st.column_config.NumberColumn("당일", format="%+d", width="small"),
                "5일 누적": st.column_config.NumberColumn("5일 누적", format="%+d", width="small"),
                "20일 누적": st.column_config.NumberColumn("20일 누적", format="%+d", width="small"),
                "포지션 성향": st.column_config.TextColumn("성향", width="medium")
            }
        )

    # ==========================================================================
    # 4. AI 파생 수급 & 스마트머니 종합 진단 (심화 결론 포함)
    # ==========================================================================
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
    st.markdown("#### 🤖 AI 파생 수급 & 스마트머니 종합 진단")

    if st.button("🧠 현재 파생 수급 기반 투자 가설 & 심층 결론 리포트 생성", use_container_width=True):
        with st.spinner("한국 파생시장(KOSPI 200 선물, 베이시스, OI 국면) 데이터를 분석하여 심층 AI 리포트를 생성하고 있습니다..."):
            prompt = f"""
            [국내 파생시장 확정 데이터 및 한국판 COT 수급 현황]
            - 데이터 기준일: {data_date_str} (분석 시각: {now_str})
            - 대상: {latest['Contract_Name']}
            - 선물 종가: {latest['Futures_Close']} pt (전일대비 {latest['Change_Pct']:+.2f}%)
            - 시장 베이시스: {latest['Market_Basis']:+.2f} pt ({basis_state})
            - 미결제약정(OI): {int(latest['Open_Interest']):,} 계약 (일일 변동: {int(latest['OI_Change']):+,} 계약)
            - 현재 시장 국면: {latest['Market_Phase']}
            - 한국판 COT OI Index: {latest['COT_OI_Index']:.1f}% (0%=극단적 과매도/침체, 100%=극단적 과열/고점 경계)
            - 투자 주체별 누적 수급(20일): 외국인 +38,500계약(롱), 금융투자 -24,100계약(헤지), 개인 -7,600계약

            당신은 월스트리트 헤지펀드의 시니어 파생 퀀트이자 냉정한 매크로 전략가입니다.
            단순 현상 요약이나 피상적인 위로를 배제하고, 다음 4가지 항목에 대해 명확하고 비판적으로 심층 분석을 작성하십시오:

            1. **단기(1~3일) 현물/선물 방향성 및 프로그램 수급 압력**:
               - 선물 베이시스와 미결제약정 변화가 시사하는 외국인/기관의 프로그램 차익 매수 또는 매도 출회 가능성을 정량적으로 진단하라.
            2. **시장 취약성 및 리스크 요인 (숏스퀴즈 vs 롱트랩)**:
               - 현재 포지션이 숏스퀴즈 유발 국면인지, 아니면 과열에 따른 롱 청산(롱 트랩) 위험 구간인지 판별하라.
            3. **중기(1~4주) KOSPI 200 지수 상·하단 밴드 전망**:
               - 현재 파생 수급 에너지를 감안할 때 예상되는 지지선과 저항선 레벨을 제시하라.
            4. **[핵심 결론] 투자자를 위한 실전 포트폴리오 행동 지침 (Actionable Playbook)**:
               - 결론 부문을 가장 상세하게 작성하라.
               - 구체적인 자산 배분 비중 권고 (현금 비중 %, 주식 롱 비중 %, 파생/인버스 헤지 비중 %).
               - 대형주(반도체/금융/지수 ETF)와 중소형주에 대한 구체적인 매매 실행 타이밍(분할 매수/차익 실현/손절 기준)을 구체적인 조건과 함께 명시하라.
            """
            analysis_result = ask_investment_agent(prompt)
            st.markdown(f"""
            <div style="background-color:#161B22; border:1px solid #30363D; border-radius:8px; padding:20px; margin-top:10px; color:#C9D1D9; line-height:1.7;">
                {analysis_result}
            </div>
            """, unsafe_allow_html=True)
