"""
services/sec_service.py
SEC EDGAR 13F-HR 공시 데이터 수집 및 기관 포트폴리오 분석 엔진
(강력한 Session 기반 통신 방어 및 네임스페이스 무시 내장 XML 파서 탑재)
"""
import logging
import time
import xml.etree.ElementTree as ET
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import streamlit as st
from config import INSTITUTIONS

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. SEC 전용 강행 돌파 통신 세션 설정 (Timeout, Rate Limit 완벽 방어)
# ==============================================================================
def get_sec_session() -> requests.Session:
    """SEC EDGAR의 엄격한 연결 끊김 현상을 방어하기 위한 강력한 세션 생성기"""
    session = requests.Session()
    
    # SEC 공식 가이드라인 규격 헤더 (필수)
    session.headers.update({
        "User-Agent": "MacroQuantResearchApp/3.0 (admin@macroquant.com)",
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov"
    })
    
    # 타임아웃(Read timed out) 및 접속 거부 시 최대 5회 기하급수적 재시도(Exponential Backoff)
    retries = Retry(
        total=5,
        backoff_factor=1.5, # 1.5s, 3s, 6s... 간격으로 대기 후 재시도
        status_forcelist=[403, 408, 429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    return session


# ==============================================================================
# 2. 통합 13F 분기 데이터 크롤러 (실제 달러 단위 판별 및 무적 XML 파서 적용)
# ==============================================================================
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_sec_13f_multi_quarters(cik: str, max_quarters: int = 4):
    """
    최대 max_quarters 분기만큼의 13F 공시를 수집하여
    [(df, meta_info), (df_prev, meta_info_prev), ...] 형태로 반환
    """
    clean_cik = str(cik).lstrip("0")
    base_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={clean_cik}&type=13F-HR&dateb=&owner=exclude&count=20"
    
    session = get_sec_session()

    try:
        res = session.get(base_url, timeout=30)
        res.raise_for_status()
    except Exception as e:
        return None, f"SEC EDGAR 연결 실패 (서버 점검 또는 통신 지연): {str(e)}\n우측 상단의 [데이터 새로고침] 버튼을 눌러주세요."

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
            # 13F-HR 공시 문서만 추출 (수정 공시 제외)
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
            time.sleep(0.3) # SEC API 초당 호출 횟수 제한(Rate Limit)을 안전하게 우회
            doc_res = session.get(doc_url, timeout=30)
            doc_res.raise_for_status()
        except Exception as e:
            logger.warning(f"13F 문서 페이지 접근 실패 ({filing_date}): {e}")
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
            time.sleep(0.3)
            xml_res = session.get(xml_url, timeout=30)
            xml_res.raise_for_status()
        except Exception as e:
            logger.warning(f"13F XML 다운로드 타임아웃 ({filing_date}): {e}")
            continue

        # =====================================================================
        # [핵심 수정]: lxml 의존성이 없는 순수 파이썬 내장 ElementTree 무적 파서
        # 기관별로 제각각인 XML Namespace(xmlns)를 완전히 무시하고 태그 끝단어만 추적합니다.
        # =====================================================================
        try:
            root = ET.fromstring(xml_res.content)
            data = []
            
            # 문서 내의 모든 태그를 순회하면서 infoTable을 찾아냄
            for info_table in root.iter():
                if info_table.tag.lower().endswith("infotable"):
                    name, title_class, cusip, val_text = "", "", "", "0"
                    shares = 0.0
                    
                    # infoTable 내부의 자식 태그들을 네임스페이스 무시하고 탐색
                    for child in info_table.iter():
                        tag_name = child.tag.lower()
                        if tag_name.endswith("nameofissuer"):
                            name = child.text
                        elif tag_name.endswith("titleofclass"):
                            title_class = child.text
                        elif tag_name.endswith("cusip"):
                            cusip = child.text
                        elif tag_name.endswith("value"):
                            val_text = child.text
                        elif tag_name.endswith("sshprnamt"):
                            try:
                                shares = float(child.text) if child.text else 0.0
                            except ValueError:
                                pass
                    
                    # 2023년 이후 SEC 13F XML의 Value는 '실제 달러(Exact USD)' 단위
                    try:
                        val = float(val_text)
                    except ValueError:
                        val = 0.0

                    if name and val > 0:
                        data.append({
                            'name': name.strip().upper(),
                            'class': title_class.strip() if title_class else "",
                            'cusip': cusip.strip() if cusip else "",
                            'value': val,
                            'shares': shares
                        })
        except Exception as e:
            logger.warning(f"XML 파싱 에러 ({filing_date}): {e}")
            continue

        if not data:
            continue

        df = pd.DataFrame(data)
        
        # [스마트 스케일러] 2023년 이전 공시 파일이거나 총 AUM이 비정상적으로 작다면 '천 달러 단위' 축약본으로 간주
        if df['value'].sum() > 0 and df['value'].sum() < 100_000_000:
            df['value'] = df['value'] * 1000.0
            
        # 종목명(CUSIP 기준)으로 그룹화하여 옵션/본주 분산 표기 합산
        df = df.groupby(['name', 'cusip', 'class'], as_index=False).agg({'value':'sum', 'shares':'sum'})
        df = df.sort_values(by='value', ascending=False).reset_index(drop=True)
        
        total_aum = df['value'].sum()
        df['weight'] = (df['value'] / total_aum) * 100

        # 대략적인 Report Date 추정 (Filing date에서 가장 가까운 직전 분기말)
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
        return None, "성공적으로 추출된 분기 데이터가 없습니다. (기관의 공시 문서가 비어있거나 지원되지 않는 형식입니다.)"

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


# ==============================================================================
# 3. Consensus (교집합) 분석용 헬퍼 함수
# ==============================================================================
@st.cache_data(ttl=86400, show_spinner=False)
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
        time.sleep(0.3) # SEC API 밴 방지 (Rate Limit)
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
        
        # 종목명 전처리 (불필요한 공백, INC, CORP 등 제거하여 매칭 확률 높임)
        df['Name_Clean'] = df['name'].str.upper().str.replace(r'\b(INC|CORP|LLC|LTD|PLC|COMPANY|CO)\b', '', regex=True)
        df['Name_Clean'] = df['Name_Clean'].str.replace(r'[^\w\s]', '', regex=True).str.strip()
        
        # 각 기관별 상위 100개 종목만 추출 (꼬리 종목 노이즈 제거)
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

    # 3. 'Name_Clean' 기준으로 그룹화하여 교집합 계산
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
