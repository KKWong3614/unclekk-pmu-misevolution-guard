# unclekk-pmu-misevolution-guard v1.2.2 独立第三方深度审计报告

**审计日期**: 2026-08-30  
**审计者**: 独立第三方 subagent  
**审计范围**: 三道闸硬拦截护栏安全性和完整性验证  
**测试环境**: Windows 10, Python 3.12.10, 隔离环境运行

---

## 安全评分: 86/100

| 维度 | 得分 | 权重 | 说明 |
|------|------|------|------|
| 正确性 | 22/25 | 25 | 核心功能正确，版本不一致扣3分 |
| 完整性 | 22/25 | 25 | 34条规则全覆盖，死代码扣3分 |
| 安全性 | 19/20 | 20 | guard:allow机制正确，审计日志污染扣1分 |
| 代码质量 | 11/15 | 15 | 死代码问题，并发安全设计正确 |
| 设计 | 12/15 | 15 | 架构合理，冗余导入扣3分 |

---

## P0 级缺陷（功能断裂/数据风险）

**无 P0 级缺陷**

独立验证结果：
- ✅ `guard:allow:all` 被正确拒绝（pass set 为空）
- ✅ 精确 `rule_id` 可放行（如 `hardcoded.openai_key`）
- ✅ 真密钥 + `guard:allow:all` 仍被拦截（permissionDecision=deny）
- ✅ 审计日志追加写正确（10线程测试，10条全部保留）
- ✅ hooks.json 跨平台兼容（CODEBUDDY_PLUGIN_ROOT + python3 -c + || true）

---

## P1 级缺陷

### P1-1: SKILL.md/package.json 版本与 CHANGELOG 不一致
- **位置**: `SKILL.md:5`, `package.json:3`, `CHANGELOG.md:10`
- **问题**: SKILL.md frontmatter 和 package.json 声明版本为 `1.2.1`，但 CHANGELOG 最新条目为 `[1.2.2] - 2026-08-30`
- **影响**: 版本不一致可能导致依赖管理混乱，用户无法通过单一来源确认实际版本
- **证据**:
  ```
  SKILL.md:5  version: 1.2.1
  package.json:3  "version": "1.2.1"
  CHANGELOG.md:10  ## [1.2.2] - 2026-08-30
  ```
- **修复建议**: 将 SKILL.md 和 package.json 的版本号统一更新为 `1.2.2`

### P1-2: drift_report.py 死代码（未使用导入）
- **位置**: `scripts/drift_report.py:36`
- **问题**: 导入了 `is_guarded_path` 但从未调用
- **影响**: 增加维护负担，可能误导读者认为该函数被使用
- **证据**:
  ```python
  # line 36
  from redflags import scan_file, highest_severity, is_guarded_path  # noqa: E402
  # is_guarded_path 调用次数: 0
  ```
- **修复建议**: 从导入列表中移除 `is_guarded_path`

### P1-3: write_gate.py 死代码（未使用变量）
- **位置**: `scripts/write_gate.py:34`
- **问题**: 定义了 `SEVERITY_RANK` 字典但从未使用
- **影响**: 无用代码增加维护负担
- **证据**:
  ```python
  # line 34
  SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}
  # 在整个文件中仅定义一次，无其他引用
  ```
- **修复建议**: 删除 `SEVERITY_RANK` 定义

### P1-4: test_rule_coverage.py 死代码（未使用变量）
- **位置**: `scripts/test_rule_coverage.py:16`
- **问题**: 定义了 `SEV_MAP` 字典但从未使用
- **影响**: 无用代码，测试脚本应保持精简
- **证据**:
  ```python
  # line 16
  SEV_MAP = {"deny": "high", "warn": "medium", "allow": "none"}
  # 在整个文件中仅定义一次，无其他引用
  ```
- **修复建议**: 删除 `SEV_MAP` 定义

### P1-5: 审计日志混入测试数据污染统计
- **位置**: `audit/audit-log.jsonl`
- **问题**: 测试运行产生的记录混入正式审计日志，导致 lineage_risk 统计失真
- **影响**: drift_report 的血缘风险分布统计被污染，可能影响闸二/闸三判断
- **证据**:
  ```
  审计日志总记录数: 144
  测试记录数: 22（来自 test_concurrent.py 和 selftest.py）
  lineage_risk 分布: {'low': 23, 'n/a': 121}
  ```
  测试记录示例：
  ```json
  {"ts": "2026-08-30T01:56:18.894195+00:00", "test": 5}
  ```
- **修复建议**: 
  1. 清空测试产生的审计日志：`rm audit/audit-log.jsonl`
  2. 或在测试脚本中使用临时目录，避免污染正式日志

---

## P2 级缺陷

**无 P2 级缺陷**

---

## 测试验证结果

| 测试套件 | 结果 | 说明 |
|----------|------|------|
| test_redflags.py | 16/16 PASS | 核心功能测试全部通过 |
| selftest.py | 6/6 PASS | 安装自检全部通过 |
| test_rule_coverage.py | 34/34 PASS | 规则覆盖率100% |
| test_concurrent.py | PASS | 10线程并发写入全部保留 |
| test_redflags_extended.py | 6/6 PASS | 扩展边界测试全部通过 |
| 语法检查 | 9/9 OK | 所有脚本 AST 解析通过 |

---

## 独立验证结果

### 1. guard:allow 自毁开关机制（P0级验证）

| 测试项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| `guard:allow:all` 拒绝 | pass set 为空 | `set()` | ✅ PASS |
| 精确 rule_id 放行 | 包含 `hardcoded.openai_key` | `{'hardcoded.openai_key'}` | ✅ PASS |
| 真密钥 + `guard:allow:all` | permissionDecision=deny | deny | ✅ PASS |
| FORBIDDEN_CATS 包含 hardcoded_secret | 代码中存在 | 确认存在 | ✅ PASS |

### 2. 并发安全验证

| 测试项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| threading.Lock 存在 | 代码中存在 | 确认存在 | ✅ PASS |
| append_audit 使用锁 | 函数体中有 `_AUDIT_LOCK` | line ~114 | ✅ PASS |
| 10线程并发写入 | 10条全部保留 | 10条保留 | ✅ PASS |
| 追加写不覆盖 | 行数递增 | 133→134 | ✅ PASS |

### 3. 规则覆盖率验证

| 指标 | 值 |
|------|-----|
| 总规则数 | 34 |
| 已测试规则 | 34 |
| 未测试规则 | 0 |
| 覆盖率 | 100% |

### 4. hooks 跨平台兼容性验证

| 检查项 | 结果 |
|--------|------|
| PreToolUse hook 1 (write_gate pre) | ✅ CODEBUDDY_PLUGIN_ROOT + python3 -c + \|\| true |
| PreToolUse hook 2 (reuse_gate) | ✅ CODEBUDDY_PLUGIN_ROOT + python3 -c + \|\| true |
| PostToolUse hook (write_gate post) | ✅ CODEBUDDY_PLUGIN_ROOT + python3 -c + \|\| true |
| SessionStart hook (drift_report) | ✅ CODEBUDDY_PLUGIN_ROOT + python3 -c + \|\| true |

---

## 死代码汇总

| 文件 | 位置 | 问题 | 影响 |
|------|------|------|------|
| drift_report.py:36 | `is_guarded_path` 导入 | 从未调用 | 维护负担 |
| write_gate.py:34 | `SEVERITY_RANK` 定义 | 从未使用 | 维护负担 |
| test_rule_coverage.py:16 | `SEV_MAP` 定义 | 从未使用 | 维护负担 |

---

## 版本一致性检查

| 文件 | 声明版本 | 实际版本 | 一致性 |
|------|----------|----------|--------|
| SKILL.md:5 | 1.2.1 | 1.2.2 | ❌ 不一致 |
| package.json:3 | 1.2.1 | 1.2.2 | ❌ 不一致 |
| CHANGELOG.md:10 | - | 1.2.2 | ✅ 正确 |

---

## 审计日志污染检查

| 指标 | 值 |
|------|-----|
| 总记录数 | 144 |
| 测试记录数 | 22 |
| 污染比例 | 15.3% |
| lineage_risk 分布 | {'low': 23, 'n/a': 121} |

⚠️ **问题**: 测试数据混入正式日志，影响血缘风险统计

---

## 正则边界条件检查

| 规则 | 测试用例 | 结果 |
|------|----------|------|
| hardcoded.openai_key | `sk-` + 20字符 | ✅ 匹配 |
| hardcoded.openai_key | `sk-` + 19字符 | ✅ 不匹配 |
| hardcoded.aws_key | `AKIA` + 16字符 | ✅ 匹配 |
| bypass.disable_auth | `auth = false` | ✅ 匹配 |
| bypass.disable_auth | `AUTH_ENABLED = false` | ✅ 匹配 |

---

## 结论

**判定**: ⚠️ **有条件通过**

### 通过项
- ✅ 三道闸核心拦截逻辑正确
- ✅ guard:allow 自毁开关机制已修复
- ✅ 审计日志追加写已修复
- ✅ hooks 跨平台兼容
- ✅ 34条规则100%覆盖
- ✅ 并发安全机制正确

### 需修复项
- 🔴 P1-1: 版本不一致（SKILL.md/package.json → 1.2.2）
- 🔴 P1-2: drift_report.py 死代码（移除 is_guarded_path 导入）
- 🔴 P1-3: write_gate.py 死代码（删除 SEVERITY_RANK）
- 🔴 P1-4: test_rule_coverage.py 死代码（删除 SEV_MAP）
- 🔴 P1-5: 审计日志污染（清空测试数据）

### 修复建议优先级
1. **立即修复**: P1-1 版本不一致（影响依赖管理）
2. **尽快修复**: P1-2/P1-3/P1-4 死代码（降低维护成本）
3. **下次迭代**: P1-5 审计日志清理（不影响功能，影响统计）

---

## 审计方法学说明

本次审计采用独立第三方深度审计方法：
1. **不信任文档声称**：所有功能通过实跑验证
2. **隔离环境测试**：使用 `env -u PYTHONHOME -u UV_INTERNAL__PYTHONHOME` 隔离 Python 环境
3. **临时目录测试**：所有测试在 tempfile 中进行，不污染原文件
4. **独立代码审查**：通过 AST 分析和 grep 验证死代码
5. **边界条件测试**：验证正则规则边界、并发竞态、版本一致性

---

**审计完成时间**: 2026-08-30  
**审计报告版本**: v1.0  
**审计工具链**: Python 3.12.10, subprocess, AST, json
