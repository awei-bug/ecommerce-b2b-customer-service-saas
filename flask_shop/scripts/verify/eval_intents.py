# -*- coding: utf-8 -*-
"""评测男装导购意图规则：python scripts/verify/eval_intents.py"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Allow the documented ``python scripts/verify/eval_intents.py`` command to
# work without requiring callers to set PYTHONPATH explicitly.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask_shop.agents.intent_agent import IntentAgent
from flask_shop.agents.types import AgentContext


def load_cases(path: Path):
    with path.open('r', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default=str(Path(__file__).parents[2] / 'data' / 'evals' / 'menswear_intents.jsonl'))
    args = parser.parse_args()
    os.environ['AGENTS_LLM'] = '0'
    agent = IntentAgent()
    cases = load_cases(Path(args.dataset))
    matrix = defaultdict(Counter)
    correct = 0
    confidence = []
    for case in cases:
        ctx = AgentContext(user_text=case['text'], channel='mall_chat')
        result = agent.run(ctx)
        predicted = (result.data or {}).get('intent')
        expected = case['intent']
        matrix[expected][predicted] += 1
        confidence.append(float((result.data or {}).get('confidence') or 0))
        correct += int(predicted == expected)
    labels = sorted(set(matrix) | {p for row in matrix.values() for p in row})
    per_intent = {}
    for label in labels:
        tp = matrix[label][label]
        actual = sum(matrix[label].values())
        predicted = sum(matrix[row][label] for row in labels)
        per_intent[label] = {
            'recall': round(tp / actual, 4) if actual else 0,
            'precision': round(tp / predicted, 4) if predicted else 0,
            'support': actual,
        }
    report = {
        'dataset': str(Path(args.dataset)),
        'samples': len(cases),
        'accuracy': round(correct / len(cases), 4) if cases else 0,
        'average_confidence': round(sum(confidence) / len(confidence), 4) if confidence else 0,
        'per_intent': per_intent,
        'confusion_matrix': {expected: dict(row) for expected, row in matrix.items()},
        'note': '规则基线评测，不代表真实线上命中率；应持续用脱敏真实会话扩充数据集。',
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
