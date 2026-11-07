import os


def reject_production_demo_seed():
    names = (os.getenv('FLASK_CONFIG', ''), os.getenv('FLASK_ENV', ''), os.getenv('ENV', ''))
    if any(name.strip().lower() in ('product', 'production', 'prod') for name in names):
        raise SystemExit('拒绝在生产配置中运行演示数据脚本；请使用正式租户初始化流程。')
