# -*- coding: utf-8 -*-
"""LLM/客服回复落地校验：禁止编造商品名与价格。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


def extract_prices(text: str) -> List[float]:
    vals = []
    for m in re.finditer(r"¥\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*元", text or ""):
        g = m.group(1) or m.group(2)
        try:
            vals.append(float(g))
        except Exception:
            pass
    return vals


_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(小时|天|米|cm|mm|kg|g|ml|L|W|mAh|dB|英寸|寸|个|件|层|倍|%)")


def _card_blob(cards: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for c in cards or []:
        parts.append(str(c.get("title") or ""))
        parts.extend(str(p) for p in (c.get("selling_points") or []))
        parts.append(str(c.get("scenario") or ""))
        parts.append(str(c.get("desc") or ""))
        parts.append(str(c.get("question") or ""))
        parts.append(str(c.get("content") or ""))
        for k, v in (c.get("spec") or {}).items():
            parts.append(f"{k}{v}")
        for f in c.get("faq") or []:
            parts.append(f"{f.get('q')}{f.get('a')}")
    return re.sub(r"\s+", "", " ".join(parts))


def ground_reply(
    reply: str,
    products: List[Dict[str, Any]],
    cards: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    若回复提到的价格/品名/参数明显不在知识范围内，则回退到安全模板。
    products 来自商品库，cards 来自数据中心知识卡，两者共同构成可引用事实集。
    返回 (final_reply, meta)
    """
    reply = (reply or "").strip()
    products = products or []
    cards = cards or []
    meta = {"grounded": True, "action": "keep"}

    if not reply:
        return reply, meta

    # junk
    low = reply.lower()
    if low.startswith("user safety") or low in ("safe", "unsafe"):
        meta = {"grounded": False, "action": "reject_junk"}
        return _fallback(products, cards), meta

    names = [str(p.get("name") or "") for p in products if p.get("name")]
    names += [str(c.get("title") or "") for c in cards if c.get("title")]
    prices = set()
    for p in products:
        try:
            prices.add(round(float(p.get("price") or 0), 2))
        except Exception:
            pass
    for c in cards:
        try:
            if c.get("price") is not None:
                prices.add(round(float(c["price"]), 2))
        except Exception:
            pass

    # 参数类数字必须能在知识卡里找到，否则视为编造
    if cards:
        blob = _card_blob(cards)
        for m in _UNIT_RE.finditer(reply):
            if m.group(1) not in blob:
                meta = {
                    "grounded": False,
                    "action": "unverified_number",
                    "number": m.group(0),
                }
                return _fallback(products, cards), meta

    # If we have catalog products, check invented names:
    # only flag if reply contains a long CJK noun-like token that looks like product
    # and no product name is substring of reply and reply claims 有货/在售
    claims_have = bool(re.search(r"有货|在售|推荐你买|可以买|现货", reply))
    mentioned_known = any(_norm(n) and _norm(n) in _norm(reply) for n in names)

    bad_price = False
    for pr in extract_prices(reply):
        pr2 = round(pr, 2)
        # allow shipping gaps like 31
        if prices and pr2 not in prices and pr2 not in {99, 199, 20} and pr2 >= 5:
            # if any product price matches within 0.01 skip
            if not any(abs(pr2 - x) < 0.011 for x in prices):
                # gap tips allowed if "再买" nearby - skip strict
                if "再买" in reply or "满" in reply:
                    continue
                bad_price = True
                break

    # If catalog empty and reply claims available specific product - fallback
    if not products and claims_have and re.search(r"耳机|键盘|手环", reply):
        meta = {"grounded": False, "action": "no_catalog_claim"}
        return (
            "目前没有检索到符合条件的在售商品。你可以换个关键词，或到首页浏览全部商品。",
            meta,
        )

    # If we have products but reply doesn't mention any and invents headphones when query was headphones
    # handled by catalog already; here if bad_price and claims_have -> fallback
    if products and claims_have and not mentioned_known:
        # 声称有货却未点名任何本店商品名 → 不安全
        meta = {"grounded": False, "action": "unverified_claim", "prices_found": extract_prices(reply)}
        return _fallback(products, cards), meta

    if products and bad_price and claims_have and not mentioned_known:
        meta = {"grounded": False, "action": "price_mismatch", "prices_found": extract_prices(reply)}
        return _fallback(products, cards), meta

    # If products exist, append none - keep reply but ensure at least soft consistency
    if products and claims_have and not mentioned_known:
        # allow general guidance without naming fake SKUs
        if re.search(r"暂无|没有|未找到|本店没有", reply):
            return reply, meta
        # if model lists bullet names not in catalog - detect by lines with ¥
        fake = []
        for line in reply.splitlines():
            if "¥" in line or "元" in line:
                if not any(_norm(n) in _norm(line) for n in names):
                    # could be 满减 tip
                    if re.search(r"满|再买|包邮|减", line):
                        continue
                    fake.append(line.strip())
        if len(fake) >= 2:
            meta = {"grounded": False, "action": "fake_lines", "fake": fake[:3]}
            return _fallback(products, cards), meta

    return reply, meta


def _fallback(products: List[Dict[str, Any]], cards: Optional[List[Dict[str, Any]]] = None) -> str:
    if not products and not cards:
        return "目前没有符合条件的在售商品。请换个关键词，或去首页看看全部商品。"
    store_cards = [card for card in (cards or []) if card.get("kind") == "store"]
    if not products and store_cards:
        card = store_cards[0]
        return f"根据「{card.get('title')}」：{card.get('content')}"
    lines = ["根据本店商品库，为你匹配到："]
    if products:
        for i, p in enumerate(products[:5], 1):
            lines.append(
                f"{i}. {p.get('name')}  ¥{float(p.get('price') or 0):.2f}  库存{int(p.get('stock') or 0)}"
            )
    else:
        for i, c in enumerate((cards or [])[:5], 1):
            if c.get("kind") == "store":
                continue
            lines.append(
                f"{i}. {c.get('title')}  ¥{float(c.get('price') or 0):.2f}  库存{int(c.get('stock') or 0)}"
            )
    for c in (cards or [])[:2]:
        for point in (c.get("selling_points") or [])[:2]:
            lines.append(f"· {c.get('title')}：{point}")
    lines.append("可点击商品卡片查看，或说「怎么付款」。下单后请微信扫码并备注订单号。")
    return "\n".join(lines)
