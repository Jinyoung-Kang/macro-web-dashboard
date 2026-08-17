# views/ai_test_view.py
import streamlit as st
from services.ai_service import (
    get_secret, 
    test_cloudflare_ai,
    test_nvidia_nemotron,
    test_nvidia_gpt_oss,
    test_cerebras,
    generate_ai_briefing_with_failover
)

def render_ai_test_view():
    st.title("🤖 4대 AI API 통합 & Failover 테스트")
    st.caption("1순위 Cloudflare (DeepSeek-R1 + m2m100 번역 연계), 2순위 Nemotron-3, 3순위 GPT-OSS-20B, 4순위 Cerebras 파이프라인 검증.")
    st.divider()

    sec_cf_id = get_secret("ai.cloudflare_account_id", "")
    sec_cf_token = get_secret("ai.cloudflare_api_token", "")
    sec_nv_key = get_secret("ai.nvidia_api_key", "")
    sec_ce_key = get_secret("ai.cerebras_api_key", "")

    with st.expander("⚙️ Streamlit Secrets 인증 키 로드 상태 (클릭하여 확인)", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**🥇 1순위 Cloudflare:** {'🟢 로드 완료' if (sec_cf_id and sec_cf_token) else '🔴 미설정'}")
            cf_id = st.text_input("CF Account ID", value=sec_cf_id, key="ui_cf_id")
            cf_token = st.text_input("CF API Token", value=sec_cf_token, type="password", key="ui_cf_token")
            
            st.markdown(f"**🥈 2순위 & 🥉 3순위 NVIDIA NIM:** {'🟢 로드 완료' if sec_nv_key else '🔴 미설정'}")
            nv_key = st.text_input("NVIDIA Key", value=sec_nv_key, type="password", key="ui_nv_key")
        with c2:
            st.markdown(f"**🏅 4순위 Cerebras:** {'🟢 로드 완료' if sec_ce_key else '🔴 미설정'}")
            ce_key = st.text_input("Cerebras Key", value=sec_ce_key, type="password", key="ui_ce_key")

    test_prompt = st.text_input(
        "테스트 질문 프롬프트", 
        value="미국 증시와 연준 순유동성(Net Liquidity)의 상관관계를 2문장으로 핵심만 요약해줘."
    )
    st.write("")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        run_individual = st.button("🚀 4대 AI API 개별 연결 상태 점검", type="secondary", use_container_width=True)
    with col_btn2:
        run_failover = st.button("🛡️ 4단 Failover 무중단 파이프라인 실행", type="primary", use_container_width=True)

    if run_individual:
        st.subheader("📊 개별 API 연결 테스트 결과")
        final_cf_id = cf_id or sec_cf_id
        final_cf_token = cf_token or sec_cf_token
        final_nv = nv_key or sec_nv_key
        final_ce = ce_key or sec_ce_key

        results = {}
        with st.status("AI 엔진 개별 테스트 진행 중...", expanded=True) as status:
            st.write("1/4. 🥇 Cloudflare (DeepSeek-R1 + m2m100 번역) 호출 중...")
            # NVIDIA 키 제외, Cloudflare 내에서 자체 번역 수행
            results["1순위: Cloudflare AI"] = test_cloudflare_ai(final_cf_id, final_cf_token, test_prompt)
            
            st.write("2/4. 🥈 NVIDIA Nemotron-3 Super 호출 중...")
            results["2순위: NVIDIA Nemotron-3"] = test_nvidia_nemotron(final_nv, test_prompt)
            
            st.write("3/4. 🥉 NVIDIA GPT-OSS-20B 호출 중...")
            results["3순위: NVIDIA GPT-OSS-20B"] = test_nvidia_gpt_oss(final_nv, test_prompt)
            
            st.write("4/4. 🏅 Cerebras Cloud 호출 중...")
            results["4순위: Cerebras Cloud"] = test_cerebras(final_ce, test_prompt)
            
            status.update(label="✅ 모든 API 개별 테스트 완료!", state="complete")

        st.divider()
        cols = st.columns(2)
        for i, (name, res) in enumerate(results.items()):
            with cols[i % 2]:
                st.markdown(f"### {name}")
                if res["status"]:
                    st.success(f"🟢 정상 ({res['latency_ms']} ms)")
                    
                    # 번역 상태 정보가 있을 경우 출력 (주로 1순위 Cloudflare용)
                    if "translation_info" in res:
                        st.caption(f"**상태:** {res['translation_info']}")
                        
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
