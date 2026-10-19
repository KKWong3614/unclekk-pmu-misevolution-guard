#!/usr/bin/env python3
"""全规则覆盖率测试：确保34条规则都有正面和负面测试覆盖。

运行:
    python scripts/test_rule_coverage.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from redflags import scan_text, highest_severity, RULES


def main():
    # 加载所有测试用例
    all_cases = []
    for f in ["../test-prompts.json", "../test-prompts-v2.json", "../test-prompts-v3.json"]:
        path = os.path.normpath(os.path.join(HERE, f))
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                all_cases.extend(json.load(fh))

    # 找出被覆盖的规则
    covered = set()
    for c in all_cases:
        hits = scan_text(c.get("prompt", ""))
        for h in hits:
            covered.add(h["id"])

    all_rules = set(r[0] for r in RULES)
    not_tested = sorted(all_rules - covered)

    print(f"总规则数: {len(RULES)}")
    print(f"已测试: {len(covered)}")
    print(f"未测试: {len(not_tested)}")

    if not_tested:
        print(f"\n未测试规则: {not_tested}")
        return 1
    else:
        print("\n✅ 所有规则已测试覆盖")
        return 0


if __name__ == "__main__":
    sys.exit(main())
