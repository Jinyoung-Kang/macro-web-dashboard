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
        "max_tokens": 500
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
# 헬퍼 함수: 영어 텍스트를 NVIDIA NIM으로 한글 번역
# ==========================================
def translate_to_korean_via_nvidia(text: str, nv_key: str) -> str:
    """DeepSeek의 영어 응답을 NVIDIA NIM을 통해 자연스러운 한국어 금융 문장으로 번역"""
    if not nv_key or not text:
        return text
    
    translate_prompt = (
        "다음 금융/거시경제 분석 텍스트를 핵심 맥락을 살려 자연스럽고 간결한 한국어로 번역해줘. "
        "다른 설명 없이 번역된 한국어 결과만 출력해:\n\n"
        f"{text}"
    )
    
    trans_res = _call_openai_format("NVIDIA NIM", "https://integrate.api.nvidia.com/v1/chat/completions", nv_key, "meta/llama-3.1-8b-instruct", translate_prompt, timeout=25)
    if trans_res["status"]:
        return trans_res["response"].strip()
    return text

# ==========================================
# 1. 개별 API 호출 함수 (우선순위 순서)
# ==========================================
def test_cloudflare_ai(account_id: str, api_token: str, prompt: str, nv_key: str = "") -> dict:
    """1순위: Cloudflare Workers AI (DeepSeek-R1-32B) + NVIDIA 한글 번역"""
    model = "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b"
    if not account_id or not api_token:
        return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": 0, "response": "Account ID 또는 API Token이 누락되었습니다."}

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    
    # 한국어 유도 프롬프트
    enhanced_prompt = f"반드시 한국어로 명확하고 간결하게 답변해줘: {prompt}"
    payload = {"messages": [{"role": "user", "content": enhanced_prompt}]}
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                raw_response = data["result"]["response"]
                
                # 1) DeepSeek의 <think>...</think> 태그 제거
                cleaned_text = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL).strip()
                if not cleaned_text:
                    cleaned_text = raw_response.strip()

                # 2) 한글 글자 수가 적고 영어가 대부분인 경우 NVIDIA NIM으로 한글 번역 수행
                korean_char_count = len(re.findall(r'[\uac00-\ud7a3]', cleaned_text))
                if korean_char_count < 15 and nv_key:
                    cleaned_text = translate_to_korean_via_nvidia(cleaned_text, nv_key)

                return {"status": True, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": latency, "response": cleaned_text}
            else:
                return {"status": False, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": latency, "response": f"API Error: {data.get('errors')}"}
        else:
            return {"status": False, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}

def test_cerebras(api_key: str, prompt: str) -> dict:
    """2순위: Cerebras Cloud (GPT-OSS-120B)"""
    return _call_openai_format("Cerebras Cloud", "https://api.cerebras.ai/v1/chat/completions", api_key, "gpt-oss-120b", prompt, timeout=20)

def test_nvidia_nim(api_key: str, prompt: str) -> dict:
    """3순위: NVIDIA NIM (Llama-3.1-8B)"""
    return _call_openai_format("NVIDIA NIM", "https://integrate.api.nvidia.com/v1/chat/completions", api_key, "meta/llama-3.1-8b-instruct", prompt, timeout=30)

# ==========================================
# 2. 3단 Failover 무중단 AI 브리핑 생성 파이프라인
# ==========================================
def generate_ai_briefing_with_failover(prompt: str) -> dict:
    """
    1순위: Cloudflare Workers AI (DeepSeek-R1-32B) -> NVIDIA로 한글 번역
    2순위: Cerebras Cloud (GPT-OSS-120B)
    3순위: NVIDIA NIM (Llama-3.1-8B)
    """
    cf_id = get_secret("ai.cloudflare_account_id", "")
    cf_token = get_secret("ai.cloudflare_api_token", "")
    ce_key = get_secret("ai.cerebras_api_key", "")
    nv_key = get_secret("ai.nvidia_api_key", "")

    # [1순위] Cloudflare Workers AI
    if cf_id and cf_token:
        res = test_cloudflare_ai(cf_id, cf_token, prompt, nv_key=nv_key)
        if res["status"]:
            res["pipeline_step"] = "1순위 (Cloudflare Workers AI) 정상 응답 [한글 변환 완료]"
            return res

    # [2순위] Cerebras Cloud
    if ce_key:
        res = test_cerebras(ce_key, prompt)
        if res["status"]:
            res["pipeline_step"] = "2순위 (Cerebras Cloud) Failover 우회 성공"
            return res

    # [3순위] NVIDIA NIM
    if nv_key:
        res = test_nvidia_nim(nv_key, prompt)
        if res["status"]:
            res["pipeline_step"] = "3순위 (NVIDIA NIM) Failover 우회 성공"
            return res

    # 모든 엔진 실패 시 Graceful Fallback
    return {
        "status": False,
        "provider": "None",
        "model": "Fallback",
        "latency_ms": 0,
        "pipeline_step": "모든 AI 엔진 연결 실패",
        "response": "현재 모든 AI 서버가 일시적인 트래픽 폭주 또는 점검 상태입니다. 잠시 후 다시 새로고침해 주세요."
    }
