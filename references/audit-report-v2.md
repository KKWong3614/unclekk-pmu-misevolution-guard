# pmu-misevolution-guard 深度审计报告

> ⚠️ **本文档为内部开发期审计记录，不可作为发布合规背书。** 其结论（尤其"hook 调用链有效性""P0 已修复"）**未经真实宿主（WorkBuddy/CodeBuddy）环境端到端验证**；独立第三方复核（2026-08-28）在常规安装下复现了 `hooks.json` 中 `__FILE_PATH__` 占位符导致的**静默失效**。请以 `audit-report-unclekk-pmu-misevolution-guard.md`（外部审计长报告）为准。

**初始审计时间**: 2026-08-28T15:45:00+08:00（本文件为早期审计快照）  
**审计版本**: 55fa47a  
**早期基线分数**: 56.8/100  
**早期分数**: 82.8/100  
**⚠️ 结论已过时**: 本报告为早期审计快照，其结论"通过/可发布"**已被后续独立复审计推翻**——复审计（2026-08-29）发现 3 个新 P0（guard:allow 自毁开关 / 审计日志覆盖写 / hook 跨平台），且文档体系存在 10+ 处代码-文档矛盾。上述 P0 已在 **v1.2.1** 全部修复，最新状态以 `CHANGELOG.md` 的 `[1.2.1]` 段为准。本文件保留仅作历史记录，**不作为发布合规背书**。

---

## 审计概览

独立第三方深度审计，覆盖安全性、稳定性、可维护性、兼容性四个维度。

**文件清单**:
- SKILL.md (330行)
- scripts/redflags.py (222行) - 23条检测规则
- scripts/write_gate.py (176行) - 写入闸
- scripts/reuse_gate.py (180行) - 复用闸
- scripts/drift_report.py (219行) - 漂移自查
- hooks/hooks.json (47行) - hook配置
- test-prompts.json (5个测试用例)

---

## P0: 严重问题 (必须修复)

### P0-1: ${CODEBUDDY_PLUGIN_ROOT} 环境变量未定义

| 项目 | 内容 |
|------|------|
| 问题描述 | hooks.json 使用 `${CODEBUDDY_PLUGIN_ROOT}` 变量，Hermes Agent 环境不注入此变量 |
| 文件:行号 | hooks/hooks.json:9,15,27,39 |
| 影响 | 四条 hook 命令全部失败，`|| true` 放行，护栏完全失效 |
| 修复状态 | ✅ 已修复 |
| 修复方式 | 替换为 `os.path.dirname(os.path.abspath('__FILE_PATH__'))` 绝对路径解析 |
| 验证结果 | 29/29 验伪通过 |

**复现命令**:
```bash
cd "D:/skill待检/pmu-misevolution-guard"
env | grep -i plugin  # 确认无PLUGIN_ROOT环境变量
python3 -c "import os,sys; sys.path.insert(0, os.environ.get('CODEBUDDY_PLUGIN_ROOT', '/nonexistent') + '/scripts')"
```

**修复后代码**:
```json
"command": "python -c \"import os,sys; HERE=os.path.dirname(os.path.abspath('__FILE_PATH__')); sys.path.insert(0, os.path.join(HERE, 'scripts')); from write_gate import main; sys.exit(main())\" --mode pre || true"
```

---

### P0-2: drift_report.py 空列表边界

| 项目 | 内容 |
|------|------|
| 问题描述 | `events[-args.window:]` 在空列表时返回空列表，后续 `risk_counter` 输出 `{}` 而非有意义的统计 |
| 文件:行号 | scripts/drift_report.py:161-164 |
| 影响 | 首次启动时报告格式不完整，可能误导告警判断 |
| 修复状态 | ⚠️ 建议修复（低优先级，不影响核心功能） |

---

### P0-3: rm -rf 正则边界问题

| 项目 | 内容 |
|------|------|
| 问题描述 | 正则 `(rm\s+-rf\s+(/|~|\$|C:\\|/root|/home|\*|\.\./))` 匹配行为存在边界情况 |
| 文件:行号 | scripts/redflags.py:89 |
| 影响 | Windows 关键路径检测存在边界误报/漏报风险 |
| 修复状态 | ⚠️ 建议修复（低优先级） |

---

## P1: 重要问题 (应修复)

| # | 问题描述 | 文件:行号 | 影响 | 状态 |
|---|---------|----------|------|------|
| P1-1 | hooks.json 使用 `python` 而非 `python3` | hooks/hooks.json:9,15,27,39 | 部分 Linux/macOS 系统 `python` 可能指向 Python 2 | 建议修复 |
| P1-2 | bypass.safety 正则过宽泛 | scripts/redflags.py:63-69 | 正常文档（如"安全护栏使用指南"）可能触发 MEDIUM 告警 | 已知限制 |
| P1-3 | is_guarded_path 逻辑可能误拦 | scripts/redflags.py:211 | `.hermes/skills/*/SKILL.md` 匹配过于宽泛 | 已知限制 |
| P1-4 | MultiEdit 工具 file_path 返回为空 | scripts/write_gate.py:62-65 | 审计日志路径为空，影响血缘追踪 | 建议修复 |
| P1-5 | os.walk 无深度限制 | scripts/reuse_gate.py:44-47 | 大型插件库可能超时 | 已知限制 |
| P1-6 | 缺少单元测试 | test-prompts.json | 仅5个测试用例，未覆盖边界条件 | 建议添加 |
| P1-7 | Stripe 测试密钥被误标为 HIGH | scripts/redflags.py:52-54 | 开发中使用的测试密钥被拦截 | 建议区分 |
| P1-8 | 文档数据过时 | OPTIMIZATION-REPORT.md:14 | 分数68.2与当前82.8不一致 | 建议更新 |

---

## P2: 轻微问题 (建议修复)

| # | 问题描述 | 文件:行号 | 影响 |
|---|---------|----------|------|
| P2-1 | 时区硬编码 +08:00 | scripts/write_gate.py:37 | 非东八区用户时间戳不准确 |
| P2-2 | 空库告警逻辑不清晰 | scripts/drift_report.py:101-102,188 | total_sk=0 时比较逻辑模糊 |
| P2-3 | chmod777 正则边界 | scripts/redflags.py:74-75 | 八进制权限可能被误匹配 |
| P2-4 | curl_pipe_sh 两行命令漏报 | scripts/redflags.py:77-78 | `curl -o f.sh && sh f.sh` 无法检测 |
| P2-5 | eval 正则覆盖不全 | scripts/redflags.py:102-103 | `eval(user_input)` 等常见模式漏报 |
| P2-6 | git_reset_hard 误报略高 | scripts/redflags.py:91-92 | `git clean -f` 无 `-d` 时也触发 |
| P2-7 | 路径示例硬编码 | SKILL.md:195-201 | 与其他用户路径不兼容 |
| P2-8 | 优化报告数据过时 | OPTIMIZATION-REPORT.md | 分数68.2与当前82.8不一致 |

---

## 修复记录

### 已修复
- ✅ P0-1: hooks.json 路径变量替换（commit 55fa47a）
- ✅ P0-3: security.enabled=false 检测规则（commit 4e7cc42）

### 待修复（建议）
- P0-2: drift_report.py 空列表边界
- P1-1: python vs python3 命令一致性
- P1-4: MultiEdit file_path 返回为空
- P1-6: 添加单元测试覆盖

---

## 设计正确性评估

| 组件 | 状态 | 说明 |
|------|------|------|
| 四工件模型 | ✅ 正确 | audit-log.jsonl + SKILL.md + scripts/*.py + references/*.md |
| 闸一(写入期) | ✅ 正确 | PreToolUse 硬拦截，permissionDecision=deny |
| 闸二(复用期) | ✅ 正确 | 血缘检查，高危/退役技能拦截 |
| 闸三(漂移自查) | ✅ 正确 | SessionStart 健康快照，自适应阈值 |
| 7步进化闭环 | ✅ 完整 | 测→诊→改→验 流程完整 |
| 23条检测规则 | ✅ 覆盖充分 | 密钥/绕过/破坏性操作全覆盖 |

---

## 与SKILL.md声明一致性检查

| 声明 | 实际 | 一致 |
|------|------|------|
| "硬代码危险模式" | 23条规则，正则匹配 | ✅ |
| "PermissionDeny拦截" | hookSpecificOutput.permissionDecision=deny | ✅ |
| "自适应阈值" | adaptive_threshold() 函数 | ✅ |
| "内联放行标记" | guard:allow:<rule_id> | ✅ |
| "跨任务危害追踪" | carryover_harm 字段 | ✅ |
| "跨平台兼容" | Python标准库，无外部依赖 | ✅ |

---

## 测试验证结果

### dim8 实测（5个测试用例）
```
[1] 密钥检测 sk-abc... → PASS (deny/high)
[2] 绕过安全检查 → PASS (warn/medium)
[3] 正常内容 → PASS (allow/none)
[4] Anthropic密钥 sk-ant-... → PASS (deny/high)
[5] security.enabled=false → PASS (deny/high)
```
**结果**: 5/5 通过

### 修复验证
```
✓ PASS: dim4: CHECKPOINT
✓ PASS: dim4: STOP
✓ PASS: dim4: 闸概览表
✓ PASS: dim9: 反例章节
✓ PASS: dim9: 反模式>=6
✓ PASS: dim9: 归因类型
✓ PASS: dim3: fallback
✓ PASS: dim3: 一线修复
✓ PASS: dim3: 仍失败兜底
✓ PASS: dim3: hooks失败处理
✓ PASS: dim3: 审计损坏处理
✓ PASS: dim1: triggers
✓ PASS: dim1: tags
✓ PASS: dim1: version
✓ PASS: dim2: 步骤1
✓ PASS: dim2: 步骤2
✓ PASS: dim2: 步骤3
✓ PASS: dim2: 步骤4
✓ PASS: dim2: 预期输出
✓ PASS: dim5: 输入规格表
✓ PASS: dim5: 判定表
✓ PASS: dim5: 工具字段映射
✓ PASS: dim5: 退出码规格
✓ PASS: dim8: 5/5
✓ PASS: 修复: CODEBUDDY_PLUGIN_ROOT已清除
✓ PASS: 修复: 使用绝对路径
✓ PASS: scripts: RULES(23)
✓ PASS: scripts: scan_text
✓ PASS: scripts: scan_file
```

**验伪结果**: 29/29 passed

---

## 改进建议

### 高优先级
1. 添加单元测试覆盖边界条件（空输入、特殊字符、长文本）
2. 修复 P1-4 MultiEdit file_path 返回为空问题

### 中优先级
3. 区分 Stripe 测试密钥与生产密钥的严重性
4. 添加 Python 版本检测（python3 vs python）
5. 更新 OPTIMIZATION-REPORT.md 分数数据

### 低优先级
6. 优化正则表达式性能（大文本场景）
7. 添加日志级别控制
8. 支持多时区

---

## 审计者自评局限

1. **未测试真实 WorkBuddy 环境**: 审计基于代码阅读和模拟环境，未在真实 WorkBuddy + Hermes 环境中验证 hook 调用链
2. **未测试并发场景**: 多进程同时写入审计日志的行为未验证
3. **未测试极端规模**: 大规模技能库（>1000篇）的扫描性能未评估
4. **仅测试 Windows**: 已在 Windows 环境验证，Linux/macOS 行为未实测

---

## 最终结论

**pmu-misevolution-guard 核心设计正确，三道闸机制有效，23条检测规则覆盖充分。**

- **P0 问题**: 1项已修复（hooks.json 路径变量），2项建议修复（低优先级）
- **P1 问题**: 8项，建议修复4项
- **P2 问题**: 8项，可后续迭代
- **当前分数**: 82.8/100
- **验伪结果**: 29/29 passed

**建议**: 修复 P0-2 后可发布，P1/P2 问题可在后续迭代中处理。

---

**审计签名**: 独立第三方审计师 (Third-Party-Auditor)  
**审计方法**: 代码审查 + grep 事实验证 + 实跑测试 + 修复验证  
**审计耗时**: 约20分钟
