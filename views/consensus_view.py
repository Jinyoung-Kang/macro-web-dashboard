# views/consensus_view.py
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from config import INSTITUTIONS
from services.consensus_service import get_consensus_data

def render_consensus_view():
    st.title("🎯 기관 13F Money 교집합 분석 (Consensus Holdings)")
    st.caption("2개 이상의 주요 글로벌 기관이 동시에 보유하거나 집중 매수한 공통 종목(컨센서스)을 발굴합니다.")

    # 1. 기관 다중 선택 설정
    inst_names = list(INSTITUTIONS.keys())
    default_selected = [
        "🇺🇸 버크셔 해서웨이 (Berkshire Hathaway)",
        "🇺🇸 듀케인 패밀리 오피스 (Duquesne Family Office)",
        "🇺🇸 아팔루사 매니지먼트 (Appaloosa Management)"
    ]
    valid_defaults = [name for name in default_selected if name in inst_names]

    col_cfg1, col_cfg2 = st.columns([3, 1])
    with col_cfg1:
        selected_insts = st.multiselect(
            "비교할 기관을 선택하세요 (최소 2개 이상 권장)",
            options=inst_names,
            default=valid_defaults
        )
    with col_cfg2:
        min_overlap = st.number_input("최소 공통 보유 기관 수", min_value=2, max_value=max(2, len(selected_insts)), value=2)

    if len(selected_insts) < 2:
        st.warning("⚠️ 공통 교집합을 분석하려면 최소 2개 이상의 기관을 선택해주세요.")
        return

    selected_dict = {name: INSTITUTIONS[name] for name in selected_insts}

    with st.spinner("선택된 기관들의 13F 포트폴리오를 대조 분석 중입니다..."):
        consensus_res = get_consensus_data(selected_dict)

    if not consensus_res or consensus_res['summary'].empty:
        st.error("데이터를 불러오지 못했거나 공통 보유 종목이 없습니다.")
        return

    summary_df = consensus_res['summary']
    filtered_df = summary_df[summary_df['holder_count'] >= min_overlap].copy()

    # 2. 메인 요약 메트릭
    m1, m2, m3 = st.columns(3)
    m1.metric("분석 대상 기관 수", f"{consensus_res['institution_count']} 개")
    m2.metric(f"공통 보유 종목 수 (최소 {min_overlap}개 기관)", f"{len(filtered_df):,} 개")
    
    co_buy_count = len(filtered_df[filtered_df['buy_action_count'] >= min_overlap])
    m3.metric("동시 순매수/비중확대 종목", f"{co_buy_count:,} 개", help=f"선택한 {min_overlap}개 이상 기관이 동시에 매수한 종목")

    st.divider()

    # 3. 탭별 시각화
    tab1, tab2, tab3 = st.tabs([
        "📊 공통 보유 상위 랭킹", 
        "🔥 동시 매수(신규/확대) 집중주", 
        "📋 전체 공통 보유 종목 상세표"
    ])

    with tab1:
        top_n = st.selectbox("표시할 상위 종목 수", [10, 15, 20, 30], index=0, key="consensus_top_n")
        plot_df = filtered_df.head(top_n).sort_values(by='total_value', ascending=True).copy()

        if not plot_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=plot_df['total_value'] / 1e6,
                y=plot_df['name'],
                orientation='h',
                marker=dict(
                    color=plot_df['holder_count'],
                    colorscale='Viridis',
                    colorbar=dict(title="보유 기관 수")
                ),
                text=plot_df.apply(lambda r: f"{r['holder_count']}개 기관 (${r['total_value']/1e6:,.0f}M)", axis=1),
                textposition='outside',
                hovertemplate="<b>%{y}</b><br>합산 평가액: $%{x:,.1f}M<extra></extra>"
            ))
            fig.update_layout(
                height=max(420, top_n * 28 + 80),
                title=f"기관 13F Money 합산 평가액 상위 Top {top_n} (보유 기관수 색상 매핑)",
                xaxis_title="합산 평가액 ($M)",
                yaxis_title="",
                margin=dict(l=20, r=40, t=40, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"최소 {min_overlap}개 기관이 겹치는 공통 보유 종목이 없습니다.")

    with tab2:
        st.markdown("#### 🚀 기관들이 동시에 매수한 종목 (Conviction Buys)")
        buy_filtered = filtered_df[filtered_df['buy_action_count'] >= 2].sort_values(by=['buy_action_count', 'total_value'], ascending=[False, False])
        
        if not buy_filtered.empty:
            for _, row in buy_filtered.head(10).iterrows():
                with st.expander(f"⭐ **{row['name']}** — {row['buy_action_count']}개 기관 동시 매수 (합산 ${row['total_value']/1e6:,.1f}M)"):
                    st.write(f"**보유 기관:** {row['holders_str']}")
                    st.write(f"**평균 포트폴리오 비중:** `{row['avg_weight']:.2f}%` (최대 `{row['max_weight']:.2f}%`)")
        else:
            st.info("선택된 기관들이 직전 분기 대비 동시에 신규 매수하거나 비중을 확대한 종목이 없습니다.")

    with tab3:
        st.subheader(f"📋 교집합 보유 목록 ({len(filtered_df)}개 종목)")
        display_tbl = filtered_df[['name', 'holder_count', 'holders_str', 'total_value', 'avg_weight', 'buy_action_count']].copy()
        display_tbl.columns = ['종목명 (Issuer)', '보유 기관수', '보유 기관 목록', '합산 평가액($)', '평균 비중(%)', '매수 활동 기관수']
        display_tbl['합산 평가액($)'] = display_tbl['합산 평가액($)'].map('${:,.0f}'.format)
        display_tbl['평균 비중(%)'] = display_tbl['평균 비중(%)'].map('{:.2f}%'.format)
        st.dataframe(display_tbl, use_container_width=True, hide_index=True)
