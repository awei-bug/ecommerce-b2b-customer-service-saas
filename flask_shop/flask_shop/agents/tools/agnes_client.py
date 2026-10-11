# -*- coding: utf-8 -*-
"""Agnes AI multimodal client.

Agnes exposes OpenAI-compatible text/image endpoints and an asynchronous
video endpoint. API credentials stay server-side; callers receive normalized
responses so the rest of the application does not depend on provider details.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEFAULT_TEXT_MODEL = "agnes-3.0-flash"
DEFAULT_IMAGE_MODEL = "agnes-image-2.5-flash"
DEFAULT_VIDEO_MODEL = "agnes-video-2.5-flash"
TEXT_FALLBACK_MODELS = ("agnes-2.5-flash",)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def get_api_key() -> str:
    return _env("AGNES_API_KEY") or _env("AGNESAI_API_KEY")


def get_base_url() -> str:
    return (_env("AGNES_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")


def get_video_status_url() -> str:
    configured = _env("AGNES_VIDEO_STATUS_URL")
    if configured:
        return configured.rstrip("/")
    root = get_base_url()
    return root[:-3].rstrip("/") + "/agnesapi" if root.endswith("/v1") else root + "/agnesapi"


def get_text_model() -> str:
    return _env("AGNES_TEXT_MODEL", DEFAULT_TEXT_MODEL)


def get_image_model() -> str:
    return _env("AGNES_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)


def get_video_model() -> str:
    return _env("AGNES_VIDEO_MODEL", DEFAULT_VIDEO_MODEL)


def enabled() -> bool:
    return bool(get_api_key()) and _env("AGNES_ENABLED", "1").lower() not in {"0", "false", "no", "off"}


def _request(
    method: str,
    url: str,
    *,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 120,
    query: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
    headers = {"Authorization": f"Bearer {get_api_key()}", "Content-Type": "application/json"}
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
        return {"ok": True, "data": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:1000]
        except Exception:
            detail = str(exc)
        return {"ok": False, "error": detail, "status_code": exc.code}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "status_code": None}


def _error(message: str, *, model: Optional[str] = None, status_code: Optional[int] = None) -> Dict[str, Any]:
    return {"ok": False, "model": model, "error": message, "status_code": status_code}


def chat_completions(
    messages: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 600,
    timeout: int = 90,
) -> Dict[str, Any]:
    """Call Agnes text chat with a small model fallback chain."""
    if not enabled():
        return _error("missing_agnes_api_key", model=model)
    models: List[str] = []
    for candidate in (model or get_text_model(), *TEXT_FALLBACK_MODELS):
        if candidate and candidate not in models:
            models.append(candidate)
    last: Dict[str, Any] = _error("request_failed", model=models[0] if models else None)
    for model_id in models:
        result = _request(
            "POST",
            get_base_url() + "/chat/completions",
            body={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            timeout=timeout,
        )
        if not result.get("ok"):
            last = _error(result.get("error") or "request_failed", model=model_id, status_code=result.get("status_code"))
            logger.warning("Agnes text model %s failed: %s", model_id, str(last.get("error"))[:180])
            continue
        data = result.get("data") or {}
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if content:
            return {"ok": True, "content": content, "model": data.get("model") or model_id, "raw": data}
        last = _error("empty_response", model=model_id)
    return last


def generate_image(
    prompt: str,
    *,
    model: Optional[str] = None,
    size: str = "1K",
    ratio: str = "1:1",
    images: Optional[Iterable[str]] = None,
    response_format: str = "url",
    timeout: int = 240,
) -> Dict[str, Any]:
    """Generate or edit an image and normalize URL/Base64 output."""
    if not enabled():
        return _error("missing_agnes_api_key", model=model or get_image_model())
    model_id = model or get_image_model()
    extra: Dict[str, Any] = {"response_format": response_format}
    refs = [str(item).strip() for item in (images or []) if str(item).strip()]
    if refs:
        extra["image"] = refs
    result = _request(
        "POST",
        get_base_url() + "/images/generations",
        body={"model": model_id, "prompt": str(prompt).strip(), "size": size, "ratio": ratio, "extra_body": extra},
        timeout=timeout,
    )
    if not result.get("ok"):
        return _error(result.get("error") or "image_request_failed", model=model_id, status_code=result.get("status_code"))
    data = result.get("data") or {}
    first = (data.get("data") or [{}])[0] or {}
    return {
        "ok": bool(first.get("url") or first.get("b64_json")),
        "model": data.get("model") or model_id,
        "url": first.get("url"),
        "b64_json": first.get("b64_json"),
        "raw": data,
        "error": None if (first.get("url") or first.get("b64_json")) else "empty_response",
    }


def create_video(
    prompt: str,
    *,
    model: Optional[str] = None,
    mode: str = "text",
    seconds: str = "5",
    aspect_ratio: str = "16:9",
    size: str = "720P",
    first_frame: Optional[str] = None,
    last_frame: Optional[str] = None,
    images: Optional[Iterable[str]] = None,
    audios: Optional[Iterable[str]] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Create an asynchronous Agnes video task."""
    if not enabled():
        return _error("missing_agnes_api_key", model=model or get_video_model())
    model_id = model or get_video_model()
    body: Dict[str, Any] = {
        "model": model_id,
        "prompt": str(prompt).strip(),
        "mode": mode,
        "seconds": str(seconds),
        "size": size,
        "aspect_ratio": aspect_ratio,
    }
    if first_frame:
        body["first_frame"] = first_frame
    if last_frame:
        body["last_frame"] = last_frame
    if images:
        body["images"] = [str(item).strip() for item in images if str(item).strip()]
    if audios:
        body["audios"] = [str(item).strip() for item in audios if str(item).strip()]
    result = _request("POST", get_base_url() + "/videos", body=body, timeout=timeout)
    if not result.get("ok"):
        return _error(result.get("error") or "video_request_failed", model=model_id, status_code=result.get("status_code"))
    data = result.get("data") or {}
    video_id = data.get("video_id") or data.get("id") or data.get("task_id")
    return {"ok": bool(video_id), "model": data.get("model") or model_id, "video_id": video_id, "status": data.get("status") or "queued", "raw": data, "error": None if video_id else "missing_video_id"}


def get_video(video_id: str, *, model: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """Read an asynchronous video task status and generated URL."""
    if not enabled():
        return _error("missing_agnes_api_key", model=model or get_video_model())
    model_id = model or get_video_model()
    result = _request("GET", get_video_status_url(), query={"video_id": str(video_id), "model_name": model_id}, timeout=timeout)
    if not result.get("ok"):
        return _error(result.get("error") or "video_status_failed", model=model_id, status_code=result.get("status_code"))
    data = result.get("data") or {}
    return {"ok": True, "model": data.get("model") or model_id, "video_id": data.get("video_id") or video_id, "status": data.get("status") or "queued", "progress": data.get("progress"), "url": data.get("url") or (data.get("metadata") or {}).get("url"), "raw": data}


def decode_b64_image(value: str) -> bytes:
    """Decode a provider Base64 payload for optional local persistence."""
    raw = str(value or "")
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)
