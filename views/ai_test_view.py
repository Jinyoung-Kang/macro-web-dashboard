# views/ai_test_view.py
import streamlit as st
from services.ai_service import (
    get_secret, 
    check_ollama_status,
    test_cloudflare_ai,
    test_nvidia_nemotron,
    test_nvidia_gpt_oss,
    test_cerebras,
    test_local_ollama,
    translate_smart_korean,
    generate_ai_briefing_with_failover
)

def render_ai_test_view():
    st.title("🤖 AI API 통합 & 로컬 Ollama 테스트")
    st.caption("클라우드 엔진 4종(Cloudflare, Nemotron, GPT-OSS, Cerebras) 및 맥북 로컬 Ollama의 실시간 연결 상태를 검증합니다.")
    st.divider()

    sec_cf_id = get_secret("ai.cloudflare_account_id", "")
    sec_cf_token = get_secret("ai.cloudflare_api_token", "")
    sec_nv_key = get_secret("ai.nvidia_api_key", "")
    sec_ce_key = get_secret("ai.cerebras_api_key", "")

    # Ollama 로컬 서버 활성화 여부 실시간 체크
    is_ollama_alive = check_ollama_status()

    # 엔진 연결 상태 5열 배치 (Ollama + 클라우드 4종)
    with st.expander("⚙️ 엔진 연결 및 인증 키 로드 상태", expanded=True):
        c_local, c1, c2, c3, c4 = st.columns(5)
        with c_local:
            st.markdown(f"**💻 로컬 Ollama:**<br>{'🟢 켜짐 (작동중)' if is_ollama_alive else '🔴 꺼짐 (미실행)'}", unsafe_allow_html=True)
        with c1:
            st.markdown(f"**🥇 1순위 CF AI:**<br>{'🟢 로드 완료' if (sec_cf_id and sec_cf_token) else '🔴 미설정'}", unsafe_allow_html=True)
        with c2:
            st.markdown(f"**🥈 2순위 Nemotron:**<br>{'🟢 로드 완료' if sec_nv_key else '🔴 미설정'}", unsafe_allow_html=True)
        with c3:
            st.markdown(f"**🥉 3순위 GPT-OSS:**<br>{'🟢 로드 완료' if sec_nv_key else '🔴 미설정'}", unsafe_allow_html=True)
        with c4:
            st.markdown(f"**🏅 4순위 Cerebras:**<br>{'🟢 로드 완료' if sec_ce_key else '🔴 미설정'}", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🚀 4대 클라우드 AI & Failover 테스트", "🖥️ 맥북 로컬 Ollama(Llama 3.1) 무제한 번역기"])

    # TAB 1: 4대 클라우드 AI 파이프라인
    with tab1:
        test_prompt = st.text_input(
            "테스트 질문 프롬프트", 
            value="미국 증시와 연준 순유동성(Net Liquidity)의 상관관계를 2문장으로 핵심만 요약해줘.",
            key="cloud_prompt_input"
        )
        st.write("")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            run_individual = st.button("🚀 4대 AI API 개별 연결 상태 점검", type="secondary", use_container_width=True)
        with col_btn2:
            run_failover = st.button("🛡️ 4단 Failover 무중단 파이프라인 실행", type="primary", use_container_width=True)

        if run_individual:
            st.subheader("📊 개별 API 연결 테스트 결과")
            results = {}
            with st.status("AI 엔진 개별 테스트 진행 중...", expanded=True) as status:
                st.write("1/4. 🥇 Cloudflare (DeepSeek-R1 + 스마트 번역) 호출 중...")
                results["1순위: Cloudflare AI"] = test_cloudflare_ai(sec_cf_id, sec_cf_token, test_prompt)
                
                st.write("2/4. 🥈 NVIDIA Nemotron-3 Super 호출 중...")
                results["2순위: NVIDIA Nemotron-3"] = test_nvidia_nemotron(sec_nv_key, test_prompt)
                
                st.write("3/4. 🥉 NVIDIA GPT-OSS-20B 호출 중...")
                results["3순위: NVIDIA GPT-OSS-20B"] = test_nvidia_gpt_oss(sec_nv_key, test_prompt)
                
                st.write("4/4. 🏅 Cerebras Cloud 호출 중...")
                results["4순위: Cerebras Cloud"] = test_cerebras(sec_ce_key, test_prompt)
                
                status.update(label="✅ 모든 API 개별 테스트 완료!", state="complete")

            st.divider()
            cols = st.columns(2)
            for i, (name, res) in enumerate(results.items()):
                with cols[i % 2]:
                    st.markdown(f"### {name}")
                    if res["status"]:
                        st.success(f"🟢 정상 ({res['latency_ms']} ms)")
                        if "translation_info" in res:
                            st.caption(f"**번역 상태:** {res['translation_info']}")
                        st.info(res["response"])
                    else:
                        st.error("🔴 호출 실패")
                        st.caption(res["response"])

        if run_failover:
            st.subheader("🛡️ Failover 파이프라인 실제 응답 결과")
            with st.spinner("1순위 Cloudflare부터 순차 탐색하여 브리핑을 생성하는 중..."):
                res = generate_ai_briefing_with_failover(test_prompt)
            
            if res["status"]:
                st.success(f"✅ **{res['pipeline_step']}** (지연시간: {res['latency_ms']} ms | 엔진: {res['provider']})")
                st.markdown("##### 📝 AI 생성 브리핑:")
                st.info(res["response"])
            else:
                st.error(f"❌ {res['pipeline_step']}")
                st.warning(res["response"])

    # TAB 2: 맥북 로컬 Ollama 번역 전용 테스트
    with tab2:
        st.markdown("#### ⚡ 맥북 로컬 Llama 3.1 직접 번역 엔진")
        st.caption("외부 API 토큰 제한이나 과금 없이 맥북 자체 하드웨어(Apple Silicon) 연산으로 긴 금융 문장을 실시간 번역합니다.")

        sample_english = st.text_area(
            "번역할 영문 텍스트 입력 (길이 제한 없음)",
            height=130,
            value="The Federal Reserve's balance sheet reduction and changes in the Treasury General Account (TGA) directly influence broad market net liquidity. When liquidity contracts, risk assets such as equities and high-yield bonds typically face downward valuation pressure."
        )

        col_ol1, col_ol2 = st.columns(2)
        with col_ol1:
            run_ollama_direct = st.button("🖥️ 로컬 Ollama로 즉시 번역", type="primary", use_container_width=True)
        with col_ol2:
            run_smart_trans = st.button("🔄 하이브리드 스마트 번역 (로컬 $\\rightarrow$ 원격 자동선택)", use_container_width=True)

        if run_ollama_direct:
            if not is_ollama_alive:
                st.error("🔴 로컬 서버가 응답하지 않습니다. 터미널에서 `ollama run llama3.1`을 실행해 주세요.")
            else:
                with st.spinner("맥북 로컬 Llama 3.1 추론 중..."):
                    ol_res = test_local_ollama(f"다음 텍스트를 자연스러운 한국어로 번역해줘:\n\n{sample_english}")
                if ol_res["status"]:
                    st.success(f"🟢 번역 성공 ({ol_res['latency_ms']} ms)")
                    st.markdown("##### 📖 한국어 번역 결과:")
                    st.info(ol_res["response"])
                else:
                    st.error("🔴 로컬 Ollama 연결 실패")
                    st.caption(ol_res["response"])

        if run_smart_trans:
            with st.spinner("최적 번역 엔진 탐색 중..."):
                translated_text, mode_info = translate_smart_korean(sample_english, sec_cf_id, sec_cf_token)
            st.success(f"**실행 모드:** {mode_info}")
            st.markdown("##### 📖 한국어 번역 결과:")
            st.info(translated_text)
