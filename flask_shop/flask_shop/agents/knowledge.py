# -*- coding: utf-8 -*-
"""客服知识供给层：店铺事实与商品知识统一检索。

店铺政策来自商家维护的 t_store_knowledge；商品知识只使用绑定到本店在售商品的本地副本。
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

# RRF 平滑常数，取 Cormack 等 2009 年提出 RRF 时的原始取值。
RRF_K = 60


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
    from flask_shop.agents.support import refresh_product_slots

    with tenant_context(tenant_id=tenant_id):
        rows = models.ProductKnowledge.query.filter_by(tenant_id=tenant_id, status="published").all()
        products = []
        for offset in range(0, len(rows), 5):
            products.extend(refresh_product_slots(tenant_id, [
                {'id': row.product_id} for row in rows[offset:offset + 5]
            ])[0])
    out = []
    for row, product in zip(rows, products):
        if not product:
            continue
        card = row.knowledge() or {}
        if not isinstance(card, dict) or not card:
            continue
        card.update(product_id=product['id'], title=product['name'], price=product['price'], stock=product['stock'])
        card["external_id"] = row.external_id
        card["tags"] = card.get("tags") if isinstance(card.get("tags"), list) else []
        card["images"] = card.get("images") if isinstance(card.get("images"), list) else []
        selling_points = card.get("selling_points") if isinstance(card.get("selling_points"), list) else []
        faq = card.get("faq") if isinstance(card.get("faq"), list) else []
        spec = card.get("spec") if isinstance(card.get("spec"), dict) else {}
        card["selling_points"] = [value for value in selling_points if _stable_product_text(value)]
        card["faq"] = [item for item in faq if isinstance(item, dict)
                       and _stable_product_text(item.get('q')) and _stable_product_text(item.get('a'))]
        card["spec"] = {key: value for key, value in spec.items()
                        if _stable_product_text(key) and _stable_product_text(value)}
        for key in ('desc_zh', 'scenario', 'category', 'brand'):
            if not _stable_product_text(card.get(key)):
                card[key] = ''
        out.append(card)
    return out


def _stable_product_text(value: Any) -> bool:
    return not re.search(r'库存|价格|售价|优惠|折扣|包邮|现货|缺货|售罄|运费|[¥￥]|\d\s*(?:元|块|折)', str(value or ''))


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
        rows = models.StoreKnowledge.query.filter_by(tenant_id=int(tenant_id), status="published").all()
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


def _rrf_merge(
    ranked_lists: List[List[Dict[str, Any]]],
    limit: int,
    k: int = RRF_K,
) -> List[Dict[str, Any]]:
    """倒数秩融合（Reciprocal Rank Fusion）合并多路召回结果。

    为什么用 RRF 而不是直接比分数：店铺知识路的分是手工字段权重累加
    （无上界），商品路回源时拿到的分来自数据中心，两者量纲不可比，
    线性加权需要精细调参。RRF 只看排名位置，score = Σ 1/(k + rank)，
    两路排名靠前的都能进结果，不需要归一化。

    此前这里是 ``(store_cards + product_cards)[:limit]``：两路各自已按
    limit 截断，拼接后再取 limit 等于"先到先得"，只要店铺知识路占满
    名额，商品知识卡会被整条丢弃（catalog_agent 的商品兜底检索因此
    长期拿不到数据）。RRF 修正了这个退化。
    """
    fused: Dict[str, float] = {}
    cards: Dict[str, Dict[str, Any]] = {}
    for ranked in ranked_lists:
        for rank, card in enumerate(ranked or [], start=1):
            key = str(card.get("citation_id") or "")
            if not key:
                key = f"anon-{id(card)}"
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
            cards.setdefault(key, card)
    # 同分时按 citation_id 稳定排序，避免结果随机漂移
    ordered = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))
    return [cards[key] for key, _ in ordered[:limit]]


def load_knowledge(
    tenant_id: Optional[int],
    query: str,
    limit: int = 3,
    tenant_slug: str = "",
) -> List[Dict[str, Any]]:
    """返回与问题最相关的商品知识卡。

    仅使用本店已绑定商品的本地副本；未建立跨系统租户隔离前不直接回源。
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
        except Exception:
            current_app.logger.exception("store knowledge load failed")
        try:
            local = _local_cards(int(tenant_id))
            scored = []
            for card in local:
                sc = _score(card, tokens, query)
                if sc > 0:
                    scored.append((sc, card))
            scored.sort(key=lambda x: -x[0])
            product_cards = [_compact(c) for _, c in scored[:limit]]
        except Exception:
            current_app.logger.exception("product knowledge load failed")

    return _rrf_merge([store_cards, product_cards], limit)


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
