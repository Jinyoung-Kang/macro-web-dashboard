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
    st.caption("OpenRouter, Cerebras, SambaNova, NVIDIA, Cloudflare의 실시간 API 연결 상태 및 지연시간(Latency)을 점검합니다.")
    st.divider()

    # 1. API 키 셋업 UI
    with st.expander("⚙️ API 인증 키 확인 및 수정", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("##### 1. OpenRouter")
            or_key = st.text_input("OpenRouter Key", value=get_secret("ai.openrouter_api_key", ""), type="password")
            st.markdown("##### 4. NVIDIA NIM")
            nv_key = st.text_input("NVIDIA Key", value=get_secret("ai.nvidia_api_key", ""), type="password")
        with c2:
            st.markdown("##### 2. Cerebras")
            ce_key = st.text_input("Cerebras Key", value=get_secret("ai.cerebras_api_key", ""), type="password")
            st.markdown("##### 5. Cloudflare")
            cf_id = st.text_input("CF Account ID (영문/숫자 32자리)", value=get_secret("ai.cloudflare_account_id", ""))
            cf_token = st.text_input("CF API Token (Workers AI 권한)", value=get_secret("ai.cloudflare_api_token", ""), type="password")
        with c3:
            st.markdown("##### 3. SambaNova")
            st.caption("※ SambaNova는 사이트에서 카드 등록 필요 (무료)")
            sb_key = st.text_input("SambaNova Key", value=get_secret("ai.sambanova_api_key", ""), type="password")

    test_prompt = st.text_input(
        "테스트 질문 프롬프트", 
        value="미국 증시와 연준 순유동성(Net Liquidity)의 상관관계를 2문장으로 핵심만 요약해줘."
    )
    st.write("")
    
    if st.button("🚀 5대 AI API 전체 일괄 연결 테스트 실행", type="primary", use_container_width=True):
        st.subheader("📊 테스트 결과")
        
        results = {}
        
        with st.status("AI 엔진 릴레이 테스트 진행 중...", expanded=True) as status:
            st.write("1/5. OpenRouter 호출 중...")
            results["OpenRouter"] = test_openrouter(or_key, test_prompt)
            
            st.write("2/5. Cerebras 호출 중...")
            results["Cerebras"] = test_cerebras(ce_key, test_prompt)
            
            st.write("3/5. SambaNova 호출 중...")
            results["SambaNova"] = test_sambanova(sb_key, test_prompt)
            
            st.write("4/5. NVIDIA NIM 호출 중...")
            results["NVIDIA"] = test_nvidia_nim(nv_key, test_prompt)
            
            st.write("5/5. Cloudflare AI 호출 중...")
            results["Cloudflare"] = test_cloudflare_ai(cf_id, cf_token, test_prompt)
            
            status.update(label="✅ 모든 API 테스트 완료!", state="complete")
            
        st.divider()

        # 결과 카드 출력 (3열 배치)
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
