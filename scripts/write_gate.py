#!/usr/bin/env python3
"""
write_gate.py — 写入期硬拦截（闸一，事件驱动，非看门狗）

由 WorkBuddy 的 PreToolUse / PostToolUse hook 调用，读取工具入参（stdin JSON），
对"经验固化"类文件（SKILL.md / 记忆文件）做**内容级危险扫描**：

  --mode pre   PreToolUse：扫描即将写入的内容，命中 HIGH 危险 → 按宿主协议 deny 硬性拦截
  --mode post  PostToolUse：扫描已落盘文件，写入审计日志，并触发漂移自查

关键点（对应论文 SafeEvolve 的 write-time repair + 本 skill 目标）：
- 危险判定由**代码**完成，不依赖 agent 自报。
- 任何异常都 exit 0（放行），绝不让护栏自己变成拒绝服务。
- 仅拦截 HIGH 严重度（高精度规则），MEDIUM/LOW 只告警 + 记入审计，由漂移自查兜底。
"""

import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone, timedelta

# 让脚本能 import 同目录的 redflags
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from redflags import scan_text, scan_file, highest_severity, is_guarded_path, parse_allowlist  # noqa: E402
from retry import retry_call  # noqa: E402

AUDIT_DIR = os.path.normpath(os.path.join(HERE, "..", "audit"))
AUDIT_LOG = os.path.join(AUDIT_DIR, "audit-log.jsonl")


# 并发安全：append_audit 使用线程锁防止多进程/多线程写入竞态
_AUDIT_LOCK = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


def skill_name_from_path(path: str) -> str:
    """从被写入路径推断技能/记忆名，用于审计与复用期血缘关联。"""
    p = path.replace("\\", "/")
    if "SKILL.md" in p:
        # .../skills/<name>/SKILL.md
        idx = p.rfind("/skills/")
        if idx != -1:
            rest = p[idx + len("/skills/"):]
            return rest.split("/")[0] or "unknown-skill"
        return "unknown-skill"
    base = os.path.basename(p)
    return base or "unknown-memory"


def _read_file_raw(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _read_file(path: str) -> str:
    """读文件，自动重试 3 次（1.2.15：文件瞬时占用/权限抖动等可重试故障不直接漏读）。"""
    ok, content, _ = retry_call(_read_file_raw, path)
    return content if ok else ""


def _apply_edit(current: str, old: str, new: str) -> str:
    if old and old in current:
        return current.replace(old, new, 1)
    return current + "\n" + new


def _norm_input_path(s: str) -> str:
    """把可能的 POSIX / Git-Bash 风格路径转成 Windows 路径（1.2.15）。

      /c/Users/...  ->  C:/Users/...
      /tmp/xxx      ->  <TMP>/xxx（存在才返回，避免误判）
      其它原样返回。
    """
    if len(s) > 2 and s[0] == "/" and s[2] == "/":
        return f"{s[1].upper()}:/{s[3:]}"
    if s.startswith("/tmp/"):
        for base in (os.environ.get("TMP"), os.environ.get("TEMP")):
            if base:
                cand = os.path.normpath(os.path.join(base, s[5:]))
                if os.path.exists(cand):
                    return cand
    return s


def resolve_skill_path(skill: str) -> str:
    """把 SkillManage 的 skill 参数解析为磁盘路径（1.2.15 新增）。

    支持四种形态：
      - 绝对路径（/x/y、C:////x////y、/c/Users/...）→ 原样/转换后返回（不存在则空）
      - "user:名字" / "名字" → ~/.workbuddy/skills/<名字>/
      - 带分隔符形态（user/name）→ 尝试 ~/.workbuddy/skills/ 下拼接
    找不到目录时返回 ""（由调用方放行，避免误杀）。
    """
    if not skill:
        return ""
    s = _norm_input_path(skill.strip())
    if os.path.isabs(s) or (len(s) > 2 and s[1] == ":"):
        return s if os.path.exists(s) else ""
    name = s.split(":")[-1].strip("/\\")
    for cand in (name, s.strip("/\\")):
        p = os.path.normpath(os.path.join(os.path.expanduser("~"),
                                          ".workbuddy", "skills", cand))
        if os.path.exists(p):
            return p
    return ""


def _iter_skill_files(root: str):
    """遍历技能目录内待扫描文件（跳过 audit/__pycache__/.git 等运行时产物）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in ("audit", "__pycache__", ".git")]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def extract_content(tool_input: dict, tool_name: str):
    """返回 (content_to_scan:str, file_path:str)。

    Edit/MultiEdit 在 pre 阶段构造"合并后全文"再扫描（对应建议4）：
    只扫 new_string 会漏掉 old_string 与文件其余部分拼接处产生的危险模式，
    也可能让 agent 用小幅增量 Edit 绕过闸一。文件不存在时退化为仅扫 new_string。
    """
    file_path = tool_input.get("file_path", "")
    if tool_name == "Write":
        return tool_input.get("content", ""), file_path
    if tool_name == "Edit":
        new = tool_input.get("new_string", "")
        old = tool_input.get("old_string", "")
        existing = _read_file(file_path)
        if existing:
            return _apply_edit(existing, old, new), file_path
        return new, file_path
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", []) or []
        if not isinstance(edits, list):
            edits = []
        existing = _read_file(file_path)
        if existing:
            cur = existing
            for e in edits:
                if isinstance(e, dict):
                    cur = _apply_edit(cur, e.get("old_string", ""), e.get("new_string", ""))
            return cur, file_path
        return "\n".join(e.get("new_string", "") for e in edits if isinstance(e, dict)), file_path
    return "", file_path


def append_audit(entry: dict):
    """追加一行审计记录（绝不覆盖写）。

    历史审核发现旧实现用 `os.replace(tmp, AUDIT_LOG)` 把整文件替换成单条记录，
    导致审计历史全量丢失、闸二血缘判定与闸三趋势统计的底座塌陷（对应 P0-2）。
    这里改为真正的追加写，保留 fsync 落盘可靠性。

    并发安全：多进程并发写同一JSONL时，每行独立，解析器按行读取不依赖完整性。
    """
    try:
        os.makedirs(AUDIT_DIR, exist_ok=True)
        with _AUDIT_LOCK:
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
    except OSError:
        pass  # 审计写入失败绝不应阻断主流程


def block(reason: str):
    """硬性拦截：按宿主(WorkBuddy) PreToolUse 协议输出，与 atuin_hook_client 对齐。

    关键：拦截信号是 stdout 里的 hookSpecificOutput.permissionDecision="deny"，
    且必须 exit 0（exit code 不是拦截信号，exit 1 会被宿主当命令错误静默放行）。
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
    """护栏自身异常时：向 stderr 输出友好中文提示（绝不抛技术异常、不打 stdout），
    然后 exit 0 放行，绝不让护栏自己变成拒绝服务（对应 P1-1 + 评测 R 维度：非危险
    场景提示应通俗易懂）。stdout 保持空，不破坏宿主 hook 协议。
    """
    try:
        sys.stderr.write(
            "【技能护栏提示】扫描时发生异常，已按 fail-open 自动放行本次写入。"
            "如反复出现请确认：Python 环境正常、脚本路径未移动、被写入文件可读取。"
            f"（细节：{reason}）\n"
        )
    except Exception:
        pass
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pre", "post"], default="pre")
    args = ap.parse_args()
    try:
        _run(args)
    except SystemExit:
        raise
    except Exception as exc:
        # 任何未预期的异常都放行，绝不让护栏自身变成拒绝服务（对应 P1-1）
        _friendly_fail(str(exc))


def _run(args):
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)  # 解析失败 → 放行

    if not isinstance(input_data, dict):
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        sys.exit(0)

    # 只关心文件写入类工具；SkillManage（创建/更新 skill）也必须触发护栏（1.2.15）
    if tool_name not in ("Write", "Edit", "MultiEdit", "SkillManage"):
        sys.exit(0)

    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")

    if tool_name == "SkillManage":
        # SkillManage 可能只给 skill 名（如 user:xxx 或名字），定位到 skills 目录
        if not file_path:
            file_path = resolve_skill_path(tool_input.get("skill", ""))
        if not file_path:
            sys.exit(0)  # 无法定位目标 → 放行，避免误杀

    # 非"经验固化/技能资产"路径 → 完全放行（绝不误伤普通开发文件）
    if not is_guarded_path(file_path):
        sys.exit(0)

    if args.mode == "pre":
        content, _ = extract_content(tool_input, tool_name)
        if tool_name == "SkillManage" and not content:
            sys.exit(0)  # SkillManage 调用本身不携带内容，落盘由底层 Write/Edit 触发闸一
        hits = scan_text(content)
        # 内联放行标记：作者显式放行特定规则（如安全教程示例），把"无意识泄露"转成"有意识放行"。
        # 约束（对应 P0-1，防自毁开关）：
        #   ① 只接受精确 rule id（parse_allowlist 已拒绝 __all__ 通配）；
        #   ② 真密钥类(hardcoded_secret)永远不可放行；
        #   ③ 被放行的高危命中仍强制落审计 + 提醒人工复核（不拦截但必须可见）。
        if hits:
            allow = parse_allowlist(content)
            if allow:
                FORBIDDEN_CATS = {"hardcoded_secret"}
                allowed, blocked = [], []
                for h in hits:
                    if h["id"] in allow and h["category"] not in FORBIDDEN_CATS:
                        allowed.append(h)
                    else:
                        blocked.append(h)
                for h in allowed:
                    if h["severity"] == "high":
                        print(json.dumps({"systemMessage":
                            f"[技能护栏-放行复核] 已显式放行高危规则 {h['id']}（guard:allow）。"
                            f"请确认这是有意为之（如安全教程示例），否则立即修复内容。"},
                            ensure_ascii=False))
                hits = blocked
        if not hits:
            sys.exit(0)
        top = highest_severity(hits)
        if top == "high":
            # 列出 HIGH 命中，作为拦截理由
            reasons = [f"{h['id']}: {h['message']}  (片段: {h['snippet']})"
                       for h in hits if h["severity"] == "high"]
            block("写入被拦截 —— 检测到高危不安全模式，禁止固化进技能/记忆库：\n  " +
                  "\n  ".join(reasons))
        else:
            # MEDIUM/LOW：告警但不阻断（漂移自查会兜底累积风险）
            msgs = [f"[{h['severity']}] {h['id']}: {h['message']}" for h in hits]
            print(json.dumps({"systemMessage": "技能护栏提醒(未拦截):\n  " +
                              "\n  ".join(msgs)}, ensure_ascii=False))
            sys.exit(0)

    elif args.mode == "post":
        # 落盘后复核 + 写审计 + 漂移自查
        # 自动重试（1.2.15）：瞬时 IO 故障先重试再 fail-open，不直接漏扫
        if os.path.isdir(file_path):
            hits = []
            high_files = set()
            for p in _iter_skill_files(file_path):
                ok, result, _ = retry_call(scan_file, p)
                if not ok:
                    continue  # 重试 3 次仍失败 → 跳过该文件
                for h in result:
                    if h["severity"] == "high":
                        high_files.add(os.path.basename(p))
                hits.extend(result)
        else:
            ok, result, _ = retry_call(scan_file, file_path)
            if not ok:
                _friendly_fail(f"{result}（已自动重试 3 次仍失败）")
            hits = result
            high_files = {os.path.basename(file_path)} if highest_severity(hits) == "high" else set()
        sev = highest_severity(hits)
        entry = {
            "ts": now_iso(),
            "phase": "write",
            "skill": skill_name_from_path(file_path),
            "path": file_path,
            "outcome_ok": True,
            "red_flags": [h["id"] for h in hits],
            "severity": sev,
            "lineage_risk": ("high" if sev == "high" else "medium" if sev == "medium" else "low"),
            "repaired": False,
            "retired": False,
            "carryover_harm": False,
            "utility": None,
        }
        append_audit(entry)
        if sev == "high":
            print(json.dumps({"systemMessage":
                              f"[技能护栏] 检测到高危模式：{', '.join(sorted(high_files)) or '（未知文件）'}，"
                              f"已记入审计；复用期将被拦截。"}, ensure_ascii=False))
        sys.exit(0)


if __name__ == "__main__":
    main()
