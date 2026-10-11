"""运行到期的租户自动化规则。

生产环境建议每 15 分钟由 Windows 任务计划或 cron 调用一次：
    python scripts/jobs/run_automation_due.py
"""
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask import g  # noqa: E402

from flask_shop import create_app, models  # noqa: E402
from flask_shop.automation.views import _execute_rule  # noqa: E402
from flask_shop.utils.tenant_query import tenant_context  # noqa: E402


def is_due(rule, now):
    if rule.status != 'enabled':
        return False
    if not rule.last_run_at:
        return True
    schedule = (rule.schedule or '').strip().lower()
    if schedule == 'hourly':
        return rule.last_run_at <= now - timedelta(hours=1)
    if schedule.startswith('daily'):
        parts = schedule.split()
        run_at = parts[1] if len(parts) > 1 else '09:00'
        try:
            hour, minute = [int(x) for x in run_at.split(':', 1)]
        except (TypeError, ValueError):
            hour, minute = 9, 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return rule.last_run_at.date() < now.date() and now >= target
    return False


def main():
    app = create_app(os.getenv('FLASK_CONFIG', 'develop'))
    now = datetime.now()
    with app.app_context(), tenant_context(disabled=True):
        rule_ids = [r.id for r in models.AutomationRule.query.filter_by(status='enabled').all() if is_due(r, now)]

    success = 0
    for rule_id in rule_ids:
        with app.test_request_context('/internal/automation-scheduler'):
            with tenant_context(disabled=True):
                rule = models.AutomationRule.query.filter_by(id=rule_id).first()
            if not rule:
                continue
            g.tenant_id = rule.tenant_id
            g.staff_id = None
            with tenant_context(tenant_id=rule.tenant_id):
                run = _execute_rule(rule)
                success += int(run.status == 'success')
                print(f'[{run.status}] tenant={rule.tenant_id} rule={rule.id} {run.summary}')
    print(f'automation due: {len(rule_ids)}, success: {success}')


if __name__ == '__main__':
    main()
