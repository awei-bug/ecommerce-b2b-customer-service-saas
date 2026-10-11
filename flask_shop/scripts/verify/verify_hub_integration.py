# -*- coding: utf-8 -*-
"""数据中心整合链路自检：写入 → 同步 → 上架 → 客服知识检索。

用法::

    python scripts/verify/verify_hub_integration.py [--slug demo]

前置：data-hub 已启动，且 DATA_HUB_URL / DATA_HUB_TOKEN / DATA_HUB_TENANT_SLUG 已配置。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402
from flask_shop.utils import hub_client, hub_sync  # noqa: E402
from flask_shop.agents import knowledge as knowledge_lib  # noqa: E402
from flask_shop.agents.types import AgentContext  # noqa: E402
from flask_shop.agents.orchestrator import AgentOrchestrator  # noqa: E402
from flask_shop.utils.tenant_query import tenant_context  # noqa: E402

SAMPLE = {
    "external_id": "cc-verify-001",
    "title": "便携榨汁杯 380ml",
    "price": 129.0,
    "stock": 30,
    "category": "厨具",
    "tags": ["榨汁杯", "便携", "USB充电"],
    "selling_points": ["380ml 容量", "USB 充电一次榨 15 杯", "刀头可拆洗"],
    "scenario": "办公室、出差",
    "spec": {"容量": "380ml", "电池": "2000mAh"},
    "faq": [{"q": "能榨冰块吗", "a": "不建议，硬物会损伤刀头"}],
    "desc_zh": "便携式榨汁杯，380ml 容量，USB 充电。",
}

checks = []


def check(name: str, ok: bool, detail: str = ""):
    checks.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))


def main():
    slug = (sys.argv[sys.argv.index('--slug') + 1] if '--slug' in sys.argv
            else os.getenv('DATA_HUB_TENANT_SLUG') or 'demo')

    app = create_app('develop')
    with app.app_context():
        if '--cleanup' in sys.argv:
            return cleanup(app, slug)

        check('hub.enabled', hub_client.hub_enabled(), app.config.get('DATA_HUB_URL') or '')
        if not hub_client.hub_enabled():
            return 1

        try:
            health = hub_client.health()
            check('hub.health', bool(health.get('ok')), health.get('service') or '')
        except Exception as exc:
            check('hub.health', False, str(exc))
            return 1

        with tenant_context(disabled=True):
            tenant = models.Tenant.query.filter_by(slug=slug).first()
        check('tenant.found', tenant is not None, slug)
        if not tenant:
            return 1

        # 1. 模拟内容平台产出写入数据中心
        stamp = datetime.now(timezone.utc).strftime('%H%M%S')
        item = dict(SAMPLE)
        item['external_id'] = f"cc-verify-{stamp}"
        item['title'] = f"便携榨汁杯 380ml #{stamp}"
        try:
            # 直接走 HTTP 写入，等价于内容平台 ingest
            import requests
            cfg_url = app.config['DATA_HUB_URL'].rstrip('/')
            resp = requests.post(
                f"{cfg_url}/hub/ingest",
                json={"tenant_slug": slug, "source": "verify", "job_id": "verify", "items": [item]},
                headers=hub_client._headers(),
                timeout=app.config.get('DATA_HUB_TIMEOUT', 10),
            )
            payload = resp.json()
            check('hub.ingest', resp.status_code == 200 and payload.get('ok_count') == 1,
                  payload.get('results', [{}])[0].get('action', ''))
        except Exception as exc:
            check('hub.ingest', False, str(exc))
            return 1

        # 2. 电商侧同步上架
        result = hub_sync.sync_from_hub(tenant, status='', limit=50, publish=True, ack=True)
        summary = result.get('summary') or {}
        created_rows = result.get('created') or []
        hit = [r for r in created_rows if r.get('external_id') == item['external_id']]
        check('sync.created', bool(hit), str(summary))

        if not hit:
            print(json_dumps(result))
            return 1
        product_id = hit[0]['product_id']

        with tenant_context(tenant_id=tenant.id):
            p = models.Product.query.get(product_id)
            k = models.ProductKnowledge.query.filter_by(external_id=item['external_id']).first()

        check('product.persisted', p is not None, f"id={product_id}")
        check('product.price', p is not None and abs(float(p.price) - 129.0) < 0.01, str(p.price if p else None))
        check('product.sell_points', bool(p and p.sell_points), (p.sell_points or '')[:40] if p else '')
        check('product.state_on_sale', p is not None and p.state == 2, str(p.state if p else None))
        check('knowledge.cached', k is not None, f"hash={(k.content_hash or '')[:8]}" if k else '')
        check('knowledge.linked', bool(k and k.product_id == product_id), str(k.product_id if k else None))

        # 3. 客服知识检索
        cards = knowledge_lib.load_knowledge(tenant.id, '榨汁杯 能榨冰块吗', limit=3)
        check('knowledge.search', len(cards) > 0, f"n={len(cards)}")
        if cards:
            top = cards[0]
            check('knowledge.top_match', '榨汁杯' in str(top.get('title') or ''), str(top.get('title')))
            check('knowledge.faq_present', len(top.get('faq') or []) > 0, str(top.get('faq'))[:60])
            check('knowledge.points_present', len(top.get('selling_points') or []) > 0,
                  str(top.get('selling_points'))[:60])

        # 4. 客服编排跑一遍（不依赖 LLM 也能出规则回复）
        ctx = AgentContext(tenant_id=tenant.id, tenant_slug=slug,
                           user_text='有没有便携榨汁杯', channel='mall_chat')
        try:
            orch = AgentOrchestrator()
            out = orch.run_chat('有没有便携榨汁杯', tenant_id=tenant.id, tenant_slug=slug, channel='mall_chat')
            data = (out or {}).get('data') or {}
            msg = data.get('reply') or ''
            know = data.get('knowledge') or {}
            check('agent.reply', len(msg) > 0, msg[:80].replace('\n', ' / '))
            check('agent.knowledge_loaded', bool(know.get('count')), str(know.get('count')))
        except Exception as exc:
            check('agent.reply', False, f"{type(exc).__name__}: {exc}")

        # 5. 幂等：再次同步不应重复建商品
        before = models.Product.query.filter_by(name=item['title']).count()
        hub_sync.sync_from_hub(tenant, status='', limit=50, publish=True, ack=True)
        with tenant_context(tenant_id=tenant.id):
            after = models.Product.query.filter_by(name=item['title']).count()
        check('sync.idempotent', after == before and before >= 1, f"before={before} after={after}")

    failed = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


def json_dumps(obj):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)[:2000]


def cleanup(app, slug):
    """删除自检产生的 cc-verify-* 数据，避免污染 demo 店铺。"""
    from flask_shop import db
    with tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug=slug).first()
    if not tenant:
        print(f'tenant not found: {slug}')
        return 1
    with tenant_context(tenant_id=tenant.id):
        rows = models.ProductKnowledge.query.filter(
            models.ProductKnowledge.external_id.like('cc-verify-%')
        ).all()
        ids = [r.product_id for r in rows if r.product_id]
        for r in rows:
            db.session.delete(r)
        for pid in ids:
            p = models.Product.query.get(pid)
            if p:
                db.session.delete(p)
        db.session.commit()
    print(f'cleaned: knowledge={len(rows)} products={len(ids)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
