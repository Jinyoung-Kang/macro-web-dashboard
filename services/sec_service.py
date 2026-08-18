"""
services/sec_service.py
SEC EDGAR 13F-HR 공시 데이터 수집 및 기관 포트폴리오 분석 엔진
(강력한 Session 기반 통신 방어, 콤마 수치 정제 및 무적 ElementTree XML 파서 탑재)
"""
import logging
import re
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
        backoff_factor=1.5,
        status_forcelist=[403, 408, 429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    return session


# ==============================================================================
# 2. 통합 13F 분기 데이터 크롤러 (콤마 제거 수치 변환 및 무적 XML 파서 적용)
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
            if "13F-HR" in doc_type:
                a_tag = cols[1].find("a", href=True)
                filing_date = cols[3].text.strip()
                if a_tag:
                    doc_link = a_tag['href'] if a_tag['href'].startswith("http") else "https://www.sec.gov" + a_tag['href']
                    history_links.append((filing_date, doc_link))
        
        if len(history_links) >= max_quarters:
            break

    if not history_links:
        return None, "13F-HR 공시 문서를 찾을 수 없습니다."

    all_results = []
    for filing_date, doc_url in history_links:
        try:
            time.sleep(0.2) # SEC API 호출 제한(Rate Limit) 준수
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
                    if fname and fname.text.strip().lower().endswith(".xml"):
                        doc_text = c[1].text.strip().lower()
                        href = fname['href']
                        full_href = href if href.startswith("http") else "https://www.sec.gov" + href
                        if "information table" in doc_text or "infotable" in doc_text:
                            xml_url = full_href
                            break
                        if not xml_url:
                            xml_url = full_href

        # 테이블에서 못 찾을 경우 XML 링크 검색 Fallback
        if not xml_url:
            for a in doc_soup.find_all("a", href=True):
                href = a['href']
                if href.lower().endswith(".xml") and not href.lower().endswith("primary_doc.xml"):
                    xml_url = href if href.startswith("http") else "https://www.sec.gov" + href
                    if "infotable" in href.lower() or "information" in href.lower():
                        break

        if not xml_url:
            continue

        try:
            time.sleep(0.2)
            xml_res = session.get(xml_url, timeout=30)
            xml_res.raise_for_status()
        except Exception as e:
            logger.warning(f"13F XML 다운로드 타임아웃 ({filing_date}): {e}")
            continue

        # =====================================================================
        # XML 파싱 (네임스페이스 무시 및 콤마 완벽 제거)
        # =====================================================================
        try:
            root = ET.fromstring(xml_res.content)
            data = []
            
            for info_table in root.iter():
                if info_table.tag.lower().endswith("infotable"):
                    name, title_class, cusip, val_text = "", "", "", "0"
                    shares = 0.0
                    
                    for child in info_table.iter():
                        tag_name = child.tag.lower()
                        text = child.text.strip() if child.text else ""
                        
                        if tag_name.endswith("nameofissuer"):
                            name = text
                        elif tag_name.endswith("titleofclass"):
                            title_class = text
                        elif tag_name.endswith("cusip"):
                            cusip = text
                        elif tag_name.endswith("value"):
                            val_text = text
                        elif tag_name.endswith("sshprnamt"):
                            try:
                                shares = float(text.replace(",", "").strip()) if text else 0.0
                            except (ValueError, TypeError):
                                shares = 0.0
                    
                    # 콤마 제거 후 부동소수점 변환
                    try:
                        val = float(val_text.replace(",", "").strip()) if val_text else 0.0
                    except (ValueError, TypeError):
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
        
        # 2023년 이전 공시 파일이거나 합산액이 $10M 미만인 경우 천 달러 단위로 간주하고 보정
        if df['value'].sum() > 0 and df['value'].sum() < 10_000_000:
            df['value'] = df['value'] * 1000.0
            
        # 종목명(CUSIP 기준)으로 그룹화하여 옵션/본주 분산 표기 합산
        df = df.groupby(['name', 'cusip', 'class'], as_index=False).agg({'value':'sum', 'shares':'sum'})
        df = df.sort_values(by='value', ascending=False).reset_index(drop=True)
        
        total_aum = df['value'].sum()
        df['weight'] = (df['value'] / total_aum) * 100.0 if total_aum > 0 else 0.0

        # Report Date 추정 (Filing date에서 가장 가까운 직전 분기말)
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
        return None, "성공적으로 추출된 분기 데이터가 없습니다. (기관의 공시 문서가 비어있거나 파싱 가능한 13F XML이 없습니다.)"

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
        time.sleep(0.2)
    return data


def calculate_consensus(inst_data):
    """모든 기관 데이터를 취합하여 공통 보유 종목(교집합)을 계산하는 함수"""
    if not inst_data:
        return pd.DataFrame()

    all_holdings = []
    for inst_name, data in inst_data.items():
        df = data['df'].copy()
        df['Institution'] = inst_name
        df['Name_Clean'] = df['name'].str.upper().str.replace(r'\b(INC|CORP|LLC|LTD|PLC|COMPANY|CO)\b', '', regex=True)
        df['Name_Clean'] = df['Name_Clean'].str.replace(r'[^\w\s]', '', regex=True).str.strip()
        df = df.head(100)
        
        for _, row in df.iterrows():
            all_holdings.append({
                'Name': row['name'],
                'Name_Clean': row['Name_Clean'],
                'Ticker': row['cusip'][:6] if 'cusip' in row else '',
                'Weight': row['weight'],
                'Institution': row['Institution']
            })

    holdings_df = pd.DataFrame(all_holdings)
    if holdings_df.empty:
        return pd.DataFrame()

    consensus = holdings_df.groupby('Name_Clean').agg(
        Name=('Name', 'first'),
        Ticker=('Ticker', 'first'),
        Institution_Count=('Institution', 'nunique'),
        Avg_Weight=('Weight', 'mean'),
        Holders=('Institution', list)
    ).reset_index()

    consensus = consensus[consensus['Institution_Count'] >= 2]
    consensus = consensus.sort_values(by=['Institution_Count', 'Avg_Weight'], ascending=[False, False]).reset_index(drop=True)
    consensus = consensus.drop(columns=['Name_Clean'])

    return consensus


def get_top_holdings_by_inst(inst_data, inst_name, top_n=20):
    """특정 기관의 상위 N개 보유 종목 데이터를 보기 좋게 포맷팅하여 반환"""
    if inst_name not in inst_data:
        return pd.DataFrame()
    
    df = inst_data[inst_name]['df'].head(top_n).copy()
    df_display = df[['name', 'cusip', 'weight', 'value', 'shares']].copy()
    df_display.columns = ['종목명 (Issuer)', 'CUSIP', '비중 (%)', '평가액 ($)', '보유 주식수']
    df_display['비중 (%)'] = df_display['비중 (%)'].map('{:.2f}%'.format)
    df_display['평가액 ($)'] = df_display['평가액 ($)'].map('${:,.0f}'.format)
    df_display['보유 주식수'] = df_display['보유 주식수'].map('{:,.0f}'.format)
    
    return df_display
