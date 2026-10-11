# -*- coding: utf-8 -*-
"""CLI: close expired unpaid orders. Used by deploy/win/close_expired_orders.bat"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from manager import app
from flask_shop.utils.order_timeout import close_expired_pending_orders
from flask_shop.utils.tenant_query import tenant_context

with app.app_context():
    with tenant_context(disabled=True):
        n = close_expired_pending_orders()
print("closed=%s" % n)
