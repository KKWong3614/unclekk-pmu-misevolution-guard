#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蜜罐探针验证器：用运行时合成的探针验证护栏的真实拦截能力。

运行:
    python scripts/test_honeypot_probes.py

验证内容：
  1) 对每个蜜罐探针用 redflags.scan_text(prose=True) 扫描，校验最高严重度与命中规则
     是否符合预期（honeypot_deny/warn 应命中预期 HIGH/MEDIUM；benign/嵌套跳过类应不命中）。
     探针由 honeypot_factory 在运行期临时合成（分发包不存储完整危险载荷）。
  2) 模拟 write_gate.extract_content 的 MultiEdit 拼接场景：两次 Edit 各自安全，但
     合并后拼出高危密钥，验证闸一不会被增量编辑绕过。

退出码 0 = 全部通过；1 = 存在失败。
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from redflags import scan_text, highest_severity, RULES  # noqa: E402
import write_gate  # noqa: E402
from honeypot_factory import generate_all  # noqa: E402


def severity_of(text):
    hits = scan_text(text, prose=True)
    return highest_severity(hits), {h["id"] for h in hits}, hits


def check_probes():
    probes = generate_all()
    failures = []
    covered = set()
    for pid, doc, exp in probes:
        sev, ids, hits = severity_of(doc)
        covered |= ids

        # 严重度比对
        if sev != exp["severity"]:
            failures.append(f"[{pid}] 严重度期望 {exp['severity']} 实际 {sev}")
            continue
        # 规则命中比对
        missing = [r for r in exp.get("rules", []) if r not in ids]
        if missing:
            failures.append(f"[{pid}] 期望命中规则未命中 {missing}（实际 {sorted(ids)}）")
        # benign/none 时不应有任何命中
        if exp["severity"] == "none" and hits:
            failures.append(f"[{pid}] 期望无命中但有命中 {sorted(ids)}")

    # 覆盖率报告
    all_rules = {r[0] for r in RULES}
    uncovered = sorted(all_rules - covered)
    print(f"探针总数: {len(probes)}")
    print(f"被蜜罐覆盖的规则: {len(covered & all_rules)} / {len(all_rules)}")
    if uncovered:
        print(f"  蜜罐未覆盖规则: {uncovered}")
    else:
        print("  ✅ 全部 34 条规则均被至少一个蜜罐探针覆盖")

    return failures


def check_multiedit_bypass():
    """模拟 MultiEdit：两次 Edit 各半密钥，合并后成完整高危密钥。

    验证 write_gate.extract_content 按『合并后全文』扫描，不被增量编辑绕过。
    （两半均 < 20 字符，单独不命中；合并后 > 20 字符命中 HIGH。）
    """
    pid = "H26"
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    # 写入前文件已有内容：密钥前半 + 占位符，待两次 Edit 拼接出完整密钥
    tmp.write("鉴权使用 X完成调用\n")
    tmp.close()
    try:
        tool_input = {
            "file_path": tmp.name,
            "edits": [
                # 第一次 Edit：把 X 替换为 sk-... 但单次仍不足 20 字符（不单独命中）
                {"old_string": "X", "new_string": "sk-ABCDEFGHIJKLMNOPQR"},
                # 第二次 Edit：把"完成调用"替换为后半密钥 + 完成调用，
                # 与第一次结果处在同一行连续 → 拼出完整密钥
                {"old_string": "完成调用", "new_string": "STUVWXYZ123456 完成调用"},
            ],
        }
        content, _ = write_gate.extract_content(tool_input, "MultiEdit")
        sev, ids, _ = severity_of(content)
        if sev == "high" and "hardcoded.openai_key" in ids:
            print(f"[{pid}] MultiEdit 拼接场景: ✅ 合并后命中 HIGH（未绕过）")
            return []
        return [f"[{pid}] MultiEdit 拼接未被拦截: sev={sev} ids={sorted(ids)} content={content!r}"]
    finally:
        os.unlink(tmp.name)


def main():
    print("=== Part A: 蜜罐探针扫描验证（运行时合成） ===")
    f1 = check_probes()
    print("\n=== Part B: MultiEdit 拼接绕过验证 ===")
    f2 = check_multiedit_bypass()

    all_fail = f1 + f2
    print()
    if all_fail:
        for x in all_fail:
            print(f"  ❌ {x}")
        print(f"\n失败 {len(all_fail)} 项")
        return 1
    print("✅ 全部蜜罐探针验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
