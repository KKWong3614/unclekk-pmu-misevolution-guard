#!/usr/bin/env bash
# [Windows] 优先使用 sync-to-cache.ps1：本 .sh 在 Git Bash 下删除操作会被 safe-delete 拦截导致中途退出。
# =============================================================================
# sync-to-cache.sh — 从实盘发布包重新生成 cache 插件实例（唯一派生通道）
# -----------------------------------------------------------------------------
# 用途：
#   把 D:\skill已检\unclekk-pmu-misevolution-guard（git 仓库 = 唯一真相源）
#   重新生成为 WorkBuddy 的 cache 插件实例，供 host 加载生效。
#   今后所有改动只在实盘做，cache 只由本脚本派生，禁止手改 cache。
#
# 映射关系（发布包结构 → 插件结构）：
#   scripts/*.py                              -> 1.0.0/scripts/*.py
#   hooks/hooks.json                          -> 1.0.0/hooks/hooks.json
#   SKILL.md                                  -> 1.0.0/skills/pmu-misevolution-guard/SKILL.md
#   README.md                                 -> 1.0.0/skills/pmu-misevolution-guard/README.md
#   references/*.md                           -> 1.0.0/skills/pmu-misevolution-guard/references/*.md
#   package.json                              -> 1.0.0/package.json
#   test-prompts.json                         -> 1.0.0/test-prompts.json
#   不复制：.git/ .gitignore audit/ *.bak __pycache__（版本控制/运行时产物）
#
# 重要约束：
#   - cache 目录名固定为 1.0.0（host 在 installed_plugins.json 写死 installPath），勿改目录名。
#   - 内容版本以 package.json 的 version 字段为准；host 注册表 version 字段由另一条命令对齐。
#   - 每次运行自动备份旧 cache 为 1.0.0.bak-<时间戳>，仅保留最新 1 个备份，避免 clutter 累积。
#
# 用法：bash sync-to-cache.sh
# =============================================================================
set -euo pipefail

# 实盘根目录 = 本脚本所在目录
SRC="$(cd "$(dirname "$0")" && pwd)"
CACHE_ROOT="C:/Users/Administrator/.workbuddy/plugins/cache/codebuddy-plugins-official/pmu-misevolution-guard"
VER_DIR="$CACHE_ROOT/1.0.0"
SKILL_DIR="$VER_DIR/skills/pmu-misevolution-guard"

echo "==> 源(实盘): $SRC"
echo "==> 目标(cache): $VER_DIR"

# 0. 备份旧 cache（时间戳），仅保留最新 1 个
if [ -d "$VER_DIR" ]; then
  BAK="$CACHE_ROOT/1.0.0.bak-$(date +%Y%m%d-%H%M%S)"
  cp -r "$VER_DIR" "$BAK"
  echo "已备份旧 cache -> $BAK"
  # 清理多余备份，仅保留最新 1 个
  # 注意：Git Bash 在 Windows 下 env 过大，xargs 会因 exec 复制 env 失败；
  #       改用 for 循环 + 直接 rm，绕开该问题。
  n=0
  for d in $(ls -dt "$CACHE_ROOT"/1.0.0.bak-* 2>/dev/null); do
    n=$((n+1))
    if [ "$n" -gt 1 ]; then rm -rf "$d"; fi
  done
  echo "已清理历史备份（仅保留最新 1 个）"
fi

# 1. 清空可变内容（保留 1.0.0/ 目录骨架，host 锁定路径）
rm -rf "$VER_DIR/scripts" "$VER_DIR/hooks" "$VER_DIR/skills" 2>/dev/null || true

# 2. 重新映射
mkdir -p "$VER_DIR/scripts" "$VER_DIR/hooks" "$SKILL_DIR/references"
cp "$SRC/scripts/"*.py "$VER_DIR/scripts/"
cp "$SRC/hooks/hooks.json" "$VER_DIR/hooks/"
cp "$SRC/SKILL.md" "$SKILL_DIR/SKILL.md"
cp "$SRC/README.md" "$SKILL_DIR/README.md"
cp "$SRC/references/"*.md "$SKILL_DIR/references/"
cp "$SRC/references/"*.json "$SKILL_DIR/references/" 2>/dev/null || true
cp "$SRC/package.json" "$VER_DIR/package.json"
cp "$SRC/test-prompts.json" "$VER_DIR/test-prompts.json" 2>/dev/null || true
cp "$SRC/test-prompts-v2.json" "$VER_DIR/test-prompts-v2.json" 2>/dev/null || true

# 3. 清理派生产物
rm -rf "$VER_DIR/scripts/__pycache__" 2>/dev/null || true

# 4. 验证关键文件存在
for f in "$VER_DIR/hooks/hooks.json" "$VER_DIR/scripts/write_gate.py" "$VER_DIR/scripts/reuse_gate.py" "$VER_DIR/scripts/drift_report.py" "$VER_DIR/scripts/redflags.py" "$SKILL_DIR/SKILL.md"; do
  if [ -f "$f" ]; then echo "OK  $f"; else echo "MISSING $f"; exit 1; fi
done

echo "✅ cache 实例已从实盘重新生成（内容版本见 package.json）。重启 host 后加载生效。"
