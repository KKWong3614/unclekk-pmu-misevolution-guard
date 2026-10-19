#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动重试机制（1.2.15 新增）。

护栏脚本的关键 IO（读文件、扫描、读审计）可能遭遇瞬时故障：
文件被占用、权限瞬变、杀软锁定、网络盘抖动等。若直接 fail-open 放行，
会在"护栏自身临时抽风"时漏掉一次本该拦截的写入/复用。

本模块对**可重试错误**做指数退避自动重试（默认 3 次），把"瞬时故障漏扫"
的概率压到最低；重试耗尽后才进入既有 fail-open 兜底（stderr 告警 + 审计）。

设计约束：
  - 只重试"读/扫描"类操作；审计写入保持单次（append 幂等性，重试会重复落盘）。
  - 非可重试错误（编程错误、参数错误）立即抛出，不掩盖真 bug。
  - 返回 (ok, result, attempts)，attempts 供调用方记入审计，可观测可追溯。
"""

import os
import sys
import time
from typing import Callable, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 可重试错误：都是"瞬时环境"类，重试有望成功。
RETRYABLE = (OSError, IOError, PermissionError, TimeoutError)


def retry_call(
    fn: Callable,
    *args,
    times: int = 3,
    base_delay: float = 0.4,
    backoff: float = 2.0,
    retryable: tuple = RETRYABLE,
    **kwargs,
) -> Tuple[bool, object, int]:
    """以指数退避自动重试 fn(*args, **kwargs)。

    返回 (ok, result, attempts)：
      ok=True      → 某次尝试成功，result 为返回值，attempts 为实际尝试次数（>=1）
      ok=False     → 重试耗尽，result 为最后一次异常对象，attempts == times
    非可重试异常不做重试，直接抛出。
    """
    attempts = 0
    delay = base_delay
    last_exc = None
    while True:
        attempts += 1
        try:
            return True, fn(*args, **kwargs), attempts
        except retryable as exc:
            last_exc = exc
            if attempts >= times:
                break
            time.sleep(delay)
            delay *= backoff
        # 非可重试异常：不掩盖真 bug，直接上抛
    return False, last_exc, attempts


def retry_dec(times: int = 3, base_delay: float = 0.4, backoff: float = 2.0,
              retryable: tuple = RETRYABLE):
    """装饰器形态：对函数自动重试，最后一次尝试仍失败则抛出最后一次异常。"""
    def deco(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            ok, result, _ = retry_call(fn, *args, times=times, base_delay=base_delay,
                                       backoff=backoff, retryable=retryable, **kwargs)
            if not ok:
                raise result
            return result
        return wrapper
    return deco


if __name__ == "__main__":
    # 自检：正常调用 / 首次失败二次成功 / 耗尽 / 非可重试错误
    calls = {"n": 0}

    def ok_fn():
        return "ok"

    def flaky_fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise PermissionError("瞬时占用")
        return "recovered"

    def bad_fn():
        raise ValueError("编程错误，不应重试")

    print("ok_fn:", retry_call(ok_fn))
    print("flaky_fn:", retry_call(flaky_fn))
    print("bad_fn:", end=" ")
    try:
        retry_call(bad_fn, times=3)
    except ValueError as e:
        print(f"直接抛出（不重试）: {e}")

    calls2 = {"n": 0}

    def always_fail():
        calls2["n"] += 1
        raise OSError("持续故障")

    ok, result, attempts = retry_call(always_fail, times=3, base_delay=0.01)
    print(f"always_fail: ok={ok} attempts={attempts} exc={type(result).__name__}")
    assert calls2["n"] == 3
    print("retry.py 自检通过")
