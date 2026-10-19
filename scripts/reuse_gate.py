#!/usr/bin/env python3
"""
reuse_gate.py — 复用期血缘拦截（闸二，事件驱动，非看门狗）

由 WorkBuddy 的 PreToolUse hook 在**技能即将被加载/复用**时调用。
读取审计日志，若该技能曾被标记为高危或已退役（无记录则直扫该技能目录全文：SKILL.md + scripts/*.py + references/*.md）→ 按宿主协议 deny 硬性阻止本次复用。

这是"不自知"的解药之一：即使某次危险技能已被写入（闸一漏网或历史遗留），
在它**真正被调用去干新任务之前**再次拦截，并提示 agent 先做归因/退役。

设计（对应论文 SafeEvolve 的 retrieval-time lineage 退役）：
- 危险判定依赖**审计日志中的客观记录**（由 write_gate 写入），不是 agent 当场自报。
- 任何异常 → exit 0 放行，护栏自身绝不造成拒绝服务。
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from redflags import scan_file, highest_severity  # noqa: E402
from retry import retry_call  # noqa: E402

AUDIT_LOG = os.path.normpath(os.path.join(HERE, "..", "audit", "audit-log.jsonl"))


def find_skill_dir(skill: str):
    """定位某技能的根目录（含 SKILL.md 的目录），用于无审计记录时的正文+脚本直扫兜底。

    优先查用户级/市场级技能目录（精确、快）；找不到再在 plugins 树里做一次有界查找。
    仅在技能加载（复用期）触发，成本可控。
    """
    home = os.path.expanduser("~")
    direct = [
        os.path.join(home, ".workbuddy", "skills", skill),
        os.path.join(home, ".workbuddy", "skills-marketplace", "skills", skill),
        os.path.join(home, ".hermes", "skills", skill),
    ]
    for c in direct:
        if os.path.isfile(os.path.join(c, "SKILL.md")):
            return c
    pb = os.path.join(home, ".workbuddy", "plugins")
    if os.path.isdir(pb):
        for root, _d, files in os.walk(pb):
            if os.path.basename(root) == skill and "SKILL.md" in files:
                return root
    return None


def collect_scan_targets(skill_dir: str):
    """收集技能目录下需扫描的文件：SKILL.md + scripts/references/hooks/bin 全部代码与文档。

    仅覆盖正文与 bundled 代码/文档，不含无关资源（图片/二进制），扫描成本可控。
    覆盖 hooks/ 与 bin/（含嵌套子目录）—— hooks/hooks.json 恰是"生命周期投毒"的高价值
    落点，必须纳入扫描（对应建议3）。
    """
    targets = []
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if os.path.isfile(skill_md):
        targets.append(skill_md)
    for sub in ("scripts", "references", "hooks", "bin"):
        d = os.path.join(skill_dir, sub)
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if fn.endswith((".py", ".md", ".json", ".sh")):
                    fp = os.path.join(root, fn)
                    if os.path.isfile(fp):
                        targets.append(fp)
    return targets


def get_skill_name(input_data: dict) -> str:
    tool_input = input_data.get("tool_input", {}) or {}
    for key in ("skill", "skill_name", "name", "skillId"):
        v = tool_input.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # 有的实现把名称放在 input_data 顶层
    for key in ("skill", "skill_name", "name"):
        v = input_data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _load_audit_raw():
    out = []
    with open(AUDIT_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load_audit():
    """读审计日志，自动重试 3 次（1.2.15）：瞬时 IO 故障不直接丢审计。"""
    if not os.path.exists(AUDIT_LOG):
        return []
    ok, out, _ = retry_call(_load_audit_raw)
    return out if ok else []


def latest_for_skill(events, skill: str):
    """取该技能最新一条记录（按 ts 升序取最后一条，对应 P2-5）。"""
    cands = [e for e in events if e.get("skill") == skill]
    if not cands:
        return None
    cands.sort(key=lambda e: e.get("ts", ""))
    return cands[-1]


def block(reason: str):
    """按宿主(WorkBuddy) PreToolUse 协议输出 deny，exit 0。

    与 write_gate 保持一致：拦截信号是 stdout 的
    hookSpecificOutput.permissionDecision="deny"，exit code 不是拦截信号。
    """
    out = {
        "continue": False,
        "stopReason": reason,
        "systemMessage": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


def _friendly_fail(reason: str):
    """护栏自身异常时：友好中文提示走 stderr（不抛技术异常、不动 stdout），
    然后 exit 0 放行（对应 P1-1 + 评测 R 维度：非危险场景提示应通俗易懂）。
    """
    try:
        sys.stderr.write(
            "【技能护栏提示】复用期扫描时发生异常，已按 fail-open 自动放行本次复用。"
            "如反复出现请确认：Python 环境正常、审计日志可读取、技能目录未移动。"
            f"（细节：{reason}）\n"
        )
    except Exception:
        pass
    sys.exit(0)


def main():
    try:
        _run()
    except SystemExit:
        raise
    except Exception as exc:
        # 任何未预期异常都放行，护栏自身绝不造成拒绝服务（对应 P1-1）
        _friendly_fail(str(exc))


def _run():
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    tool_name = (input_data.get("tool_name") or "").lower()
    # 只拦截技能加载类工具
    if tool_name not in ("skill", "skills"):
        sys.exit(0)

    skill = get_skill_name(input_data)
    if not skill:
        sys.exit(0)  # 拿不到名字就放行，避免误杀

    events = load_audit()
    rec = latest_for_skill(events, skill)
    if not rec:
        # 无审计记录：兜底直扫该技能目录全文（SKILL.md + scripts/*.py + references/*.md），
        # 关掉"遗留/全新危险技能"绕过复用闸的口子。任一文件命中 HIGH 即拦。
        sdir = find_skill_dir(skill)
        if sdir:
            high_flags = []
            for p in collect_scan_targets(sdir):
                ok, hits, _ = retry_call(scan_file, p)
                if not ok:
                    continue  # 重试 3 次仍失败 → 跳过该文件，不误杀整个技能
                if highest_severity(hits) == "high":
                    high_flags.extend(h["id"] for h in hits if h["severity"] == "high")
            if high_flags:
                block(f"复用被拦截 —— 技能「{skill}」虽无审计记录，但其正文/脚本检出高危模式 "
                      f"{sorted(set(high_flags))}。请先修复或退役后再用。")
        sys.exit(0)  # 无记录且全文无高危 → 放行

    if rec.get("retired"):
        block(f"复用被拦截 —— 技能「{skill}」已在审计中被标记为退役(retired)，"
              f"存在跨任务危害记录，禁止复用。请先走归因/修复流程。")
    risk = rec.get("lineage_risk", "low")
    if risk in ("high", "critical"):
        block(f"复用被拦截 —— 技能「{skill}」血缘风险={risk}，"
              f"曾检出高危模式 {rec.get('red_flags')}。请先修复或退役后再用。")

    sys.exit(0)


if __name__ == "__main__":
    main()
