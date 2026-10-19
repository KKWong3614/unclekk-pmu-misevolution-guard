#!/usr/bin/env python3
"""unclekk-pmu-misevolution-guard 安装后自检。

一次性验证（专治历次审计发现的"静默失效"类问题）：
  ① hook 命令为跨平台 `python3 -c` 形式，且指向正确脚本
  ② 四个脚本均可被导入
  ③ 对已知 HIGH 样本确实输出宿主 deny 协议（permissionDecision=deny, exit 0）
  ④ 审计日志可追加且行数递增
  ⑤ guard:allow:all 不再能解除闸一（自毁开关已堵）
  ⑥ 正常内容不被拦截

用法:  python3 scripts/selftest.py
退出码 0 = 全部通过；1 = 有失败（建议人工排查后再上线）。
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable  # 运行自检的解释器即护栏依赖的 python3


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f"  -- {detail}" if detail else ""))
    return ok


def run_write_gate(mode, content, path="/x/skills/selfcheck/SKILL.md"):
    inp = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": path, "content": content}})
    return subprocess.run([PY, os.path.join(HERE, "write_gate.py"), "--mode", mode],
                          input=inp, capture_output=True, text=True, timeout=20)


def main():
    passed = failed = 0

    def rec(ok):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    # ① hook 命令解析（跨平台 python3 -c 形式）
    try:
        hooks = json.load(open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8"))
        cmds = []
        for _ev, arr in hooks.get("hooks", {}).items():
            for grp in arr:
                for h in grp.get("hooks", []):
                    cmds.append(h.get("command", ""))
        hook_ok = len(cmds) >= 4 and all(
            ("python3 -c" in c) and ("runpy.run_path" in c) for c in cmds)
        rec(check("hook 命令为跨平台 python3 -c 形式", hook_ok, f"{len(cmds)} 条"))
    except Exception as e:
        rec(check("hook 命令可解析", False, str(e)))

    # ② 脚本可导入
    sys.path.insert(0, HERE)
    try:
        import redflags  # noqa: F401
        import write_gate  # noqa: F401
        import reuse_gate  # noqa: F401
        import drift_report  # noqa: F401
        rec(check("脚本均可导入", True))
    except Exception as e:
        rec(check("脚本均可导入", False, str(e)))

    # ③ 已知 HIGH 样本 → deny 协议
    r = run_write_gate("pre", "token sk-FAKETESTKEY00000000000000 secret")
    try:
        out = json.loads(r.stdout)
        deny = out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        rec(check("已知 HIGH 样本输出 deny 协议", deny and r.returncode == 0, f"rc={r.returncode}"))
    except Exception as e:
        rec(check("已知 HIGH 样本输出 deny 协议", False, str(e)))

    # ⑤ guard:allow:all 不再解除闸一
    r2 = run_write_gate("pre", "token sk-FAKETESTKEY00000000000000 # guard:allow:all")
    try:
        out2 = json.loads(r2.stdout)
        still = out2.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        rec(check("guard:allow:all 不再解除闸一", still))
    except Exception as e:
        rec(check("guard:allow:all 不再解除闸一", False, str(e)))

    # ⑥ 正常内容放行
    r3 = run_write_gate("pre", "本技能用于整理每日笔记")
    ok3 = (r3.returncode == 0) and ("permissionDecision" not in r3.stdout)
    rec(check("正常内容不被拦截", ok3))

    # ④ 审计日志追加递增（用无害内容，避免污染日志为高危标记）
    log = os.path.join(ROOT, "audit", "audit-log.jsonl")
    before = sum(1 for line in open(log, encoding="utf-8") if line.strip()) if os.path.exists(log) else 0
    run_write_gate("post", "self-check benign content")
    after = sum(1 for line in open(log, encoding="utf-8") if line.strip()) if os.path.exists(log) else 0
    rec(check("审计日志追加写(行数递增)", after > before, f"{before} -> {after}"))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
