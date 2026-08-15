# config.py

MACRO_CATEGORIES = {
    "💵 통화 및 환율 :gray[(실시간)]": {
        "달러 인덱스 (DXY) :gray[[실시간]]": "DX-Y.NYB",
        "원/달러 (USD/KRW) :gray[[실시간]]": "KRW=X",
        "달러/엔 (USD/JPY) :gray[[실시간]]": "JPY=X",
        "엔/원 100엔당 (JPY/KRW) :gray[[실시간]]": "JPYKRW=X"
    },
    "🏛️ 미국 국채 금리 :gray[(15분 지연)]": {
        "미국채 2년물 금리(%) :gray[[15분 지연]]": "2YY=F",
        "미국채 10년물 금리(%) :gray[[15분 지연]]": "^TNX",
        "미국채 30년물 금리(%) :gray[[15분 지연]]": "^TYX"
    },
    "🛢️ 원자재 :gray[(15분 지연)]": {
        "WTI 원유 ($) :gray[[15분 지연]]": "CL=F",
        "브렌트유 ($) :gray[[15분 지연]]": "BZ=F",
        "금 선물 ($) :gray[[15분 지연]]": "GC=F"
    },
    "🇺🇸 미국 주가지수 및 선물 :gray[(15분 지연)]": {
        "S&P 500 :gray[[15분 지연]]": "^GSPC",
        "S&P 500 선물 (ES) :gray[[15분 지연]]": "ES=F",
        "나스닥 100 :gray[[15분 지연]]": "^NDX",
        "나스닥 선물 (NQ) :gray[[15분 지연]]": "NQ=F"
    },
    "🌏 아시아 주요 주가지수 :gray[(15분 지연)]": {
        "코스피 (KOSPI) :gray[[15분 지연]]": "^KS11",
        "닛케이 225 (Nikkei) :gray[[15분 지연]]": "^N225",
        "상하이 종합 (SSE) :gray[[15분 지연]]": "000001.SS",
        "항셍 지수 (HSI) :gray[[15분 지연]]": "^HSI"
    }
}

INSTITUTIONS = {
    "🇰🇷 국민연금 (National Pension Service)": {"cik": "0001608046", "desc": "글로벌 자산배분 및 미국 대형 우량주 중심 장기 투자"},
    "🇺🇸 버크셔 해서웨이 (Berkshire Hathaway)": {"cik": "0001067983", "desc": "워런 버핏의 가치투자 포트폴리오, 핵심 우량주 집중"},    
    "🇺🇸 듀케인 패밀리 오피스 (Duquesne Family Office)": {"cik": "0001536411", "desc": "조지 소로스의 오른팔, 30년간 연평균 30% 수익률을 낸 전설. 테크 트렌드를 포착"},
    "🇺🇸 아팔루사 매니지먼트 (Appaloosa Management)": {"cik": "0001006438", "desc": "데이비드 테퍼의 딥밸류, 부실채권(Distressed) 및 테크/중국 성장주 베팅"},
    "🇺🇸 브리지워터 어소시에이츠 (Bridgewater)": {"cik": "0001350694", "desc": "레이 달리오 설립, 올웨더 및 글로벌 매크로 헤지펀드"},
    "🇺🇸 사이언 자산운용 (Scion Asset Management)": {"cik": "0001649339", "desc": "마이클 버리의 역발상 딥밸류 및 숏(풋옵션)/롱 전략"},
    "🇺🇸 피셔 자산운용 (Fisher Asset Management)": {"cik": "0000850529", "desc": "켄 피셔의 글로벌 성장주 및 빅테크 중심 탑다운 롱온리 전략(군중 심리를 역이용)"},
    "🇺🇸 블랙록 (BlackRock)": {"cik": "0002012383", "desc": "세계 최대 자산운용사, 광범위한 글로벌 자산군"},
    "🇺🇸 뱅가드 (Vanguard Group)": {"cik": "0000102909", "desc": "글로벌 인덱스 펀드의 거두, 시장 전체를 아우르는 포트폴리오"}
}

SPREAD_TABLE_DATA = {
    "시장 상태": ["정상 (Normal)", "평탄화 (Flattening)", "역전 (Inversion) ⚠️"],
    "스프레드 수치": ["양수 (+)", "0에 수렴", "음수 (-)"],
    "시장의 심리 및 해석": [
        "장기 미래의 불확실성(프리미엄)으로 인해 장기 금리가 더 높음.",
        "미래 경기 성장이 둔화될 것이라는 우려가 커지기 시작함.",
        "현재 인플레이션을 잡기 위해 금리를 급격히 올렸으나, 미래 경기는 침체될 것으로 확신함."
    ],
    "경제적 귀결": [
        "경제의 점진적인 성장 및 안정적 확장",
        "경기 정점 통과 및 둔화 신호",
        "역사적으로 1~2년 내 경기 침체(Recession) 도래"
    ]
}

RISK_MODEL_TABLE = {
    "지표명 (지연 수준)": [
        "CBOE VIX [15분 지연]", 
        "ICE BofA MOVE [지연/마감]", 
        "하이일드 스프레드 [1일 지연 EOD]",
        "3M 금융 CP 스프레드 [1일 지연 EOD]",
        "STLFSI4 금융스트레스지수 [주간]"
    ],
    "정상 / 안정 범위": [
        "15 ~ 20 (15 미만: 과도한 낙관)", 
        "80 ~ 120 (80 미만: 금리 초안정)", 
        "3.5% ~ 5.0% (3.5% 미만: 유동성 풍부)",
        "0.20%p ~ 0.50%p (0.20%p 미만: 풍부한 단기 유동성)",
        "0.0 이하 (0.0은 역사적 장기 평균치)"
    ],
    "위험 / 발작 임계치": [
        "30 이상 (패닉 / 급락 / 투매)", 
        "140 이상 (채권 발작 / 긴축 충격)", 
        "7.0% 이상 (본격 신용경색 / 경기침체)",
        "0.80%p ~ 1.00%p 이상 (단기 자금시장 유동성 경색)",
        "+1.0 이상 (금융 시스템 충격 및 위기 경보)"
    ],
    "지표의 성격 및 핵심 해석": [
        "주식 시장의 단기 공포 측정기. 급등 시 주가 급락 및 투매 발생 신호.",
        "채권 시장의 공포 지수. 연준 통화정책 불확실성과 유동성 경색에 민감하게 반응.",
        "한계 기업의 부도 리스크 프리미엄. 경기 침체 진입 시 가장 먼저 급등하는 신용 선행 지표.",
        "은행·금융기관의 3개월 단기 자금조달 가산금리(현대판 TED 스프레드). 은행권 유동성 위기 발생 시 급등.",
        "18개 금융시장 지표(자금, 채권, 주식 등)를 종합한 복합 척도. 0보다 크면 스트레스 고조, 1.0 초과 시 시스템 위기."
    ]
}

LIVE_CLOCK_HTML = """
<div style="
    display: flex; 
    flex-wrap: wrap;
    gap: 15px; 
    align-items: center; 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: rgba(255, 255, 255, 0.04); 
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px; 
    padding: 8px 14px; 
    color: #e0e0e0;
    font-size: 13.5px;
    margin-bottom: 5px;
">
    <div style="display: flex; align-items: center; gap: 6px;">
        <span>🇰🇷 <b>한국 (KST)</b></span>
        <span id="live-kst" style="font-family: monospace; font-weight: bold; color: #4da3ff; font-size: 14.5px;">--:--:--</span>
    </div>
    <div style="color: rgba(255, 255, 255, 0.25);">|</div>
    <div style="display: flex; align-items: center; gap: 6px;">
        <span>🗽 <b>뉴욕 (EST/EDT)</b></span>
        <span id="live-ny" style="font-family: monospace; font-weight: bold; color: #ffb74d; font-size: 14.5px;">--:--:--</span>
    </div>
</div>
<script>
function updateLiveClocks() {
    const now = new Date();
    const optKST = { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
    const optNY = { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
    
    document.getElementById('live-kst').innerText = new Intl.DateTimeFormat('ko-KR', optKST).format(now);
    document.getElementById('live-ny').innerText = new Intl.DateTimeFormat('ko-KR', optNY).format(now);
}
updateLiveClocks();
setInterval(updateLiveClocks, 1000);
</script>
"""
