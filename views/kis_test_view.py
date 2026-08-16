# views/kis_test_view.py
import streamlit as st
from services.kis_service import (
    get_kis_token,
    fetch_kis_kospi_index,
    fetch_kis_stock_quote
)

def render_kis_test_view():
    st.title("🧪 한국투자증권 REST API 연동 테스트")
    st.caption("발급받은 실전투자 APP Key 및 Secret을 기반으로 토큰 발급 및 실시간 데이터를 검증합니다.")

    # 1. 토큰 발급 상태 검증
    st.subheader("1. OAuth 2.0 인증 토큰 발급 테스트")
    col_t1, col_t2 = st.columns([3, 1])
    with col_t2:
        reissue = st.button("🔄 캐시 초기화 & 재조회", use_container_width=True, key="kis_reissue")
        if reissue:
            st.cache_data.clear()
            st.rerun()

    with st.spinner("한국투자증권 인증 서버와 통신 중..."):
        token, token_err = get_kis_token()

    if token_err or not token:
        st.error(f"❌ **인증 실패:** {token_err}")
        st.info("💡 `secrets.toml`에 `[kis_api]`의 `app_key`와 `app_secret`이 실전투자용인지 확인하세요.", icon="ℹ️")
        return
    else:
        st.success("✅ **한국투자증권 OAuth 2.0 인증 성공!**")
        with st.expander("🔑 발급된 토큰 정보 (보안 마스킹)"):
            st.code(f"{token[:15]}...{token[-10:]}", language="text")

    st.divider()

    # 2. 코스피 실시간 지수 TR 조회 테스트
    st.subheader("2. 코스피 실시간 지수 TR 조회 테스트")
    with st.spinner("코스피 실시간 지수 수신 중..."):
        kospi_data, kospi_err = fetch_kis_kospi_index()

    if kospi_data:
        st.success(f"✅ **코스피 지수 수신 성공:** {kospi_data['hname']}")
        k1, k2, k3 = st.columns(3)
        k1.metric("코스피 지수", f"{kospi_data['price']:,.2f} pt")
        k2.metric("전일 대비 등락", f"{kospi_data['diff']:+.2f} pt ({kospi_data['rate']:+.2f}%)")
        k3.metric("전일 종가", f"{kospi_data['prev_price']:,.2f} pt")
    else:
        st.error("⚠️ **코스피 지수 데이터를 수신하지 못했습니다.**")
        st.code(f"상세 원인: {kospi_err}", language="text")

    st.divider()

    # 3. 개별 종목 현재가 TR 조회 테스트
    st.subheader("3. 개별 종목 현재가 TR 조회 테스트")
    col_s1, col_s2 = st.columns([2, 1])
    with col_s1:
        shcode_input = st.text_input("조회할 종목코드 (6자리)", value="005930", key="kis_shcode_input")
    with col_s2:
        st.write("")
        st.button("📊 실시간 시세 조회", type="primary", use_container_width=True, key="kis_fetch_btn")

    target_code = shcode_input.strip()
    with st.spinner(f"종목코드 [{target_code}] 실시간 시세 수신 중..."):
        quote_data, quote_err = fetch_kis_stock_quote(target_code)

    if quote_err:
        st.error(f"⚠️ **시세 조회 오류:** {quote_err}")
    elif quote_data:
        # 한국투자증권 응답 필드 파싱
        price = float(quote_data.get("stck_prpr", 0))       # 현재가
        diff = float(quote_data.get("prdy_vrss", 0))        # 전일대비
        rate = float(quote_data.get("prdy_cttr", 0))        # 등락률
        volume = int(quote_data.get("acml_vol", 0))         # 누적거래량
        value = int(quote_data.get("acml_tr_pbmn", 0))      # 누적거래대금
        
        # 하락 부호 보정
        sign = str(quote_data.get("prdy_vrss_sign", "3"))
        if sign in ["4", "5"]:
            diff = -abs(diff)
            rate = -abs(rate)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("종목코드", f"{target_code}")
        m2.metric("현재가", f"{price:,.0f} 원", delta=f"{diff:+,.0f} 원 ({rate:+.2f}%)")
        m3.metric("누적 거래량", f"{volume:,} 주")
        m4.metric("누적 거래대금", f"{value/100000000:,.0f} 억 원")

        st.markdown("#### 📋 수신된 원본 데이터 (JSON)")
        st.json(quote_data)
