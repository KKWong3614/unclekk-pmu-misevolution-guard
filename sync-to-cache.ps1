# =============================================================================
# sync-to-cache.ps1 — 从实盘发布包重新生成 cache 插件实例（唯一派生通道）
# -----------------------------------------------------------------------------
# 用途：
#   把 D:\skill已检\unclekk-pmu-misevolution-guard（git 仓库 = 唯一真相源）
#   重新生成为 WorkBuddy 的 cache 插件实例，供 host 加载生效。
#   今后所有改动只在实盘做，cache 只由本脚本派生，禁止手改 cache。
#
# 映射（发布包结构 → 插件结构）：
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
# 用法（PowerShell）：
#   powershell -ExecutionPolicy Bypass -File "D:\skill已检\unclekk-pmu-misevolution-guard\sync-to-cache.ps1"
# =============================================================================
$ErrorActionPreference = 'Stop'

$SRC = Split-Path -Parent $MyInvocation.MyCommand.Definition
$CACHE_ROOT = "C:\Users\Administrator\.workbuddy\plugins\cache\codebuddy-plugins-official\pmu-misevolution-guard"
$VER_DIR = Join-Path $CACHE_ROOT "1.0.0"
$SKILL_DIR = Join-Path $VER_DIR "skills\pmu-misevolution-guard"

Write-Host "==> 源(实盘): $SRC"
Write-Host "==> 目标(cache): $VER_DIR"

# 0. 备份旧 cache，仅保留最新 1 个
if (Test-Path $VER_DIR) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $bak = Join-Path $CACHE_ROOT "1.0.0.bak-$stamp"
    Copy-Item $VER_DIR $bak -Recurse -Force
    Write-Host "已备份旧 cache -> $bak"
}
# 清理多余备份，保留最新 1 个（PowerShell 原生删除，绕过 safe-delete 回收站）
Get-ChildItem $CACHE_ROOT -Directory -Filter '1.0.0.bak-*' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 1 |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
Write-Host "已清理历史备份（仅保留最新 1 个）"

# 1. 清空可变内容（保留 1.0.0/ 目录骨架，host 锁定路径）
Remove-Item (Join-Path $VER_DIR 'scripts') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $VER_DIR 'hooks')   -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $VER_DIR 'skills')  -Recurse -Force -ErrorAction SilentlyContinue

# 2. 重新映射
New-Item -ItemType Directory -Force -Path (Join-Path $VER_DIR 'scripts') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $VER_DIR 'hooks')   | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $SKILL_DIR 'references') | Out-Null
Copy-Item (Join-Path $SRC 'scripts\*.py')            (Join-Path $VER_DIR 'scripts') -Force
Copy-Item (Join-Path $SRC 'hooks\hooks.json')        (Join-Path $VER_DIR 'hooks')   -Force
Copy-Item (Join-Path $SRC 'SKILL.md')                (Join-Path $SKILL_DIR 'SKILL.md') -Force
Copy-Item (Join-Path $SRC 'README.md')               (Join-Path $SKILL_DIR 'README.md') -Force
Copy-Item (Join-Path $SRC 'references\*.md')         (Join-Path $SKILL_DIR 'references') -Force
Copy-Item (Join-Path $SRC 'references\*.json')        (Join-Path $SKILL_DIR 'references') -Force
Copy-Item (Join-Path $SRC 'package.json')            (Join-Path $VER_DIR 'package.json') -Force
if (Test-Path (Join-Path $SRC 'test-prompts.json')) {
    Copy-Item (Join-Path $SRC 'test-prompts.json')   (Join-Path $VER_DIR 'test-prompts.json') -Force
}
if (Test-Path (Join-Path $SRC 'test-prompts-v2.json')) {
    Copy-Item (Join-Path $SRC 'test-prompts-v2.json') (Join-Path $VER_DIR 'test-prompts-v2.json') -Force
}

# 3. 清理派生产物
Remove-Item (Join-Path $VER_DIR 'scripts\__pycache__') -Recurse -Force -ErrorAction SilentlyContinue

# 4. 验证关键文件存在
$files = @(
    (Join-Path $VER_DIR 'hooks\hooks.json'),
    (Join-Path $VER_DIR 'scripts\write_gate.py'),
    (Join-Path $VER_DIR 'scripts\reuse_gate.py'),
    (Join-Path $VER_DIR 'scripts\drift_report.py'),
    (Join-Path $VER_DIR 'scripts\redflags.py'),
    (Join-Path $SKILL_DIR 'SKILL.md')
)
foreach ($f in $files) {
    if (Test-Path $f) { Write-Host "OK  $f" } else { Write-Error "MISSING $f"; exit 1 }
}
Write-Host "✅ cache 实例已从实盘重新生成（内容版本见 package.json）。重启 host 后加载生效。"
