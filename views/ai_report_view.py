"""
views/ai_report_view.py
🤖 AI 종합 데이터 분석 & 결론 리포트
전체 메뉴의 데이터를 수집하여 AI로 분석 결과를 도출합니다.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import importlib
import inspect
import pandas as pd
import streamlit as st
from services.ai_service import call_selected_ai_engine
from services.prompts import COMPREHENSIVE_REPORT_PROMPT

def safe_load_dataframe(module_path: str, expected_func: str, *args):
    """함수명이 변경되었더라도 모듈 내에서 데이터프레임을 반환하는 함수를 찾아내는 무적 스캐너"""
    try:
        mod = importlib.import_module(module_path)
        
        # 1. 예상되는 함수명 우선 시도
        func = getattr(mod, expected_func, None)
        if func:
            try:
                res = func(*args) if args else func()
                if isinstance(res, pd.DataFrame) and not res.empty: return res
                if isinstance(res, dict) and 'sector' in res: return res['sector']
            except: pass
            
        # 2. 실패 시 모듈 내의 get_ 또는 fetch_ 로 시작하는 모든 함수 탐색 (Fallback)
        for name, obj in inspect.getmembers(mod, inspect.isfunction):
            if name.startswith('get_') or name.startswith('fetch_'):
                try:
                    res = obj(*args) if args else obj()
                    if isinstance(res, pd.DataFrame) and not res.empty: return res
                    if isinstance(res, dict) and 'sector' in res: return res['sector']
                except: pass
    except Exception as e:
        return f"모듈 로드 에러: {e}"
    return None


def build_comprehensive_context() -> str:
    """대시보드의 5대 핵심 모듈 데이터를 안전하게 취합하는 Context 빌더"""
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S KST")
    
    context = f"### [대시보드 전체 종합 데이터 (Global Market Aggregated Data)]\n"
    context += f"- 데이터 수집 기준 시각: {now_str}\n"
    context += f"- 💡 안내: 휴장일(주말/공휴일) 또는 실시간 데이터 지연 시, 각 지표별로 가장 최근의 확정 영업일 종가를 기준으로 데이터를 수집했습니다.\n\n"
    
    # 1. 거시경제 매크로 (언패킹 오류 완벽 차단)
    context += "#### 1. 거시경제 매크로 지표\n"
    try:
        import services.macro_service as ms
        res = None
        if hasattr(ms, 'get_collected_macro_data'): res = ms.get_collected_macro_data()
        elif hasattr(ms, 'fetch_macro_data'): res = ms.fetch_macro_data()
        
        macro_dict = {}
        if isinstance(res, (tuple, list)):
            for item in res:
                if isinstance(item, dict) and len(item) > 0:
                    first_val = list(item.values())[0]
                    if isinstance(first_val, dict):
                        macro_dict = item
                        break
        elif isinstance(res, dict):
            macro_dict = res
            
        if macro_dict:
            for cat, items in macro_dict.items():
                if not isinstance(items, dict): continue
                context += f"- {cat}\n"
                for name, info in items.items():
                    if isinstance(info, dict):
                        price = info.get("price", info.get("price_str", "N/A"))
                        pct = info.get("change_pct", info.get("delta_str", "0.0"))
                        context += f"  * {name}: {price} ({pct}%)\n"
        else:
            context += "- 매크로 데이터를 파싱할 수 없습니다.\n"
    except Exception as e:
        context += f"- 매크로 데이터 로드 실패: {e}\n"

    # 2. 연준 유동성 (가장 최근 영업일 데이터 추출)
    context += "\n#### 2. 연준 순유동성 트래커\n"
    df_liq = safe_load_dataframe('services.liquidity_service', 'get_fed_liquidity_data')
    if isinstance(df_liq, pd.DataFrame):
        last_liq = df_liq.iloc[-1]
        date_str = last_liq['Date'].strftime('%Y-%m-%d') if hasattr(last_liq, 'Date') and isinstance(last_liq['Date'], pd.Timestamp) else "가장 최근 영업일"
        
        walcl = last_liq.get('WALCL', 0)
        wtre = last_liq.get('WTREGEN', 0)
        rrp = last_liq.get('RRPONTSYD', 0)
        net_liq = last_liq.get('Net_Liquidity', walcl - wtre - rrp)
        
        context += f"- 기준일: {date_str}\n"
        context += f"- 연준 총자산: ${walcl/1e9:.1f}B\n"
        context += f"- TGA: ${wtre/1e9:.1f}B\n"
        context += f"- 역레포(ON RRP): ${rrp/1e9:.1f}B\n"
        context += f"- 순유동성: ${net_liq/1e9:.1f}B\n"
    else:
        context += f"- 로드 실패: {df_liq}\n"

    # 3. 섹터 로테이션
    context += "\n#### 3. 11대 섹터 로테이션 (최근 1개월 수익률)\n"
    df_sec = safe_load_dataframe('services.sector_service', 'get_sector_performance', '1mo')
    if isinstance(df_sec, pd.DataFrame):
        for _, r in df_sec.head(5).iterrows():
            sec_name = r.get('Sector', r.get('섹터', 'Unknown'))
            ret = r.get('Return', r.get('수익률', 0))
            context += f"- {sec_name}: {ret:.2f}%\n"
    else:
        context += f"- 로드 실패: {df_sec}\n"

    # 4. 글로벌 스마트머니 COT
    context += "\n#### 4. S&P 500 COT 스마트머니 포지션\n"
    df_cot = safe_load_dataframe('services.cot_service', 'get_cot_history', '099741')
    if isinstance(df_cot, pd.DataFrame):
        last_cot = df_cot.iloc[-1]
        date_str = last_cot['Date'].strftime('%Y-%m-%d') if hasattr(last_cot, 'Date') and isinstance(last_cot['Date'], pd.Timestamp) else "가장 최근 확정일"
        
        context += f"- 기준일: {date_str}\n"
        context += f"- 딜러(헤저) 순포지션: {last_cot.get('Dealer_Net', 0):,}\n"
        context += f"- 투기(스마트머니) 순포지션: {last_cot.get('Asset_Mgr_Net', 0):,}\n"
        context += f"- COT 과열/침체 인덱스: {last_cot.get('COT_Index', 0):.1f}%\n"
    else:
        context += f"- 로드 실패: {df_cot}\n"

    # 5. 국내 파생 수급 (KRX)
    context += "\n#### 5. 국내 KOSPI 200 파생 & 미결제약정 수급\n"
    df_krx = safe_load_dataframe('services.krx_service', 'get_krx_futures_history', 20)
    if isinstance(df_krx, pd.DataFrame):
        last_krx = df_krx.iloc[-1]
        date_str = last_krx['Date'].strftime('%Y-%m-%d') if hasattr(last_krx, 'Date') and isinstance(last_krx['Date'], pd.Timestamp) else "가장 최근 영업일"
        
        context += f"- 기준일: {date_str}\n"
        context += f"- 선물 종가: {last_krx.get('Futures_Close', 0)} pt ({last_krx.get('Change_Pct', 0):+.2f}%)\n"
        context += f"- 시장 베이시스: {last_krx.get('Market_Basis', 0):+.2f} pt\n"
        context += f"- 미결제약정: {last_krx.get('Open_Interest', 0):,} 계약\n"
        context += f"- 파생 수급 국면: {last_krx.get('Market_Phase', '알수없음')}\n"
        context += f"- 한국판 COT Index: {last_krx.get('COT_OI_Index', 0):.1f}%\n"
    else:
        context += f"- 시계열 로드 실패: {df_krx}\n"

    df_inv = safe_load_dataframe('services.krx_service', 'get_krx_investor_derivatives_summary')
    if isinstance(df_inv, pd.DataFrame):
        context += "- 주요 투자자 20일 누적 순매수:\n"
        for _, r in df_inv.iterrows():
            subj = r.get('투자 주체', r.get('주체', 'Unknown'))
            amt = r.get('20일 누적', r.get('20일 누적 순매수 (계약)', 0))
            context += f"  * {subj}: {amt:+,} 계약\n"

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
            from services.ai_service import call_selected_ai_engine
            from services.prompts import COMPREHENSIVE_REPORT_PROMPT
            res = call_selected_ai_engine(selected_engine, prompt=context_data, system_prompt=COMPREHENSIVE_REPORT_PROMPT)
            
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                step_info = res.get("pipeline_step", "단일 호출 완료")
                st.caption(f"⚡ **실행 엔진 파이프라인**: `{step_info}`")
                st.divider()
                
                # 리포트 상단에 기준 시각 강제 고정 삽입
                report_header = f"### 📅 데이터 수집 및 분석 기준 시각: {now_kst}\n\n"
                st.markdown(report_header + res.get("response", "데이터 처리에 실패했습니다."))
                
            with st.expander("🔍 AI에게 전달된 원본 통합 데이터(Context) 확인"):
                st.code(context_data, language="markdown")
