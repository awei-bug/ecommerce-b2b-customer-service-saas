# -*- coding: utf-8 -*-
"""客服知识供给层：店铺事实与商品知识统一检索。

店铺政策来自商家维护的 t_store_knowledge；商品事实优先使用本地
t_product_knowledge 副本，未命中时再回源数据中心。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from flask import current_app

from flask_shop import models
from flask_shop.utils.tenant_query import tenant_context

TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]{1,4}")
STOP_TOKENS = {"请问", "一下", "你们", "我们", "这个", "那个", "可以", "是否", "怎么", "什么", "多少"}
POLICY_QUERY_PATTERNS = [
    r"付款|支付|收款|转账|扫码|发票|开票",
    r"发货|配送|快递|运费|包邮|到货|物流时效",
    r"退款|退货|换货|售后|质保|保修|维修|无理由",
    r"营业时间|客服时间|门店|自提|会员|积分|优惠券|政策|规则",
]


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [
        t for t in TOKEN_RE.findall(str(text).lower())
        if (len(t) > 1 or t.isdigit()) and t not in STOP_TOKENS
    ]


def _score(card: Dict[str, Any], tokens: List[str], raw: str) -> float:
    if not tokens:
        return 0.0
    title = str(card.get("title") or "")
    low = title.lower()
    score = 0.0
    if raw and raw.lower() in low:
        score += 20
    for tok in tokens:
        if tok in low:
            score += 6
        for tag in card.get("tags") or []:
            if tok in str(tag).lower():
                score += 4
                break
        for field in ("category", "brand", "scenario"):
            if card.get(field) and tok in str(card[field]).lower():
                score += 3
        for point in card.get("selling_points") or []:
            if tok in str(point).lower():
                score += 1.5
                break
        if card.get("desc_zh") and tok in str(card["desc_zh"]).lower():
            score += 0.6
        for faq in card.get("faq") or []:
            if tok in str(faq.get("q") or "").lower():
                score += 3
                break
    return score


def _compact(card: Dict[str, Any], max_points: int = 5, max_faq: int = 3) -> Dict[str, Any]:
    desc = str(card.get("desc_zh") or "")
    if len(desc) > 220:
        desc = desc[:220].rstrip() + "..."
    numbers = set()
    price = card.get("price")
    if price is not None:
        try:
            numbers.add(round(float(price), 2))
        except (TypeError, ValueError):
            pass
    for val in (card.get("spec") or {}).values():
        m = re.search(r"(\d+(?:\.\d+)?)", str(val))
        if m:
            numbers.add(round(float(m.group(1)), 2))
    identifier = card.get("product_id") or card.get("external_id")
    return {
        "kind": "product",
        "citation_id": f"PRODUCT-{identifier}" if identifier else None,
        "source_label": "商品知识库",
        "external_id": card.get("external_id"),
        "product_id": card.get("product_id"),
        "title": card.get("title"),
        "price": price,
        "currency": card.get("currency") or "CNY",
        "stock": card.get("stock"),
        "category": card.get("category"),
        "brand": card.get("brand"),
        "scenario": card.get("scenario"),
        "selling_points": [str(p) for p in (card.get("selling_points") or []) if str(p).strip()][:max_points],
        "spec": dict(card.get("spec") or {}),
        "faq": [{"q": f.get("q"), "a": f.get("a")} for f in (card.get("faq") or [])][:max_faq],
        "desc": desc,
        "images": (card.get("images") or [])[:3],
        "allowed_numbers": sorted(numbers),
    }


def _local_cards(tenant_id: int) -> List[Dict[str, Any]]:
    with tenant_context(tenant_id=tenant_id):
        rows = models.ProductKnowledge.query.filter_by(status="published").all()
    out = []
    for row in rows:
        card = row.knowledge() or {}
        if not card:
            continue
        card["product_id"] = row.product_id
        card["external_id"] = row.external_id
        out.append(card)
    return out


def _store_score(row, tokens: List[str], raw: str) -> float:
    raw_low = (raw or "").lower()
    title = (row.title or "").lower()
    question = (row.question or "").lower()
    content = (row.content or "").lower()
    keywords = [str(item).lower() for item in row.keywords()]
    score = 0.0
    if raw_low and raw_low in title:
        score += 24
    if raw_low and raw_low in question:
        score += 18
    for keyword in keywords:
        if keyword and keyword in raw_low:
            score += 12
    for token in tokens:
        if token in title:
            score += 8
        if token in question:
            score += 6
        if any(token in keyword or keyword in token for keyword in keywords):
            score += 5
        if token in content:
            score += 1.5
    return score


def load_store_knowledge(tenant_id: Optional[int], query: str, limit: int = 3) -> List[Dict[str, Any]]:
    if not tenant_id or not (query or "").strip():
        return []
    tokens = tokenize(query)
    with tenant_context(tenant_id=int(tenant_id)):
        rows = models.StoreKnowledge.query.filter_by(status="published").all()
    scored = [(_store_score(row, tokens, query), row) for row in rows]
    scored = [(score, row) for score, row in scored if score >= 4]
    scored.sort(key=lambda item: (-item[0], -(item[1].priority or 0), item[1].id))
    return [
        {
            "kind": "store",
            "id": row.id,
            "citation_id": f"KB-{row.id}",
            "title": row.title,
            "category": row.category,
            "question": row.question,
            "content": row.content,
            "keywords": row.keywords(),
            "source_label": row.source_label or "商家知识库",
            "score": round(score, 2),
        }
        for score, row in scored[:limit]
    ]


def requires_grounded_answer(text: str, intent: Optional[str] = None) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if intent in {"pay_help", "refund", "track"}:
        return True
    return any(re.search(pattern, value, re.I) for pattern in POLICY_QUERY_PATTERNS)


def load_knowledge(
    tenant_id: Optional[int],
    query: str,
    limit: int = 3,
    tenant_slug: str = "",
) -> List[Dict[str, Any]]:
    """返回与问题最相关的商品知识卡。

    本地副本无结果时回源数据中心，保证内容平台新产出即刻可被客服引用。
    """
    query = (query or "").strip()
    if not query:
        return []

    tokens = tokenize(query)
    store_cards: List[Dict[str, Any]] = []
    product_cards: List[Dict[str, Any]] = []

    if tenant_id:
        try:
            store_cards = load_store_knowledge(int(tenant_id), query, limit=limit)
            local = _local_cards(int(tenant_id))
            scored = []
            for card in local:
                sc = _score(card, tokens, query)
                if sc > 0:
                    scored.append((sc, card))
            scored.sort(key=lambda x: -x[0])
            product_cards = [_compact(c) for _, c in scored[:limit]]
        except Exception:
            current_app.logger.exception("local knowledge load failed")
            store_cards = []
            product_cards = []

    if not product_cards:
        try:
            from flask_shop.utils import hub_client

            if hub_client.hub_enabled():
                product_cards = [_compact(card) for card in hub_client.search(
                    query, limit=limit, published_only=True,
                )]
        except Exception:
            current_app.logger.exception("hub knowledge search failed")
            product_cards = []

    return (store_cards + product_cards)[:limit]


def citations(cards: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for card in cards or []:
        citation_id = str(card.get("citation_id") or "").strip()
        if not citation_id or citation_id in seen:
            continue
        seen.add(citation_id)
        out.append({
            "id": citation_id,
            "title": str(card.get("title") or "知识条目")[:128],
            "category": str(card.get("category") or "product")[:24],
            "source": str(card.get("source_label") or "店铺知识")[:64],
        })
        if len(out) >= limit:
            break
    return out


def knowledge_brief(cards: List[Dict[str, Any]]) -> str:
    """把知识卡压成给模型看的事实块，明确「只能引用这些」。"""
    if not cards:
        return ""
    lines = []
    for card in cards:
        if card.get("kind") == "store":
            lines.append(f"【{card.get('citation_id')}｜{card.get('title')}】")
            if card.get("question"):
                lines.append(f"- 适用问题：{card['question']}")
            lines.append(f"- 已确认规则：{card.get('content')}")
            continue
        lines.append(f"【{card.get('citation_id')}｜{card.get('title')}】售价 ¥{card.get('price')} 库存 {card.get('stock')}")
        for point in card.get("selling_points") or []:
            lines.append(f"- 卖点：{point}")
        if card.get("scenario"):
            lines.append(f"- 适用场景：{card['scenario']}")
        for k, v in (card.get("spec") or {}).items():
            lines.append(f"- {k}：{v}")
        for faq in card.get("faq") or []:
            lines.append(f"- 问：{faq.get('q')} 答：{faq.get('a')}")
        if card.get("desc"):
            lines.append(f"- 描述：{card['desc']}")
    return "\n".join(lines)
