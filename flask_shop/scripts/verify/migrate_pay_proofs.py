"""Copy one tenant's legacy payment proofs to private storage; never delete originals."""
import argparse
import os
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description='按店铺迁移旧付款截图；默认只预演，保留原文件')
    parser.add_argument('--tenant', required=True, help='待迁移店铺标识')
    parser.add_argument('--execute', action='store_true', help='实际复制截图并更新订单引用')
    parser.add_argument('--confirm-database', default='', help='执行时必须与配置中的数据库名完全一致')
    args = parser.parse_args()

    from flask_shop import create_app, models
    from flask_shop.utils.migrate_pay_proofs import migrate_tenant_proofs
    from flask_shop.utils.tenant_query import tenant_context

    app = create_app(os.getenv('FLASK_CONFIG', 'develop'), initialize_schema=False, start_background=False)
    database = make_url(app.config['SQLALCHEMY_DATABASE_URI']).database
    if args.execute and (not database or database == ':memory:' or args.confirm_database != database):
        print('拒绝执行：数据库名称与确认值不一致')
        return 2
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug=args.tenant).first()
        if not tenant:
            print('指定店铺不存在')
            return 2
        result = migrate_tenant_proofs(tenant.id, execute=args.execute)
    print(f"{'执行' if args.execute else '预演'}：检查 {result['checked']} 条，迁移 {result['migrated']} 条，异常 {len(result['errors'])} 条")
    for order_id, error in result['errors']:
        print(f'订单 {order_id}: {error}')
    print('原文件不会删除；需在核验、备份与清理旧缓存后另行规划删除。')
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
