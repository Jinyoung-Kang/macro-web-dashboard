# views/cot_view.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from services.cot_service import fetch_cftc_cot_legacy

# 자산군별 CFTC Contract Code 매핑
ASSET_CODES = {
    "S&P 500 (E-MINI)": "13874A",
    "NASDAQ 100 (E-MINI)": "209742",
    "미국 국채 10년물 (10Y T-Note)": "043602",
    "달러 인덱스 (DXY)": "098662",
    "WTI 원유 (Crude Oil)": "067651",
    "금 (Gold)": "088691"
}

def render_cot_view():
    st.title("🏛️ 글로벌 스마트머니 (CFTC COT)")
    st.caption("헤지펀드 및 대형 투기자본(Non-Commercial)의 시장별 롱/숏 포지셔닝을 추적하여 글로벌 거시 트렌드의 극단값(과열/침체)을 분석합니다.")
    st.divider()

    # 상단 컨트롤 패널
    c1, c2 = st.columns([2, 1])
    with c1:
        selected_asset = st.selectbox("조회할 기초 자산 선택", list(ASSET_CODES.keys()), index=0)
    with c2:
        period_str = st.selectbox("조회 기간", ["최근 1년", "최근 3년", "최근 5년"], index=1)
        
    # 기간 설정 (1년 = 약 52주)
    limit_map = {"최근 1년": 52, "최근 3년": 156, "최근 5년": 260}
    weeks_to_fetch = limit_map[period_str]

    with st.spinner(f"{selected_asset}의 COT 데이터를 불러오는 중..."):
        df, err = fetch_cftc_cot_legacy(ASSET_CODES[selected_asset], limit=weeks_to_fetch)

    if err:
        st.error(err)
        return
    if df is None or df.empty:
        st.warning("데이터가 존재하지 않습니다.")
        return

    # 데이터 연산: 최신 기준일 및 증감 계산
    latest_date = df['date'].iloc[0]
    prev_date = df['date'].iloc[1] if len(df) > 1 else latest_date
    
    curr_net = df['net_position'].iloc[0]
    prev_net = df['net_position'].iloc[1] if len(df) > 1 else curr_net
    wow_change = curr_net - prev_net
    
    max_net = df['net_position'].max()
    min_net = df['net_position'].min()
    
    # COT Index 계산 (0 ~ 100%)
    if max_net - min_net == 0:
        cot_index = 50.0
    else:
        cot_index = ((curr_net - min_net) / (max_net - min_net)) * 100

    # 1. 핵심 지표 & 기준 날짜 대시보드
    st.markdown("### 📌 현재 포지션 요약")
    st.info(f"📅 **데이터 기준일(Report Date):** `{latest_date.strftime('%Y년 %m월 %d일')}` (매주 금요일 발표, 화요일 장마감 기준 집계)")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("투기세력 순포지션 (Net)", f"{curr_net:,.0f} 계약", f"{wow_change:+,.0f} 계약 (WoW)")
    col2.metric("롱 (Long / 매수)", f"{df['long'].iloc[0]:,.0f} 계약", f"{df['long'].iloc[0] - df['long'].iloc[1]:+,.0f} 계약")
    col3.metric("숏 (Short / 매도)", f"{df['short'].iloc[0]:,.0f} 계약", f"{- (df['short'].iloc[0] - df['short'].iloc[1]):+,.0f} 계약", delta_color="inverse")

    st.write("")

    # 2. 해석 및 가이드
    st.markdown("### 💡 데이터 해석 가이드")
    with st.expander("COT Index 기반 역발상 투자 시그널 (클릭하여 펼치기)", expanded=True):
        st.markdown(f"**현재 {selected_asset}의 COT Index:** `{cot_index:.1f}%`")
        st.progress(int(cot_index))
        st.markdown("""
        * **COT Index란?** 선택한 기간 내 최고/최저치 대비 현재 순포지션의 상대적 위치를 나타냅니다.
        * 🔴 **과열 구간 (80% 이상):** 투기 자본이 극단적인 매수(Long) 상태입니다. 더 이상 살 사람이 없어 **하락 반전(조정)**될 위험이 높습니다.
        * 🔵 **침체 구간 (20% 이하):** 투기 자본이 극단적인 매도(Short) 상태입니다. 매도 물량이 소진되어 숏커버링(Short Squeeze)에 의한 **상승 반전** 가능성이 큽니다.
        """)

    # 3. 메인 시계열 차트
    st.markdown("### 📊 투기세력 순포지션 추이")
    
    fig = go.Figure()
    # 순포지션을 막대그래프로 (양수: Blue, 음수: Red)
    colors = ['#EF4444' if val < 0 else '#3B82F6' for val in df['net_position']]
    fig.add_trace(go.Bar(
        x=df['date'], y=df['net_position'], 
        name="Net Position", 
        marker_color=colors,
        hovertemplate="%{x|%Y-%m-%d}<br>Net: %{y:,.0f}<extra></extra>"
    ))
    
    fig.update_layout(
        height=450,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="발표 일자",
        yaxis_title="순포지션 계약 수"
    )
    # 기준선(Zero Line)
    fig.update_yaxes(zeroline=True, zerolinewidth=2, zerolinecolor='gray')
    st.plotly_chart(fig, use_container_width=True)

    # 4. 상세 원본 데이터
    st.markdown(f"##### 📋 주간 포지션 원본 데이터 ({period_str})")
    disp_df = df.copy()
    disp_df['date'] = disp_df['date'].dt.strftime('%Y-%m-%d')
    disp_df.columns = ['발표일자', '롱(매수) 계약', '숏(매도) 계약', '순포지션(Net)']
    for c in disp_df.columns[1:]:
        disp_df[c] = disp_df[c].map('{:,.0f}'.format)
    st.dataframe(disp_df, use_container_width=True, hide_index=True)
