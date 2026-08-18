# services/sec_service.py
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re
import xml.etree.ElementTree as ET
import streamlit as st
import time
from config import INSTITUTIONS

@st.cache_data(ttl=86400)
def fetch_sec_13f_multi_quarters(cik: str, max_quarters: int = 4):
    """
    최대 max_quarters 분기만큼의 13F 공시를 역순으로 수집하여
    [(df, meta_info), (df_prev, meta_info_prev), ...] 형태로 반환
    """
    base_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F-HR&dateb=&owner=exclude&count=20"
    
    # [수정1] SEC 공식 가이드라인 헤더 강제 지정 (단순 IP 차단 및 Timeout 에러 방어)
    headers = {
        "User-Agent": "MacroDashboard/2.0 (contact@macrodashboard.com) Mozilla/5.0",
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov"
    }

    try:
        res = requests.get(base_url, headers=headers, timeout=15)
        res.raise_for_status()
    except requests.exceptions.RequestException as e:
        return None, f"SEC EDGAR 연결 실패: {str(e)}"

    soup = BeautifulSoup(res.text, "html.parser")
    tables = soup.find_all("table", class_="tableFile2")
    if not tables:
        return None, f"해당 CIK({cik})의 13F-HR 검색 결과 테이블을 찾을 수 없습니다."

    rows = tables[0].find_all("tr")[1:]
    history_links = []
    
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 4:
            doc_type = cols[0].text.strip()
            if doc_type == "13F-HR":
                a_tag = cols[1].find("a", href=True)
                filing_date = cols[3].text.strip()
                if a_tag:
                    doc_link = "https://www.sec.gov" + a_tag['href']
                    history_links.append((filing_date, doc_link))
        
        if len(history_links) >= max_quarters:
            break

    if not history_links:
        return None, "13F-HR 공시 문서를 찾을 수 없습니다."

    all_results = []
    for filing_date, doc_url in history_links:
        try:
            time.sleep(0.15) # SEC API 초당 호출 횟수 제한(Rate Limit) 우회
            doc_res = requests.get(doc_url, headers=headers, timeout=15)
            doc_res.raise_for_status()
        except requests.exceptions.RequestException as e:
            continue

        doc_soup = BeautifulSoup(doc_res.text, "html.parser")
        xml_url = None
        tables2 = doc_soup.find_all("table", class_="tableFile")
        
        if tables2:
            for r in tables2[0].find_all("tr")[1:]:
                c = r.find_all("td")
                if len(c) >= 3:
                    fname = c[2].find("a", href=True)
                    if fname and fname.text.strip().endswith(".xml"):
                        doc_text = c[1].text.strip().lower()
                        if "information table" in doc_text or "infotable" in doc_text:
                            xml_url = "https://www.sec.gov" + fname['href']
                            break
                        if not xml_url:
                            xml_url = "https://www.sec.gov" + fname['href']

        if not xml_url:
            continue

        try:
            time.sleep(0.15)
            xml_res = requests.get(xml_url, headers=headers, timeout=20)
            xml_res.raise_for_status()
        except requests.exceptions.RequestException as e:
            continue

        root = ET.fromstring(xml_res.content)
        ns = {'n': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {'n': ''}

        data = []
        for info in root.findall('n:infoTable', ns):
            name = info.find('n:nameOfIssuer', ns).text if info.find('n:nameOfIssuer', ns) is not None else ''
            title_class = info.find('n:titleOfClass', ns).text if info.find('n:titleOfClass', ns) is not None else ''
            cusip = info.find('n:cusip', ns).text if info.find('n:cusip', ns) is not None else ''
            val_text = info.find('n:value', ns).text if info.find('n:value', ns) is not None else '0'
            
            shrs_info = info.find('n:shrsOrPrnAmt', ns)
            shares = 0
            if shrs_info is not None:
                shamt = shrs_info.find('n:sshPrnamt', ns)
                if shamt is not None:
                    shares = float(shamt.text)
            
            # [수정2] 2023년 이후 SEC 13F XML의 Value는 실제 달러(Exact USD) 단위임.
            # 과거의 천 달러 기준 곱하기(* 1000)를 삭제하여 AUM이 1,000배 부풀려지는 현상 방지.[cite: 22]
            try:
                val = float(val_text)
            except ValueError:
                val = 0.0

            data.append({
                'name': name,
                'class': title_class,
                'cusip': cusip,
                'value': val,
                'shares': shares
            })

        if not data:
            continue

        df = pd.DataFrame(data)
        
        # [스마트 보정] 총 자산이 $100M(13F 최소 신고액) 미만이면, 과거 천 달러 축약본으로 간주하고 * 1000 복원[cite: 22]
        if df['value'].sum() > 0 and df['value'].sum() < 100_000_000:
            df['value'] = df['value'] * 1000.0
            
        # 종목명(CUSIP 기준)으로 그룹화하여 옵션/본주 분산 표기 합산[cite: 22]
        df = df.groupby(['name', 'cusip', 'class'], as_index=False).agg({'value':'sum', 'shares':'sum'})
        df = df.sort_values(by='value', ascending=False).reset_index(drop=True)
        
        total_aum = df['value'].sum()
        df['weight'] = (df['value'] / total_aum) * 100

        # 대략적인 Report Date 추정 (Filing date에서 가장 가까운 직전 분기말)[cite: 22]
        fd_dt = pd.to_datetime(filing_date)
        year = fd_dt.year
        month = fd_dt.month
        
        if month in [1, 2, 3]: report_date = f"{year-1}-12-31"
        elif month in [4, 5, 6]: report_date = f"{year}-03-31"
        elif month in [7, 8, 9]: report_date = f"{year}-06-30"
        else: report_date = f"{year}-09-30"

        meta_info = {
            "filing_date": filing_date,
            "report_date": report_date
        }
        
        all_results.append((df, meta_info))

    if not all_results:
        return None, "성공적으로 추출된 분기 데이터가 없습니다."

    return all_results, None

def classify_qoq_action(row):
    """직전 분기 대비 비중 증감폭을 기준으로 매수/매도/유지 액션 분류"""
    diff = row['weight_diff']
    shares_curr = row['shares_curr']
    shares_prev = row['shares_prev']
    
    if shares_prev == 0 and shares_curr > 0:
        return "🆕 신규 매수 (New)"
    elif shares_curr == 0 and shares_prev > 0:
        return "❌ 전량 매도 (Closed)"
    elif diff > 0.05:
        return "📈 비중 확대 (Added)"
    elif diff < -0.05:
        return "📉 비중 축소 (Reduced)"
    else:
        return "⚪ 유지 (Unchanged)"

def format_currency(val):
    if val >= 1e9:
        return f"${val/1e9:,.2f}B"
    elif val >= 1e6:
        return f"${val/1e6:,.2f}M"
    else:
        return f"${val:,.0f}"

# ==========================================
# 🆕 Consensus (교집합) 분석용 헬퍼 함수
# ==========================================

@st.cache_data(ttl=86400)
def load_all_institutions_data():
    """등록된 모든 기관의 가장 최신 분기 13F 데이터를 일괄 수집하여 딕셔너리로 반환"""
    data = {}
    for inst_name, info in INSTITUTIONS.items():
        hist, err = fetch_sec_13f_multi_quarters(info['cik'], max_quarters=1)
        if hist and not err:
            df, meta = hist[0]
            data[inst_name] = {
                'df': df,
                'meta': meta
            }
        time.sleep(0.2) # SEC API 밴 방지 (Rate Limit)[cite: 22]
    return data

def calculate_consensus(inst_data):
    """
    모든 기관 데이터를 취합하여 공통 보유 종목(교집합)을 계산하는 함수.
    반환: DataFrame (보유 기관 수, 평균 비중, 보유 기관 리스트 등 포함)
    """
    if not inst_data:
        return pd.DataFrame()

    all_holdings = []
    
    # 1. 모든 기관의 종목 데이터를 하나의 리스트로 취합
    for inst_name, data in inst_data.items():
        df = data['df'].copy()
        df['Institution'] = inst_name
        
        # 종목명 전처리 (불필요한 공백, INC, CORP 등 제거하여 매칭 확률 높임)[cite: 22]
        df['Name_Clean'] = df['name'].str.upper().str.replace(r'\b(INC|CORP|LLC|LTD|PLC|COMPANY|CO)\b', '', regex=True)
        df['Name_Clean'] = df['Name_Clean'].str.replace(r'[^\w\s]', '', regex=True).str.strip()
        
        # 각 기관별 상위 100개 종목만 추출 (꼬리 종목 노이즈 제거)[cite: 22]
        df = df.head(100)
        
        for _, row in df.iterrows():
            all_holdings.append({
                'Name': row['name'],
                'Name_Clean': row['Name_Clean'],
                'Ticker': row['cusip'][:6], # 임시로 CUSIP 앞자리를 티커 대용으로 사용
                'Weight': row['weight'],
                'Institution': row['Institution']
            })

    # 2. 취합된 데이터를 데이터프레임으로 변환
    holdings_df = pd.DataFrame(all_holdings)
    
    if holdings_df.empty:
        return pd.DataFrame()

    # 3. 'Name_Clean' 기준으로 그룹화하여 교집합 계산[cite: 22]
    consensus = holdings_df.groupby('Name_Clean').agg(
        Name=('Name', 'first'),          # 원래 이름 1개 가져오기
        Ticker=('Ticker', 'first'),
        Institution_Count=('Institution', 'nunique'), # 보유 기관 수
        Avg_Weight=('Weight', 'mean'),   # 평균 비중
        Holders=('Institution', list)    # 어떤 기관들이 보유했는지 리스트화
    ).reset_index()

    # 4. 2개 기관 이상 보유한 종목만 필터링 후 기관 수 -> 비중 순으로 정렬
    consensus = consensus[consensus['Institution_Count'] >= 2]
    consensus = consensus.sort_values(by=['Institution_Count', 'Avg_Weight'], ascending=[False, False]).reset_index(drop=True)
    
    # 불필요한 컬럼 정리
    consensus = consensus.drop(columns=['Name_Clean'])

    return consensus

def get_top_holdings_by_inst(inst_data, inst_name, top_n=20):
    """특정 기관의 상위 N개 보유 종목 데이터를 보기 좋게 포맷팅하여 반환"""
    if inst_name not in inst_data:
        return pd.DataFrame()
    
    df = inst_data[inst_name]['df'].head(top_n).copy()
    
    # 출력용 컬럼 정리
    df_display = df[['name', 'cusip', 'weight', 'value', 'shares']].copy()
    df_display.columns = ['종목명 (Issuer)', 'CUSIP', '비중 (%)', '평가액 ($)', '보유 주식수']
    df_display['비중 (%)'] = df_display['비중 (%)'].map('{:.2f}%'.format)
    df_display['평가액 ($)'] = df_display['평가액 ($)'].map('${:,.0f}'.format)
    df_display['보유 주식수'] = df_display['보유 주식수'].map('{:,.0f}'.format)
    
    return df_display
