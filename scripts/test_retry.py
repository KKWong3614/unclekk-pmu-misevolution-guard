#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动重试机制测试（1.2.15 新增）。

覆盖：正常调用 / 首次失败二次成功 / 重试耗尽返回失败与 attempts /
非可重试错误立即抛出不掩盖 / 装饰器形态 / retry_call 用于真实 IO（读被锁文件→恢复）。
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from retry import retry_call, retry_dec  # noqa: E402

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


# 1) 正常调用：一次成功，attempts=1
ok, result, attempts = retry_call(lambda: "fine")
check("正常调用一次成功", ok and result == "fine" and attempts == 1)

# 2) 首次失败第二次成功：attempts=2 且返回值正确
calls = {"n": 0}

def flaky():
    calls["n"] += 1
    if calls["n"] < 2:
        raise PermissionError("瞬时占用")
    return "recovered"

ok, result, attempts = retry_call(flaky, times=3, base_delay=0.01)
check("首次失败二次成功", ok and result == "recovered" and attempts == 2 and calls["n"] == 2)

# 3) 重试耗尽：ok=False，attempts==times，result 为最后一次异常
calls2 = {"n": 0}

def always_fail():
    calls2["n"] += 1
    raise OSError("持续故障")

ok, result, attempts = retry_call(always_fail, times=3, base_delay=0.01)
check("重试耗尽返回失败", (not ok) and attempts == 3 and isinstance(result, OSError) and calls2["n"] == 3)

# 4) 非可重试错误：立即抛出，不重试（不掩盖真 bug）
calls3 = {"n": 0}

def bad():
    calls3["n"] += 1
    raise ValueError("编程错误")

try:
    retry_call(bad, times=3)
    check("非可重试错误抛出", False)
except ValueError:
    check("非可重试错误抛出", calls3["n"] == 1)

# 5) 装饰器形态：对函数自动重试
calls4 = {"n": 0}

@retry_dec(times=3, base_delay=0.01)
def deco_fn():
    calls4["n"] += 1
    if calls4["n"] < 3:
        raise TimeoutError("瞬超时")
    return "deco-ok"

try:
    r = deco_fn()
    check("装饰器形态重试成功", r == "deco-ok" and calls4["n"] == 3)
except TimeoutError:
    check("装饰器形态重试成功", False)

# 6) 真实 IO：文件先被锁（模拟占用）后可读——retry 后成功读到内容
fd, p = tempfile.mkstemp(suffix=".md")
os.write(fd, b"# hello\nsk-FAKETESTKEY00000000000000\n")
os.close(fd)
calls5 = {"n": 0}

def locked_read(path):
    calls5["n"] += 1
    if calls5["n"] == 1:
        raise PermissionError("模拟文件被占用")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

ok, content, attempts = retry_call(locked_read, p, times=3, base_delay=0.01)
os.unlink(p)
check("真实 IO 重试后成功读取", ok and "FAKETEST" in content and attempts == 2)

# 7) 真实 IO：持续读失败 → 返回失败（不抛异常，由调用方 fail-open）
fd, p2 = tempfile.mkstemp(suffix=".md")
os.close(fd)
calls6 = {"n": 0}

def always_locked(path):
    calls6["n"] += 1
    raise OSError("持续占用")

ok, result, attempts = retry_call(always_locked, p2, times=3, base_delay=0.01)
os.unlink(p2)
check("持续 IO 失败返回失败", (not ok) and attempts == 3)

print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
