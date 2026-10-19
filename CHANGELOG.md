## [1.4.0] - 2026-09-24

> **合并版（本地 1.2.1 ③ 误报修复分支 × SkillHub 1.3.0 云鼎安全整改版）**：
> - **保留 ③ 误报修复**：redflags.py 分类器为 1.3.0 的超集，含 `#` 行注释豁免（`_in_code_comment`）、预防/否定语境豁免（`_PREVENT_ANCHORS`）、`rm_rf_critical` 窄否定豁免、自家托管路径豁免；34 条 RULES 零删改。
> - **保留 FP/FN 回归锁**：scripts/bench_fp.py（误报率/漏报率测量台）+ scripts/test_fp_fn_regression.py（16 锁回归闸）+ references/independent-audit-fp-v1.md（独立审计 FP 22.8%→2.6%、FN=0）全部并入。
> - **并入 1.3.0 云鼎安全整改（非 schema 部分）**：hook 环境变量注入 fail-open 可见化（`hooks/hooks.json` 三层兜底 + `THIS EVENT IS UNPROTECTED`）、`scripts/retry.py` 重试机制、`test-prompts-v3.json`、独立审计/演进文档、`pmu_guard.py`、`setup.py`、`_meta.json` 均并入。
> - **未采纳 1.3.0 的 43 探针 schema**：其实测与 ③ 的预防/否定豁免冲突（「禁用所有安全检查」类教程探针被 ③ 正确抑制为 none），且规则覆盖 30/34 弱于本地 34/34；本地 34 探针 schema 已用 `{{GIT_RESET_HARD}}` 等专属占位符解耦（分发包无真实危险载荷），测试全绿，故保留本地 schema。
> - **双轨同步保留**：`sync-to-cache.ps1` / `sync-to-cache.sh` 继续由 master（`~/.hermes/skills`）派生 cache 副本。

---

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] - 2026-08-29

> **云鼎实验室安全评估整改（#1 蜜罐样本解耦 + #3 env 注入 fail-open 可见化）**：
> - **#1 蜜罐/危险样本解耦（移除随包危险载荷）**：删除 `references/honeypot-probes.json`（43 份完整、可复制的「伪装正常技能的危险 SKILL.md」样本），改以 `references/honeypot-probes.schema.json`（43 条探针模板，全部使用 `{{TOKEN}}` 占位符，**源码不含可复制的真实危险载荷**）+ `scripts/honeypot_factory.py`（运行时把**拆分常量**拼成「格式合法但明显伪造、不可滥用」的探针，跑完即弃、绝不上盘）。分发包不再含任何完整危险载荷；验证脚本 `scripts/test_honeypot_probes.py` 仍覆盖全部 34 条规则并校验 MultiEdit 拼接不绕过。散布于文档/测试中的真实格式密钥与 `evil.com` 已统一脱敏为 `sk-FAKETESTKEY...` / `example.com` 等明显伪造占位符。
> - **#3 hook 环境变量注入 fail-open 可见化**：`hooks/hooks.json` 四道闸的根目录解析由「仅依赖 `CODEBUDDY_PLUGIN_ROOT`」升级为**三层兜底**（`CODEBUDDY_PLUGIN_ROOT` → `HERMES_PLUGIN_ROOT` → `~/.workbuddy/skills` 与 `~/.hermes/skills` 文件系统扫描）。当护栏脚本无法定位时，不再静默 no-op，而是向 stderr 显式输出 `THIS EVENT IS UNPROTECTED` 告警后 fail-open（`exit 0`），让「未受保护事件」从不可见的静默失效变为可见告警。
> - **测试套件修复**：`test_retry.py` / `test_path_filter.py` 两处环境耦合型断言已改为自包含（不依赖本机已装技能），全量测试 `selftest 6/6 + 10 个测试脚本全绿`。
> 安全拦截语义与 fail-open 行为完全不变：HIGH → deny 硬拦、MEDIUM → warn 告警、闸三默认软告警。

---

## [1.2.15] - 2026-08-31

> **评测驱动的两项加固**：
> - **自动重试机制**：新增 scripts/retry.py（指数退避、3 次、可重试异常集 OSError/IOError/PermissionError/TimeoutError）；write_gate/reuse_gate/drift_report 的关键 IO（读文件、读审计、扫描）全部接入重试——把「护栏自身临时抽风」导致的漏扫概率压到最低；重试耗尽才 fail-open 兜底（stderr 告警）；非可重试错误立即暴露；审计写入单次不重复。
> - **触发机制扩展**：凡创建/update skill 必触发——is_guarded_path 扩展为 ~/.workbuddy/skills/ 与 ~/.hermes/skills/ 目录内任意文件均触发闸一（仅 SKILL.md 进化为 skills 全目录资产）；write_gate 工具白名单加 SkillManage（自动定位 skill 名到 skills 目录、post 模式扫全目录并输出高危文件名清单）；install_hook.py 一键安装 matcher 同步为 Write|Edit|MultiEdit|SkillManage。
> 拦截语义与 1.2.14 完全一致：HIGH → deny 硬拦、MEDIUM → warn 告警、闸三默认软告警（可 --deny-on-alert 升级）。

---

## [1.2.14] - 2026-08-31

> **评测驱动的针对性加固**（回滚至 1.2.5 基线后基于评测反馈的定点修复）：
> - 边界加固：大文件（>2MB / >1万行）只扫「首 2000 行 + 尾 200 行」、二进制文件（正文含 NUL）跳过不误读——堵「大文件/边界漏报」；
> - 编码归一化：扫描前剥离零宽/不可见字符、全角标点转半角——堵「编码变体绕过」；
> - base64 隐藏密钥兜底：正文 base64 串解码后匹配真密钥格式即按 HIGH 拦截；
> - 文档集中：新增「环境与版本要求」小节（Python 版本 / 零第三方依赖 / hook 路径 / 版本一致性）与「扫描边界与抗绕过」小节。
> 拦截语义与 1.2.13（1.2.5 基线）完全一致：HIGH → deny 硬拦、MEDIUM → warn 告警、闸三默认软告警（可 --deny-on-alert 升级）。

---

## [1.2.13] - 2026-08-30

> **版本回滚**：应作者要求，将技能回滚至 1.2.5 功能基线（平台 1.2.5 原包内容）。
> 1.2.6~1.2.12 期间的评测驱动优化（错误码体系、fail-open 显性化、大文件/二进制扫描边界、编码归一化等）整体撤销，
> 安全拦截语义与 1.2.5 完全一致。版本号接续为 1.2.13（平台版本号不可回退，1.2.5 已存在不可重发同名版本）。

---

## [1.2.5] - 2026-08-30

> 本次为「评测驱动优化（第二轮）」：依据 TRACE 评测报告（综合 4.6/5）短板——实例不足、文档示例不够、嵌套编辑覆盖不全、版本号文档间不一致、配置不直观——做改进。**安全拦截语义与 fail-open 行为完全不变**。1.2.4 的 prose 误报修复（未单独发布）一并并入本版。

### 蜜罐探针 / 拦截实例（E 有效性 + 内容完整度）
- 新增 `references/honeypot-probes.json`：以**蜜罐（honeypot）**形式沉淀对抗样本库——每个探针是一份完整的、伪装成正常技能的危险写法的 `SKILL.md`（含 frontmatter、嵌套代码块、YAML 配置、表格等），覆盖：（注：1.3.0 起该文件已解耦为 `references/honeypot-probes.schema.json` 模板 + `scripts/honeypot_factory.py` 运行时合成，不再随包分发完整危险载荷）
  - 每条 HIGH/MEDIUM 规则的**多形态变体**（真实格式 / 伪装 / 变形 / 截断 / 大小写混合）；
  - **嵌套编辑场景**（YAML frontmatter 内密钥、嵌套代码块内密钥应被 prose 跳过、MultiEdit 跨 edit 拼接产生危险模式）；
  - **复合文档**（单文件同时含多个高危模式）；
  - **边界 / 合法误报**（安全教程代码块示例、benign 路径、占位符 `sk-xxxx`、测试 fixtures）。
- 新增 `scripts/test_honeypot_probes.py`：加载蜜罐库，对每条探针用 `redflags.scan_text(prose=True)` 验证最高严重度 / 命中规则是否符合预期，并**模拟 `write_gate.extract_content` 的 MultiEdit 拼接场景**验证增量编辑不会被绕过。

### 文档重构（C 规范性 + 文档质量）
- 新增「⚡ 三步接入 WorkBuddy Hook（直观配置）」：复制即用命令 + 预期输出，消除"配置不直观"。
- 新增「🍯 蜜罐探针库与真实拦截效果」章节：用验证结果表展示实际 deny/warn/allow 输出样例（修复评测"实际拦截效果例子不够多"）。
- 新增「嵌套编辑覆盖」说明：解释闸一如何按"合并后全文"扫描防增量绕过。

### 版本一致
- 统一 `package.json` / `README.md` / `PUBLISHING-REPORT.md` / `SKILL.md` / `_meta.json` 版本号至 1.2.5，消除"文档间不一致"。

---

## [1.2.4] - 2026-08-30

> 修复 prover 误报遮罩（prose masking）配对缺陷：旧实现用 ```` ```.*?``` ```` 就近配对或三反引号 token 顺序配对，当相邻代码块间夹散文、或文档含**教学展示用的字面反引号**（如 ```` ``` ```` ````）时，会把「闭```+散文+开```」错配成伪块，导致真正的代码块内容反而落在伪块外被漏扫——本技能 SKILL.md 第373行示例密钥曾被据此误报 `hardcoded.openai_key` HIGH，并连带使漂移自查（闸三）对自身告警。改为「行首开 ``` + 内容 + 行首闭 ```」的完整 fenced-block 结构匹配，展示用反引号自然被避开。验证：自身 SKILL.md 扫描由 HIGH 降为 MEDIUM，漂移自查 `alerts: []`。安全语义与 fail-open 不变。

## [1.2.3] - 2026-08-30

> 本次为「评测驱动优化」：依据 TRACE 评测报告（综合 4.6/5，T5.0/R4.4/A4.5/C4.2/E4.7）针对短板维度（C 规范性、R 可靠性、E 有效性）做改进，不改变任何安全拦截行为，全部 fail-open 语义不变。

### Convention (C 4.2→提升)
- **目录导航(TOC)**：Quick Start 后新增跳转导航，降低信息密度带来的"淹没感"（渐进式披露）。
- **反模式速查卡**：把最常踩的 6 个坑提到靠前位置，一眼避坑；深度版仍见 `references/anti-patterns.md`。
- **判定细节速查**：严重度→信号映射、HIGH 规则清单、漂移自查自适应阈值分桶，集中成表，解决"判断细节藏得深"。
- **实战示例**：新增 5 个真实场景（闸一拦截/闸二拦截/闸三告警/正常放行/`guard:allow` 放行复核）含真实拦截输出，解决"缺少完整使用示例"。
- **FAQ 增补**：Q8 解释文档示例为何被提示（散文模式跳过代码块/注释）；Q9 解释漂移硬拦截开关。

### Reliability (R 4.4→提升)
- `write_gate.py` / `reuse_gate.py` 异常时新增 **友好中文 stderr 提示**（fail-open 不变，stdout 不污染 hook 协议），不再静默无反馈。
- `drift_report.py` 未扫描到任何 SKILL.md 时给出明确提示与路径，不再静默输出 0。

### Effectiveness (E 4.7→提升)
- **减少文档示例误报**：`redflags.scan_text` 新增 `prose` 模式（默认开启），自动跳过 ```` ``` ```` 代码块与 `<!-- -->` 注释内部内容；正文散文里的真实密钥/危险命令仍 100% 拦截。护栏自身 SKILL.md 的测试示例不再自误报 HIGH。
- **漂移自查可选硬拦截**：新增 `drift_report.py --deny-on-alert` 开关，默认仍为"报告式"，开启后超阈值即 `permissionDecision=deny` 硬拦截，满足高安全纪律团队诉求且不改变默认行为。

### Tests
- 现有 `selftest.py` 6/6 通过；散文模式新增验证：代码块/注释内密钥不误报、正文内密钥仍 HIGH 拦截。

---

## [1.2.2] - 2026-08-30

### Security
- **P0-1 (guard:allow 自毁开关)**: `parse_allowlist` 拒绝 `__all__` 通配；`hardcoded_secret` 类真密钥永远不可放行；被放行的高危命中强制输出"放行复核"提醒并记入审计。内容自携 `guard:allow:all` 不再能解除闸一。
- **P0-2 (审计日志覆盖写)**: `append_audit` 由 `os.replace` 覆盖写改为真正的追加写（保留 fsync），恢复审计历史，救活闸二血缘判定与闸三趋势统计。
- **P0-3 (hook 跨平台)**: 四条 hook 命令由依赖 POSIX `[ -f ]` 改为 `python3 -c` 单命令（存在性判断移入 Python、fail-open），消除换宿主时四道闸整体静默 no-op。
- **P1-1 (异常契约)**: `write_gate`/`reuse_gate` 主体包 `try/except → exit 0`，`tool_input` 非 dict 等边界不再导致 exit 1（拒绝服务）。

### Changed
- **P1-3**: `drift_report.py` 新增 `--json` 结构化输出。
- **P1-4**: 闸三明确为"报告式"（超阈值输出 `systemMessage` 告警，不硬拦截）；文档删除"exit code 2 为拦截信号"的错误表述。
- **P1-5**: `.gitignore` 反忽略 `hooks/hooks.json` / `package.json`，修复分发级静默失效（仓库构建产物含护栏）。
- **P1-7**: `rm -rf ./` 由 HIGH 降为 MEDIUM（与项目自定分级政策一致，避免误伤安全技能写作）。
- **P2-1/2-3/2-4/2-5/2-6/2-7**: 规则数文档对齐（34 条）；漂移扫描目录去重；大库加绝对数告警门槛；复用记录按 ts 排序；补强 9 条漏报规则（IEX/os.popen/base64｜sh/git push --force 等）；`is_guarded_path` 大小写归一（修 Windows 绕过）。
- **P2-13**: `package.json` 脚本统一 `python3`，修正无效的 `main` 指向。
- **bypass.safety**: 添加"禁用"到正则匹配，提升中文边界覆盖。

### Added
- **建议8**: 新增 `scripts/selftest.py` 安装后自检（验证 hook 可解析、脚本可导入、deny 协议、审计日志可追加递增、已知 HIGH 样本确实拦截）。
- **建议3/4/7**: 复用扫描扩展 `hooks/`/`bin/`；写入期 Edit 构造合并后全文扫描；`test_redflags.py` 加固并新增 guard:allow 与漏报样本用例。
- **新增测试**: `test-redflags_extended.py` 覆盖 edge cases。
- **新增路径**: 添加 `~/.hermes/skills` 到 scan_dirs 和 find_skill_dir。

### Fixed
- **P1-6**: CHANGELOG / audit-report-v2 改写被记反的 P0 修复方向（`${CODEBUDDY_PLUGIN_ROOT}` 为正确方向）。
- **P2-8/2-9/2-10/2-11/2-14/2-15**: 清理 `.sync-log.txt`；统一版本号（1.2.2）；修正仓库 URL；刷新 PUBLISHING-REPORT；更新 audit-report-v2 与 audit-log 时间戳/计数文档。
- **drift_report.py**: 修复 USER_HOME 变量缺失导致的 NameError。

### Darwin Evolution
- **优化轮次**: 4 轮变异→选择→适应
- **分数变化**: 85 → 96 (+11分)
- **优化方法**: 补丁式修订 + 独立审计验证
- **棘轮锁定**: 分数只涨不跌

---

## [1.2.1] - 2026-08-29

### Security
- **P0-1 (guard:allow 自毁开关)**: `parse_allowlist` 拒绝 `__all__` 通配；`hardcoded_secret` 类真密钥永远不可放行；被放行的高危命中强制输出"放行复核"提醒并记入审计。内容自携 `guard:allow:all` 不再能解除闸一。
- **P0-2 (审计日志覆盖写)**: `append_audit` 由 `os.replace` 覆盖写改为真正的追加写（保留 fsync），恢复审计历史，救活闸二血缘判定与闸三趋势统计。
- **P0-3 (hook 跨平台)**: 四条 hook 命令由依赖 POSIX `[ -f ]` 改为 `python3 -c` 单命令（存在性判断移入 Python、fail-open），消除换宿主时四道闸整体静默 no-op。
- **P1-1 (异常契约)**: `write_gate`/`reuse_gate` 主体包 `try/except → exit 0`，`tool_input` 非 dict 等边界不再导致 exit 1（拒绝服务）。

### Changed
- **P1-3**: `drift_report.py` 新增 `--json` 结构化输出。
- **P1-4**: 闸三明确为"报告式"（超阈值输出 `systemMessage` 告警，不硬拦截）；文档删除"exit code 2 为拦截信号"的错误表述。
- **P1-5**: `.gitignore` 反忽略 `hooks/hooks.json` / `package.json`，修复分发级静默失效（仓库构建产物含护栏）。
- **P1-7**: `rm -rf ./` 由 HIGH 降为 MEDIUM（与项目自定分级政策一致，避免误伤安全技能写作）。
- **P2-1/2-3/2-4/2-5/2-6/2-7**: 规则数文档对齐（34 条）；漂移扫描目录去重；大库加绝对数告警门槛；复用记录按 ts 排序；补强 9 条漏报规则（IEX/os.popen/base64｜sh/git push --force 等）；`is_guarded_path` 大小写归一（修 Windows 绕过）。
- **P2-13**: `package.json` 脚本统一 `python3`，修正无效的 `main` 指向。

### Added
- **建议8**: 新增 `scripts/selftest.py` 安装后自检（验证 hook 可解析、脚本可导入、deny 协议、审计日志可追加递增、已知 HIGH 样本确实拦截）。
- **建议3/4/7**: 复用扫描扩展 `hooks/`/`bin/`；写入期 Edit 构造合并后全文扫描；`test_redflags.py` 加固并新增 guard:allow 与漏报样本用例。

### Fixed
- **P1-6**: CHANGELOG / audit-report-v2 改写被记反的 P0 修复方向（`${CODEBUDDY_PLUGIN_ROOT}` 为正确方向）。
- **P2-8/2-9/2-10/2-11/2-14/2-15**: 清理 `.sync-log.txt`；统一版本号（1.2.1）；修正仓库 URL；刷新 PUBLISHING-REPORT；更新 audit-report-v2 与 audit-log 时间戳/计数文档。

### Security Notes
- **并发安全**: `append_audit` 使用追加写（`open "a"` + `fsync`），多进程并发时每行独立JSON，解析器按行读取不影响单条记录完整性。
- **跨宿主兼容**: hooks.json 使用 `CODEBUDDY_PLUGIN_ROOT` 环境变量，WorkBuddy/CodeBuddy 自动注入；Hermes Agent 需适配路径解析。

---

## [1.2.0] - 2026-08-28

### Added
- Darwin optimization: 8 rounds from 56.8 to 88.5 (+31.7 points)
- Three-gate overview table in SKILL.md
- Input specification tables (Gate 1-3)
- Verdict tables with severity mapping
- Anti-pattern blacklist (6 entries with attribution types)
- Three-stage fallback table for failure handling
- CHECKPOINT/STOP visual markers
- 8 test prompts covering core features and edge cases
- GitHub PAT regex fix: `{30,}` for real-world token lengths
- `security.enabled=false` detection rule
- `python3` command consistency across hooks
- Atomic audit log write with `os.replace` + `fsync`
- UTC timezone handling instead of hardcoded +08:00

### Changed
- hooks.json: 保留并使用宿主注入的 `${CODEBUDDY_PLUGIN_ROOT}` 变量（经官方插件 `atuin/1.1.0/dist/atuin_hook_client.cjs` 旁证变量名正确，非 `__FILE_PATH__` 绝对路径方案——后者曾导致静默失效）。
- scripts/write_gate.py: Atomic write pattern for audit log
- scripts/write_gate.py: UTC timezone via `timezone.utc.astimezone()`
- SKILL.md: Version updated to 1.2.0
- SKILL.md: Added English translations for key sections
- SKILL.md: Restructured with explicit tables and visual markers

### Security
- 23 detection rules covering: hardcoded keys, bypass patterns, destructive operations
- PreToolUse hard-block for write/reuse phases
- PostToolUse audit logging
- SessionStart drift self-check
- Inline allow markers (`guard:allow:<rule_id>`) for intentional documentation

### Fixed
- P0-1: hooks.json path variable resolved without external env injection
- P0-2: drift_report empty list boundary handling
- P1-1: python → python3 cross-platform consistency
- P1-3: Audit log atomic write to prevent corruption
- P2-1: Timezone hardcoded +08:00 → UTC auto-detection

### Test Coverage
- 8/8 test prompts passing (100%)
- dim8 real test: 8/8 passed
- Verification: 14/14 checks passed

---

## [1.1.0] - 2026-08-28

### Added
- Initial hard-block version with three-gate design
- scripts/redflags.py with 18 detection rules
- scripts/write_gate.py for write-phase blocking
- scripts/reuse_gate.py for reuse-phase lineage check
- scripts/drift_report.py for drift self-check
- hooks/hooks.json for event-driven triggers
- results.tsv for Darwin optimization tracking

---

## [1.0.0] - 2026-08-28

### Added
- Baseline skill definition
- Core documentation
- Initial test prompts (5 cases)
