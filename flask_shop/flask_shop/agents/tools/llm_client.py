# -*- coding: utf-8 -*-
"""OpenRouter LLM 客户端：优先读用户/系统环境变量 OPENROUTER_API_KEY。"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "google/gemma-4-31b-it:free"
DEFAULT_BASE = "https://openrouter.ai/api/v1"
FALLBACK_MODELS = [
    "google/gemma-4-31b-it:free",
    "z-ai/glm-5.2:free",
    "nvidia/nemotron-3.5-lightning:free",
    "openrouter/free",
]


def _provider() -> str:
    """Select the configured gateway; Agnes is preferred when its key exists."""
    configured = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if configured in {"agnes", "openrouter"}:
        return configured
    return "agnes" if os.getenv("AGNES_API_KEY") or os.getenv("AGNESAI_API_KEY") else "openrouter"



def _read_user_env(name: str) -> Optional[str]:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            try:
                val, _ = winreg.QueryValueEx(key, name)
                return str(val) if val else None
            except FileNotFoundError:
                return None
    except Exception:
        return None


def get_openrouter_key() -> str:
    return (
        os.getenv("OPENROUTER_API_KEY")
        or _read_user_env("OPENROUTER_API_KEY")
        or os.getenv("OPENAI_API_KEY")  # 仅当 base 指向 openrouter 时有意义
        or _read_user_env("OPENAI_API_KEY")
        or ""
    ).strip()


def get_openrouter_base() -> str:
    return (
        os.getenv("OPENROUTER_BASE_URL")
        or _read_user_env("OPENROUTER_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or DEFAULT_BASE
    ).strip().rstrip("/")


def get_default_model() -> str:
    return (
        os.getenv("OPENROUTER_MODEL")
        or _read_user_env("OPENROUTER_MODEL")
        or DEFAULT_MODEL
    ).strip()


def llm_enabled() -> bool:
    if (os.getenv("AGENTS_LLM") or "1").strip() in ("0", "false", "False", "no"):
        return False
    if _provider() == "agnes":
        from flask_shop.agents.tools.agnes_client import enabled as agnes_enabled

        return agnes_enabled()
    key = get_openrouter_key()
    if not key:
        return False
    # OpenRouter 官方 key 或显式 base
    base = get_openrouter_base()
    if key.startswith("sk-or-v1-"):
        return True
    if "openrouter.ai" in base:
        return True
    # 其它兼容网关也允许
    return bool(key)



def chat_completions(
    messages: List[Dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 600,
    timeout: int = 60,
) -> Dict[str, Any]:
    """调用 OpenAI 兼容 Chat Completions。失败时按 FALLBACK_MODELS 重试。"""
    if _provider() == "agnes":
        from flask_shop.agents.tools.agnes_client import chat_completions as agnes_chat_completions

        return agnes_chat_completions(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    key = get_openrouter_key()
    if not key:
        return {"ok": False, "content": "", "model": None, "raw_error": "missing_api_key"}

    base = get_openrouter_base() or DEFAULT_BASE
    if key.startswith("sk-or-v1-") and "openrouter.ai" not in base:
        base = DEFAULT_BASE
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")

    models_try = []
    primary = model or get_default_model()
    models_try.append(primary)
    for m in FALLBACK_MODELS:
        if m not in models_try:
            models_try.append(m)

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://127.0.0.1:5173"),
        "X-Title": os.getenv("OPENROUTER_APP_TITLE", "flask-shop-multi-agent"),
    }

    last_err = None
    for model_id in models_try:
        # skip known non-chat free models
        if "content-safety" in model_id or "lyria" in model_id:
            continue
        body = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            content = (
                ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            ).strip()
            # reject junk safety-only answers
            if content.lower().startswith("user safety:") or content.lower() in ("safe", "unsafe"):
                last_err = f"junk_response from {model_id}"
                continue
            if not content:
                last_err = f"empty from {model_id}"
                continue
            return {
                "ok": True,
                "content": content,
                "model": data.get("model") or model_id,
                "raw_error": None,
            }
        except Exception as e:
            last_err = str(e)
            if hasattr(e, "read"):
                try:
                    last_err = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
            logger.warning("openrouter try %s fail: %s", model_id, last_err[:200])
            continue
    return {"ok": False, "content": "", "model": primary, "raw_error": str(last_err)}



def llm_json(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.1,
) -> Dict[str, Any]:
    """要求模型返回 JSON 对象；失败则 ok=False。"""
    messages = [
        {"role": "system", "content": system + "\n只输出 JSON 对象，不要 markdown 代码块。"},
        {"role": "user", "content": user},
    ]
    r = chat_completions(messages, model=model, temperature=temperature, max_tokens=500)
    if not r.get("ok"):
        return r
    text = r.get("content") or ""
    # strip ```json
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:].strip()
    try:
        # find first { }
        i = t.find("{")
        j = t.rfind("}")
        if i >= 0 and j > i:
            obj = json.loads(t[i : j + 1])
            return {"ok": True, "data": obj, "model": r.get("model"), "content": text}
    except Exception as e:
        return {"ok": False, "content": text, "model": r.get("model"), "raw_error": f"json_parse: {e}"}
    return {"ok": False, "content": text, "model": r.get("model"), "raw_error": "no_json"}
