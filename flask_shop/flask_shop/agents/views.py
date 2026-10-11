# -*- coding: utf-8 -*-
"""多智能体 HTTP 入口。"""
from __future__ import annotations

from flask import Blueprint, g, request

from flask_shop.agents.orchestrator import orchestrator
import json
import time
from flask_shop.agents.memory import get_session, save_session, resolve_followup
import uuid
from flask_shop.utils.token import login_required, verify_token
from flask_shop.utils.rbac import permission_required
from flask_shop.utils.rate_limit import rate_limit

agents_bp = Blueprint("agents", __name__, url_prefix="/api/agents")


def _extract_token():
    tok = (
        request.headers.get("token")
        or request.headers.get("X-Customer-Token")
        or request.headers.get("Authorization", "")
    )
    if isinstance(tok, str) and tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    return tok


def _resolve_tenant_slug():
    body = request.get_json(silent=True) or {}
    slug = (
        request.headers.get("X-Tenant-Slug")
        or body.get("tenant_slug")
        or request.args.get("tenant_slug")
        or "demo"
    )
    return (slug or "demo").strip()


@agents_bp.route("/health/", methods=["GET"])
def agents_health():
    from flask_shop.agents.tools import agnes_client

    return {
        "status": 200,
        "msg": "ok",
        "data": {
            "system": "multi-agent-commerce",
            "agents": ["intent", "catalog", "promo", "order", "cs", "ops", "risk"],
            "mode": "collaborative_specialists",
            "providers": {
                "agnes": {
                    "configured": agnes_client.enabled(),
                    "text_model": agnes_client.get_text_model(),
                    "image_model": agnes_client.get_image_model(),
                    "video_model": agnes_client.get_video_model(),
                },
            },
        },
    }


@agents_bp.route("/chat/", methods=["POST"])
@rate_limit(max_calls=40, per_seconds=60, prefix="agents_chat")
def agents_chat():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or body.get("message") or "").strip()
    if not text:
        return {"status": 400, "msg": "请输入内容"}

    customer_id = getattr(g, "customer_id", None)
    if not customer_id:
        payload = verify_token(_extract_token())
        if payload and payload.get("typ") == "customer":
            customer_id = payload.get("customer_id") or payload.get("id")

    slug = _resolve_tenant_slug()
    tenant_id = getattr(g, "tenant_id", None)
    if tenant_id is None:
        try:
            from flask_shop import models
            from flask_shop.utils.tenant_query import tenant_context

            with tenant_context(disabled=True):
                t = models.Tenant.query.filter_by(slug=slug).first()
                tenant_id = t.id if t else None
        except Exception:
            tenant_id = None

    t0 = time.time()
    session_id = (body.get("session_id") or "").strip() or uuid.uuid4().hex

    # 人工已接管或正在排队时，顾客消息只进入人工时间线，避免 AI 抢答。
    if tenant_id is not None:
        try:
            from flask_shop.agents import support

            support_row = support.get_conversation(tenant_id, session_id)
            if support_row and support_row.status in ("waiting", "active"):
                support.persist_customer_waiting_message(support_row, text, int(customer_id) if customer_id else None)
                state_text = "人工客服正在处理，请稍候。" if support_row.status == "active" else "消息已进入人工客服队列，请稍候。"
                return {
                    "status": 200,
                    "msg": "ok",
                    "data": {
                        "session_id": session_id,
                        "reply": state_text,
                        "intent": {"intent": "cs", "label": "人工客服"},
                        "products": [],
                        "actions": [],
                        "need_human": True,
                        "blocked": False,
                        "agents_ran": ["support_queue"],
                        "suggested_replies": [],
                        "support": support_row.to_dict(include_people=False),
                    },
                }
        except Exception:
            pass

    sess = get_session(session_id)
    persistent_memory = {}
    if tenant_id is not None:
        try:
            from flask_shop.agents import support
            persistent_memory = support.get_memory_context(
                tenant_id, session_id, int(customer_id) if customer_id else None
            )
            if not sess.get("last_products") and persistent_memory.get("last_products"):
                sess["last_products"] = persistent_memory.get("last_products")
        except Exception:
            persistent_memory = {}
    follow = resolve_followup(text, sess)
    if follow.get("is_followup") and follow.get("product"):
        p = follow["product"]
        # rewrite user text to concrete product ask for order guidance
        text = f"我想购买商品「{p.get('name')}」(id={p.get('id')}, 价格{p.get('price')})，请告诉我怎么下单付款"

    result = orchestrator.run_chat(
        text,
        tenant_slug=slug,
        tenant_id=tenant_id,
        customer_id=int(customer_id) if customer_id else None,
        channel="mall_chat",
        memory=persistent_memory,
    )
    data = (result or {}).get("data") or {}
    save_session(
        session_id,
        user_text=body.get("text") or text,
        reply=data.get("reply") or "",
        products=data.get("products") or sess.get("last_products") or [],
        intent=data.get("intent") or {},
    )
    if isinstance(result, dict) and isinstance(result.get("data"), dict):
        result["data"]["session_id"] = session_id
        if follow.get("is_followup"):
            result["data"]["followup"] = follow
        if tenant_id is not None:
            try:
                from flask_shop.agents import support

                support_row = support.persist_agent_turn(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    customer_id=int(customer_id) if customer_id else None,
                    user_text=body.get("text") or text,
                    result=result,
                )
                result["data"]["support"] = support_row.to_dict(include_people=False)
            except Exception:
                try:
                    from flask_shop import db
                    db.session.rollback()
                except Exception:
                    pass
    _persist_trace(
        result,
        text=body.get("text") or text,
        session_id=session_id,
        channel="mall_chat",
        tenant_id=tenant_id,
        customer_id=int(customer_id) if customer_id else None,
        t0=t0,
    )
    return result


@agents_bp.route("/ops/", methods=["POST"])
@login_required
@rate_limit(max_calls=30, per_seconds=60, prefix="agents_ops")
def agents_ops():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or body.get("message") or "今日经营情况").strip()
    slug = _resolve_tenant_slug()
    listing_hit = any(k in text for k in ("上架", "发布商品", "新品上架"))
    if (not listing_hit) and "运营" not in text and "订单" not in text and "库存" not in text:
        text = f"运营分析：{text}"
    t0 = time.time()
    result = orchestrator.run_chat(
        text,
        tenant_slug=slug,
        tenant_id=getattr(g, "tenant_id", None),
        staff_id=getattr(g, "staff_id", None),
        channel="admin_ops",
    )
    _persist_trace(
        result,
        text=text,
        session_id=(result.get("data") or {}).get("session_id"),
        channel="admin_ops",
        tenant_id=getattr(g, "tenant_id", None),
        staff_id=getattr(g, "staff_id", None),
        t0=t0,
    )
    return result


def _persist_trace(result, *, text, session_id, channel, tenant_id, customer_id=None, staff_id=None, t0=None):
    try:
        from flask_shop import db, models
        data = (result or {}).get("data") or {}
        intent = data.get("intent") or {}
        llm = (intent.get("llm") or {})
        model = llm.get("model") or ((data.get("cs") or {}).get("llm") or {}).get("model")
        # cs llm may only be in ctx - try trace
        agents_ran = data.get("agents_ran") or []
        row = models.AgentTrace(
            tenant_id=tenant_id,
            session_id=session_id or data.get("session_id"),
            channel=channel,
            user_text=(text or "")[:512],
            reply=(data.get("reply") or "")[:4000],
            intent=(intent.get("intent") or "")[:64],
            agents_ran=",".join([str(a) for a in agents_ran])[:255],
            model=(model or "")[:128] or None,
            blocked=1 if data.get("blocked") else 0,
            need_human=1 if data.get("need_human") else 0,
            customer_id=customer_id,
            staff_id=staff_id,
            latency_ms=int((time.time() - t0) * 1000) if t0 else 0,
            extra_json=json.dumps({
                "products": [
                    {"id": p.get("id"), "name": p.get("name"), "price": p.get("price")}
                    for p in (data.get("products") or [])[:5]
                ],
                "trace_tail": (data.get("trace") or [])[-8:],
                "citations": (data.get("citations") or [])[:3],
            }, ensure_ascii=False)[:65000],
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        try:
            from flask_shop import db
            db.session.rollback()
        except Exception:
            pass


# ---------- 商品内容 ----------
@agents_bp.route("/product-content/", methods=["POST"])
@login_required
def agent_product_content():
    """
    商品内容 Agent。
    body:
      商品草稿字段 name/price/introduce/weight/...
      apply: true 时写回商品并可选上架
      product_id: 已有商品 id（apply 时必填，除非 create_new）
      publish: true 时 state=2 上架（默认 true）
      create_new: true 时新建商品再上架
    """
    from flask_shop import db, models
    from flask_shop.agents.content_agent import run_product_content_agent
    from flask_shop.utils.quota import check_product_quota

    body = request.get_json(silent=True) or {}
    tenant_id = getattr(g, "tenant_id", None)
    result = run_product_content_agent(tenant_id, body)
    if result.get("status") != 200:
        return result

    data = result.get("data") or {}
    apply = bool(body.get("apply") or body.get("auto_apply"))
    publish = body.get("publish")
    if publish is None:
        publish = True
    publish = bool(publish)
    create_new = bool(body.get("create_new"))
    product_id = body.get("product_id") or body.get("id")

    if not apply:
        result["data"] = {
            **data,
            "applied": False,
            "published": False,
            "hint": "仅生成未写库。传 apply=true 可回填并上架",
        }
        return result

    try:
        product = None
        if create_new or not product_id:
            ok_q, err_q = check_product_quota(tenant_id)
            if not ok_q:
                return {"status": 400, "msg": err_q, "data": data}
            name = (data.get("title") or body.get("name") or "未命名商品").strip()[:128]
            product = models.Product(
                tenant_id=tenant_id,
                name=name,
                price=float(body.get("price") or 0),
                number=int(body.get("number") or body.get("stock") or 10),
                introduce=(data.get("sell_points") or body.get("introduce") or "")[:2000],
                weight=float(body.get("weight") or 0.3),
                state=2 if publish else 0,
            )
            db.session.add(product)
            db.session.flush()
        else:
            product = models.Product.query.filter_by(id=int(product_id), tenant_id=tenant_id).first()
            if not product:
                return {"status": 404, "msg": "商品不存在", "data": data}
            if data.get("title"):
                product.name = str(data.get("title")).strip()[:128]
            if data.get("sell_points"):
                product.introduce = str(data.get("sell_points"))[:2000]
                if hasattr(product, "sell_points"):
                    product.sell_points = str(data.get("sell_points"))[:2000]
            if publish:
                product.state = 2

        if hasattr(product, "sell_points") and data.get("sell_points"):
            product.sell_points = str(data.get("sell_points"))[:2000]

        if publish:
            product.state = 2

        db.session.commit()
        result["data"] = {
            **data,
            "applied": True,
            "published": bool(product.state == 2),
            "product_id": product.id,
            "product": product.to_dict(),
        }
        result["msg"] = "已生成并上架" if product.state == 2 else "已生成并保存（未上架）"
        return result
    except Exception as e:
        db.session.rollback()
        return {"status": 500, "msg": f"写库失败: {e}", "data": data}


# ---------- Agnes 多模态素材 ----------
@agents_bp.route("/media/image/", methods=["POST"])
@login_required
@rate_limit(max_calls=10, per_seconds=60, prefix="agnes_image")
def agent_media_image():
    """调用 Agnes 免费图像模型生成商品图/营销图。"""
    from flask_shop.agents.tools import agnes_client

    body = request.get_json(silent=True) or {}
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return {"status": 400, "msg": "prompt 不能为空"}
    try:
        size = str(body.get("size") or "1K").upper()
        ratio = str(body.get("ratio") or "1:1")
        if size not in {"1K", "2K", "3K", "4K"}:
            return {"status": 400, "msg": "size 仅支持 1K / 2K / 3K / 4K"}
        if ratio not in {"1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"}:
            return {"status": 400, "msg": "ratio 不受支持"}
        result = agnes_client.generate_image(
            prompt,
            model=body.get("model"),
            size=size,
            ratio=ratio,
            images=body.get("images") or body.get("reference_images") or [],
            response_format="b64_json" if body.get("response_format") == "b64_json" else "url",
            timeout=min(max(int(body.get("timeout") or 240), 30), 360),
        )
    except (TypeError, ValueError) as exc:
        return {"status": 400, "msg": f"图片参数不合法: {exc}"}
    if not result.get("ok"):
        status = 503 if result.get("error") == "missing_agnes_api_key" else 502
        return {"status": status, "msg": result.get("error") or "Agnes 图片生成失败", "data": {"model": result.get("model")}}
    return {"status": 200, "msg": "图片生成完成", "data": {k: result.get(k) for k in ("model", "url", "b64_json", "raw") if result.get(k) is not None}}


@agents_bp.route("/media/video/", methods=["POST"])
@login_required
@rate_limit(max_calls=4, per_seconds=60, prefix="agnes_video")
def agent_media_video_create():
    """创建 Agnes 异步视频任务；前端随后使用 video_id 轮询。"""
    from flask_shop.agents.tools import agnes_client

    body = request.get_json(silent=True) or {}
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return {"status": 400, "msg": "prompt 不能为空"}
    mode = str(body.get("mode") or "text")
    if mode not in {"text", "keyframe", "reference"}:
        return {"status": 400, "msg": "mode 仅支持 text / keyframe / reference"}
    try:
        seconds = str(body.get("seconds") or "5")
        if seconds not in {str(x) for x in range(4, 13)}:
            return {"status": 400, "msg": "seconds 必须是 4 到 12 秒"}
        result = agnes_client.create_video(
            prompt,
            model=body.get("model"),
            mode=mode,
            seconds=seconds,
            aspect_ratio=str(body.get("aspect_ratio") or "16:9"),
            size="720P",
            first_frame=body.get("first_frame"),
            last_frame=body.get("last_frame"),
            images=body.get("images") or [],
            audios=body.get("audios") or [],
        )
    except (TypeError, ValueError) as exc:
        return {"status": 400, "msg": f"视频参数不合法: {exc}"}
    if not result.get("ok"):
        status = 503 if result.get("error") == "missing_agnes_api_key" else 502
        return {"status": status, "msg": result.get("error") or "Agnes 视频任务创建失败", "data": {"model": result.get("model")}}
    return {"status": 202, "msg": "视频任务已创建", "data": {"model": result.get("model"), "video_id": result.get("video_id"), "status": result.get("status"), "raw": result.get("raw")}}


@agents_bp.route("/media/video/<video_id>/", methods=["GET"])
@login_required
def agent_media_video_status(video_id):
    from flask_shop.agents.tools import agnes_client

    if not video_id or len(video_id) > 200:
        return {"status": 400, "msg": "video_id 不合法"}
    result = agnes_client.get_video(video_id)
    if not result.get("ok"):
        status = 503 if result.get("error") == "missing_agnes_api_key" else 502
        return {"status": status, "msg": result.get("error") or "Agnes 视频状态查询失败"}
    return {"status": 200, "msg": "ok", "data": {k: result.get(k) for k in ("model", "video_id", "status", "progress", "url", "raw") if result.get(k) is not None}}


# ---------- 客服中心 ----------
def _support_customer_context(session_id):
    """Resolve a public mall session while preventing cross-tenant/customer reads."""
    from flask_shop import models
    from flask_shop.agents import support
    from flask_shop.utils.tenant_query import tenant_context

    slug = _resolve_tenant_slug()
    with tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug=slug, status=1).first()
    if not tenant:
        return None, ({"status": 404, "msg": "店铺不存在"}, 404)
    g.tenant = tenant
    g.tenant_id = tenant.id
    row = support.get_conversation(tenant.id, session_id)
    if not row:
        return None, ({"status": 404, "msg": "会话不存在"}, 404)
    payload = verify_token(_extract_token())
    customer_id = None
    if payload and payload.get("typ") == "customer" and int(payload.get("tenant_id") or 0) == int(tenant.id):
        customer_id = int(payload.get("customer_id") or payload.get("id") or 0) or None
    if row.customer_id and row.customer_id != customer_id:
        return None, ({"status": 403, "msg": "无权访问该会话"}, 403)
    return row, None


@agents_bp.route("/support/session/<session_id>/messages/", methods=["GET"])
def support_customer_messages(session_id):
    from flask_shop import models

    row, error = _support_customer_context(session_id)
    if error:
        return error
    after_id = max(int(request.args.get("after_id") or 0), 0)
    messages = row.messages.filter(models.SupportMessage.id > after_id).order_by(models.SupportMessage.id.asc()).limit(100).all()
    return {
        "status": 200,
        "msg": "ok",
        "data": {
            "conversation": row.to_dict(include_people=False),
            "messages": [item.to_dict() for item in messages],
        },
    }


@agents_bp.route("/support/session/<session_id>/satisfaction/", methods=["POST"])
def support_customer_satisfaction(session_id):
    from flask_shop import db

    row, error = _support_customer_context(session_id)
    if error:
        return error
    body = request.get_json(silent=True) or {}
    try:
        score = int(body.get("score"))
    except (TypeError, ValueError):
        return {"status": 400, "msg": "score 必须是 1 到 5"}
    if score not in range(1, 6):
        return {"status": 400, "msg": "score 必须是 1 到 5"}
    if row.status != "resolved":
        return {"status": 400, "msg": "人工服务结束后才能评价"}
    row.satisfaction = score
    row.satisfaction_note = str(body.get("note") or "").strip()[:500] or None
    db.session.commit()
    return {"status": 200, "msg": "感谢你的评价", "data": row.to_dict(include_people=False)}


def _support_row(conversation_id):
    from flask_shop import models
    return models.SupportConversation.query.filter_by(id=conversation_id, tenant_id=g.tenant_id).first()


KNOWLEDGE_CATEGORIES = {"faq", "payment", "shipping", "refund", "product", "other"}
KNOWLEDGE_STATUSES = {"published", "draft", "disabled"}


def _knowledge_keywords(value):
    if isinstance(value, list):
        items = value
    else:
        import re
        items = re.split(r"[,，;；|\n]+", str(value or ""))
    cleaned = []
    for item in items:
        keyword = str(item or "").strip()
        if keyword and keyword not in cleaned:
            cleaned.append(keyword[:32])
    return cleaned[:20]


def _knowledge_payload(body, *, source_type="manual"):
    title = str(body.get("title") or "").strip()
    question = str(body.get("question") or "").strip()
    content = str(body.get("content") or "").strip()
    category = str(body.get("category") or "faq").strip().lower()
    status = str(body.get("status") or "draft").strip().lower()
    if not title:
        raise ValueError("标题不能为空")
    if len(title) > 128:
        raise ValueError("标题不能超过 128 个字符")
    if len(question) > 500:
        raise ValueError("适用问题不能超过 500 个字符")
    if not content:
        raise ValueError("知识内容不能为空")
    if len(content) > 8000:
        raise ValueError("知识内容不能超过 8000 个字符")
    if category not in KNOWLEDGE_CATEGORIES:
        raise ValueError("知识分类不合法")
    if status not in KNOWLEDGE_STATUSES:
        raise ValueError("知识状态不合法")
    try:
        priority = int(body.get("priority") or 0)
    except (TypeError, ValueError):
        raise ValueError("优先级必须是 0 到 100 的整数")
    if not 0 <= priority <= 100:
        raise ValueError("优先级必须是 0 到 100 的整数")
    return {
        "title": title,
        "question": question or None,
        "content": content,
        "category": category,
        "status": status,
        "priority": priority,
        "keywords": _knowledge_keywords(body.get("keywords")),
        "source_type": source_type,
        "source_label": "商家知识库" if source_type != "demo" else "演示知识库",
    }


def _apply_knowledge_payload(row, payload):
    for key in ("title", "question", "content", "category", "status", "priority", "source_type", "source_label"):
        setattr(row, key, payload[key])
    row.set_keywords(payload["keywords"])


@agents_bp.route("/knowledge/", methods=["GET"])
@login_required
@permission_required("service:read")
def store_knowledge_list():
    from sqlalchemy import or_
    from flask_shop import models

    rows = models.StoreKnowledge.query.filter_by(tenant_id=g.tenant_id)
    status = str(request.args.get("status") or "").strip()
    category = str(request.args.get("category") or "").strip()
    query = str(request.args.get("q") or "").strip()
    if status in KNOWLEDGE_STATUSES:
        rows = rows.filter(models.StoreKnowledge.status == status)
    if category in KNOWLEDGE_CATEGORIES:
        rows = rows.filter(models.StoreKnowledge.category == category)
    if query:
        like = f"%{query[:80]}%"
        rows = rows.filter(or_(
            models.StoreKnowledge.title.like(like),
            models.StoreKnowledge.question.like(like),
            models.StoreKnowledge.content.like(like),
            models.StoreKnowledge.keywords_json.like(like),
        ))
    try:
        limit = min(max(int(request.args.get("limit") or 200), 1), 200)
    except (TypeError, ValueError):
        limit = 200
    items = rows.order_by(
        models.StoreKnowledge.priority.desc(),
        models.StoreKnowledge.update_time.desc(),
    ).limit(limit).all()
    counts = {
        key: models.StoreKnowledge.query.filter_by(tenant_id=g.tenant_id, status=key).count()
        for key in ("published", "draft", "disabled")
    }
    return {"status": 200, "msg": "ok", "data": {"items": [row.to_dict() for row in items], "counts": counts}}


@agents_bp.route("/knowledge/", methods=["POST"])
@login_required
@permission_required("service:manage")
def store_knowledge_create():
    from flask_shop import db, models
    from flask_shop.utils.audit import write_audit

    try:
        payload = _knowledge_payload(request.get_json(silent=True) or {})
    except ValueError as exc:
        return {"status": 400, "msg": str(exc)}
    exists = models.StoreKnowledge.query.filter_by(tenant_id=g.tenant_id, title=payload["title"]).first()
    if exists:
        return {"status": 409, "msg": "同名知识已存在，请编辑原条目"}
    row = models.StoreKnowledge(tenant_id=g.tenant_id)
    _apply_knowledge_payload(row, payload)
    db.session.add(row)
    db.session.commit()
    write_audit("knowledge.create", "store_knowledge", row.id, row.title)
    return {"status": 200, "msg": "知识已创建", "data": row.to_dict()}


@agents_bp.route("/knowledge/<int:knowledge_id>/", methods=["PUT"])
@login_required
@permission_required("service:manage")
def store_knowledge_update(knowledge_id):
    from flask_shop import db, models
    from flask_shop.utils.audit import write_audit

    row = models.StoreKnowledge.query.filter_by(id=knowledge_id, tenant_id=g.tenant_id).first()
    if not row:
        return {"status": 404, "msg": "知识条目不存在"}
    try:
        payload = _knowledge_payload(request.get_json(silent=True) or {}, source_type=row.source_type or "manual")
    except ValueError as exc:
        return {"status": 400, "msg": str(exc)}
    duplicate = models.StoreKnowledge.query.filter(
        models.StoreKnowledge.tenant_id == g.tenant_id,
        models.StoreKnowledge.title == payload["title"],
        models.StoreKnowledge.id != row.id,
    ).first()
    if duplicate:
        return {"status": 409, "msg": "同名知识已存在，请修改标题"}
    _apply_knowledge_payload(row, payload)
    db.session.commit()
    write_audit("knowledge.update", "store_knowledge", row.id, row.title)
    return {"status": 200, "msg": "知识已更新", "data": row.to_dict()}


@agents_bp.route("/knowledge/<int:knowledge_id>/", methods=["DELETE"])
@login_required
@permission_required("service:manage")
def store_knowledge_delete(knowledge_id):
    from flask_shop import db, models
    from flask_shop.utils.audit import write_audit

    row = models.StoreKnowledge.query.filter_by(id=knowledge_id, tenant_id=g.tenant_id).first()
    if not row:
        return {"status": 404, "msg": "知识条目不存在"}
    title = row.title
    db.session.delete(row)
    db.session.commit()
    write_audit("knowledge.delete", "store_knowledge", knowledge_id, title)
    return {"status": 200, "msg": "知识已删除"}


@agents_bp.route("/knowledge/template/", methods=["GET"])
@login_required
@permission_required("service:read")
def store_knowledge_template():
    from flask import Response

    content = (
        "title,category,question,content,keywords,status,priority\r\n"
        "发货时效,shipping,下单后多久发货,现货订单通常在付款确认后 48 小时内发出,发货;配送,draft,50\r\n"
    )
    return Response(
        "\ufeff" + content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=store_knowledge_template.csv"},
    )


@agents_bp.route("/knowledge/import/", methods=["POST"])
@login_required
@permission_required("service:manage")
def store_knowledge_import():
    import csv
    import io
    from flask_shop import db, models
    from flask_shop.utils.audit import write_audit

    upload = request.files.get("file")
    if not upload or not str(upload.filename or "").lower().endswith(".csv"):
        return {"status": 400, "msg": "请选择 CSV 文件"}
    raw = upload.stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        return {"status": 413, "msg": "CSV 文件不能超过 1 MB"}
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {"status": 400, "msg": "CSV 必须使用 UTF-8 编码"}
    reader = csv.DictReader(io.StringIO(text))
    fields = set(reader.fieldnames or [])
    if not {"title", "content"}.issubset(fields):
        return {"status": 400, "msg": "CSV 缺少 title 或 content 列"}
    created = 0
    updated = 0
    errors = []
    for index, source in enumerate(reader, start=2):
        if index > 302:
            errors.append({"row": index, "reason": "单次最多导入 300 条"})
            break
        try:
            payload = _knowledge_payload(source, source_type="import")
            row = models.StoreKnowledge.query.filter_by(
                tenant_id=g.tenant_id,
                title=payload["title"],
            ).first()
            if row:
                payload["source_type"] = row.source_type if row.source_type == "demo" else "import"
                _apply_knowledge_payload(row, payload)
                updated += 1
            else:
                row = models.StoreKnowledge(tenant_id=g.tenant_id)
                _apply_knowledge_payload(row, payload)
                db.session.add(row)
                created += 1
        except ValueError as exc:
            errors.append({"row": index, "title": str(source.get("title") or "")[:128], "reason": str(exc)})
    db.session.commit()
    write_audit(
        "knowledge.import",
        "store_knowledge",
        None,
        f"created={created} updated={updated} errors={len(errors)}",
    )
    return {
        "status": 200,
        "msg": "导入完成",
        "data": {"created": created, "updated": updated, "errors": errors, "error_count": len(errors)},
    }


@agents_bp.route("/support/inbox/", methods=["GET"])
@login_required
@permission_required("service:read")
def support_inbox():
    from datetime import datetime
    from sqlalchemy import or_
    from flask_shop import models

    status = str(request.args.get("status") or "").strip()
    query = str(request.args.get("q") or "").strip()
    assignee = str(request.args.get("assignee") or "").strip()
    rows = models.SupportConversation.query.filter_by(tenant_id=g.tenant_id)
    if status and status != "all":
        wanted = [item for item in status.split(",") if item in {"bot", "waiting", "active", "resolved"}]
        if wanted:
            rows = rows.filter(models.SupportConversation.status.in_(wanted))
    if assignee == "mine":
        rows = rows.filter(models.SupportConversation.assignee_id == g.staff_id)
    if query:
        like = f"%{query[:80]}%"
        rows = rows.filter(or_(
            models.SupportConversation.subject.like(like),
            models.SupportConversation.last_message.like(like),
            models.SupportConversation.session_id.like(like),
        ))
    items = rows.order_by(
        models.SupportConversation.need_human.desc(),
        models.SupportConversation.update_time.desc(),
    ).limit(min(int(request.args.get("limit") or 100), 200)).all()
    now = datetime.now()
    data = []
    for item in items:
        value = item.to_dict()
        started = item.update_time or item.create_time
        value["waiting_minutes"] = max(int((now - started).total_seconds() // 60), 0) if started and item.status == "waiting" else 0
        data.append(value)
    counts = {
        key: models.SupportConversation.query.filter_by(tenant_id=g.tenant_id, status=key).count()
        for key in ("bot", "waiting", "active", "resolved")
    }
    rated = models.SupportConversation.query.filter(
        models.SupportConversation.tenant_id == g.tenant_id,
        models.SupportConversation.satisfaction.isnot(None),
    ).all()
    satisfaction = round(sum(x.satisfaction for x in rated) / len(rated), 1) if rated else None
    return {"status": 200, "msg": "ok", "data": {"items": data, "counts": counts, "satisfaction": satisfaction}}


@agents_bp.route("/support/conversations/<int:conversation_id>/", methods=["GET"])
@login_required
@permission_required("service:read")
def support_conversation_detail(conversation_id):
    from flask_shop import models

    row = _support_row(conversation_id)
    if not row:
        return {"status": 404, "msg": "会话不存在"}
    orders = []
    if row.customer_id:
        orders = models.Order.query.filter_by(
            tenant_id=g.tenant_id,
            customer_id=row.customer_id,
        ).order_by(models.Order.id.desc()).limit(5).all()
    return {
        "status": 200,
        "msg": "ok",
        "data": {
            "conversation": row.to_dict(),
            "messages": [item.to_dict() for item in row.messages.order_by(models.SupportMessage.id.asc()).limit(500).all()],
            "orders": [item.to_dict() for item in orders],
        },
    }


@agents_bp.route("/support/conversations/<int:conversation_id>/claim/", methods=["POST"])
@login_required
@permission_required("service:reply")
def support_conversation_claim(conversation_id):
    from flask_shop.agents import support
    from flask_shop.utils.audit import write_audit

    row = _support_row(conversation_id)
    if not row:
        return {"status": 404, "msg": "会话不存在"}
    if row.status == "resolved":
        return {"status": 400, "msg": "会话已结束"}
    if row.assignee_id not in (None, g.staff_id):
        return {"status": 409, "msg": "该会话已由其他客服接待"}
    support.claim(row, g.staff_id)
    write_audit("support.claim", "support_conversation", row.id, row.session_id)
    return {"status": 200, "msg": "已接入会话", "data": row.to_dict()}


@agents_bp.route("/support/conversations/<int:conversation_id>/reply/", methods=["POST"])
@login_required
@permission_required("service:reply")
def support_conversation_reply(conversation_id):
    from flask_shop.agents import support
    from flask_shop.utils.audit import write_audit

    row = _support_row(conversation_id)
    if not row:
        return {"status": 404, "msg": "会话不存在"}
    content = str((request.get_json(silent=True) or {}).get("content") or "").strip()
    if not content:
        return {"status": 400, "msg": "回复内容不能为空"}
    try:
        support.reply(row, g.staff_id, content)
    except (ValueError, PermissionError) as exc:
        return {"status": 409, "msg": str(exc)}
    write_audit("support.reply", "support_conversation", row.id, content[:80])
    return {"status": 200, "msg": "回复已发送", "data": row.to_dict()}


@agents_bp.route("/support/conversations/<int:conversation_id>/resolve/", methods=["POST"])
@login_required
@permission_required("service:reply")
def support_conversation_resolve(conversation_id):
    from flask_shop.agents import support
    from flask_shop.utils.audit import write_audit

    row = _support_row(conversation_id)
    if not row:
        return {"status": 404, "msg": "会话不存在"}
    try:
        support.resolve(row, g.staff_id)
    except PermissionError as exc:
        return {"status": 409, "msg": str(exc)}
    write_audit("support.resolve", "support_conversation", row.id, row.session_id)
    return {"status": 200, "msg": "会话已结束", "data": row.to_dict()}


@agents_bp.route("/support/conversations/<int:conversation_id>/priority/", methods=["PUT"])
@login_required
@permission_required("service:manage")
def support_conversation_priority(conversation_id):
    from flask_shop import db
    from flask_shop.utils.audit import write_audit

    row = _support_row(conversation_id)
    if not row:
        return {"status": 404, "msg": "会话不存在"}
    priority = str((request.get_json(silent=True) or {}).get("priority") or "")
    if priority not in {"normal", "high", "urgent"}:
        return {"status": 400, "msg": "priority 不合法"}
    row.priority = priority
    db.session.commit()
    write_audit("support.priority", "support_conversation", row.id, priority)
    return {"status": 200, "msg": "优先级已更新", "data": row.to_dict()}


@agents_bp.route("/task-logs/", methods=["GET"])
@login_required
def agent_task_logs():
    from flask_shop import models
    from flask_shop.utils.tenant_query import tenant_context
    limit = min(int(request.args.get("limit") or 50), 200)
    with tenant_context(disabled=True):
        q = models.AgentTaskLog.query.filter_by(tenant_id=g.tenant_id).order_by(models.AgentTaskLog.id.desc()).limit(limit)
        return {"status": 200, "msg": "ok", "data": [x.to_dict() for x in q.all()]}
