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
            {"role": "system", "content": "You are a professional financial analyst. Always respond in fluent and clear Korean. Do not include introductory or explanatory phrases."},
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
# 헬퍼 함수: Cloudflare Llama-3.1-8B를 이용한 고품질 한글 번역
# ==========================================
def translate_to_korean_via_cloudflare(text: str, account_id: str, api_token: str) -> tuple[str, str]:
    """Cloudflare Llama 3.1 8B 모델을 이용해 영어 텍스트를 자연스러운 한국어로 번역"""
    if not account_id or not api_token or not text:
        return text, "🔴 번역 불가 (인증키 누락)"

    model = "@cf/meta/llama-3.1-8b-instruct"
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    
    translate_prompt = (
        "다음 텍스트를 전문가의 어조로 자연스럽고 매끄러운 한국어로 번역해. "
        "서론, 배경 설명, 인사말을 절대 포함하지 말고 번역된 결과만 즉시 출력해:\n\n"
        f"{text}"
    )
    
    payload = {
        "messages": [{"role": "user", "content": translate_prompt}],
        "max_tokens": 1500
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                translated_text = data["result"]["response"].strip()
                return translated_text, "🟢 Llama-3.1-8B 한글 번역 보정 완료"
            else:
                return text, f"🔴 번역 API 실패: {data.get('errors')}"
        else:
            return text, f"🔴 번역 HTTP 에러: {resp.status_code}"
    except Exception as e:
        return text, f"🔴 번역 통신 에러: {str(e)}"

# ==========================================
# 개별 API 테스트 함수 (4개 모델)
# ==========================================
def test_cloudflare_ai(account_id: str, api_token: str, prompt: str) -> dict:
    """1순위: Cloudflare DeepSeek-R1-32B + Llama 3.1 8B 번역 연계"""
    model = "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b"
    if not account_id or not api_token:
        return {"status": False, "provider": "Cloudflare AI", "model": model, "latency_ms": 0, "response": "Account ID 또는 API Token 누락"}

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    
    # 서론을 자르기 위해 프롬프트 강화
    enhanced_prompt = f"서론이나 부연 설명 없이, 반드시 핵심만 한국어로 요약해줘: {prompt}"
    payload = {"messages": [{"role": "user", "content": enhanced_prompt}], "max_tokens": 1500}
    
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
                # 한글 글자 수가 15자 미만이면 Llama 3.1 8B 번역기 가동
                if len(re.findall(r'[\uac00-\ud7a3]', cleaned)) < 15:
                    cleaned, translation_info = translate_to_korean_via_cloudflare(cleaned, account_id, api_token)

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
    """4순위: Cerebras GPT-OSS-120b"""
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
            res["pipeline_step"] = "4순위 (Cerebras GPT-OSS-120b) Failover 성공"
            return res

    return {
        "status": False,
        "provider": "None",
        "model": "Fallback",
        "latency_ms": 0,
        "pipeline_step": "모든 AI 엔진 연결 실패",
        "response": "현재 모든 AI 서버가 일시적인 트래픽 폭주 또는 점검 상태입니다. 잠시 후 다시 시도해 주세요."
    }
