# views/consensus_view.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from services.sec_service import load_all_institutions_data, calculate_consensus
from services.ai_service import call_selected_ai_engine
from services.prompts import SEC_13F_CONSENSUS_PROMPT

def render_consensus_view():
    st.title("🤝 기관 13F Money 교집합 분석")
    st.caption("SEC Form 13F 공시 데이터를 기반으로 글로벌 대형 기관들의 공통 포지셔닝(Consensus)을 분석합니다.")
    st.divider()

    with st.spinner("SEC 13F 기관 공시 데이터를 로드하는 중..."):
        inst_data = load_all_institutions_data()

    if not inst_data:
        st.error("13F 데이터를 불러올 수 없습니다. 네트워크 연결 또는 데이터 소스를 확인해 주세요.")
        return

    consensus_df = calculate_consensus(inst_data)

    if consensus_df.empty:
        st.info("현재 공통으로 보유한 종목 데이터가 없습니다.")
        return

    # ==========================================
    # 🤖 [신규] SEC 13F 기관 Money 교집합 기반 투자 테마 요약 (AI)
    # ==========================================
    st.subheader("💡 SEC 13F 기관 Money 교집합 기반 투자 테마 요약 (13F Consensus Summary)")
    st.markdown(
        "대형 기관 및 슈퍼 인베스터들이 최근 공통으로 보유·확대한 종목군을 바탕으로, "
        "**글로벌 스마트머니의 핵심 투자 내러티브와 공통 철학**을 AI가 구조화하여 분석합니다."
    )

    col_ai_sel, col_ai_btn = st.columns([2, 1])
    with col_ai_sel:
        ai_engine = st.selectbox(
            "분석에 사용할 AI 엔진을 선택하세요",
            [
                "🛡️ 자동 탐색 (4단 Failover 무중단)",
                "🥇 1순위: NVIDIA Nemotron-3 Super (120B)",
                "🥈 2순위: Cloudflare AI (DeepSeek-R1-32B)",
                "🥉 3순위: NVIDIA GPT-OSS-20B",
                "🏅 4순위: Cerebras Cloud (GPT-OSS-120B)"
            ],
            key="consensus_ai_engine_select"
        )
    with col_ai_btn:
        st.write("")
        run_13f_ai = st.button("🚀 13F 스마트머니 테마 분석 실행", type="primary", use_container_width=True)

    if run_13f_ai:
        # 상위 교집합 종목 20개 추출하여 AI에게 전달
        top_consensus = consensus_df.head(20)
        summary_lines = []
        for _, row in top_consensus.iterrows():
            holders_str = ", ".join(row.get("Holders", [])) if isinstance(row.get("Holders"), list) else str(row.get("Holders", ""))
            summary_lines.append(
                f"- 종목명: {row.get('Name', 'N/A')} ({row.get('Ticker', 'N/A')}) | "
                f"보유 기관 수: {row.get('Institution_Count', 0)}개 기관 | "
                f"평균 비중: {row.get('Avg_Weight', 0):.2f}% | "
                f"주요 보유 기관: {holders_str}"
            )
        
        context_data = "\n".join(summary_lines)
        user_prompt = (
            f"[최신 SEC 13F 대형 기관 공통 보유 상위 종목 현황]:\n"
            f"{context_data}\n\n"
            f"위 13F 공통 매수 데이터를 심층 분석하여 글로벌 기관들의 핵심 투자 내러티브와 공통 철학을 구조화된 형식으로 작성해줘."
        )

        with st.spinner(f"'{ai_engine}' 엔진으로 13F 스마트머니 내러티브를 분석 중..."):
            res = call_selected_ai_engine(ai_engine, user_prompt, SEC_13F_CONSENSUS_PROMPT)

        if res["status"]:
            st.success(f"✅ 분석 완료 (엔진: {res['provider']} | 지연시간: {res['latency_ms']} ms)")
            if "translation_info" in res:
                st.caption(f"**번역 상태:** {res['translation_info']}")
            st.markdown(f"<div style='padding:1rem; border-radius:0.5rem; background-color:rgba(0,100,255,0.1);'>{res['response']}</div>", unsafe_allow_html=True)
        else:
            st.error("🔴 분석 생성 실패")
            st.caption(res["response"])

    st.divider()

    # ==========================================
    # 1. 시각화: 상위 교집합 종목 버블 차트 (기존 원본 복원)
    # ==========================================
    st.subheader("💡 주요 기관 공통 보유 종목 시각화 (Top 20)")
    st.caption("원의 크기는 '보유 기관 수', 색상은 '평균 포트폴리오 비중'을 나타냅니다.")
    
    top_bubble_df = consensus_df.head(20).copy()
    
    # Plotly 버블 차트 생성
    fig = px.scatter(
        top_bubble_df,
        x="Institution_Count",
        y="Avg_Weight",
        size="Institution_Count",
        color="Avg_Weight",
        hover_name="Name",
        hover_data={
            "Ticker": True,
            "Institution_Count": True,
            "Avg_Weight": ":.2f%",
            "Holders": False
        },
        text="Ticker",
        color_continuous_scale="Viridis",
        size_max=40
    )

    fig.update_traces(
        textposition='top center',
        marker=dict(line=dict(width=1, color='DarkSlateGrey')),
        hovertemplate="<b>%{hovertext}</b> (%{customdata[0]})<br>" +
                      "보유 기관 수: %{x}개<br>" +
                      "평균 비중: %{y:.2f}%<extra></extra>"
    )

    fig.update_layout(
        height=500,
        xaxis_title="보유 기관 수 (Institution Count)",
        yaxis_title="기관 평균 포트폴리오 비중 (%)",
        xaxis=dict(tickmode='linear', tick0=1, dtick=1),
        margin=dict(l=20, r=20, t=40, b=20),
        coloraxis_colorbar=dict(title="평균 비중(%)")
    )

    st.plotly_chart(fig, use_container_width=True)
    st.divider()

    # ==========================================
    # 2. 13F Consensus 메인 데이터 테이블 (기존 원본 복원)
    # ==========================================
    st.subheader("📊 기관 공통 보유 종목 상세 (Consensus Top Holdings)")
    
    display_df = consensus_df.copy()
    if "Holders" in display_df.columns:
        display_df["Holders"] = display_df["Holders"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
        
    display_df.columns = ["종목명 (Issuer)", "티커", "보유 기관 수", "평균 비중 (%)", "주요 보유 기관"]
    display_df["평균 비중 (%)"] = display_df["평균 비중 (%)"].map("{:.2f}%".format)
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
