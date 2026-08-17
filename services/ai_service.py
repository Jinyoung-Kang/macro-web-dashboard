# services/ai_service.py
import re
import time
import requests
import streamlit as st

def get_secret(key_path: str, default: str = "") -> str:
    """Streamlit Cloud Settings 및 secrets.toml에서 안전하게 키를 추출하는 헬퍼 함수"""
    try:
        if not hasattr(st, "secrets") or not st.secrets:
            return default

        keys = key_path.split(".")
        val = st.secrets
        found = True
        for k in keys:
            if hasattr(val, "get") and val.get(k) is not None:
                val = val.get(k)
            elif hasattr(val, "__getitem__") and k in val:
                val = val[k]
            else:
                found = False
                break
        if found and val:
            return str(val).strip()

        leaf_key = keys[-1]
        if hasattr(st.secrets, "get") and st.secrets.get(leaf_key) is not None:
            return str(st.secrets.get(leaf_key)).strip()
        elif hasattr(st.secrets, "__getitem__") and leaf_key in st.secrets:
            return str(st.secrets[leaf_key]).strip()

        upper_key = leaf_key.upper()
        if hasattr(st.secrets, "get") and st.secrets.get(upper_key) is not None:
            return str(st.secrets.get(upper_key)).strip()
        elif hasattr(st.secrets, "__getitem__") and upper_key in st.secrets:
            return str(st.secrets[upper_key]).strip()

    except Exception:
        pass
    return default

def _call_openai_format(provider: str, url: str, api_key: str, model: str, prompt: str, timeout: int = 30) -> dict:
    """OpenAI 호환 API 공통 호출 내부 함수"""
    if not api_key:
        return {"status": False, "provider": provider, "model": model, "latency_ms": 0, "response": "API 키가 누락되었습니다."}
    
    headers = {
        "Authorization": f"Bearer {api_key}", 
        "Content-Type": "application/json"
    }
    payload = {
        "model": model, 
        "messages": [
            {"role": "system", "content": "You are a professional financial analyst. Always respond in fluent and clear Korean."},
            {"role": "user", "content": prompt}
        ], 
        "temperature": 0.2, 
        "max_tokens": 1500
    }
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"]
            return {"status": True, "provider": provider, "model": model, "latency_ms": latency, "response": text.strip()}
        else:
            return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except requests.exceptions.Timeout:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"타임아웃 에러 ({timeout}초 초과)"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}

# ==========================================
# 헬퍼 함수: 로컬 Ollama 및 Cloudflare 하이브리드 한글 번역기
# ==========================================
def translate_smart_korean(text: str, account_id: str = "", api_token: str = "") -> tuple[str, str]:
    """
    1) 맥북 로컬 Ollama (Llama 3.1) 우선 시도 (글자 수 제한 없음, 100% 무료)
    2) 로컬 Ollama 미실행 또는 클라우드 배포 시 Cloudflare Llama 3.1로 자동 우회
    """
    if not text:
        return text, "내용 없음"

    translate_prompt = (
        "다음 금융 텍스트를 핵심 맥락을 살려 자연스럽고 매끄러운 한국어로 번역해줘. "
        "서론이나 부연 설명 없이 번역 결과 본문만 출력해:\n\n"
        f"{text}"
    )

    # 1. 맥북 로컬 Ollama 시도 (http://localhost:11434)
    try:
        ollama_url = "http://localhost:11434/v1/chat/completions"
        ollama_payload = {
            "model": "llama3.1",
            "messages": [
                {"role": "system", "content": "You are a professional financial translator. Translate English into fluent Korean accurately."},
                {"role": "user", "content": translate_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 2048
        }
        res_ollama = requests.post(ollama_url, json=ollama_payload, timeout=8)
        if res_ollama.status_code == 200:
            translated = res_ollama.json()["choices"][0]["message"]["content"].strip()
            return translated, "🖥️ 맥북 로컬 Ollama (Llama-3.1) 무제한 번역 완료"
    except Exception:
        # 로컬 Ollama가 꺼져있거나 Streamlit Cloud 배포 환경일 경우 Cloudflare로 자동 전환
        pass

    # 2. Cloudflare Llama 3.1 8B 폴백 번역
    if account_id and api_token:
        cf_model = "@cf/meta/llama-3.1-8b-instruct"
        cf_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{cf_model}"
        cf_headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        cf_payload = {"messages": [{"role": "user", "content": translate_prompt}]}
        
        try:
            cf_resp = requests.post(cf_url, headers=cf_headers, json=cf_payload, timeout=20)
            if cf_resp.status_code == 200:
                data = cf_resp.json()
                if data.get("success"):
                    translated = data["result"]["response"].strip()
                    return translated, "☁️ Cloudflare (Llama-3.1-8B) 원격 번역 완료"
        except Exception:
            pass

    return text, "🔴 번역 실패 (원본 텍스트 유지)"

# ==========================================
# 개별 API 테스트 함수
# ==========================================
def test_local_ollama(prompt: str) -> dict:
    """맥북 로컬 Ollama Llama 3.1 테스트"""
    url = "http://localhost:11434/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "llama3.1",
        "messages": [
            {"role": "system", "content": "You are a professional financial analyst. Always respond in fluent and clear Korean."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 2048
    }
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        latency = int((time.time() - start_time) * 1000)
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"]
            return {"status": True, "provider": "Local Ollama (MacBook)", "model": "llama3.1", "latency_ms": latency, "response": text.strip()}
        else:
            return {"status": False, "provider": "Local Ollama (MacBook)", "model": "llama3.1", "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "Local Ollama (MacBook)", "model": "llama3.1", "latency_ms": latency, "response": f"로컬 연결 실패 (Ollama 앱 실행 여부 확인): {str(e)}"}

def test_cloudflare_ai(account_id: str, api_token: str, prompt: str) -> dict:
    """1순위: Cloudflare DeepSeek-R1-32B + 스마트 번역 연계"""
    model = "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b"
    if not account_id or not api_token:
        return {"status": False, "provider": "Cloudflare AI", "model": model, "latency_ms": 0, "response": "Account ID 또는 API Token 누락"}

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    payload = {"messages": [{"role": "user", "content": f"반드시 한국어로 요약해줘: {prompt}"}]}
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                raw = data["result"]["response"]
                cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                if not cleaned:
                    cleaned = raw.strip()
                
                translation_info = "⚪ 번역 생략 (자체 한글 출력)"
                if len(re.findall(r'[\uac00-\ud7a3]', cleaned)) < 15:
                    cleaned, translation_info = translate_smart_korean(cleaned, account_id, api_token)

                return {
                    "status": True, 
                    "provider": "Cloudflare AI", 
                    "model": model, 
                    "latency_ms": latency, 
                    "response": cleaned,
                    "translation_info": translation_info
                }
            else:
                return {"status": False, "provider": "Cloudflare AI", "model": model, "latency_ms": latency, "response": f"API Error: {data.get('errors')}"}
        else:
            return {"status": False, "provider": "Cloudflare AI", "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "Cloudflare AI", "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}

def test_nvidia_nemotron(api_key: str, prompt: str) -> dict:
    """2순위: NVIDIA Nemotron-3 Super 120B"""
    return _call_openai_format("NVIDIA NIM (Nemotron)", "https://integrate.api.nvidia.com/v1/chat/completions", api_key, "nvidia/nemotron-3-super-120b-a12b", prompt, timeout=40)

def test_nvidia_gpt_oss(api_key: str, prompt: str) -> dict:
    """3순위: NVIDIA GPT-OSS-20B"""
    return _call_openai_format("NVIDIA NIM (GPT-OSS)", "https://integrate.api.nvidia.com/v1/chat/completions", api_key, "openai/gpt-oss-20b", prompt, timeout=30)

def test_cerebras(api_key: str, prompt: str) -> dict:
    """4순위: Cerebras Cloud"""
    return _call_openai_format("Cerebras Cloud", "https://api.cerebras.ai/v1/chat/completions", api_key, "gpt-oss-120b", prompt, timeout=20)

# ==========================================
# 4단 Failover 무중단 AI 브리핑 생성 파이프라인
# ==========================================
def generate_ai_briefing_with_failover(prompt: str) -> dict:
    cf_id = get_secret("ai.cloudflare_account_id", "")
    cf_token = get_secret("ai.cloudflare_api_token", "")
    nv_key = get_secret("ai.nvidia_api_key", "")
    ce_key = get_secret("ai.cerebras_api_key", "")

    # 1순위
    if cf_id and cf_token:
        res = test_cloudflare_ai(cf_id, cf_token, prompt)
        if res["status"]:
            trans_msg = res.get("translation_info", "상태 없음")
            res["pipeline_step"] = f"1순위 (Cloudflare AI) 정상 응답 [{trans_msg}]"
            return res

    # 2순위
    if nv_key:
        res = test_nvidia_nemotron(nv_key, prompt)
        if res["status"]:
            res["pipeline_step"] = "2순위 (NVIDIA Nemotron-3) Failover 성공"
            return res

    # 3순위
    if nv_key:
        res = test_nvidia_gpt_oss(nv_key, prompt)
        if res["status"]:
            res["pipeline_step"] = "3순위 (NVIDIA GPT-OSS-20B) Failover 성공"
            return res

    # 4순위
    if ce_key:
        res = test_cerebras(ce_key, prompt)
        if res["status"]:
            res["pipeline_step"] = "4순위 (Cerebras Cloud) Failover 성공"
            return res

    return {
        "status": False,
        "provider": "None",
        "model": "Fallback",
        "latency_ms": 0,
        "pipeline_step": "모든 AI 엔진 연결 실패",
        "response": "현재 모든 AI 서버가 일시적인 트래픽 폭주 또는 점검 상태입니다. 잠시 후 다시 시도해 주세요."
    }
