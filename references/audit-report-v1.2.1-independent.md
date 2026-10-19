══════════════════════════════════════
  unclekk-pmu-misevolution-guard v1.2.1 — 深度审计报告
══════════════════════════════════════

安全评分: 88/100

| 维度 | 得分 | 权重 | 说明 |
|------|------|------|------|
| 正确性 | 22/25 | 25 | guard:allow 自毁开关已修复，审计日志追加写正确，34条规则匹配文档；drift_report 空列表边界正常 |
| 完整性 | 21/25 | 25 | 16/16 测试通过，selftest 6/6 通过；hooks.json 跨平台已修复；死代码 is_guarded_path 在 drift_report.py 未使用 |
| 安全性 | 17/20 | 20 | guard:allow:all 被拒绝 ✅，hardcoded_secret 永远不可放行 ✅，无命令注入风险 ✅；审计日志含测试数据残留 |
| 代码质量 | 14/15 | 15 | 无裸 except，异常契约正确，append_audit 有 fsync；是死代码需清理 |
| 设计 | 14/15 | 15 | 三道闸架构清晰，规则分离合理，自适应阈值设计良好 |

## P0 级缺陷（功能断裂/数据风险）
无

## P1 级缺陷
### P1-1: drift_report.py 导入 is_guarded_path 但未使用（死代码）
- 位置: scripts/drift_report.py:36
- 问题: `from redflags import scan_file, highest_severity, is_guarded_path` 中 is_guarded_path 被导入但从未调用
- 影响: 轻微代码膨胀，增加维护认知负担；不影响功能
- 修复: 从 import 语句中移除 is_guarded_path

### P1-2: 审计日志混入测试数据（非生产环境风险，但污染审计底座）
- 位置: audit/audit-log.jsonl:4-5, 11-13
- 问题: 日志中包含 `"test": 1/2/3/4` 和 `"verify": "append_test_1"` 等非生产测试条目，时间戳为 2026-01-01
- 影响: 漂移自查的 writes/reuses 计数虚高，lineage_risk_dist 被污染（当前 n/a:17）
- 修复: 运行前清理 audit/ 目录，或添加 --clean 标志

## P2 级缺陷
### P2-1: rm -rf ./ 正则边界（低风险，已知且有意降为 MEDIUM）
- 位置: scripts/redflags.py:92-93
- 问题: `destructive.rm_rf_local` 正则 `rm\s+-rf\s+\./` 不会匹配 `rm -rf ./dist`（需要空格后跟路径），仅匹配 `rm -rf ./` 本身
- 影响: CHANGELOG v1.2.1 已将此规则从 HIGH 降为 MEDIUM（P1-7），符合设计意图；但仍可能漏报 `rm -rf .\src`
- 修复: 如需更精确，可改为 `rm\s+-rf\s+\.\s*/?\s*(\S*)` 或保持现状（MEDIUM 仅告警）

### P2-2: hooks.json timeout 偏短（PreToolUse 15s，SessionStart 30s）
- 位置: hooks/hooks.json:12, 19, 32, 44
- 问题: 大规模技能库扫描时 drift_report.py 可能超过 15s 超时（实际测试 ~429 篇耗时未知）
- 影响: SessionStart 30s 足够；PreToolUse 15s 对预扫描可能紧张
- 修复: 考虑将 PreToolUse timeout 提高到 30s

### P2-3: SKILL.md 文档中规则分级统计表缺失
- 位置: SKILL.md:149-151
- 问题: 文档声称"🔴 HIGH 13 / ⚠️ MEDIUM 19 / ℹ️ LOW 2（共 34）"，但未提供分规则明细表
- 影响: 审计者难以快速验证每条规则的分类
- 修复: 在 references/red-flags.md 中添加完整规则表

## 实跑验证结果

### test_redflags.py
```
16/16 PASS
```

### selftest.py
```
[PASS] hook 命令为跨平台 python3 -c 形式  -- 4 条
[PASS] 脚本均可导入
[PASS] 已知 HIGH 样本输出 deny 协议  -- rc=0
[PASS] guard:allow:all 不再解除闸一
[PASS] 正常内容不被拦截
[PASS] 审计日志追加写(行数递增)  -- 5 -> 6
6/6 PASS
```

### guard:allow 机制验证
| 测试用例 | 预期 | 实际 | 结果 |
|----------|------|------|------|
| guard:allow:all + 普通内容 | exit 0, 无 deny | exit 0, 无 deny | ✅ |
| guard:allow:all + hardcoded_secret | deny | deny | ✅ |
| guard:allow:all + bypass.disable_auth | deny | deny | ✅ |
| guard:allow:bypass.disable_auth + bypass.disable_auth | 放行(有提醒) | 放行(有提醒) | ✅ |
| guard:allow:hardcoded_secret.api_key + sk-xxx | deny | deny | ✅ |
| 空 stdin | exit 0 | exit 0 | ✅ |
| tool_input 非 dict | exit 0 | exit 0 | ✅ |

### drift_report 验证
| 测试用例 | 预期 | 实际 | 结果 |
|----------|------|------|------|
| --scan /nonexistent | exit 0, 无崩溃 | exit 0, 正常报告 | ✅ |
| --json | JSON 输出 | valid JSON | ✅ |
| 空审计日志 | 无告警 | status=ok | ✅ |

### 审计日志追加验证
- 初始行数: 0
- 写入 1 条后: 1 行
- 追加写模式正确，fsync 落盘

## 规则统计验证
- SKILL.md 声称: 34 条（HIGH 13 / MEDIUM 19 / LOW 2）
- redflags.py RULES 列表: 34 条 ✅
- parse 验证: `len(redflags.RULES) == 34` ✅

## 关键发现
1. **P0-1 guard:allow 自毁开关**: ✅ 已修复（v1.2.1）- parse_allowlist 拒绝 all/__all__
2. **P0-2 审计日志追加写**: ✅ 已修复（v1.2.1）- 使用 `open("a")` + fsync
3. **P0-3 hooks 跨平台**: ✅ 已修复（v1.2.1）- 使用 `python3 -c` + runpy.run_path
4. **P1-1 异常契约**: ✅ 已修复（v1.2.1）- try/except → exit 0

## 修复验伪
- test_redflags.py: 16/16 passed ✅
- selftest.py: 6/6 passed ✅
- guard:allow 机制: 5/5 cases passed ✅
- 审计日志追加: 1/1 passed ✅

══════════════════════════════════════
  审计结论: v1.2.1 关键 P0 修复已落地，功能真实可用。
  遗留 P1-1/P1-2 为代码质量与数据清理问题，不影响核心防护能力。
══════════════════════════════════════
