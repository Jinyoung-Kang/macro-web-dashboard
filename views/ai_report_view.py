"""
views/ai_report_view.py
🤖 AI 종합 데이터 분석 & 결론 리포트
전체 메뉴의 데이터를 수집하여 AI로 분석 결과를 도출합니다.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd
from services.ai_service import call_selected_ai_engine
from services.prompts import COMPREHENSIVE_REPORT_PROMPT

def build_comprehensive_context() -> str:
    """대시보드의 5대 핵심 모듈 데이터를 안전하게 취합하는 Context 빌더"""
    now_str = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    context = f"### [대시보드 전체 종합 데이터 (Global Market Aggregated Data)]\n- 데이터 수집 기준 시각: {now_str}\n\n"
    
    # 1. 거시경제 매크로 (언패킹 오류 방지)
    try:
        from services.macro_service import get_collected_macro_data
        # get_collected_macro_data()는 (collected_data, r10_c, r10_p, r2_c, r2_p) 형태의 튜플을 반환
        macro_result = get_collected_macro_data()
        
        # 첫 번째 요소가 실제 딕셔너리인지 안전하게 검증
        if isinstance(macro_result, tuple) and len(macro_result) >= 1 and isinstance(macro_result[0], dict):
            macro_data_dict = macro_result[0]
            context += "#### 1. 거시경제 매크로 지표\n"
            for cat, items in macro_data_dict.items():
                context += f"- {cat}\n"
                for name, info in items.items():
                    price = info.get("price", "N/A")
                    pct = info.get("change_pct", "N/A")
                    context += f"  * {name}: {price} ({pct}%)\n"
        else:
            context += "#### 1. 거시경제 매크로 지표\n- 데이터 형식이 올바르지 않아 매크로 지표를 로드할 수 없습니다.\n"
    except Exception as e:
        context += f"#### 1. 거시경제 매크로 지표\n- 데이터 로드 실패: {e}\n"

    # 2. 연준 유동성
    try:
        from services.liquidity_service import get_fed_liquidity_data
        df_liq = get_fed_liquidity_data()
        if not df_liq.empty:
            last_liq = df_liq.iloc[-1]
            date_str = last_liq['Date'].strftime('%Y-%m-%d') if hasattr(last_liq['Date'], 'strftime') else last_liq['Date']
            context += f"\n#### 2. 연준 순유동성 트래커\n"
            context += f"- 기준일: {date_str}\n"
            context += f"- 연준 총자산: ${last_liq.get('WALCL', 0)/1e9:.1f}B\n"
            context += f"- TGA: ${last_liq.get('WTREGEN', 0)/1e9:.1f}B\n"
            context += f"- 역레포(ON RRP): ${last_liq.get('RRPONTSYD', 0)/1e9:.1f}B\n"
            context += f"- 순유동성: ${last_liq.get('Net_Liquidity', 0)/1e9:.1f}B\n"
    except Exception as e:
        context += f"\n#### 2. 연준 순유동성 트래커\n- 로드 실패: {e}\n"

    # 3. 섹터 로테이션
    try:
        from services.sector_service import get_sector_performance
        sec_perf = get_sector_performance("1mo")
        if isinstance(sec_perf, dict) and not sec_perf.get("sector", pd.DataFrame()).empty:
            df_s = sec_perf["sector"]
            context += "\n#### 3. 11대 섹터 로테이션 (최근 1개월 수익률 Top 5)\n"
            for _, r in df_s.head(5).iterrows():
                context += f"- {r.get('Sector', '')}: {r.get('Return', 0):.2f}%\n"
    except Exception as e:
        context += f"\n#### 3. 섹터 로테이션\n- 로드 실패: {e}\n"

    # 4. 글로벌 스마트머니 (COT)
    try:
        from services.cot_service import get_cot_history
        df_cot = get_cot_history("099741") # S&P 500
        if not df_cot.empty:
            last_cot = df_cot.iloc[-1]
            date_str = last_cot['Date'].strftime('%Y-%m-%d') if hasattr(last_cot['Date'], 'strftime') else last_cot['Date']
            context += f"\n#### 4. S&P 500 COT 스마트머니 포지션\n"
            context += f"- 기준일: {date_str}\n"
            context += f"- 딜러(헤저) 순포지션: {last_cot.get('Dealer_Net', 0):,}\n"
            context += f"- 투기(스마트머니) 순포지션: {last_cot.get('Asset_Mgr_Net', 0):,}\n"
            context += f"- COT 과열/침체 인덱스: {last_cot.get('COT_Index', 0):.1f}%\n"
    except Exception as e:
        context += f"\n#### 4. 글로벌 스마트머니 COT\n- 로드 실패: {e}\n"

    # 5. 국내 파생 수급 (KRX)
    try:
        from services.krx_service import get_krx_futures_history, get_krx_investor_derivatives_summary
        df_krx = get_krx_futures_history(20)
        if not df_krx.empty:
            last_krx = df_krx.iloc[-1]
            date_str = last_krx['Date'].strftime('%Y-%m-%d') if hasattr(last_krx['Date'], 'strftime') else last_krx['Date']
            context += f"\n#### 5. 국내 KOSPI 200 파생 & 미결제약정 수급\n"
            context += f"- 기준일: {date_str}\n"
            context += f"- 선물 종가: {last_krx.get('Futures_Close', 0)} pt ({last_krx.get('Change_Pct', 0):+.2f}%)\n"
            context += f"- 시장 베이시스: {last_krx.get('Market_Basis', 0):+.2f} pt\n"
            context += f"- 미결제약정: {last_krx.get('Open_Interest', 0):,} 계약\n"
            context += f"- 파생 수급 국면: {last_krx.get('Market_Phase', '')}\n"
            context += f"- 한국판 COT Index: {last_krx.get('COT_OI_Index', 0):.1f}%\n"
        
        df_inv = get_krx_investor_derivatives_summary()
        if not df_inv.empty:
            context += "- 주요 투자자 20일 누적 순매수:\n"
            for _, r in df_inv.iterrows():
                context += f"  * {r.get('투자 주체', '')}: {r.get('20일 누적', 0):+,} 계약\n"
    except Exception as e:
        context += f"\n#### 5. 국내 파생 수급\n- 로드 실패: {e}\n"
        
    return context


def render_ai_report_view():
    st.markdown("""
    <div style="padding: 4px 0 12px 0;">
        <h2 style="margin:0; font-weight: 700; color: #F0F6FC;">
            🤖 AI 종합 데이터 분석 & 결론 리포트
        </h2>
        <p style="margin: 4px 0 0 0; color: #8B949E; font-size: 0.92rem;">
            거시경제, 연준 유동성, 로테이션, 글로벌 COT, 국내 파생 등 대시보드 내 모든 데이터를 수집하여 통합 인사이트를 도출합니다.
        </p>
    </div>
    """, unsafe_allow_html=True)

    engine_options = [
        "자동 탐색 (Failover 무중단)",
        "NVIDIA NIM (Nemotron-3-Super)",
        "Cloudflare (DeepSeek-R1 번역)",
        "NVIDIA NIM (GPT-OSS-20B)",
        "Cerebras Cloud (Llama-3.3)"
    ]
    
    c1, c2 = st.columns([1, 2])
    with c1:
        selected_engine = st.selectbox("AI 분석 엔진 선택", options=engine_options, index=0)

    if st.button("🧠 전체 데이터 스캔 및 종합 AI 리포트 생성", use_container_width=True):
        with st.spinner(f"[{selected_engine}] 대시보드의 모든 실시간/확정 데이터를 취합하여 정밀 퀀트 분석을 수행하고 있습니다..."):
            context_data = build_comprehensive_context()
            res = call_selected_ai_engine(selected_engine, prompt=context_data, system_prompt=COMPREHENSIVE_REPORT_PROMPT)
            
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                step_info = res.get("pipeline_step", "단일 호출 완료")
                st.caption(f"⚡ **실행 엔진 파이프라인**: `{step_info}`")
                st.divider()
                st.markdown(res.get("response", "데이터 처리에 실패했습니다."))
                
            with st.expander("🔍 AI에게 전달된 원본 통합 데이터(Context) 확인"):
                st.code(context_data, language="markdown")
