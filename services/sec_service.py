# services/sec_service.py
import streamlit as st
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import pandas as pd

@st.cache_data(ttl=86400, show_spinner=False)
def parse_single_13f(cik: str, acc_clean: str, accession_number: str, report_date: str, user_agent: str):
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    dir_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/index.json"
    
    try:
        dir_resp = requests.get(dir_url, headers=headers, timeout=15)
        xml_filename = None
        if dir_resp.status_code == 200:
            dir_data = dir_resp.json()
            for item in dir_data.get('directory', {}).get('item', []):
                name = item.get('name', '')
                if name.endswith('.xml') and not name.startswith('primary') and '13f' in name.lower():
                    xml_filename = name
                    break
            if not xml_filename:
                for item in dir_data.get('directory', {}).get('item', []):
                    name = item.get('name', '')
                    if name.endswith('.xml') and not name.startswith('primary'):
                        xml_filename = name
                        break
        
        if not xml_filename:
            htm_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{accession_number}-index.htm"
            htm_resp = requests.get(htm_url, headers=headers, timeout=15)
            if htm_resp.status_code == 200:
                soup = BeautifulSoup(htm_resp.text, 'html.parser')
                for row in soup.find_all('tr'):
                    text = row.get_text()
                    if 'INFORMATION TABLE' in text and '.xml' in text:
                        for link in row.find_all('a'):
                            if link.get('href', '').endswith('.xml'):
                                xml_filename = link.get('href').split('/')[-1]
                                break

        if not xml_filename:
            return None

        xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{xml_filename}"
        xml_resp = requests.get(xml_url, headers=headers, timeout=25)
        if xml_resp.status_code != 200:
            return None

        root = ET.fromstring(xml_resp.content)
        holdings = []
        for child in root:
            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if tag_name.lower() in ['infotable', 'informationtable']:
                row = {}
                for elem in child:
                    t = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                    if t == 'nameOfIssuer':
                        row['name'] = elem.text.strip().upper() if elem.text else ""
                    elif t == 'titleOfClass':
                        row['class'] = elem.text
                    elif t == 'cusip':
                        row['cusip'] = elem.text
                    elif t == 'value':
                        try:
                            row['value'] = float(elem.text)
                        except Exception:
                            row['value'] = 0.0
                    elif t == 'shrsOrPrnAmt':
                        for sub in elem:
                            subt = sub.tag.split('}')[-1] if '}' in sub.tag else sub.tag
                            if subt == 'sshPrnamt':
                                try:
                                    row['shares'] = float(sub.text)
                                except Exception:
                                    row['shares'] = 0.0
                if row.get('name') and row.get('value', 0) > 0:
                    holdings.append(row)

        if not holdings:
            return None

        df = pd.DataFrame(holdings)
        total_v = df['value'].sum()
        if total_v < 10000000 and len(df) > 10:
            df['value'] = df['value'] * 1000

        df = df.groupby('name', as_index=False).agg({
            'value': 'sum',
            'shares': 'sum',
            'class': 'first',
            'cusip': 'first'
        })
        df['weight'] = (df['value'] / df['value'].sum()) * 100
        df['report_date'] = report_date
        return df
    except Exception:
        return None

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_sec_13f_multi_quarters(cik: str, max_quarters: int = 8):
    user_agent = st.secrets.get("sec", {}).get("user_agent", "MacroDashboard user@gmail.com")
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    
    try:
        sub_url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        r = requests.get(sub_url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None, f"SEC API 접근 실패 (상태 코드: {r.status_code})"
        
        sub_data = r.json()
        recent = sub_data.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        
        quarters_to_fetch = []
        seen_dates = set()
        
        for idx, f in enumerate(forms):
            if f in ['13F-HR', '13F-HR/A']:
                r_date = recent['reportDate'][idx]
                if r_date not in seen_dates:
                    seen_dates.add(r_date)
                    quarters_to_fetch.append({
                        "accession_number": recent['accessionNumber'][idx],
                        "report_date": r_date,
                        "filing_date": recent['filingDate'][idx]
                    })
                if len(quarters_to_fetch) >= max_quarters:
                    break

        if not quarters_to_fetch:
            return None, "13F 공시 이력을 찾을 수 없습니다."

        parsed_dfs = []
        for q in quarters_to_fetch:
            acc_clean = q['accession_number'].replace('-', '')
            df_q = parse_single_13f(cik, acc_clean, q['accession_number'], q['report_date'], user_agent)
            if df_q is not None and not df_q.empty:
                parsed_dfs.append((df_q, q))

        if not parsed_dfs:
            return None, "13F 데이터를 파싱하지 못했습니다."

        return parsed_dfs, None
    except Exception as e:
        return None, f"오류 발생: {str(e)}"

def classify_qoq_action(row):
    if row['shares_prev'] == 0 and row['shares_curr'] > 0:
        return "🟢 신규 매수 (New Buy)"
    elif row['shares_curr'] == 0 and row['shares_prev'] > 0:
        return "🔴 전량 매도 (Sold Out)"
    elif row['shares_diff'] > 0:
        return "🔵 비중 확대 (Increased)"
    elif row['shares_diff'] < 0:
        return "🟡 비중 축소 (Decreased)"
    else:
        return "⚪ 유지 (Unchanged)"
