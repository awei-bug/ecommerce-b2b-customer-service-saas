# -*- coding: utf-8 -*-
"""商品文案生成 Agent。"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from flask_shop import db, models
from flask_shop.agents.tools.llm_client import chat_completions, llm_enabled


PRODUCT_SYSTEM = """你是电商商品内容编辑。根据商品草稿输出严格 JSON：
{
  "title": "中文优化标题，不超过40字",
  "sell_points": "3条真实、简洁的卖点，用分号分隔",
  "description": "中文商品简介，不超过200字"
}
只能基于输入信息组织文案，缺少的材质、规格、功效或承诺不要编造。不要 markdown。"""


def _log_task(
    tenant_id: Optional[int],
    product_draft: Dict[str, Any],
    output: Dict[str, Any],
    model: Optional[str],
    latency_ms: int,
) -> None:
    try:
        db.session.add(models.AgentTaskLog(
            tenant_id=tenant_id,
            agent_name="product_content",
            task_type="product_copy",
            ref_type="product",
            ref_id=str(product_draft.get("id") or product_draft.get("product_id") or ""),
            input_text=json.dumps(product_draft, ensure_ascii=False)[:4000],
            output_json=json.dumps(output, ensure_ascii=False),
            status="ok",
            model=model,
            latency_ms=latency_ms,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def run_product_content_agent(
    tenant_id: int,
    product_draft: Dict[str, Any],
    *,
    use_llm: bool = True,
) -> Dict[str, Any]:
    started = time.time()
    name = str(product_draft.get("name") or "商品").strip()
    intro = str(product_draft.get("introduce") or "").strip()
    fallback = {
        "title": name[:40] or "商品",
        "sell_points": intro[:200] or "品质精选; 信息透明; 售后有保障",
        "description": intro[:200] or f"{name}，商品信息以详情页和实际规格为准。",
    }

    data = fallback
    model_used = None
    if use_llm and llm_enabled():
        result = chat_completions(
            [
                {"role": "system", "content": PRODUCT_SYSTEM},
                {"role": "user", "content": json.dumps(product_draft, ensure_ascii=False)},
            ],
            temperature=0.4,
            max_tokens=500,
        )
        model_used = result.get("model")
        if result.get("ok") and result.get("content"):
            try:
                text = result["content"]
                start, end = text.find("{"), text.rfind("}")
                if start >= 0 and end > start:
                    parsed = json.loads(text[start:end + 1])
                    data = {**fallback, **{k: parsed[k] for k in fallback if parsed.get(k)}}
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

    latency_ms = int((time.time() - started) * 1000)
    _log_task(tenant_id, product_draft, data, model_used, latency_ms)
    return {
        "status": 200,
        "msg": "ok",
        "data": data,
        "model": model_used,
        "latency_ms": latency_ms,
    }
