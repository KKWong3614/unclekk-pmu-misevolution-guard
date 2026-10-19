#!/usr/bin/env python3
"""扫描边界测试（评测 A·能力边界：大文件/二进制不误读、不漏报）。

覆盖：超大文件截断扫描（首尾仍检出）、二进制文件跳过（不误读乱码）、
return_meta 边界决策可观测。
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from redflags import scan_file, scan_text, highest_severity  # noqa: E402

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


def tmpfile(data: bytes) -> str:
    fd, p = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return p


# 1) 超过 1 万行的文件：头部密钥仍被检出（首尾扫描兜底不漏报）
secret = "sk-FAKETESTKEY00000000000000"
big = (secret + "\n") + ("# 填充行\n" * 12000)
p = tmpfile(big.encode())
hits, meta = scan_file(p, return_meta=True)
os.unlink(p)
check("超万行文件标记 too_large", meta.get("reason") == "too_large")
check("超万行文件头部密钥仍检出 HIGH",
      highest_severity(hits) == "high" and any(x["id"] == "hardcoded.openai_key" for x in hits))

# 2) 超过 2MB 字节的文件：尾部高危仍检出（文件尾是脚本/配置常见危险落点）
tail_secret = "AKIAFAKETESTKEYEXAMPLE00"  # AWS key, 20 位
huge = ("# 填充\n" * 150000) + ("key = " + tail_secret + "\n")
p = tmpfile(huge.encode())
hits, meta = scan_file(p, return_meta=True)
os.unlink(p)
check("超 2MB 文件标记 too_large", meta.get("reason") == "too_large")
check("超 2MB 文件尾部密钥仍检出 HIGH",
      highest_severity(hits) == "high" and any(x["id"] == "hardcoded.aws_key" for x in hits))

# 3) 二进制文件（正文含 NUL）：跳过全文，不误读乱码
p = tmpfile(b"\x00\x01\x02\xff\xfe sk-FAKETESTKEY00000000000000")
hits, meta = scan_file(p, return_meta=True)
os.unlink(p)
check("二进制文件标记 binary", meta.get("reason") == "binary")
check("二进制文件不产出命中", hits == [])

# 4) 正常小文件：不截断，meta.reason 不设置
p = tmpfile("正常内容\n".encode())
hits, meta = scan_file(p, return_meta=True)
os.unlink(p)
check("正常文件不截断", meta.get("truncated") is False and "reason" not in meta)
check("正常文件扫描正常", hits == [])

# 5) 兼容性：单参调用返回 hits（既有调用方 write_gate/reuse_gate/drift_report 不受影响）
p = tmpfile((secret + "\n").encode())
hits = scan_file(p)
os.unlink(p)
check("单参 scan_file 返回列表", isinstance(hits, list) and highest_severity(hits) == "high")

# 6) 截断扫描不改变行号语义（prose 掩码仍有效）
h = scan_text("```\n" + secret + "\n```")
check("代码块内密钥仍被 prose 掩码跳过", highest_severity(h) == "none")

print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
