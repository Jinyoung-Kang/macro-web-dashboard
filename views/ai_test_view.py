# views/ai_test_view.py
import streamlit as st
from services.ai_service import (
    get_secret, 
    test_openrouter, 
    test_cerebras, 
    test_sambanova, 
    test_nvidia_nim, 
    test_cloudflare_ai
)

def render_ai_test_view():
    st.title("🤖 5대 AI API 연결 통합 테스트")
    st.caption("Streamlit Cloud Secrets에 등록된 키를 바탕으로 실시간 API 연결 상태 및 지연시간(Latency)을 점검합니다.")
    st.divider()

    sec_or_key = get_secret("ai.openrouter_api_key", "")
    sec_ce_key = get_secret("ai.cerebras_api_key", "")
    sec_sb_key = get_secret("ai.sambanova_api_key", "")
    sec_nv_key = get_secret("ai.nvidia_api_key", "")
    sec_cf_id = get_secret("ai.cloudflare_account_id", "")
    sec_cf_token = get_secret("ai.cloudflare_api_token", "")

    with st.expander("⚙️ Streamlit Secrets 인증 키 로드 상태 확인 (클릭하여 펼치기)", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**1. OpenRouter:** {'🟢 로드 완료' if sec_or_key else '🔴 미설정'}")
            or_key = st.text_input("OpenRouter Key", value=sec_or_key, type="password", key="ui_or_key")
            
            st.markdown(f"**4. NVIDIA NIM:** {'🟢 로드 완료' if sec_nv_key else '🔴 미설정'}")
            nv_key = st.text_input("NVIDIA Key", value=sec_nv_key, type="password", key="ui_nv_key")
            
        with c2:
            st.markdown(f"**2. Cerebras:** {'🟢 로드 완료' if sec_ce_key else '🔴 미설정'}")
            ce_key = st.text_input("Cerebras Key", value=sec_ce_key, type="password", key="ui_ce_key")
            
            st.markdown(f"**5. Cloudflare:** {'🟢 로드 완료' if (sec_cf_id and sec_cf_token) else '🔴 미설정'}")
            cf_id = st.text_input("CF Account ID (32자리)", value=sec_cf_id, key="ui_cf_id")
            cf_token = st.text_input("CF API Token", value=sec_cf_token, type="password", key="ui_cf_token")
            
        with c3:
            st.markdown(f"**3. SambaNova:** {'🟢 로드 완료' if sec_sb_key else '🔴 미설정'}")
            sb_key = st.text_input("SambaNova Key", value=sec_sb_key, type="password", key="ui_sb_key")

    test_prompt = st.text_input(
        "테스트 질문 프롬프트", 
        value="미국 증시와 연준 순유동성(Net Liquidity)의 상관관계를 2문장으로 핵심만 요약해줘."
    )
    st.write("")
    
    if st.button("🚀 5대 AI API 전체 일괄 연결 테스트 실행", type="primary", use_container_width=True):
        st.subheader("📊 테스트 결과")
        
        final_or = or_key or sec_or_key
        final_ce = ce_key or sec_ce_key
        final_sb = sb_key or sec_sb_key
        final_nv = nv_key or sec_nv_key
        final_cf_id = cf_id or sec_cf_id
        final_cf_token = cf_token or sec_cf_token

        results = {}
        
        with st.status("AI 엔진 릴레이 테스트 진행 중...", expanded=True) as status:
            st.write("1/5. OpenRouter (Phi-3-Mini) 호출 중...")
            results["OpenRouter"] = test_openrouter(final_or, test_prompt)
            
            st.write("2/5. Cerebras (Llama-3.1-8B) 호출 중...")
            results["Cerebras"] = test_cerebras(final_ce, test_prompt)
            
            st.write("3/5. SambaNova 호출 중...")
            results["SambaNova"] = test_sambanova(final_sb, test_prompt)
            
            st.write("4/5. NVIDIA NIM 호출 중...")
            results["NVIDIA"] = test_nvidia_nim(final_nv, test_prompt)
            
            st.write("5/5. Cloudflare AI 호출 중...")
            results["Cloudflare"] = test_cloudflare_ai(final_cf_id, final_cf_token, test_prompt)
            
            status.update(label="✅ 모든 API 테스트 완료!", state="complete")
            
        st.divider()

        cols = st.columns(3)
        for i, (name, res) in enumerate(results.items()):
            with cols[i % 3]:
                st.markdown(f"### {name}")
                if res["status"]:
                    st.success(f"🟢 정상 작동 ({res['latency_ms']} ms)")
                    st.info(res["response"])
                else:
                    st.error("🔴 호출 실패")
                    st.caption(res["response"])
