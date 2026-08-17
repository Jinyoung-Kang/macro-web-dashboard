# services/ai_service.py
import re
import time
import requests
import streamlit as st
from services.prompts import INVESTMENT_AGENT_PROMPT

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

def _call_openai_format(provider: str, url: str, api_key: str, model: str, prompt: str, system_prompt: str = "You are a professional financial analyst. Always respond in fluent and clear Korean. Do not include introductory or explanatory phrases.", timeout: int = 40) -> dict:
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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ], 
        "temperature": 0.2, 
        "max_tokens": 3000
    }
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"]
            # 표 렌더링 방해하는 <br> 태그 일괄 공백 치환
            text = re.sub(r'(?i)&lt;br\s*/?&gt;|<br\s*/?>', ' ', text)
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
# 헬퍼 함수 1: NVIDIA GPT-OSS-20B 1순위 번역
# ==========================================
def translate_to_korean_via_nvidia(text: str, api_key: str) -> tuple[bool, str]:
    if not api_key or not text:
        return False, text

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    system_prompt = "You are a professional financial translator. Translate the text into 100% natural Korean. Do not leave any Chinese characters."
    translate_prompt = (
        "다음 텍스트에 포함된 모든 중국어와 한자를 완벽하고 자연스러운 100% 한국어(한글)로 번역해. "
        "예를 들어 '美聯儲'는 '미 연준'으로, '下次'는 '다음'으로 변환해. "
        "어떤 경우에도 한자나 중국어 병기를 남기지 마. 서론, 배경 설명, 인사말을 빼고 오직 번역된 결과만 즉시 출력해:\n\n"
        f"{text}"
    )

    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": translate_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 2000
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 200:
            translated_text = resp.json()["choices"][0]["message"]["content"].strip()
            translated_text = translated_text.replace("美聯儲", "미 연준").replace("下次", "다음")
            # HTML 태그 제거
            translated_text = re.sub(r'(?i)&lt;br\s*/?&gt;|<br\s*/?>', ' ', translated_text)
            return True, translated_text
        else:
            return False, text
    except Exception:
        return False, text

# ==========================================
# 헬퍼 함수 2: Cloudflare Llama-3.1-8B 2순위 번역
# ==========================================
def translate_to_korean_via_cloudflare(text: str, account_id: str, api_token: str) -> tuple[str, str]:
    if not account_id or not api_token or not text:
        return text, "🔴 번역 불가 (인증키 누락)"

    model = "@cf/meta/llama-3.1-8b-instruct"
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    
    translate_prompt = (
        "다음 텍스트에 포함된 모든 중국어와 한자를 완벽하고 자연스러운 100% 한국어(한글)로 번역해. "
        "예를 들어 '美聯儲'는 '미 연준'으로 변환해. 어떤 경우에도 한자나 중국어 병기를 남기지 마. "
        "서론, 배경 설명, 인사말을 빼고 오직 번역된 결과만 즉시 출력해:\n\n"
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
                translated_text = translated_text.replace("美聯儲", "미 연준").replace("下次", "다음") 
                # HTML 태그 제거
                translated_text = re.sub(r'(?i)&lt;br\s*/?&gt;|<br\s*/?>', ' ', translated_text)
                return translated_text, "🟡 CF Llama-3.1-8B 우회 번역 완료"
            else:
                return text, f"🔴 CF 번역 API 실패: {data.get('errors')}"
        else:
            return text, f"🔴 CF 번역 HTTP 에러: {resp.status_code}"
    except Exception as e:
        return text, f"🔴 CF 번역 통신 에러: {str(e)}"

# ==========================================
# 개별 API 테스트 함수 (4개 모델)
# ==========================================
def test_nvidia_nemotron(api_key: str, prompt: str, use_custom_prompt: bool = False) -> dict:
    sys_prompt = INVESTMENT_AGENT_PROMPT if use_custom_prompt else "You are a professional financial analyst. Always respond in fluent and clear Korean. Do not include introductory or explanatory phrases."
    return _call_openai_format("NVIDIA NIM (Nemotron)", "https://integrate.api.nvidia.com/v1/chat/completions", api_key, "nvidia/nemotron-3-super-120b-a12b", prompt, system_prompt=sys_prompt, timeout=60)

def test_cloudflare_ai(account_id: str, api_token: str, prompt: str, use_custom_prompt: bool = False) -> dict:
    model = "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b"
    if not account_id or not api_token:
        return {"status": False, "provider": "Cloudflare AI", "model": model, "latency_ms": 0, "response": "Account ID 또는 API Token 누락"}

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    
    if use_custom_prompt:
        enhanced_prompt = f"{INVESTMENT_AGENT_PROMPT}\n\n[중요: 모든 답변은 반드시 100% 한글로만 작성하고 한자나 중국어는 절대 섞어 쓰지 마세요.]\n\n사용자 질문: {prompt}"
    else:
        enhanced_prompt = f"서론이나 부연 설명 없이, 반드시 핵심만 100% 한글로 요약해줘(한자/중국어 절대 사용 금지): {prompt}"
        
    payload = {"messages": [{"role": "user", "content": enhanced_prompt}], "max_tokens": 3000}
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        latency = int((time.time() - start_time) * 1000)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                raw = data["result"]["response"]
                cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                if not cleaned:
                    cleaned = raw.strip()
                
                # HTML 태그 제거
                cleaned = re.sub(r'(?i)&lt;br\s*/?&gt;|<br\s*/?>', ' ', cleaned)
                
                translation_info = "⚪ 번역 생략 (자체 한글 출력)"
                
                has_chinese = bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', cleaned)) 
                if has_chinese or len(re.findall(r'[\uac00-\ud7a3]', cleaned)) < 15:
                    
                    nv_key = get_secret("ai.nvidia_api_key", "")
                    translated_ok = False
                    if nv_key:
                        is_ok, trans_text = translate_to_korean_via_nvidia(cleaned, nv_key)
                        if is_ok:
                            cleaned = trans_text
                            translation_info = "🟢 NVIDIA GPT-OSS 100% 한글 번역 완료"
                            translated_ok = True
                    
                    if not translated_ok:
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

def test_nvidia_gpt_oss(api_key: str, prompt: str, use_custom_prompt: bool = False) -> dict:
    sys_prompt = INVESTMENT_AGENT_PROMPT if use_custom_prompt else "You are a professional financial analyst. Always respond in fluent and clear Korean. Do not include introductory or explanatory phrases."
    return _call_openai_format("NVIDIA NIM (GPT-OSS)", "https://integrate.api.nvidia.com/v1/chat/completions", api_key, "openai/gpt-oss-20b", prompt, system_prompt=sys_prompt, timeout=40)

def test_cerebras(api_key: str, prompt: str, use_custom_prompt: bool = False) -> dict:
    sys_prompt = INVESTMENT_AGENT_PROMPT if use_custom_prompt else "You are a professional financial analyst. Always respond in fluent and clear Korean. Do not include introductory or explanatory phrases."
    return _call_openai_format("Cerebras Cloud", "https://api.cerebras.ai/v1/chat/completions", api_key, "gpt-oss-120b", prompt, system_prompt=sys_prompt, timeout=30)

# ==========================================
# 4단 Failover 무중단 AI 브리핑 생성 파이프라인
# ==========================================
def generate_ai_briefing_with_failover(prompt: str, use_custom_prompt: bool = False) -> dict:
    nv_key = get_secret("ai.nvidia_api_key", "")
    cf_id = get_secret("ai.cloudflare_account_id", "")
    cf_token = get_secret("ai.cloudflare_api_token", "")
    ce_key = get_secret("ai.cerebras_api_key", "")

    if nv_key:
        res = test_nvidia_nemotron(nv_key, prompt, use_custom_prompt)
        if res["status"]:
            res["pipeline_step"] = "1순위 (NVIDIA Nemotron-3) 정상 응답"
            return res

    if cf_id and cf_token:
        res = test_cloudflare_ai(cf_id, cf_token, prompt, use_custom_prompt)
        if res["status"]:
            trans_msg = res.get("translation_info", "상태 없음")
            res["pipeline_step"] = f"2순위 (Cloudflare AI) Failover 성공 [{trans_msg}]"
            return res

    if nv_key:
        res = test_nvidia_gpt_oss(nv_key, prompt, use_custom_prompt)
        if res["status"]:
            res["pipeline_step"] = "3순위 (NVIDIA GPT-OSS-20B) Failover 성공"
            return res

    if ce_key:
        res = test_cerebras(ce_key, prompt, use_custom_prompt)
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
