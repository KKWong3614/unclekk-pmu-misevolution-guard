#!/usr/bin/env python3
"""并发安全测试：验证append_audit在多线程并发场景下的完整性。

运行:
    python scripts/test_concurrent.py
退出码 0 = 所有记录写入成功。
"""
import json
import os
import sys
import os
import threading
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from write_gate import append_audit, AUDIT_LOG


def main():
    # 测试并发写入实际AUDIT_LOG
    N = 10
    results = []
    lock = threading.Lock()

    def append(i):
        try:
            append_audit({"ts": datetime.now(timezone.utc).isoformat(), "test": i})
            with lock:
                results.append(i)
        except Exception as e:
            with lock:
                results.append(f"error:{i}:{e}")

    threads = [threading.Thread(target=append, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 验证：读取AUDIT_LOG末尾N行
    if not os.path.exists(AUDIT_LOG):
        print("FAIL: AUDIT_LOG not found")
        return 1

    with open(AUDIT_LOG, "r", encoding="utf-8") as f:
        all_lines = [l.strip() for l in f if l.strip()]

    # 检查最后N条是否都是我们的测试记录
    recent = all_lines[-N:] if len(all_lines) >= N else all_lines
    test_ids = [json.loads(l).get("test") for l in recent]
    passed = len(results) == N and all(r in test_ids for r in range(N))

    print(f"Threads: {N}, results: {len(results)}, recent lines: {len(recent)}")
    print(f"Test IDs in recent: {test_ids}")
    if passed:
        print("PASS")
        return 0
    else:
        print("FAIL: not all records written correctly")
        return 1


if __name__ == "__main__":
    sys.exit(main())
