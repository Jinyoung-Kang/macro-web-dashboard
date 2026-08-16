# views/ls_test_view.py
import streamlit as st
from services.ls_service import get_ls_token, fetch_stock_quote

def render_ls_test_view():
    st.title("🧪 LS증권 OPEN API 연동 테스트")
    st.caption("발급받은 APP Key 및 Secret Key를 기반으로 토큰 발급 및 실시간 주식 시세 조회를 검증합니다.")

    # 1. 토큰 발급 상태 검증 섹션
    st.subheader("1. OAuth 2.0 인증 토큰 발급 테스트")
    
    col_t1, col_t2 = st.columns([3, 1])
    with col_t2:
        reissue = st.button("🔄 토큰 재발급", use_container_width=True)
        if reissue:
            st.cache_data.clear()

    with st.spinner("LS증권 인증 서버와 통신 중..."):
        token, token_err = get_ls_token()

    if token_err:
        st.error(f"❌ **인증 실패:** {token_err}")
        st.info("💡 **확인 사항:** `secrets.toml`에 등록한 `app_key`와 `app_secret`이 올바른지 확인해주세요.", icon="ℹ️")
        return
    else:
        st.success("✅ **LS증권 OAuth 2.0 인증 성공! 정상적으로 접근 토큰을 획득했습니다.**")
        with st.expander("🔑 발급된 토큰 정보 (보안 마스킹)"):
            st.code(f"{token[:12]}...{token[-8:]}", language="text")

    st.divider()

    # 2. 실시간 국내 주식 현재가 조회 테스트
    st.subheader("2. 국내 주식 실시간 현재가(t1102 TR) 조회 테스트")
    
    col_s1, col_s2 = st.columns([2, 1])
    with col_s1:
        shcode_input = st.text_input("조회할 종목코드 (6자리)", value="005930")
    with col_s2:
        st.write("")
        fetch_btn = st.button("📊 실시간 시세 조회", type="primary", use_container_width=True)

    target_code = shcode_input.strip()
    
    with st.spinner(f"종목코드 [{target_code}] 실시간 시세 수신 중..."):
        quote_data, quote_err = fetch_stock_quote(target_code)

    if quote_err:
        st.error(f"⚠️ **시세 조회 오류:** {quote_err}")
    elif quote_data:
        hname = quote_data.get("hname", "-")
        price = float(quote_data.get("price", 0))
        diff = float(quote_data.get("change", 0))
        rate = float(quote_data.get("diff", 0))
        volume = int(quote_data.get("volume", 0))
        value = int(quote_data.get("value", 0))

        # 메트릭 카드 렌더링
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("종목명", f"{hname} ({target_code})")
        m2.metric(
            "현재가",
            f"{price:,.0f} 원",
            delta=f"{diff:+,.0f} 원 ({rate:+.2f}%)",
            delta_color="normal"
        )
        m3.metric("누적 거래량", f"{volume:,} 주")
        m4.metric("누적 거래대금", f"{value/100:,.0f} 억 원")

        st.markdown("#### 📋 수신된 원본 TR 데이터 (JSON)")
        st.json(quote_data)
