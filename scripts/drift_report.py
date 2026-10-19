#!/usr/bin/env python3
"""
drift_report.py — 漂移自查（闸三，事件驱动，非看门狗）

读取审计日志 + **直接扫描技能库目录下的 SKILL.md 正文**，计算"进化期安全"指标，
在危险累积成大事之前给出告警。

与旧版的关键区别（也是本 skill 从"声明式"变"硬代码"的核心）：
  - 旧版只信 JSONL 里 agent 自报的 red_flags 字段 → 可造假/可漏报。
  - 本版**直接对 SKILL.md 正文跑 redflags.scan_file 做客观内容扫描**，
    危险判定不再依赖 agent 自觉。

用法:
    python drift_report.py [审计日志.jsonl | 扫描目录] [--scan DIR ...] [--unsafe-threshold 0.20]

退出码:
    0  正常（无告警）
    2  触发告警（技能库存在高危固化 / 出现跨任务 carryover 危害）

触发方式（非看门狗）:
    - PostToolUse hook 在每次技能/记忆写入后调用（增量自查）
    - SessionStart hook 在会话开始时调用（每日健康快照）
    - 也可手动运行
"""

import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from redflags import scan_file, highest_severity, parse_allowlist  # noqa: E402
from retry import retry_call  # noqa: E402

# 审计日志：自定位（随脚本位置走，跨机器/跨 agent 可移植）
DEFAULT_AUDIT = os.path.normpath(os.path.join(HERE, "..", "audit", "audit-log.jsonl"))
# 技能库扫描目录：用用户主目录相对路径（expanduser），不写死具体用户名/盘符，
# 换机器/换账号/别的 agent 加载都不会因路径失效而阻塞。
USER_HOME = os.path.expanduser("~")
# 默认扫描标准技能库位置（用户主目录相对，可移植）
SCAN_DIRS = [
    os.path.join(USER_HOME, ".workbuddy", "skills"),
    os.path.join(USER_HOME, ".workbuddy", "skills-marketplace", "skills"),
    os.path.join(USER_HOME, ".hermes", "skills"),
]


def _load_events_raw(path):
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def load_events(path):
    """读审计日志，自动重试 3 次（1.2.15）：瞬时 IO 故障不直接丢审计。"""
    if not path or not os.path.exists(path):
        return []
    ok, events, _ = retry_call(_load_events_raw, path)
    return events if ok else []


def scan_library(dirs):
    """直接扫描目录下所有 SKILL.md，返回 (total, dangerous_high, details)。

    注意：这里只把 HIGH 严重度（无歧义真危险：真实密钥、关闭鉴权/TLS、
    关键路径递归删除、格式化磁盘、eval 外部输入）计入 dangerous，
    因为 MEDIUM/LOW（环境绝对路径、安装命令、'默认'措辞等）在大量合法技能里
    本就常见，若一并计为危险会让漂移自查失去信号意义。
    """
    total = 0
    dangerous = 0
    details = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if fn.upper() != "SKILL.MD":
                    continue
                fp = os.path.join(root, fn)
                ok, hits, _ = retry_call(scan_file, fp)
                if not ok:
                    continue  # 重试 3 次仍失败 → 跳过该文件
                # 复用 write_gate 的内联放行机制（guard:allow:<rule_id>）：
                # 文档在"列举危险模式/禁止清单"语境下写的高危词应被放行，避免误报。
                try:
                    with open(fp, encoding="utf-8") as _f:
                        _allow = parse_allowlist(_f.read())
                    if _allow:
                        hits = [h for h in hits if h["id"] not in _allow]
                except Exception:
                    pass
                total += 1
                top = highest_severity(hits)
                if top == "high":
                    dangerous += 1
                    details.append({
                        "path": fp,
                        "severity": top,
                        "flags": [h["id"] for h in hits if h["severity"] == "high"],
                    })
    return total, dangerous, details


def pct(n, d):
    return 0.0 if d == 0 else 100.0 * n / d


def adaptive_threshold(total: int) -> float:
    """随技能库规模自适应不安全率阈值：小库更敏感（宁可多报），大库放宽（避免误报淹没）。

    - 小型库(<=50 篇)：10% —— 库小，单点危险占比高，应更灵敏
    - 中型库(51-300)：20% —— 默认平衡点
    - 大型库(>300)：30% —— 库大，个别历史遗留会被稀释，放宽避免告警失效
    """
    if total <= 50:
        return 0.10
    if total <= 300:
        return 0.20
    return 0.30


def main():
    ap = argparse.ArgumentParser(description="Skill Misevolution 漂移自查（内容扫描版）")
    ap.add_argument("path", nargs="?", default=None,
                    help="审计日志 .jsonl 路径，或要扫描的目录")
    ap.add_argument("--scan", action="append", default=None,
                    help="额外要扫描的技能/记忆目录（可多次）")
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--unsafe-window", type=int, default=50,
                    help="不安全创作率统计的『近期窗口』写入数（默认 50）；"
                         "仅看近期趋势，避免修复前历史条目把率值永远顶在高位、"
                         "导致误报告警无法自愈（内容扫描 HIGH 率仍为全量，安全不丢）")
    ap.add_argument("--unsafe-threshold", type=float, default=None,
                    help="不安全率阈值(0-1)；不传则按库规模自适应")
    ap.add_argument("--json", action="store_true",
                    help="以 JSON 输出指标（便于结构化集成），仍按是否告警返回 0/2")
    ap.add_argument("--deny-on-alert", action="store_true",
                    help="可选硬拦截模式：默认闸三为『报告式』(超阈值仅告警、不拦截写入)；"
                         "开启本开关后，一旦触发告警即输出 permissionDecision=deny 硬拦截信号。"
                         "仅建议对安全纪律要求极高的团队显式开启，不改变默认 fail-open 行为。")
    args = ap.parse_args()

    # 解析 path
    audit_path = DEFAULT_AUDIT
    scan_dirs = []
    if args.path:
        if args.path.endswith(".jsonl") or os.path.isfile(args.path):
            audit_path = args.path
        else:
            scan_dirs.append(args.path)
    # 默认扫描标准技能库位置（用户主目录相对，可移植）
    scan_dirs.extend(SCAN_DIRS)
    mem_dir = os.path.join(USER_HOME, ".workbuddy", "memory")
    if os.path.isdir(mem_dir):
        scan_dirs.append(mem_dir)
    if args.scan:
        scan_dirs.extend(args.scan)

    # 去重：避免 --scan / path 与默认目录重复计数（对应 P2-3），
    # 否则 ~/.workbuddy/skills 等会被计两次、分母虚高、不安全率被系统性低估。
    seen_dirs = set()
    deduped = []
    for d in scan_dirs:
        nd = os.path.normpath(d)
        if nd not in seen_dirs:
            seen_dirs.add(nd)
            deduped.append(d)
    scan_dirs = deduped

    events = load_events(audit_path)
    total_sk, dangerous_sk, sk_details = scan_library(scan_dirs)
    # 非危险场景友好诊断（评测 R 维度）：未找到任何 SKILL.md 时明确提示，
    # 避免静默输出 0 让用户误以为"一切正常"。
    if total_sk == 0:
        print("提示：本次未在扫描目录中找到任何 SKILL.md。")
        print("      请确认技能目录路径是否正确（默认扫 ~/.workbuddy/skills 等标准位置），")
        print("      或用 --scan DIR 追加要扫描的目录。")
        print(f"      本次已扫描目录：{[os.path.normpath(d) for d in scan_dirs]}")
    # 阈值：未显式指定时按库规模自适应（小库更敏感，大库放宽避免误报淹没）
    if args.unsafe_threshold is not None:
        threshold = args.unsafe_threshold
        thr_src = "显式指定"
    else:
        threshold = adaptive_threshold(total_sk)
        thr_src = f"自适应(库规模 {total_sk} 篇)"

    writes = [e for e in events if e.get("phase") == "write"]
    reuses = [e for e in events if e.get("phase") == "reuse"]
    # ③ 误报专项（2026-09-24）：审计日志"不安全创作率"分子对齐"内容扫描"口径——
    # 仅计 medium+/high 严重度，剔除纯 LOW（pref.temp_to_default 等 advisory）噪声。
    # 否则文档语境关键词（"默认/绕过/路径"）会把绝大多数正常技能写作计为"不安全"，
    # 触发 50%+ 虚报告警，训练用户忽略护栏、真危险被淹没。
    unsafe_writes = [e for e in writes if e.get("severity") in ("medium", "high")]
    advisory_writes = [e for e in writes
                       if e.get("red_flags") and e.get("severity") == "low"]
    # 近期窗口：漂移看"近期趋势"而非全量历史。修复前写入的历史条目（旧分类器记的
    # medium）不应永远把率值顶高；近期窗口随干净写入累积而自愈，误报告警自然消退。
    recent_writes = writes[-args.unsafe_window:] if args.unsafe_window > 0 else writes
    recent_unsafe = [e for e in recent_writes if e.get("severity") in ("medium", "high")]
    carryover = [e for e in events if e.get("carryover_harm")]
    retired = [e for e in events if e.get("retired")]
    window = events[-args.window:]
    win_carryover = [e for e in window if e.get("carryover_harm")]

    risk_counter = Counter(e.get("lineage_risk", "n/a") for e in events)

    alerts = []
    rate = pct(dangerous_sk, total_sk) / 100.0 if total_sk else 0.0
    over_rate = total_sk and rate > threshold
    # 大库加绝对数门槛：>300 篇时需同时 dangerous_sk>=10，避免少数历史遗留被稀释
    # 导致告警失效（对应 P2-4）。
    abs_floor_ok = (total_sk <= 300) or (dangerous_sk >= 10)
    if over_rate and abs_floor_ok:
        alerts.append(
            f"[ALERT] 技能库内容扫描不安全率 {pct(dangerous_sk, total_sk):.1f}% "
            f"超过阈值 {threshold*100:.0f}% —— 危险做法已固化在库中")
    # 不安全创作率：仅看近期窗口（medium+/high），避免历史虚报无法自愈
    if recent_writes and pct(len(recent_unsafe), len(recent_writes)) / 100.0 > threshold:
        alerts.append(
            f"[ALERT] 近期(unsafe-window={len(recent_writes)})不安全创作率(medium+/high) "
            f"{pct(len(recent_unsafe), len(recent_writes)):.1f}% 超过阈值 {threshold*100:.0f}%")
    if win_carryover:
        alerts.append(
            f"[ALERT] 近期窗口出现 {len(win_carryover)} 次 carryover 危害 —— "
            f"已有不安全技能在跨任务造成实际伤害，立即停用并审计技能库")
    if carryover:
        alerts.append(
            f"[ALERT] 历史累计 {len(carryover)} 次 carryover 危害，建议回查这些技能并确认已退役")

    if args.json:
        out = {
            "status": "alert" if alerts else "ok",
            "unsafe_rate": round(rate, 4),
            "threshold": threshold,
            "library_size": total_sk,
            "dangerous_high": dangerous_sk,
            "writes": len(writes),
            "reuses": len(reuses),
            "unsafe_writes": len(unsafe_writes),
            "carryover": len(carryover),
            "retired": len(retired),
            "lineage_risk_dist": dict(risk_counter),
            "alerts": alerts,
        }
        print(json.dumps(out, ensure_ascii=False))
        # 可选硬拦截：开启 --deny-on-alert 且存在告警时，输出 deny 协议（exit 0，
        # 与其他闸一致——拦截信号在 stdout，不在 exit code）。
        if alerts and args.deny_on_alert:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "；".join(alerts),
                }
            }, ensure_ascii=False))
            return 0
        return 2 if alerts else 0

    print("=" * 60)
    print("  Skill Misevolution 漂移自查报告（内容扫描版）")
    print("=" * 60)
    print(f"  [审计日志] {audit_path}")
    print(f"  写入期 / 复用期事件 : {len(writes)} / {len(reuses)}")
    print(f"  不安全创作(medium+/high·全量) : {len(unsafe_writes)}/{len(writes)}"
          f"  ({pct(len(unsafe_writes), len(writes)):.1f}%)  -- 历史，仅供参考")
    print(f"  不安全创作(medium+/high·近{len(recent_writes)}笔) : {len(recent_unsafe)}/{len(recent_writes)}"
          f"  ({pct(len(recent_unsafe), len(recent_writes)):.1f}%)  -- 告警用此项")
    print(f"  仅 advisory(LOW) 事件    : {len(advisory_writes)}/{len(writes)}"
          f"  ({pct(len(advisory_writes), len(writes)):.1f}%)  -- 不计入告警")
    print(f"  累计 carryover 危害  : {len(carryover)}")
    print(f"  已退役技能事件       : {len(retired)}")
    print(f"  血缘风险分布         : {dict(risk_counter)}")
    print("-" * 60)
    print(f"  不安全率阈值         : {threshold*100:.0f}%  ({thr_src})")
    print(f"  [技能库内容扫描] 扫描目录数: {len(scan_dirs)}")
    print(f"  扫描 SKILL.md 总数   : {total_sk}")
    print(f"  含高危模式(HIGH)     : {dangerous_sk}/{total_sk}"
          f"  ({pct(dangerous_sk, total_sk):.1f}%)")
    for d in sk_details:
        print(f"    - [{d['severity'].upper()}] {d['path']}")
        print(f"        flags: {', '.join(d['flags'])}")
    print("=" * 60)

    if alerts:
        # 额外输出 systemMessage，使闸三在宿主侧可见（exit code 被 || true 吞掉，
        # 但 systemMessage 会被宿主呈现，对应 P1-4）。
        print(json.dumps({"systemMessage":
                          "技能护栏漂移自查告警：\n  " + "\n  ".join(alerts)},
                         ensure_ascii=False))
        print()
        print("!!! 告警 !!!")
        for a in alerts:
            print("  " + a)
        print("  行动建议: 立即停止进化 -> 逐条复核被标记技能 -> 局部修复或退役")
        print("=" * 60)
        # 可选硬拦截：开启 --deny-on-alert 时，告警即输出 deny 协议而非仅报告。
        if args.deny_on_alert:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "；".join(alerts),
                }
            }, ensure_ascii=False))
            return 0
        return 2

    print("  状态: 未触告警。继续保持每次进化都受护栏约束的纪律。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
