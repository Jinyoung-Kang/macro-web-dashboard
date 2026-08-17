# services/ai_service.py
import time
import requests
import streamlit as st

def get_secret(key_path: str, default: str = "") -> str:
    """Streamlit Cloud Settings 및 로컬 secrets.toml에서 안전하게 키를 추출하는 헬퍼 함수"""
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

def _call_openai_format(provider, url, api_key, model, prompt, timeout=30):
    """OpenAI 호환 API 공통 호출 함수"""
    if not api_key:
        return {"status": False, "provider": provider, "model": model, "latency_ms": 0, "response": "API 키가 누락되었습니다. (Streamlit 설정의 Secrets를 확인하세요)"}
    
    headers = {
        "Authorization": f"Bearer {api_key}", 
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "Macro Web Dashboard"
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
            return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": "HTTP 402: 결제 수단 등록이 필요합니다."}
        else:
            return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except requests.exceptions.Timeout:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"타임아웃 에러 ({timeout}초 초과)"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": provider, "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}

# ==========================================
# 각 플랫폼별 호출 함수 (에러 발생 모델명 전면 수정)
# ==========================================
def test_openrouter(api_key: str, prompt: str) -> dict:
    # 가장 안정적인 최신 오픈모델인 openai/gpt-oss-120b 무료 버전으로 변경
    return _call_openai_format("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", api_key, "openai/gpt-oss-120b:free", prompt)

def test_cerebras(api_key: str, prompt: str) -> dict:
    # Cerebras의 공식 최신 모델인 gpt-oss-120b로 수정
    return _call_openai_format("Cerebras Cloud", "https://api.cerebras.ai/v1/chat/completions", api_key, "gpt-oss-120b", prompt)

def test_sambanova(api_key: str, prompt: str) -> dict:
    return _call_openai_format("SambaNova Cloud", "https://api.sambanova.ai/v1/chat/completions", api_key, "Meta-Llama-3.1-8B-Instruct", prompt)

def test_nvidia_nim(api_key: str, prompt: str) -> dict:
    return _call_openai_format("NVIDIA NIM", "https://integrate.api.nvidia.com/v1/chat/completions", api_key, "meta/llama-3.1-8b-instruct", prompt, timeout=60)

def test_cloudflare_ai(account_id: str, api_token: str, prompt: str) -> dict:
    model = "@cf/meta/llama-3.1-8b-instruct"
    if not account_id or not api_token:
        return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": 0, "response": "Account ID 또는 API Token이 누락되었습니다."}

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
            return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": "HTTP 401: 인증 실패. Cloudflare API 토큰 권한을 확인하세요."}
        else:
            return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}
