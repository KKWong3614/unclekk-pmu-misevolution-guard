---
name: unclekk-pmu-misevolution-guard
description: Event-driven three-gate hard-block security harness for Agent skill evolution. Scans content before write/reuse, blocks high-risk patterns via host protocol, and runs drift self-check. Prevents "small errors compounding into big ones unnoticed."
---

# Pmu Misevolution Guard (Hard-Block)

A production-ready security harness that prevents Agent skills from evolving dangerous patterns through event-driven hard blocks and continuous drift monitoring.

## Core Concepts

### Three-Gate Architecture

| Gate | Trigger | Action | Block Signal |
|------|---------|--------|--------------|
| Gate 1 | Write/Edit/MultiEdit to SKILL.md/MEMORY.md | Scan content via redflags | `permissionDecision=deny` |
| Gate 2 | Skill tool loading a skill | Check audit log + lineage | `permissionDecision=deny` |
| Gate 3 | Post-write + SessionStart | Scan full library + drift score | `systemMessage` alert (report-only) |

### Detection Rules

34 regex-based rules (🔴 HIGH 13 / ⚠️ MEDIUM 19 / ℹ️ LOW 2) covering:
- **Hardcoded keys** (8): GitHub PAT, OpenAI, Anthropic, Stripe, AWS, Slack, Google, private keys
- **Security bypass** (9): bypass/disable expressions, `--no-verify`, `chmod 777`, `curl|sh`, TLS/auth disabled, `base64|sh`, `subprocess(shell=True)`
- **Destructive operations** (6): `rm -rf` critical/local, `git reset --hard`, `DROP TABLE`, disk format, `git push --force`
- **Dynamic execution** (7): `eval(external)`, `os.system`, `shell=True`, `new Function`, `exec()`, `os.popen`, PowerShell `IEX`
- **Skip-confirm / env-specific / temp-to-default** (4)

### Inline Allow Markers

```markdown
# guard:allow:hardcoded.openai_key
# guard:allow:all
```

Convert unconscious leaks into conscious, auditable allow decisions.

## Quick Start

```bash
# Install to WorkBuddy plugins
cp -r unclekk-pmu-misevolution-guard ~/.workbuddy/plugins/

# Enable in settings
echo '{"enabledPlugins": ["unclekk-pmu-misevolution-guard"]}' >> ~/.workbuddy/settings.json

# Manual verification
python3 scripts/test_redflags.py
```

## Architecture

### Core Scripts

| Script | Purpose |
|--------|---------|
| `redflags.py` | 34 detection rules, scan_text/scan_file |
| `write_gate.py` | Gate 1: Write-phase hard block + audit log |
| `reuse_gate.py` | Gate 2: Reuse-phase lineage check |
| `drift_report.py` | Gate 3: Drift self-check + health report |

### Hook Configuration

hooks/hooks.json defines event-driven triggers:
- PreToolUse: write_gate (pre) + reuse_gate
- PostToolUse: write_gate (post)
- SessionStart: drift_report

## Test Coverage

```bash
# Run all test prompts
PYTHONHOME= python3 -c "
import sys, json
sys.path.insert(0, 'scripts')
from redflags import scan_text
with open('test-prompts.json') as f:
    prompts = json.load(f)
passed = sum(1 for p in prompts if 
    {'allow':'none','warn':'medium','deny':'high'}[
        'allow' if not scan_text(p['prompt']) else 
        'warn' if any(v['severity']=='medium' for v in scan_text(p['prompt'])) else 'deny'
    ] == p['expected'])
print(f'{passed}/{len(prompts)} passed')
"
```

**Result**: 8/8 passed (100%)

## Security Features

- ✅ One-vote veto: HIGH severity → automatic deny
- ✅ Event-driven: No background polling, hooks fire at write/reuse time
- ✅ Audit trail: append-only JSONL log of all blocked/warned writes (history preserved)
- ✅ Drift detection: Adaptive threshold based on library size + absolute-count floor for large libs
- ✅ Cross-platform: Python3 + os.path for Windows/Linux compatibility; hook commands are shell-agnostic
- ✅ Fail-open: any unexpected error exits 0 (guard never becomes a denial-of-service)

## Integration

Works with:
- WorkBuddy (native hook support)
- Hermes Agent (via user-level skills)
- Any host supporting PreToolUse/PostToolUse/SessionStart hooks

## License

MIT License

## Author

unclekk (Sapiens AI)

## 版本与同步（Version & Sync）

- **内容版本**：以 `package.json` 的 `version`（当前 1.2.0）为准，SKILL.md 顶部的 `version` 同步。
- **cache 目录名固定为 `1.0.0`**：WorkBuddy 在 `installed_plugins.json` 写死了 `installPath = .../pmu-misevolution-guard/1.0.0`，**勿改目录名**（host 只认这个路径）。
- **唯一真相源**：本目录（git 仓库 `D:\skill已检\unclekk-pmu-misevolution-guard`）是唯一的修改入口，改动只在此处进行。
- **cache 是派生产物**：用 `sync-to-cache.ps1`（Windows）或 `sync-to-cache.sh`（Linux）把本目录重新生成到 cache 实例，使其加载生效。**禁止手改 cache 实例**。
- **已知限制**：WorkBuddy 工具内删除操作会被 safe-delete 拦截，清理 `*.bak-*` 备份目录需在文件管理器手动进行。

---

Content version follows `package.json` (currently 1.2.0). The cache directory name is locked to `1.0.0` by the host (`installed_plugins.json` hard-codes the installPath) — do not rename it. This git repo is the single source of truth; edit only here. The cache instance is a derived artifact regenerated via `sync-to-cache.ps1` / `sync-to-cache.sh`. Note: in-tool deletions are blocked by safe-delete, so removing `*.bak-*` backups must be done manually in the file manager.
