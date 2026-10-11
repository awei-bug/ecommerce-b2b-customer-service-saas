# -*- coding: utf-8 -*-
"""命令行从数据中心同步商品（可挂定时任务）。

用法::

    python scripts/jobs/sync_from_hub.py                 # 同步当前配置租户
    python scripts/jobs/sync_from_hub.py --slug demo     # 指定租户
    python scripts/jobs/sync_from_hub.py --draft         # 存草稿不直接上架
    python scripts/jobs/sync_from_hub.py --since 2026-09-01T00:00:00+00:00
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, models  # noqa: E402
from flask_shop.utils import hub_sync  # noqa: E402
from flask_shop.utils.tenant_query import tenant_context  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slug', default=os.getenv('DATA_HUB_TENANT_SLUG', ''))
    parser.add_argument('--status', default='')
    parser.add_argument('--since', default='')
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--draft', action='store_true', help='存草稿态，不直接上架')
    parser.add_argument('--no-ack', action='store_true', help='不回执数据中心')
    args = parser.parse_args()

    app = create_app('develop')
    with app.app_context():
        slug = args.slug or app.config.get('DATA_HUB_TENANT_SLUG') or 'demo'
        with tenant_context(disabled=True):
            tenant = models.Tenant.query.filter_by(slug=slug).first()
        if not tenant:
            print(f'tenant not found: {slug}')
            return 2

        result = hub_sync.sync_from_hub(
            tenant,
            status=args.status,
            since=args.since,
            limit=args.limit,
            publish=not args.draft,
            ack=not args.no_ack,
        )
        print(json.dumps(result.get('summary') or {}, ensure_ascii=False))
        for row in (result.get('errors') or [])[:10]:
            print('ERR', row)
        return 0


if __name__ == '__main__':
    sys.exit(main())
