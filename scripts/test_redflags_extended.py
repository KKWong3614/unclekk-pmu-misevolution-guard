#!/usr/bin/env python3
"""扩展测试：验证新增 edge case 和 boundary case。

运行:
    python scripts/test_redflags_extended.py
退出码 0 = 全部通过；1 = 有失败。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from redflags import scan_text, highest_severity

SEV_MAP = {"deny": "high", "warn": "medium", "allow": "none", "low": "low"}


def main():
    # 加载扩展测试用例
    cases_path = os.path.normpath(os.path.join(HERE, "..", "test-prompts-v2.json"))
    if not os.path.exists(cases_path):
        print(f"SKIP: 未找到扩展测试用例 {cases_path}")
        return 0

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    passed = failed = skipped = 0
    for c in cases:
        if not isinstance(c, dict) or "prompt" not in c or "expected" not in c:
            print(f"[SKIP] 用例结构异常: {c!r}")
            skipped += 1
            continue

        cid = c.get("id", "?")
        text = c.get("prompt", "")
        expected = SEV_MAP.get(c.get("expected"))
        if expected is None:
            print(f"[SKIP] #{cid} expected 未知: {c.get('expected')!r}")
            skipped += 1
            continue

        actual = highest_severity(scan_text(text))
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] #{cid} expected={expected} actual={actual} ({c.get('category')})")
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n结果: {passed} 通过, {failed} 失败, {skipped} 跳过, 共 {len(cases)} 条")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
