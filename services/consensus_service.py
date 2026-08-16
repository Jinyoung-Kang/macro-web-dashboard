# services/consensus_service.py
import pandas as pd
from services.sec_service import fetch_sec_13f_multi_quarters, classify_qoq_action

def get_consensus_data(selected_institutions: dict, target_quarter_idx: int = 0):
    """
    선택된 기관들의 13F 데이터를 취합하여 공통 보유 및 동시 매수 종목을 추출합니다.
    """
    institution_dfs = {}
    
    for inst_name, inst_info in selected_institutions.items():
        history_results, err = fetch_sec_13f_multi_quarters(inst_info['cik'], max_quarters=4)
        if not err and history_results and len(history_results) > target_quarter_idx:
            curr_df, curr_meta = history_results[target_quarter_idx]
            curr_df = curr_df.copy()
            curr_df['institution'] = inst_name
            curr_df['report_date'] = curr_meta['report_date']
            
            # 직전 분기 대비 액션 계산
            if len(history_results) > target_quarter_idx + 1:
                prev_df, _ = history_results[target_quarter_idx + 1]
                merged = pd.merge(
                    curr_df[['name', 'shares', 'weight', 'value']],
                    prev_df[['name', 'shares', 'weight', 'value']],
                    on='name',
                    how='outer',
                    suffixes=('_curr', '_prev')
                ).fillna(0)
                merged['shares_diff'] = merged['shares_curr'] - merged['shares_prev']
                merged['weight_diff'] = merged['weight_curr'] - merged['weight_prev']
                merged['action'] = merged.apply(classify_qoq_action, axis=1)
                
                curr_df = pd.merge(curr_df, merged[['name', 'action', 'weight_diff']], on='name', how='left')
            else:
                curr_df['action'] = "정보 없음"
                curr_df['weight_diff'] = 0.0
                
            institution_dfs[inst_name] = curr_df

    if not institution_dfs:
        return None

    # 전체 데이터 취합
    all_records = pd.concat(institution_dfs.values(), ignore_index=True)
    
    # 종목별 집계 (교집합 분석)
    summary_df = all_records.groupby('name').agg(
        holder_count=('institution', 'nunique'),
        holders=('institution', lambda x: list(x)),
        total_value=('value', 'sum'),
        avg_weight=('weight', 'mean'),
        max_weight=('weight', 'max'),
        actions=('action', lambda x: list(x))
    ).reset_index()

    # 원문 기관명 리스트 포맷팅
    summary_df['holders_str'] = summary_df['holders'].apply(lambda h_list: ", ".join([h.split()[1] if len(h.split()) > 1 else h for h in h_list]))
    
    # 동시 매수(신규 매수/비중 확대) 여부 집계
    summary_df['buy_action_count'] = summary_df['actions'].apply(
        lambda acts: sum(1 for a in acts if "신규 매수" in str(a) or "비중 확대" in str(a))
    )

    return {
        "raw_records": all_records,
        "summary": summary_df.sort_values(by=['holder_count', 'total_value'], ascending=[False, False]).reset_index(drop=True),
        "institution_count": len(institution_dfs)
    }
