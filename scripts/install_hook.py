#!/usr/bin/env python3
"""
install_hook.py — 一键把三道闸接入 WorkBuddy hook（开箱即用）

解决评测 E·开箱即用度：「配置 hook 需要一定技术基础，普通人可能需要帮助才能完成初始设置」。

做了什么：
  - 自动读取（或创建）`~/.workbuddy/settings.json`
  - 备份原文件（`.bak-<时间戳>`）
  - 把三道闸合并进顶层 `hooks` 块（PreToolUse 写入/复用闸、PostToolUse 审计、SessionStart 漂移）
  - 每条命令自动加 `|| true`（护栏自身崩了按 fail-open 放行，绝不卡死你的正常写入）
  - 幂等：已存在的命令不会重复添加
  - 不改写你已有的其它 hook（只往对应 matcher 里追加）

用法：
  python scripts/install_hook.py                  # 用当前 Python + 自动定位技能目录
  python scripts/install_hook.py --python /绝对路径/python.exe --dry-run
  python scripts/install_hook.py --settings /别的/settings.json

完成后**重启 WorkBuddy** 让配置重新加载。
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)  # scripts/.. 即技能根目录


def build_gates(skill_dir, python):
    """返回 [(event, matcher, command), ...]，命令均带 `|| true` 的 fail-open 尾巴。"""
    def cmd(script_name, *args):
        script = os.path.join(SKILL_DIR, "scripts", script_name)
        return f'"{python}" "{script}" {" ".join(args)} || true'

    wg = os.path.join(SKILL_DIR, "scripts", "write_gate.py")
    rg = os.path.join(SKILL_DIR, "scripts", "reuse_gate.py")
    dr = os.path.join(SKILL_DIR, "scripts", "drift_report.py")
    return [
        ("PreToolUse", "Write|Edit|MultiEdit|SkillManage",
         f'"{python}" "{wg}" --mode pre || true'),
        ("PreToolUse", "Skill|Skills",
         f'"{python}" "{rg}" || true'),
        ("PostToolUse", "Write|Edit|MultiEdit|SkillManage",
         f'"{python}" "{wg}" --mode post || true'),
        ("SessionStart", "startup|resume|clear|compact",
         f'"{python}" "{dr}" || true'),
    ]


def merge_hooks(settings, gates):
    """把三道闸合并进 settings["hooks"]，保留已有 hook，幂等。返回新增条数。"""
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks
    added = 0
    for event, matcher, command in gates:
        lst = hooks.setdefault(event, [])
        if not isinstance(lst, list):
            lst = []
            hooks[event] = lst
        entry = next((e for e in lst if isinstance(e, dict) and e.get("matcher") == matcher), None)
        if entry is None:
            entry = {"matcher": matcher, "hooks": []}
            lst.append(entry)
        hooks_list = entry.setdefault("hooks", [])
        if not any(isinstance(h, dict) and h.get("command") == command for h in hooks_list):
            hooks_list.append({"command": command})
            added += 1
    return added


def main():
    ap = argparse.ArgumentParser(description="一键接入 WorkBuddy 三道闸 hook")
    ap.add_argument("--settings", default=os.path.join(os.path.expanduser("~"), ".workbuddy", "settings.json"))
    ap.add_argument("--python", default=sys.executable,
                    help="Python 解释器绝对路径（默认用运行本脚本的解释器）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要写入的内容，不落盘")
    args = ap.parse_args()

    settings_path = os.path.abspath(args.settings)
    python = os.path.abspath(args.python)
    gates = build_gates(SKILL_DIR, python)

    # 读取或初始化 settings
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[PMU-30] settings.json 解析失败：{e}\n请先修复该文件或换 --settings 指定正确路径。")
                return 2
    else:
        settings = {}
        print(f"未找到 settings.json，将新建：{settings_path}")

    before = json.dumps(settings, sort_keys=True)
    added = merge_hooks(settings, gates)
    after = json.dumps(settings, sort_keys=True)

    if args.dry_run:
        print("=== dry-run：将要写入的 hooks 块 ===")
        print(json.dumps(settings.get("hooks", {}), ensure_ascii=False, indent=2))
        print(f"（新增/更新命令数：{added}，未落盘）")
        return 0

    if before == after:
        print("✓ 三道闸已就位，无需改动。重启 WorkBuddy 即可生效。")
        return 0

    # 备份 + 写入
    backup = settings_path + f".bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(settings_path, backup) if os.path.exists(settings_path) else None
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    print(f"✓ 已写入 hooks 到：{settings_path}")
    if os.path.exists(backup):
        print(f"  （原文件已备份：{backup}）")
    print(f"✓ 新增/更新 {added} 条 hook 命令。")
    print("\n下一步：重启 WorkBuddy 让配置重新加载，然后写一条含真密钥的 SKILL.md 验证拦截。")
    print("如需撤销：用备份文件覆盖 settings.json 即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
