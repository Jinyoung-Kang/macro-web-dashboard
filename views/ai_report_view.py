"""
views/ai_report_view.py
🤖 AI 종합 데이터 분석 & 결론 리포트
전체 메뉴의 데이터를 수집하여 AI로 분석 결과를 도출합니다.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import importlib
import pandas as pd
import streamlit as st
from services.ai_service import call_selected_ai_engine
from services.prompts import COMPREHENSIVE_REPORT_PROMPT

def safe_invoke(module_name: str, func_names: list, *args):
    """모듈 내에 존재하는 함수명을 다이나믹하게 찾아 실행하는 강력한 방어 로직"""
    try:
        mod = importlib.import_module(module_name)
        for fname in func_names:
            if hasattr(mod, fname):
                func = getattr(mod, fname)
                try:
                    return func(*args)
                except TypeError:
                    return func() # 인자 없이 재시도
    except Exception:
        pass
    return None

def build_comprehensive_context() -> str:
    """대시보드의 5대 핵심 모듈 데이터를 안전하게 취합하는 Context 빌더"""
    now_str = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    context = f"### [대시보드 전체 종합 데이터 (Global Market Aggregated Data)]\n- 데이터 수집 기준 시각: {now_str}\n\n"
    
    # 1. 거시경제 매크로 (리스트/튜플 언패킹 오류 완벽 차단)
    try:
        macro_result = safe_invoke('services.macro_service', ['get_collected_macro_data', 'fetch_macro_data'])
        macro_data_dict = {}
        
        # 반환값이 튜플, 리스트, 딕셔너리 중 어떤 것이든 딕셔너리 데이터만 정밀 타겟팅
        if isinstance(macro_result, (tuple, list)):
            for item in macro_result:
                if isinstance(item, dict) and len(item) > 0 and isinstance(list(item.values())[0], dict):
                    macro_data_dict = item
                    break
        elif isinstance(macro_result, dict):
            macro_data_dict = macro_result
            
        if macro_data_dict:
            context += "#### 1. 거시경제 매크로 지표\n"
            for cat, items in macro_data_dict.items():
                if not isinstance(items, dict): continue
                context += f"- {cat}\n"
                for name, info in items.items():
                    price = info.get("price", "N/A") if isinstance(info, dict) else "N/A"
                    pct = info.get("change_pct", "0.0") if isinstance(info, dict) else "0.0"
                    context += f"  * {name}: {price} ({pct}%)\n"
        else:
            context += "#### 1. 거시경제 매크로 지표\n- 데이터 로드 실패 (데이터 형식 불일치)\n"
    except Exception as e:
        context += f"#### 1. 거시경제 매크로 지표\n- 데이터 로드 실패: {e}\n"

    # 2. 연준 유동성
    try:
        df_liq = safe_invoke('services.liquidity_service', ['get_fed_liquidity_data', 'get_liquidity_data', 'fetch_liquidity'])
        if df_liq is not None and isinstance(df_liq, pd.DataFrame) and not df_liq.empty:
            last_liq = df_liq.iloc[-1]
            date_str = last_liq['Date'].strftime('%Y-%m-%d') if hasattr(last_liq['Date'], 'strftime') else last_liq['Date']
            context += f"\n#### 2. 연준 순유동성 트래커\n"
            context += f"- 기준일: {date_str} (가장 최근 데이터)\n"
            context += f"- 연준 총자산: ${last_liq.get('WALCL', 0)/1e9:.1f}B\n"
            context += f"- TGA: ${last_liq.get('WTREGEN', 0)/1e9:.1f}B\n"
            context += f"- 역레포(ON RRP): ${last_liq.get('RRPONTSYD', 0)/1e9:.1f}B\n"
            context += f"- 순유동성: ${last_liq.get('Net_Liquidity', 0)/1e9:.1f}B\n"
        else:
            context += "\n#### 2. 연준 순유동성 트래커\n- 최근 데이터를 찾을 수 없습니다.\n"
    except Exception as e:
        context += f"\n#### 2. 연준 순유동성 트래커\n- 로드 실패: {e}\n"

    # 3. 섹터 로테이션
    try:
        sec_perf = safe_invoke('services.sector_service', ['get_sector_performance', 'get_sector_data'], "1mo")
        df_s = None
        if isinstance(sec_perf, dict) and "sector" in sec_perf:
            df_s = sec_perf["sector"]
        elif isinstance(sec_perf, pd.DataFrame):
            df_s = sec_perf
            
        if df_s is not None and not df_s.empty:
            context += "\n#### 3. 11대 섹터 로테이션 (최근 1개월 수익률 Top 5)\n"
            for _, r in df_s.head(5).iterrows():
                context += f"- {r.get('Sector', r.get('섹터', 'Unknown'))}: {r.get('Return', r.get('수익률', 0)):.2f}%\n"
        else:
            context += "\n#### 3. 섹터 로테이션\n- 데이터를 찾을 수 없습니다.\n"
    except Exception as e:
        context += f"\n#### 3. 섹터 로테이션\n- 로드 실패: {e}\n"

    # 4. 글로벌 스마트머니 (COT)
    try:
        df_cot = safe_invoke('services.cot_service', ['get_cot_history', 'get_cot_data', 'fetch_cot_history'], "099741")
        if df_cot is not None and isinstance(df_cot, pd.DataFrame) and not df_cot.empty:
            last_cot = df_cot.iloc[-1]
            date_str = last_cot['Date'].strftime('%Y-%m-%d') if hasattr(last_cot['Date'], 'strftime') else last_cot['Date']
            context += f"\n#### 4. S&P 500 COT 스마트머니 포지션\n"
            context += f"- 기준일: {date_str} (가장 최근 확정치)\n"
            context += f"- 딜러(헤저) 순포지션: {last_cot.get('Dealer_Net', 0):,}\n"
            context += f"- 투기(스마트머니) 순포지션: {last_cot.get('Asset_Mgr_Net', 0):,}\n"
            context += f"- COT 과열/침체 인덱스: {last_cot.get('COT_Index', 0):.1f}%\n"
        else:
            context += "\n#### 4. 글로벌 스마트머니 COT\n- 최근 데이터를 찾을 수 없습니다.\n"
    except Exception as e:
        context += f"\n#### 4. 글로벌 스마트머니 COT\n- 로드 실패: {e}\n"

    # 5. 국내 파생 수급 (KRX)
    try:
        df_krx = safe_invoke('services.krx_service', ['get_krx_futures_history', 'get_futures_data'], 20)
        if df_krx is not None and isinstance(df_krx, pd.DataFrame) and not df_krx.empty:
            last_krx = df_krx.iloc[-1]
            date_str = last_krx['Date'].strftime('%Y-%m-%d') if hasattr(last_krx['Date'], 'strftime') else last_krx['Date']
            context += f"\n#### 5. 국내 KOSPI 200 파생 & 미결제약정 수급\n"
            context += f"- 기준일: {date_str} (최근 영업일)\n"
            context += f"- 선물 종가: {last_krx.get('Futures_Close', 0)} pt ({last_krx.get('Change_Pct', 0):+.2f}%)\n"
            context += f"- 시장 베이시스: {last_krx.get('Market_Basis', 0):+.2f} pt\n"
            context += f"- 미결제약정: {last_krx.get('Open_Interest', 0):,} 계약\n"
            context += f"- 파생 수급 국면: {last_krx.get('Market_Phase', '')}\n"
            context += f"- 한국판 COT Index: {last_krx.get('COT_OI_Index', 0):.1f}%\n"
        else:
            context += "\n#### 5. 국내 파생 수급\n- 파생 데이터를 찾을 수 없습니다.\n"
            
        df_inv = safe_invoke('services.krx_service', ['get_krx_investor_derivatives_summary', 'get_investor_summary'])
        if df_inv is not None and isinstance(df_inv, pd.DataFrame) and not df_inv.empty:
            context += "- 주요 투자자 20일 누적 순매수:\n"
            for _, r in df_inv.iterrows():
                context += f"  * {r.get('투자 주체', '')}: {r.get('20일 누적', r.get('20일 누적 순매수 (계약)', 0)):+,} 계약\n"
    except Exception as e:
        context += f"\n#### 5. 국내 파생 수급\n- 로드 실패: {e}\n"
        
    return context


def render_ai_report_view():
    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    
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
                
                # 리포트 상단에 기준 시각 강제 고정 삽입
                report_header = f"**[📅 데이터 수집 및 분석 기준 시각: {now_kst}]**\n\n"
                st.markdown(report_header + res.get("response", "데이터 처리에 실패했습니다."))
                
            with st.expander("🔍 AI에게 전달된 원본 통합 데이터(Context) 확인"):
                st.code(context_data, language="markdown")
