import requests
import json
import time
from typing import List, Dict, Any, Optional, Tuple

from core import config


def ask_llm(
    prompt: str,
    system_prompt: str = None,
    provider: str = None,
    model: str = None,
    history: list = None,
    image_info: dict = None
) -> str:
    """
    Intelligent LLM Dispatcher with Multi-Key Pool Rotation & Provider Cascade.
    Supports multimodal Vision requests via image_info.
    """
    sys_prompt = system_prompt or "You are KURO, a CLI-based AI system assistant running locally. Be concise, accurate, and execution-focused."

    # Try requested provider first, then cascade to remaining available providers
    if provider:
        providers_to_try = [provider] + [p for p in config.PROVIDER_CHAIN if p.lower() != provider.lower()]
    else:
        providers_to_try = config.PROVIDER_CHAIN

    last_error = ""

    for prov in providers_to_try:
        prov = prov.lower()
        pool = config.KEY_POOLS.get(prov)
        if not pool and prov != "ollama":
            continue

        # Get list of models to try for this provider
        if model and prov == provider:
            models_for_prov = [model] + [m for m in config.MODEL_CHAINS.get(prov, []) if m != model]
        else:
            models_for_prov = config.MODEL_CHAINS.get(prov, [])

        if not models_for_prov:
            models_for_prov = [config.get_active_model(prov)]

        # Try available keys for this provider
        max_key_attempts = max(1, len(pool.keys) if pool else 1)
        for _ in range(max_key_attempts):
            api_key = pool.get_available_key() if pool else "none"
            if not api_key and prov != "ollama":
                break

            for target_model in models_for_prov:
                success, response, status_code = _dispatch_request(
                    provider=prov,
                    model=target_model,
                    api_key=api_key,
                    prompt=prompt,
                    system_prompt=sys_prompt,
                    history=history,
                    image_info=image_info
                )

                if success:
                    return response

                last_error = response

                # Handle Rate Limit / Quota Exhaustion (429)
                if status_code == 429:
                    if pool and api_key:
                        pool.mark_rate_limited(api_key, cooldown_seconds=60.0)
                    # Try next model or next key in pool
                    continue

                # Handle Temporary Server Unavailable (503, 502, 504, 500) -> Try next model immediately
                elif status_code in (500, 502, 503, 504):
                    continue

                # Handle Invalid / Expired Key (401, 403)
                elif status_code in (401, 403):
                    if pool and api_key:
                        pool.mark_invalid(api_key)
                    break

                # Handle Model Not Found (404) -> Continue to next model
                elif status_code == 404:
                    continue

    if not last_error:
        return ("[KURO Setup Notice]\n"
                "No active API keys found or all configured keys are cooling down.\n\n"
                "Use `/key <YOUR_API_KEY>` or `/key <provider> <YOUR_API_KEY>` inside KURO to add a key,\n"
                "or set GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY in your .env file.\n"
                "Free Gemini Key: https://aistudio.google.com/app/apikey\n"
                "Free Groq Key: https://console.groq.com/keys")

    return last_error


def _dispatch_request(
    provider: str,
    model: str,
    api_key: str,
    prompt: str,
    system_prompt: str,
    history: list = None,
    image_info: dict = None
) -> Tuple[bool, str, int]:
    """Dispatches request to appropriate provider API backend."""
    if provider == "gemini":
        return _call_gemini_api(prompt, system_prompt, model, api_key, history, image_info)
    elif provider == "groq":
        return _call_openai_compatible(
            url="https://api.groq.com/openai/v1/chat/completions",
            api_key=api_key,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            history=history
        )
    elif provider == "openrouter":
        return _call_openai_compatible(
            url=f"{config.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
            api_key=api_key,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            history=history
        )
    elif provider == "ollama":
        return _call_openai_compatible(
            url=f"{config.OLLAMA_BASE_URL.rstrip('/')}/chat/completions",
            api_key="ollama",
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            history=history
        )
    elif provider == "openai":
        return _call_openai_compatible(
            url=f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            api_key=api_key,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            history=history
        )
    return False, f"Unknown provider '{provider}'", 400


def _call_gemini_api(
    prompt: str,
    system_prompt: str,
    model: str,
    api_key: str,
    history: list = None,
    image_info: dict = None
) -> Tuple[bool, str, int]:
    """Direct REST call to Gemini v1beta API with Multimodal Vision support."""
    if not api_key:
        return False, "GEMINI_API_KEY is missing", 401

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    contents = []
    if history:
        for item in history:
            role = "user" if item.get("role") in ("user", "human") else "model"
            contents.append({"role": role, "parts": [{"text": item.get("content", "")}]})

    user_parts = []
    if image_info and image_info.get("b64_data"):
        user_parts.append({
            "inline_data": {
                "mime_type": image_info.get("mime_type", "image/png"),
                "data": image_info.get("b64_data")
            }
        })
    user_parts.append({"text": prompt})
    contents.append({"role": "user", "parts": user_parts})

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096
        }
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts:
                    return True, parts[0].get("text", ""), 200
            return True, "[KURO] Received empty content from Gemini.", 200
        else:
            return False, f"[Gemini {res.status_code}] {res.text}", res.status_code
    except Exception as e:
        return False, f"[Connection Error] Gemini API unreachable: {str(e)}", 503


def _call_openai_compatible(
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str,
    history: list = None
) -> Tuple[bool, str, int]:
    """Generic OpenAI-compatible API caller for Groq, OpenRouter, Ollama, OpenAI."""
    headers = {
        "Content-Type": "application/json"
    }
    if api_key and api_key != "ollama":
        headers["Authorization"] = f"Bearer {api_key}"

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for item in history:
            raw_role = item.get("role", "user")
            if raw_role in ("model", "assistant", "ai"):
                norm_role = "assistant"
            elif raw_role in ("system",):
                norm_role = "system"
            else:
                norm_role = "user"
            messages.append({"role": norm_role, "content": item.get("content", "")})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            choices = data.get("choices", [])
            if choices:
                return True, choices[0].get("message", {}).get("content", ""), 200
            return True, "[KURO] Received empty response.", 200
        else:
            return False, f"[API Error {res.status_code}] {res.text}", res.status_code
    except Exception as e:
        return False, f"[Connection Error] API unreachable ({url}): {str(e)}", 503
