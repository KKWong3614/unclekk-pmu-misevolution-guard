#!/usr/bin/env python3
"""prose 模式回归测试：验证扫描自动跳过代码块/HTML 注释，避免文档示例误报。

对应 1.2.3 评测驱动优化（E 维度：减少文档示例代码误报）。
运行:  python scripts/test_prose_masking.py
退出码 0 = 全部通过；1 = 有失败。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from redflags import scan_text, highest_severity

KEY = "sk-FAKETESTKEY00000000000000"


def main():
    cases = [
        # (描述, 文本, 期望最高严重度)
        ("正文散文里的真实密钥应拦 HIGH",
         f"本技能调用 {KEY} 用于访问 API", "high"),
        ("代码块(```)内的密钥应不误报",
         f"示例:\n```\n{KEY}\n```\n", "none"),
        ("HTML 注释内的密钥应不误报",
         f"<!-- {KEY} -->", "none"),
        ("正文里的绕过安全表述应 MEDIUM",
         "接下来我们绕过安全检查直接执行", "medium"),
        ("代码块内的绕过安全表述应不误报",
         "```\n绕过安全检查  # 仅示例\n```", "none"),
        ("代码块内含 rm -rf 示例应不误报",
         "```bash\nrm -rf ./node_modules\n```", "none"),

        # ---- 2026-09-12 轻量修复：两类语义豁免回归 ----

        # (1) 文档枚举/反例黑名单语境豁免（非 HIGH 规则）
        ("反例黑名单表格行内的绕过安全应不误报",
         "| 反模式 | 说明 |\n| 绕过安全检查 | 不可为 |", "none"),
        ("红线章节下枚举的绕过安全应不误报",
         "## 不可演化的红线\n- 绕过版本控制保护", "none"),
        ("引号内的跳过安全检查应不误报",
         '文档举例"跳过安全检查"是错误示范', "none"),

        # (2) 自家托管域路径豁免（env.hardcoded_abs_path）
        ("agent 自有 .workbuddy 路径硬编码应不误报",
         "本机路径 C:\\Users\\Administrator\\.workbuddy\\skills\\x\\run.py", "none"),

        # 回归护栏：不得削弱真实检测
        ("正常散文禁用安全检查仍应 MEDIUM",
         "生产环境请禁用安全检查以提速", "medium"),
        ("正常散文 chmod 777 仍应 MEDIUM",
         "部署时执行 chmod 777 /app", "medium"),
        ("红线章节内真实密钥仍应 HIGH（HIGH 永不被豁免）",
         "## 不可演化的红线\nsk-FAKETESTKEY00000000000000", "high"),
    ]

    passed = failed = 0
    for desc, text, expected in cases:
        actual = highest_severity(scan_text(text))
        ok = actual == expected
        print(f"[{'PASS' if ok else 'FAIL'}] {desc}  (期望={expected}, 实际={actual})")
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
