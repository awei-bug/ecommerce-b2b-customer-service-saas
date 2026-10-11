# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("AGENTS_LLM", "0")
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)
from flask_shop import create_app
from flask_shop.agents.orchestrator import orchestrator

CASES = [
  {"text": "你好", "expect_intent": "greeting"},
  {"text": "有没有耳机", "expect_intent_in": ["search", "recommend"], "expect_keyword": "耳机"},
  {"text": "预算100以内", "expect_budget_max": 100},
  {"text": "有没有100块钱左右的耳机", "expect_intent_in": ["search", "recommend"], "expect_keyword": "耳机", "expect_budget_max": 100},
  {"text": "怎么付款", "expect_intent": "pay_help"},
  {"text": "查订单", "expect_intent": "order_status"},
  {"text": "物流到哪了", "expect_intent": "track"},
  {"text": "我要退款", "expect_intent": "refund"},
  {"text": "今日运营情况", "expect_intent": "ops"},
  {"text": "推荐点什么", "expect_intent_in": ["recommend", "search"]},
]

def main():
    app = create_app(os.getenv("FLASK_CONFIG") or "develop")
    passed, failed = 0, []
    with app.app_context():
        for i, case in enumerate(CASES, 1):
            r = orchestrator.run_chat(case["text"], tenant_slug="demo", channel="eval")
            data = (r or {}).get("data") or {}
            intent = (data.get("intent") or {}).get("intent")
            kws = (data.get("intent") or {}).get("keywords") or []
            budget = (data.get("intent") or {}).get("budget_max")
            ok, reasons = True, []
            if "expect_intent" in case and intent != case["expect_intent"]:
                ok=False; reasons.append(f"intent={intent}")
            if "expect_intent_in" in case and intent not in case["expect_intent_in"]:
                ok=False; reasons.append(f"intent={intent}")
            if "expect_keyword" in case and case["expect_keyword"] not in kws:
                ok=False; reasons.append(f"kw={kws}")
            if "expect_budget_max" in case:
                if budget is None or float(budget) != float(case["expect_budget_max"]):
                    ok=False; reasons.append(f"budget={budget}")
            if ok:
                passed += 1
                print(f"[OK] {i} {case['text'][:24]} -> {intent}")
            else:
                failed.append((case["text"], reasons, intent))
                print(f"[FAIL] {i} {case['text'][:24]} {reasons}")
    print(f"passed {passed}/{len(CASES)}")
    if failed:
        return 1
    print("EVAL_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
