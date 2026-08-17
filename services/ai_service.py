# services/ai_service.py
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
        "messages": [{"role": "user", "content": prompt}], 
        "temperature": 0.2, 
        "max_tokens": 400
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
# 1. 개별 API 호출/테스트 함수 (3대 엔진)
# ==========================================
def test_cerebras(api_key: str, prompt: str) -> dict:
    return _call_openai_format("Cerebras Cloud", "https://api.cerebras.ai/v1/chat/completions", api_key, "gpt-oss-120b", prompt, timeout=20)

def test_cloudflare_ai(account_id: str, api_token: str, prompt: str) -> dict:
    model = "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b"
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
        else:
            return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return {"status": False, "provider": "Cloudflare", "model": model, "latency_ms": latency, "response": f"통신 에러: {str(e)}"}

def test_nvidia_nim(api_key: str, prompt: str) -> dict:
    return _call_openai_format("NVIDIA NIM", "https://integrate.api.nvidia.com/v1/chat/completions", api_key, "deepseek-ai/deepseek-r1-distill-qwen-32b", prompt, timeout=40)

# ==========================================
# 2. 3단 Failover 무중단 AI 브리핑 생성 파이프라인
# ==========================================
def generate_ai_briefing_with_failover(prompt: str) -> dict:
    """
    Cerebras (1순위) -> Cloudflare (2순위) -> NVIDIA NIM (3순위)
    순서대로 시도하며 첫 번째 성공 응답을 즉시 반환하는 무중단 Failover 엔진
    """
    ce_key = get_secret("ai.cerebras_api_key", "")
    cf_id = get_secret("ai.cloudflare_account_id", "")
    cf_token = get_secret("ai.cloudflare_api_token", "")
    nv_key = get_secret("ai.nvidia_api_key", "")

    # 1순위: Cerebras (초고속 엔진)
    if ce_key:
        res = test_cerebras(ce_key, prompt)
        if res["status"]:
            res["pipeline_step"] = "1순위 (Cerebras Cloud) 정상 응답"
            return res

    # 2순위: Cloudflare Workers AI (글로벌 엣지 백업)
    if cf_id and cf_token:
        res = test_cloudflare_ai(cf_id, cf_token, prompt)
        if res["status"]:
            res["pipeline_step"] = "2순위 (Cloudflare Workers AI) Failover 우회 성공"
            return res

    # 3순위: NVIDIA NIM (최종 비상 백업)
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
