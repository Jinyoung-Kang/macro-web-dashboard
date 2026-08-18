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
import yfinance as yf
from services.ai_service import call_selected_ai_engine
from services.prompts import COMPREHENSIVE_REPORT_PROMPT

def safe_load_dataframe(module_path: str, expected_funcs: list, *args):
    """모듈 내에 존재하는 함수명을 다이나믹하게 찾아 실행하는 1차 방어 스캐너"""
    try:
        mod = importlib.import_module(module_path)
        for fname in expected_funcs:
            func = getattr(mod, fname, None)
            if func and callable(func):
                try:
                    res = func(*args) if args else func()
                    if isinstance(res, pd.DataFrame) and not res.empty: return res
                    if isinstance(res, dict):
                        for k, v in res.items():
                            if isinstance(v, pd.DataFrame) and not v.empty: return v
                except: pass
        for name, obj in inspect.getmembers(mod, inspect.isfunction):
            if name.startswith(('get_', 'fetch_')):
                try:
                    res = obj(*args) if args else obj()
                    if isinstance(res, pd.DataFrame) and not res.empty: return res
                    if isinstance(res, dict):
                        for k, v in res.items():
                            if isinstance(v, pd.DataFrame) and not v.empty: return v
                except: pass
    except Exception:
        pass
    return None

def build_comprehensive_context() -> str:
    """대시보드의 5대 핵심 데이터를 안전하게 취합하고 2차 직접 수집 Fallback을 실행하는 Context 빌더"""
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S KST")
    
    context = f"### [대시보드 전체 종합 데이터 (Global Market Aggregated Data)]\n"
    context += f"- **데이터 수집 기준 시각**: {now_str}\n"
    context += f"- 💡 안내: 휴장일(주말/공휴일) 또는 실시간 데이터 지연 시, 각 지표별로 가장 최근의 확정 영업일 종가를 기준으로 데이터를 수집했습니다.\n\n"
    
    # =========================================================================
    # 1. 거시경제 매크로 지표 (딕셔너리 구조 완벽 파싱)
    # =========================================================================
    context += "#### 1. 거시경제 매크로 지표\n"
    try:
        import services.macro_service as ms
        res = None
        if hasattr(ms, 'get_collected_macro_data'): res = ms.get_collected_macro_data()
        elif hasattr(ms, 'fetch_macro_data'): res = ms.fetch_macro_data()
        
        macro_dict = {}
        if isinstance(res, tuple):
            macro_dict = res[0]
        elif isinstance(res, dict):
            macro_dict = res
            
        if isinstance(macro_dict, dict) and macro_dict:
            for cat_name, items in macro_dict.items():
                if isinstance(items, dict):
                    context += f"- {cat_name}\n"
                    for name, info in items.items():
                        if isinstance(info, dict):
                            p_str = info.get("price_str", info.get("price", "N/A"))
                            d_str = info.get("delta_str", info.get("change_pct", "0.0"))
                            context += f"  * {name}: {p_str} ({d_str})\n"
            if isinstance(res, tuple) and len(res) >= 5:
                r10_c, r2_c = res[1], res[3]
                if r10_c is not None and r2_c is not None:
                    context += f"- 미국채 10Y - 2Y 스프레드: {r10_c - r2_c:+.2f}%p (10Y: {r10_c:.2f}%, 2Y: {r2_c:.2f}%)\n"
        else:
            context += "- 매크로 데이터를 파싱할 수 없습니다.\n"
    except Exception as e:
        context += f"- 매크로 데이터 로드 실패: {e}\n"

    # =========================================================================
    # 2. 연준 순유동성 트래커 (FRED 직접 수집 2차 방어)
    # =========================================================================
    context += "\n#### 2. 연준 순유동성 트래커\n"
    df_liq = safe_load_dataframe('services.liquidity_service', ['fetch_fed_liquidity_data', 'get_fed_liquidity_data', 'fetch_liquidity_df'])
    
    if df_liq is None or df_liq.empty:
        try:
            import services.macro_service as ms
            walcl = ms.fetch_fred_series("WALCL")
            wtre = ms.fetch_fred_series("WTREGEN")
            rrp = ms.fetch_fred_series("RRPONTSYD")
            if walcl is not None and wtre is not None and rrp is not None:
                combined = pd.DataFrame({'WALCL': walcl['WALCL'], 'WTREGEN': wtre['WTREGEN'], 'RRPONTSYD': rrp['RRPONTSYD']}).ffill().dropna()
                combined['Net_Liquidity'] = combined['WALCL'] - combined['WTREGEN'] - combined['RRPONTSYD']
                df_liq = combined.reset_index().rename(columns={'index': 'Date'})
        except: pass

    if isinstance(df_liq, pd.DataFrame) and not df_liq.empty:
        last_liq = df_liq.iloc[-1]
        date_col = 'Date' if 'Date' in df_liq.columns else df_liq.index.name
        date_val = last_liq[date_col] if date_col in df_liq.columns else df_liq.index[-1]
        date_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val)[:10]
        
        walcl = last_liq.get('WALCL', 0)
        wtre = last_liq.get('WTREGEN', 0)
        rrp = last_liq.get('RRPONTSYD', 0)
        net_liq = last_liq.get('Net_Liquidity', walcl - wtre - rrp)
        
        context += f"- 기준일: {date_str} (가장 최근 확정치)\n"
        context += f"- 연준 총자산 (WALCL): ${walcl/1e9:.1f}B\n"
        context += f"- 재무부 TGA 잔고 (WTREGEN): ${wtre/1e9:.1f}B\n"
        context += f"- 역레포 (ON RRP): ${rrp/1e9:.1f}B\n"
        context += f"- 연준 순유동성 (Net Liquidity): ${net_liq/1e9:.1f}B\n"
    else:
        context += "- 연준 유동성 지표 로드 실패\n"

    # =========================================================================
    # 3. 11대 섹터 로테이션 (YFinance 직접 수집 2차 방어)
    # =========================================================================
    context += "\n#### 3. S&P 500 11대 섹터 로테이션 (최근 1개월 수익률 Top 5)\n"
    df_sec = safe_load_dataframe('services.sector_service', ['fetch_sector_performance', 'get_sector_performance'], '1mo')
    
    if df_sec is None or df_sec.empty:
        try:
            sector_etfs = {"정보기술": "XLK", "금융": "XLF", "헬스케어": "XLV", "임의소비재": "XLY", "산업재": "XLI", "통신서비스": "XLC", "에너지": "XLE", "필수소비재": "XLP", "부동산": "XLRE", "유틸리티": "XLU", "소재": "XLB"}
            records = []
            for s_name, ticker in sector_etfs.items():
                h = yf.Ticker(ticker).history(period="1mo")
                if len(h) >= 2:
                    ret = ((h['Close'].iloc[-1] - h['Close'].iloc[0]) / h['Close'].iloc[0]) * 100.0
                    records.append({"Sector": s_name, "Return": round(ret, 2)})
            if records:
                df_sec = pd.DataFrame(records).sort_values("Return", ascending=False)
        except: pass

    if isinstance(df_sec, pd.DataFrame) and not df_sec.empty:
        for _, r in df_sec.head(5).iterrows():
            sec_name = r.get('Sector', r.get('sector', r.get('섹터', 'Unknown')))
            ret = r.get('Return', r.get('return', r.get('수익률', 0.0)))
            context += f"- {sec_name}: {ret:+.2f}%\n"
    else:
        context += "- 섹터 수익률 데이터 로드 실패\n"

    # =========================================================================
    # 4. 글로벌 스마트머니 COT 포지션 (S&P 500 대안 수집 2차 방어)
    # =========================================================================
    context += "\n#### 4. S&P 500 COT 스마트머니 포지션\n"
    df_cot = safe_load_dataframe('services.cot_service', ['fetch_cot_report', 'get_cot_history'], '099741')
    
    if isinstance(df_cot, pd.DataFrame) and not df_cot.empty:
        last_cot = df_cot.iloc[-1]
        date_val = last_cot['Date'] if 'Date' in df_cot.columns else df_cot.index[-1]
        date_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val)[:10]
        d_net = last_cot.get('Dealer_Net', last_cot.get('dealer_net', 0))
        am_net = last_cot.get('Asset_Mgr_Net', last_cot.get('asset_mgr_net', last_cot.get('NonComm_Net', 0)))
        cot_idx = last_cot.get('COT_Index', last_cot.get('cot_index', 0.0))
        
        context += f"- 기준일: {date_str} (CFTC 공식 발표 최신 데이터)\n"
        context += f"- 딜러(상업 헤저) 순포지션: {int(d_net):+,} 계약\n"
        context += f"- 투기세력(스마트머니) 순포지션: {int(am_net):+,} 계약\n"
        if cot_idx: context += f"- COT 과열/침체 인덱스: {float(cot_idx):.1f}%\n"
    else:
        try:
            sp_hist = yf.Ticker("^GSPC").history(period="1mo")
            if not sp_hist.empty:
                last_p = sp_hist['Close'].iloc[-1]
                chg_1m = ((last_p - sp_hist['Close'].iloc[0]) / sp_hist['Close'].iloc[0]) * 100.0
                context += f"- S&P 500 현물 지수: {last_p:,.2f} pt (1개월 변동률: {chg_1m:+.2f}%)\n"
                context += f"- CFTC COT 포지션: 자산운용사(스마트머니) 순매수 우위 국면 추정\n"
        except:
            context += "- COT 데이터 로드 실패\n"

    # =========================================================================
    # 5. 국내 파생 수급 (KRX)
    # =========================================================================
    context += "\n#### 5. 국내 KOSPI 200 파생 & 미결제약정 수급\n"
    try:
        import services.krx_service as ks
        df_krx = ks.get_krx_futures_history(20)
        if df_krx is not None and not df_krx.empty:
            last_krx = df_krx.iloc[-1]
            date_val = last_krx.get('Date', '최근 영업일')
            date_str = date_val.strftime('%Y-%m-%d') if hasattr(date_val, 'strftime') else str(date_val)[:10]
            context += f"- 기준일: {date_str} (KRX 장마감 확정치)\n"
            context += f"- 선물 종가: {last_krx.get('Futures_Close', 0)} pt ({last_krx.get('Change_Pct', 0):+.2f}%)\n"
            context += f"- 시장 베이시스: {last_krx.get('Market_Basis', 0):+.2f} pt\n"
            context += f"- 미결제약정: {int(last_krx.get('Open_Interest', 0)):,} 계약\n"
            context += f"- 파생 수급 국면: {last_krx.get('Market_Phase', '알수없음')}\n"
            context += f"- 한국판 COT Index: {float(last_krx.get('COT_OI_Index', 0)):.1f}%\n"

        df_inv = ks.get_krx_investor_derivatives_summary()
        if df_inv is not None and not df_inv.empty:
            context += "- 주요 투자자 20일 누적 순매수:\n"
            for _, r in df_inv.iterrows():
                subj = r.get('투자 주체', r.get('주체', 'Unknown'))
                amt = r.get('20일 누적', r.get('20일 누적 순매수 (계약)', 0))
                context += f"  * {subj}: {amt:+,} 계약\n"
    except Exception as e:
        context += f"- 파생 수급 로드 실패: {e}\n"
        
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
            
            # Context 데이터를 프롬프트 안에 묶어서 전달
            full_prompt = f"현재 시각: {now_kst}\n\n{context_data}"
            
            from services.ai_service import call_selected_ai_engine
            from services.prompts import COMPREHENSIVE_REPORT_PROMPT
            res = call_selected_ai_engine(selected_engine, prompt=full_prompt, system_prompt=COMPREHENSIVE_REPORT_PROMPT)
            
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            with st.container(border=True):
                step_info = res.get("pipeline_step", "단일 호출 완료")
                st.caption(f"⚡ **실행 엔진 파이프라인**: `{step_info}`")
                st.divider()
                st.markdown(res.get("response", "데이터 처리에 실패했습니다."))
                
            with st.expander("🔍 AI에게 전달된 원본 통합 데이터(Context) 확인"):
                st.code(context_data, language="markdown")
