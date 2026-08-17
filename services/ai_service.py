# services/ai_service.py
import time
import requests
import streamlit as st

def get_secret(key_path, default=""):
    keys = key_path.split(".")
    val = st.secrets
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return str(val) if val else default

def _call_openai_format(provider, url, api_key, model, prompt, timeout=30):
    """OpenAI API 규격을 사용하는 플랫폼 공통 호출 함수"""
    if not api_key:
        return {"status": False, "provider": provider, "model": model, "latency_ms": 0, "response": "API 키가 누락되었습니다. (.streamlit/secrets.toml 확인)"}
    
    headers = {
        "Authorization": f"Bearer {api_key}", 
        "Content-Type": "application/json"
    }
    payload = {
        "model": model, 
        "messages": [{"role": "user", "content": prompt}], 
        "temperature": 0.2, 
        "max_tokens": 300
    }
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"]
            return {"status": True, "provider": provider, "model": model, "latency_ms": latency, "response": text.strip()}
        elif resp.status_code == 402:
            return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": "HTTP 402: 결제 수단 등록이 필요합니다. (플랫폼에 카드 등록 필요)"}
        else:
            return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except requests.exceptions.Timeout:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"타임아웃 에러 ({timeout}초 초과): 서버 콜드스타트 지연"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}

# ==========================================
# 각 플랫폼별 호출 래퍼 함수 (최신 무료 모델 슬러그 적용)
# ==========================================
def test_openrouter(api_key: str, prompt: str) -> dict:
    # 70B 모델 유료화로 인해 100% 무료인 8B 모델로 교체
    return _call_openai_format("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", api_key, "meta-llama/llama-3.1-8b-instruct:free", prompt)

def test_cerebras(api_key: str, prompt: str) -> dict:
    # 404 에러 방지를 위해 정확한 모델명 적용
    return _call_openai_format("Cerebras Cloud", "https://api.cerebras.ai/v1/chat/completions", api_key, "llama3.1-8b", prompt)

def test_sambanova(api_key: str, prompt: str) -> dict:
    # SambaNova 402 에러 대비
    return _call_openai_format("SambaNova Cloud", "https://api.sambanova.ai/v1/chat/completions", api_key, "Meta-Llama-3.1-8B-Instruct", prompt)

def test_nvidia_nim(api_key: str, prompt: str) -> dict:
    # NVIDIA 콜드스타트 타임아웃 방지를 위해 8B 모델로 낮추고 타임아웃 60초 부여
    return _call_openai_format("NVIDIA NIM", "https://integrate.api.nvidia.com/v1/chat/completions", api_key, "meta/llama-3.1-8b-instruct", prompt, timeout=60)

def test_cloudflare_ai(account_id: str, api_token: str, prompt: str) -> dict:
    model = "@cf/meta/llama-3.1-8b-instruct"
    if not account_id or not api_token:
        return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": 0, "response": "Account ID 또는 Token 누락"}

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    payload = {"messages": [{"role": "user", "content": prompt}]}
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                return {"status": True, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": data["result"]["response"].strip()}
            else:
                return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": f"API Error: {data.get('errors')}"}
        elif resp.status_code == 401:
            return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": "HTTP 401: 인증 에러. Cloudflare 대시보드에서 'Workers AI' 권한이 있는 API 토큰을 새로 발급받아 입력하세요."}
        else:
            return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}
