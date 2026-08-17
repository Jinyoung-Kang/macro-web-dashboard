# views/ai_test_view.py
import streamlit as st
from services.ai_service import (
    get_secret, 
    test_google_ai, 
    test_nvidia_nim, 
    test_cloudflare_ai
)

def render_ai_test_view():
    st.title("🤖 AI API 연결 통합 테스트 (Failover Engine Test)")
    st.caption("Google AI Studio, NVIDIA NIM, Cloudflare Workers AI 3대 인프라의 실시간 연결 상태 및 추론 지연시간(Latency)을 점검합니다.")
    st.divider()

    # 1. API 키 설정 (secrets에서 자동 로드 + UI 직접 수정 지원)
    with st.expander("⚙️ API 인증 키 확인 및 수정", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### 1. Google AI Studio")
            default_google = get_secret("ai.google_api_key", "")
            google_key = st.text_input("Google API Key", value=default_google, type="password", key="test_google_key")

            st.markdown("##### 2. NVIDIA NIM")
            default_nvidia = get_secret("ai.nvidia_api_key", "")
            nvidia_key = st.text_input("NVIDIA API Key", value=default_nvidia, type="password", key="test_nvidia_key")

        with col2:
            st.markdown("##### 3. Cloudflare Workers AI")
            default_cf_id = get_secret("ai.cloudflare_account_id", "")
            default_cf_token = get_secret("ai.cloudflare_api_token", "")
            cf_account_id = st.text_input("Cloudflare Account ID", value=default_cf_id, key="test_cf_id")
            cf_token = st.text_input("Cloudflare API Token", value=default_cf_token, type="password", key="test_cf_token")

    # 2. 테스트 프롬프트 설정
    test_prompt = st.text_input(
        "테스트 질문 프롬프트", 
        value="미국 증시와 연준 순유동성(Net Liquidity)의 상관관계를 2문장으로 핵심만 요약해줘."
    )

    st.write("")
    
    # 일괄 테스트 실행 버튼
    if st.button("🚀 3대 AI API 전체 일괄 연결 테스트 실행", type="primary", use_container_width=True):
        st.subheader("📊 테스트 결과")
        
        # 1) Google
        with st.status("Google AI Studio (Gemini 2.0 Flash) 테스트 중...", expanded=True) as status_g:
            res_g = test_google_ai(google_key, prompt=test_prompt)
            if res_g["status"]:
                status_g.update(label=f"✅ Google AI Studio 성공 ({res_g['latency_ms']}ms)", state="complete")
            else:
                status_g.update(label="❌ Google AI Studio 실패", state="error")
        
        # 2) NVIDIA
        with st.status("NVIDIA NIM (Llama 3.3 70B) 테스트 중...", expanded=True) as status_n:
            res_n = test_nvidia_nim(nvidia_key, prompt=test_prompt)
            if res_n["status"]:
                status_n.update(label=f"✅ NVIDIA NIM 성공 ({res_n['latency_ms']}ms)", state="complete")
            else:
                status_n.update(label="❌ NVIDIA NIM 실패", state="error")

        # 3) Cloudflare
        with st.status("Cloudflare Workers AI (Llama 3.3 70B) 테스트 중...", expanded=True) as status_c:
            res_c = test_cloudflare_ai(cf_account_id, cf_token, prompt=test_prompt)
            if res_c["status"]:
                status_c.update(label=f"✅ Cloudflare Workers AI 성공 ({res_c['latency_ms']}ms)", state="complete")
            else:
                status_c.update(label="❌ Cloudflare Workers AI 실패", state="error")

        st.divider()

        # 상세 결과 메트릭 카드 표시
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("### 🌐 Google Gemini")
            if res_g["status"]:
                st.success(f"🟢 정상 작동 ({res_g['latency_ms']} ms)")
                st.info(res_g["response"])
            else:
                st.error("🔴 호출 실패")
                st.caption(res_g["response"])

        with c2:
            st.markdown("### ⚡ NVIDIA NIM")
            if res_n["status"]:
                st.success(f"🟢 정상 작동 ({res_n['latency_ms']} ms)")
                st.info(res_n["response"])
            else:
                st.error("🔴 호출 실패")
                st.caption(res_n["response"])

        with c3:
            st.markdown("### ☁️ Cloudflare AI")
            if res_c["status"]:
                st.success(f"🟢 정상 작동 ({res_c['latency_ms']} ms)")
                st.info(res_c["response"])
            else:
                st.error("🔴 호출 실패")
                st.caption(res_c["response"])
