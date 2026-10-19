#!/usr/bin/env python3
"""编码变体覆盖测试（评测 E·内容完整度：特殊编码可能检测不到）。

覆盖三类绕过：零宽字符插入、全角标点变体、base64 编码隐藏密钥。
"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from redflags import scan_text, highest_severity  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name}")


# 1) 零宽字符插入绕过：s<ZWSP>k-...
zw = "s\u200bk-abcdef1234567890ghijklmnop"
h = scan_text(zw)
check("零宽字符插入的密钥被检出 HIGH", highest_severity(h) == "high"
       and any(x["id"] == "hardcoded.openai_key" for x in h))

# 2) 全角句号变体：security．enabled=false（．= U+FF0E）
fw = "settings: security．enabled=false"
h = scan_text(fw)
check("全角标点变体的关闭鉴权被检出 HIGH", highest_severity(h) == "high"
       and any(x["id"] == "bypass.disable_auth" for x in h))

# 3) base64 编码隐藏密钥
secret = "sk-FAKETESTKEY00000000000000"
tok = base64.b64encode(secret.encode()).decode()
h = scan_text("密钥藏在下面这串里：" + tok)
check("base64 隐藏密钥被检出 HIGH", highest_severity(h) == "high"
       and any(x["id"] == "hardcoded.base64_obfuscated" for x in h))

# 4) 良性 base64（非密钥）不应误报
benign = base64.b64encode(b"the quick brown fox jumps over").decode()
h = scan_text("附件指纹：" + benign)
check("良性 base64 不误报", highest_severity(h) == "none")

# 5) 归一化不影响正常检测（无编码变体时仍按原文判定）
h = scan_text("本技能调用 API：sk-FAKETESTKEY00000000000000")
check("普通密钥仍正常检出", highest_severity(h) == "high")

# 6) 代码块内的 base64 密钥应被 prose 掩码跳过（不误报）
h = scan_text("```\n" + tok + "\n```")
check("代码块内 base64 密钥被掩码跳过", highest_severity(h) == "none")


print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
