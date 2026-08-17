# services/ai_service.py
import time
import requests
import streamlit as st

def get_secret(key_path, default=""):
    """secrets.toml에서 안전하게 키를 추출하는 헬퍼 함수"""
    keys = key_path.split(".")
    val = st.secrets
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return str(val) if val else default

def test_google_ai(api_key: str, prompt: str = "금융 시장의 핵심 거시경제 지표 3가지만 단답형으로 나열해줘.") -> dict:
    """1. Google AI Studio (Gemini 2.0 Flash) 테스트"""
    if not api_key:
        return {"status": False, "provider": "Google AI Studio", "model": "gemini-2.0-flash", "latency_ms": 0, "response": "API 키가 입력되지 않았습니다."}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return {"status": True, "provider": "Google AI Studio", "model": "gemini-2.0-flash", "latency_ms": latency, "response": text.strip()}
        else:
            return {"status": False, "provider": "Google AI Studio", "model": "gemini-2.0-flash", "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "Google AI Studio", "model": "gemini-2.0-flash", "latency_ms": latency, "response": f"통신 에러: {str(e)}"}

def test_nvidia_nim(api_key: str, model: str = "meta/llama-3.3-70b-instruct", prompt: str = "금융 시장의 핵심 거시경제 지표 3가지만 단답형으로 나열해줘.") -> dict:
    """2. NVIDIA NIM (Llama 3.3 70B Instruct) 테스트"""
    if not api_key:
        return {"status": False, "provider": "NVIDIA NIM", "model": model, "latency_ms": 0, "response": "API 키가 입력되지 않았습니다."}
    
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 200
    }
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return {"status": True, "provider": "NVIDIA NIM", "model": model, "latency_ms": latency, "response": text.strip()}
        else:
            return {"status": False, "provider": "NVIDIA NIM", "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "NVIDIA NIM", "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}

def test_cloudflare_ai(account_id: str, api_token: str, model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast", prompt: str = "금융 시장의 핵심 거시경제 지표 3가지만 단답형으로 나열해줘.") -> dict:
    """3. Cloudflare Workers AI (Llama 3.3 70B) 테스트"""
    if not account_id or not api_token:
        return {"status": False, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": 0, "response": "Account ID 또는 API Token이 누락되었습니다."}
    
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"role": "user", "content": prompt}]
    }
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success", False):
                text = data["result"]["response"]
                return {"status": True, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": latency, "response": text.strip()}
            else:
                return {"status": False, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": latency, "response": f"Cloudflare API Error: {data.get('errors')}"}
        else:
            return {"status": False, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "Cloudflare Workers AI", "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}
