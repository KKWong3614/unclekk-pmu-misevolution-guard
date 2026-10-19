---
slug: unclekk-pmu-misevolution-guard
name: unclekk-pmu-misevolution-guard
displayName: UncleKK 技能误进化护栏（硬拦截版）
version: 1.4.0
summary: >-
  当 Agent 把"成功"经验固化成技能/记忆/流程，或检索复用已有技能时，用事件驱动的三道闸硬代码扫描内容、命中高危即按宿主协议 deny 硬拦截，防"小错累积成大错而不自知"。 | When an Agent hardens a "successful" experience into a skill/memory/workflow, or reuses an existing one, an event-driven three-gate hard-code scans content and denies high-risk patterns per the host protocol, preventing "small errors compounding into big ones unnoticed."
description: >-
  当 Agent 准备把一次"成功"经验固化成可复用技能/记忆/流程（写入期），或准备检索复用已有技能（复用期），或需要周期性自查"是否在悄悄把危险做法固化进技能库"（漂移自查）时加载本 skill。本版为事件驱动的三道闸硬代码：由 WorkBuddy/Hermes hook 自动触发，直接扫描文件内容做客观危险判定，命中高危即按宿主协议 permissionDecision=deny 硬拦截，非看门狗、非声明式、不靠 agent 自觉运行。
license: MIT
tags: [硬拦截, 安全护栏, 技能进化, 三道闸, 审计日志, 漂移自查, 高危拦截, 密钥检测, 安全治理]
triggers: [优化skill, skill评分, 自动优化, 达尔文, darwin, 审计, 深度审计, 安全护栏, 硬拦截, 技能进化, 误进化, 三道闸, skill guard, evolution guard]
---

# Pmu Misevolution Guard（技能误进化护栏 · 硬拦截版）

**🔴 CHECKPOINT · 本skill是事件驱动的三道闸硬代码护栏，不是声明式检查表，不靠自觉运行。**

**🛑 STOP · 命中HIGH严重度 → 宿主协议 deny → 硬拦截，非建议性提醒。**

---

## 本版与"纯方法论版"的根本区别 | Core Difference from the "Pure Methodology" Version

|| 维度 Dimension | 旧版（声明式） Old (Declarative) | 本版（硬拦截） New (Hard-Block) |
||---|---|---|
|| 危险谁判定 Who judges danger | agent 自觉填 `red_flags` agent fills `red_flags` voluntarily | **代码直接扫文件内容** code scans file content directly |
|| 拦不拦得住 Block or not | 不拦，仅提醒 no block, only warns | **命中高危 → 宿主协议 deny → 硬性拦截** high-risk hit → host deny → hard block |
|| 触发方式 Trigger | 靠 agent 记得跑 relies on agent remembering | **hook 在写入/复用发生的那一刻自动跑** hook runs the moment write/reuse happens |
|| 漏报后果 Miss consequence | 静默失效 silent failure | 漂移自查在累积前暴露趋势 drift self-check exposes trend before accumulation |

> **🛑 STOP · 一句话立场**：进化优化的是**任务结果**，不是**程序安全**——一次"成功"不等于"做法安全"。

One-line stance: Evolution optimizes the **task outcome**, not **program safety** — one "success" ≠ "safe practice."

---

## ⚡ 新手快速开始 | Quick Start（零学习成本）

**这个护栏是干什么的？** 当 Agent 把"成功经验"固化成技能/记忆/流程，或复用已有技能时，用三道闸硬代码扫描文件内容，命中高危即按宿主协议 `deny` 硬拦截——防"小错累积成大错而不自知"。

**怎么触发？** 装为插件后**全自动**，不需要你手动跑；hook 在写入 / 复用 / 会话开始的瞬间触发。你也可以手动调用验证：

```
✅ "帮我审一下刚写的 xxx skill，看有没有把危险做法固化进去"
✅ "对 unclekk-xxx 跑一次漂移自查，看不安全率有没有超阈值"
✅ "我要改 SKILL.md，先跑写入期护栏确认不会误伤正常内容"
✅ "这个技能准备复用，先过一下复用期血缘闸"
✅ "给我看上次的审计日志和漂移报告"
```

**一句话上手**：复制上面任意一句发出来 → 护栏自动扫描 → 命中高危就拦，正常内容放行，你只管看结果。

---

## 🔴 CHECKPOINT · 三道闸概览

| 闸 | 触发时机 | 核心动作 | 拦截信号 | 超时阈值 |
|---|---|---|---|---|
| 闸一 | Write/Edit/MultiEdit指向SKILL.md/MEMORY.md | 调用`redflags.scan_text`扫描内容 | `permissionDecision=deny` | 15秒 |
| 闸二 | Skill工具即将加载技能 | 查审计日志+直扫全目录 | `permissionDecision=deny` | 15秒 |
| 闸三 | 每次写入后 + SessionStart | 扫全库SKILL.md+算不安全率 | systemMessage 告警（非硬拦截） | 30秒 |

---

## 三道闸（全部由代码自动执行，无后台轮询） | Three Gates (All Auto-Executed by Code, No Background Polling)

> 三道闸的触发时机与拦截信号见上方「🔴 CHECKPOINT · 三道闸概览」表格（唯一权威定义，避免重复维护导致不一致）。

---

### 闸一：写入期硬拦截（PreToolUse · `scripts/write_gate.py --mode pre`） | Gate 1: Write-Phase Hard Block

**触发条件**：Write / Edit / MultiEdit 工具指向以下文件：
- `SKILL.md`（技能定义文件）
- `MEMORY.md`（记忆文件）
- `.workbuddy/memory/` 目录内任何文件
- `.hermes/skills/*/SKILL.md`（Hermes Agent技能目录）

**输入规格**：
| 工具 | 字段 | 提取方式 |
|------|------|----------|
| Write | `content` | 直接取 `content` 字符串 |
| Edit | `new_string` | 取 `new_string` 字段 |
| MultiEdit | `edits` | 取全部 `edits` 数组，合并所有 `new_string` |

**动作**：调用 `redflags.scan_text(text)` 做客观扫描。

**判定**：
| 严重度 | 信号 | 动作 |
|--------|------|------|
| 🔴 HIGH | `permissionDecision=deny` | 宿主协议拦截，写入失败 |
| ⚠️ MEDIUM | `permissionDecision=warn` | 仅告警，写入放行 |
| ℹ️ LOW | `permissionDecision=info` | 仅记录，写入放行 |

**🛑 STOP · 非固化类文件（普通代码、数据）一律放行，绝不误伤正常开发。**
Non-hardening files (ordinary code, data) are always allowed — normal development is never falsely blocked.

**内联放行标记（有意为之的文档用）**：若需在技能里正文档一个高危示例（如安全教程展示真实格式密钥），可在文件注释中写 `# guard:allow:<rule_id>`（例如 `bypass.disable_auth`）显式放行**精确**那条规则。约束：① 仅接受精确 rule id，**`# guard:allow:all` 已被代码拒绝**（否则内容自携开关即可解除整条闸一，是自毁开关）；② `hardcoded_secret` 类（真密钥）**永远不可放行**；③ 被放行的高危命中仍强制输出"放行复核"提醒并记入审计。这是把"无意识泄露"转为**有意识、可审计的放行决策**，与护栏"防不自知"初衷一致。
**Inline allow marker (for intentional documentation):** To document a high-risk example on purpose, add `# guard:allow:<rule_id>` (e.g. `bypass.disable_auth`) in a file comment to explicitly allow that **exact** rule. Constraints: ① only an exact rule id is accepted — `# guard:allow:all` is **rejected by code** (a self-destruct switch); ② `hardcoded_secret` rules (real keys) can **never** be allowed; ③ an allowed HIGH hit still emits a "放行复核" reminder and is logged. This converts "unconscious leak" into a conscious, auditable allow decision.

---

### 🔴 CHECKPOINT · 闸二：复用期血缘拦截（PreToolUse · `scripts/reuse_gate.py`） | Gate 2: Reuse-Phase Lineage Block

**触发条件**：Skill工具即将加载某技能（`Skill(name=...)` 调用前）。

**输入规格**：技能名称 / 技能路径。

**动作**：
1. 读审计日志 `audit/audit-log.jsonl`
2. 取该技能最新记录（按timestamp排序）
3. 检查 `retired` 字段 和 `lineage_risk` 字段

**判定**：
| 条件 | 信号 | 动作 |
|------|------|------|
| `retired=true` | `permissionDecision=deny` | 拦截复用，提示先归因修复 |
| `lineage_risk=high` | `permissionDecision=deny` | 拦截复用，提示先归因修复 |
| `lineage_risk=critical` | `permissionDecision=deny` | 拦截复用，提示先归因修复 |
| 无审计记录 | 直扫全目录 | 任一HIGH → deny |

**🛑 STOP · 血缘风险必须追溯源头，不能仅凭当前内容放行。**
Lineage risk must be traced to source — current content alone doesn't guarantee safety.

---

### 🔴 CHECKPOINT · 闸三：漂移自查（PostToolUse + SessionStart · `scripts/drift_report.py`） | Gate 3: Drift Self-Check

**触发条件**：每次写入后 + 会话开始时。

**动作**：
1. 扫全库 SKILL.md 文件（默认扫描 `~/.workbuddy/skills`、`~/.workbuddy/skills-marketplace/skills`、`~/.hermes/skills`、`~/.workbuddy/memory`，可用 `--scan DIR` 追加目录）
2. 计算不安全率 = HIGH规则命中数 / 总文件数
3. 自适应阈值（按库规模分桶）：小型库(≤50篇)=10% / 中型库(51–300篇)=20% / 大型库(>300篇)=30%；未显式指定 `--unsafe-threshold` 时自动采用
4. 不安全率超阈值 → exit code 2 + 输出告警

**判定**：
| 不安全率 | 信号 | 动作 |
|----------|------|------|
| ≤ 阈值 | 无输出 | 健康，继续运行 |
| > 阈值 | systemMessage 告警（不硬拦截） | 输出告警，建议停用复核 |

**🛑 STOP · 漂移自查不拦截写入，只暴露趋势——让决策者知道"水在变浑"。**
Drift self-check doesn't block writes, only exposes trends — lets decision-makers know "the water is getting murky."

---

## 34 条检测规则 | 34 Detection Rules

按严重度：🔴 HIGH 13 / ⚠️ MEDIUM 19 / ℹ️ LOW 2（共 34）。

| 类别 | 规则数 | 示例 |
|------|--------|------|
| 硬编码密钥 hardcoded_secret | 8 | GitHub PAT, OpenAI, Anthropic, Stripe, AWS, Slack, Google, 私钥块 |
| 绕过安全 bypass_safety | 9 | bypass/disable 表述, no-verify, chmod 777, curl｜sh, 关 TLS/鉴权, base64｜sh, subprocess shell=True |
| 破坏性操作 destructive | 6 | rm -rf 关键路径/本地, git reset --hard, DROP TABLE, 格式化磁盘, git push --force |
| 动态执行 dynamic_exec | 7 | eval(外部串), os.system, shell=True, new Function, exec(), os.popen, IEX |
| 跳过确认 skip_confirm | 1 | 跳过确认/假定已授权 |
| 环境特定 env_specific | 2 | 硬编码绝对路径, export 长常量 |
| 临时泛化 temp_to_default | 1 | 永远/默认式表述 |

完整规则见 `scripts/redflags.py`（代码客观判定，可独立 `python redflags.py <file>` 调试）。

---

## 能力边界说明 | Capability Boundary

### ✅ 擅长处理（硬拦截护栏能覆盖的）
1. **写入固化拦截**：Write / Edit / MultiEdit 指向 `SKILL.md` / `MEMORY.md` / 记忆目录 / Hermes 技能目录时，扫到硬编码密钥、`rm -rf`、bypass 等高危即 `deny`。
2. **复用血缘拦截**：加载技能前查审计日志，`retired` / `lineage_risk=high` / `critical` 即 `deny`，强制先归因修复。
3. **漂移自查**：周期性扫全库，计算不安全率，超自适应阈值即 systemMessage 告警。
4. **有意识放行**：用 `# guard:allow:<rule_id>` 精确放行文档性高危示例，仍留审计痕迹，把"无意识泄露"转为"有意识放行"。

### ⚠️ 需要素材才能做
1. **判定某次"成功"是否真安全**：需提供该次改动的文件内容——只看结论无法判定危险。
2. **复用闸信用评估**：需该技能的 `audit-log.jsonl` 记录才能判定血缘风险；无记录时退化为直扫全目录。
3. **自定义阈值 / 目录**：需用户显式传入 `--unsafe-threshold` / `--scan` 参数才生效，否则用默认自适应。

### ❌ 超出范围（附替代方案）
1. **帮你写 Skill 内容**：本护栏只扫描拦截，不生成 Skill → 用 `skill-creator`。
2. **实时运行时防护（拦截已运行进程）**：本护栏是写入 / 复用期静态扫描，非 RASP → 用专门运行时防护方案。
3. **跨设备云端同步拦截**：本护栏基于本地文件系统扫描 → 用 `cross-agent-memory` 同步后再扫。
4. **自动修复高危内容**：本护栏只拦截 + 告警，不自动改写 → 由人工或 agent 修复后重试写入。

---

## 受众说明 | Who Should Use This

| 用户类型 | 如何使用 |
|---------|---------|
| **个人 Agent 开发者** | 装为 WorkBuddy / Hermes 插件，hook 自动跑，零手动介入 |
| **团队安全负责人** | 作为 CI / 合并前卡点，审计日志留痕可追溯 |
| **审核员 / 合规** | 用 audit-report 与漂移自查报告作为统一评审基线 |
| **初学者** | 先读上方"新手快速开始"，再用测试用例验证拦截是否生效 |

---

## 定制化使用指南 | Customization

可在触发或调用脚本时传入以下参数定制行为：

- **阈值覆盖**：`drift_report.py --unsafe-threshold 0.15` 覆盖默认自适应阈值。
- **扫描目录**：`drift_report.py --scan DIR` 追加扫描目录（默认扫 `~/.workbuddy/skills`、`~/.workbuddy/skills-marketplace/skills`、`~/.hermes/skills`、`~/.workbuddy/memory`）。
- **精确放行**：在文件注释写 `# guard:allow:<rule_id>` 放行某条精确规则（`hardcoded_secret` 真密钥类永远不可放行）。
- **输出格式**：`--json` 输出结构化指标（`{"status","unsafe_rate","alerts"}`），便于接入看板。
- **触发词裁剪**：`frontmatter` 的 `triggers` 可按项目增删中文触发词。

---

## 安装与验证 | Install & Verify

### 步骤1：安装插件

```bash
# WorkBuddy 环境
cp -r unclekk-pmu-misevolution-guard ~/.workbuddy/plugins/

# Hermes Agent 环境（用户级skill）
cp -r unclekk-pmu-misevolution-guard ~/.hermes/skills/
```

### 步骤2：验证文件完整性

```bash
cd ~/.workbuddy/plugins/unclekk-pmu-misevolution-guard
test -f SKILL.md && echo "✓ SKILL.md 存在" || echo "✗ SKILL.md 缺失"
test -d scripts && echo "✓ scripts/ 目录存在" || echo "✗ scripts/ 目录缺失"
test -f hooks/hooks.json && echo "✓ hooks.json 存在" || echo "✗ hooks.json 缺失"
test -f scripts/redflags.py && echo "✓ redflags.py 存在" || echo "✗ redflags.py 缺失"
```

**预期输出**：全部显示 `✓ ...存在`

---

### 步骤2：验证硬拦截是否生效

**测试用例1：含密钥的写入（应被拦截）**
```
新建测试 SKILL.md，写入一行含真实格式密钥：
sk-abcdef1234567890ghijklmnop
```
**预期结果**：写入被拦截，提示 `检测到疑似 OpenAI 格式硬编码密钥`

---

**测试用例2：绕过安全机制（应告警）**
```
写入一行：绕过安全检查
```
**预期结果**：写入放行，但输出告警 `检测到'绕过/禁用安全机制'表述`

---

**测试用例3：正常内容（应放行）**
```
写入：本技能用于整理每日笔记
```
**预期结果**：写入正常放行，无告警

---

### 步骤3：验证漂移自查

**触发条件**：会话开始时自动运行

**预期输出**（默认文本报告；加 `--json` 输出结构化指标）：
```
============================================================
  Skill Misevolution 漂移自查报告（内容扫描版）
============================================================
  [审计日志] D:\...\audit\audit-log.jsonl
  写入期 / 复用期事件 : 2 / 0
  审计中不安全创作     : 0/2  (0.0%)
  累计 carryover 危害  : 0
  已退役技能事件       : 0
  血缘风险分布         : {'low': 2}
------------------------------------------------------------
  不安全率阈值         : 30%  (自适应(库规模 426 篇))
  [技能库内容扫描] 扫描目录数: 4
  扫描 SKILL.md 总数   : 426
  含高危模式(HIGH)     : 4/426  (0.9%)
============================================================
  状态: 未触告警。继续保持每次进化都受护栏约束的纪律。
============================================================
```

**异常情况**：
- 不安全率 > 阈值（且大库需同时达到绝对数门槛）→ 输出 `{"systemMessage": ...}` 告警（闸三为**报告式**，不硬拦截写入），exit code 2。
- `--json` 模式输出 `{"status":"alert"|"ok", "unsafe_rate":..., "alerts":[...]}`，便于结构化集成。

---

### 步骤4：兜底方案（如hooks未自动加载）

**方案A：手动挂载插件**
```bash
# 复制skill目录到WorkBuddy插件目录
cp -r unclekk-pmu-misevolution-guard ~/.workbuddy/plugins/

# 编辑 settings.json，添加enabledPlugins
echo '{"enabledPlugins": ["unclekk-pmu-misevolution-guard"]}' >> ~/.workbuddy/settings.json
```

**方案B：合并hooks到现有插件**
```bash
# 读取本skill的hooks.json
cat ~/.workbuddy/plugins/unclekk-pmu-misevolution-guard/hooks/hooks.json

# 合并到已启用插件的hooks.json（手动编辑）
```

---

**🛑 STOP · 验证失败处理**：
| 症状 | 原因 | 处理 |
|------|------|------|
| 密钥写入未被拦截 | redflags.py未加载 | 检查PYTHONHOME环境变量 |
| hooks.json报错 | WorkBuddy版本过旧 | 升级到支持用户级skill的WorkBuddy |
| 漂移自查超时 | 技能库过大 | 降低扫描频率，仅保留SessionStart |

---

## 🛑 STOP · 运行纪律（护栏自身的行为约束）

**错误处理规范**：护栏自身向用户 / 宿主输出的所有信息一律为用户语言，**禁止向上抛出 `ImportError` / `FileNotFoundError` 等技术异常**；任何"缺少某条件"的提示必须采用「缺少[具体项] + 如何补充」格式（如"缺少 hooks.json → 请执行步骤4方案A挂载"），绝不允许笼统说"出错了"。

**隐私与数据处理**：护栏只在本地读取被写入 / 被复用文件的内容做模式匹配，**不向任何外部地址回传、不上传文件内容**；审计日志 `audit-log.jsonl` 仅落在本机目录，记录"命中规则 / 严重度 / 时间 / 血缘风险"等元数据而非文件全文；若需在技能中引用真实密钥作教学示例，须用 `guard:allow:<rule_id>` 显式放行并脱敏（真密钥永远不可放行）。

**信息不足时降级**：本护栏以 hook 自动触发为主、无需用户输入；若被手动调用且输入模糊（如"帮我看看"），**先给一个基于默认假设的版本**（默认跑全库漂移自查），再追问是否需要限定目录 / 阈值，绝不挂起等待也不给空回复。

**判定纪律（禁止胡编）**：所有拦截 / 放行判定一律以 `redflags.py` **代码扫描的客观结果为准**，绝不基于"感觉危险""可能不安全"等猜测放行或拦截；输出中命中项须注明命中的规则 id 与严重度，决策逻辑可追溯。

---

## 🔴 CHECKPOINT · 反例黑名单（本skill优化时不要做的事）

| # | 反模式 | 为什么不要做 | 替代做法 | 归因类型 |
|---|--------|--------------|----------|----------|
| 1 | **把护栏当建议性提醒** | 护栏是硬代码，不是文档示例，应靠代码判定而非agent自觉 | 用`permissionDecision=deny`硬拦截，不是"建议谨慎" | 技能缺陷 |
| 2 | **静默放行高危内容** | 放过一次后可能有累积效应，"小错累积成大错"正是本skill要防的 | HIGH规则必须拦截，不靠agent判断是否"真危险" | 技能缺陷 |
| 3 | **用guard:allow:all绕过关键规则** | 作者若主动加`guard:allow:all`到含真实密钥的文件，护栏即被放开 | 用`guard:allow:<rule_id>`精确放行，不放开整条规则 | 技能缺陷 |
| 4 | **忽略漂移自查的阈值变化** | 库规模变化时阈值自适应，但agent可能仍用旧阈值判断 | 报告中标注阈值来源（自适应/显式），按报告执行 | 执行失误 |
| 5 | **把测试密钥写入真实技能文件** | 测试时用真实格式密钥会触发误报，破坏技能可用性 | 用`guard:allow:<rule_id>`标记测试内容，或改用占位符 | 执行失误 |
| 6 | **复用闸只扫SKILL.md** | 危险逻辑可能藏在scripts或references中 | 无审计记录时直扫全目录（SKILL.md + scripts/*.py + references/*.md） | 技能缺陷 |

> 以上为速览；完整「反模式分类 + 错误写法 vs 正确写法对比」见 `references/anti-patterns.md`。

---

## 🛑 STOP · 失败模式编码（三段式fallback）

| 场景 | 触发条件 | 一线修复 | 仍失败兜底 |
|------|----------|----------|------------|
| hooks.json 加载失败 | WorkBuddy 未自动发现用户级skill的hooks | 把hooks.json合并到已启用插件 | 手动加载脚本，用CLI替代hook |
| 脚本文件找不到 | 路径解析错误 / python缺失 | 检查`${CODEBUDDY_PLUGIN_ROOT}`注入 | 改用绝对路径或手动指定脚本路径 |
| 审计日志损坏 | JSONL格式错误 / 文件锁冲突 | 备份后重建审计日志 | 清空旧日志，从当前写入重新开始 |
| 漂移自查超时 | 技能库过大 / 文件扫描耗时 | 降低扫描频率（仅SessionStart） | 跳过漂移自查，依赖闸一/闸二 |
| 误拦正常技能写作 | 正则过于宽泛 / MEDIUM误判为HIGH | 检查`guard:allow`标记是否正确 | 向规则维护者反馈，调整正则 |
| 放行标记滥用 | 作者用`guard:allow:all`掩盖真实密钥 | 人工审计标记记录 | 拒绝放行，要求改用环境变量 |
After the fallback, all three gates fire automatically end-to-end.

---

## 常见问题 FAQ（通用）

**Q1：装好之后需要我手动跑吗？**
不需要。hook 在写入 / 复用 / 会话开始的瞬间自动触发三道闸；你只需像平时一样写技能，护栏默默在后台判。

**Q2：正常写代码会被误拦吗？**
不会。闸一只拦固化类文件（`SKILL.md` / `MEMORY.md` / 记忆目录 / Hermes 技能目录）；普通代码、数据文件一律放行。

**Q3：测试时想写个示例密钥但被拦了怎么办？**
用 `# guard:allow:<rule_id>` 精确放行那条规则（如 `bypass.disable_auth`），或在示例里用占位符 `sk-xxxx` 而非真实格式串；真密钥永远不可放行。

**Q4：漂移自查报了告警，是不是写入被拦了？**
不是。闸三只暴露趋势、不硬拦写入，你仍可读告警决定要不要停用复核。

**Q5：阈值怎么定？**
默认按库规模自适应（≤50篇 10% / 51–300篇 20% / >300篇 30%）；可用 `--unsafe-threshold` 显式覆盖。

**Q6：审计日志在哪？**
在技能目录的 `audit/audit-log.jsonl`，记录命中规则、严重度、时间、血缘风险等元数据。

**Q7：能只扫某个目录吗？**
能，`drift_report.py --scan DIR` 追加扫描目录；复用闸在无审计记录时会直扫全目录（SKILL.md + scripts + references）。

> 更深的边缘场景（并发、规则改名、大库采样、误判申诉等）见 `references/faq-deep.md`。

---

## 参考文件 | Reference Files

- `references/red-flags.md` — 会累积成大事的"小错"清单（含检测问题与复利机制）
  `references/red-flags.md` — the "small errors" list that compound into big ones (detection questions + compounding mechanism)
- `references/audit-log.md` — 审计日志 JSONL 格式与字段
  `references/audit-log.md` — audit-log JSONL format and fields
- `references/anti-patterns.md` — 反模式分类 + 错误写法 vs 正确写法逐条对比（深度版）
  `references/anti-patterns.md` — anti-pattern categories with wrong-vs-right contrasts (deep version)
- `references/faq-deep.md` — 深度 FAQ（边缘场景 / 工具兼容 / 安全合规）
  `references/faq-deep.md` — deep FAQ (edge cases / tool compatibility / security compliance)
- `scripts/redflags.py` — 危险模式正则库（硬代码核心，可独立 `python redflags.py <file>` 调试）
  `scripts/redflags.py` — dangerous-pattern regex library (hard-code core; debug standalone with `python redflags.py <file>`)
- `scripts/write_gate.py` — 写入期拦截 + 审计记录
  `scripts/write_gate.py` — write-phase block + audit logging
- `scripts/reuse_gate.py` — 复用期血缘拦截
  `scripts/reuse_gate.py` — reuse-phase lineage block
- `scripts/drift_report.py` — 漂移自查（内容扫描版）
  `scripts/drift_report.py` — drift self-check (content-scan version)
- `hooks/hooks.json` — 自动触发配置（PreToolUse / PostToolUse / SessionStart）
  `hooks/hooks.json` — auto-trigger configuration (PreToolUse / PostToolUse / SessionStart)

## 版本与 lineage（1.4.0）

本版为**合并版**：以本地 1.2.1（含 ③ 误报专项修复 + 双轨 master→cache 同步 + 34 探针解耦 schema（用 `{{GIT_RESET_HARD}}` 等专属占位符，分发包无真实危险载荷））为 base，叠加 SkillHub 1.3.0 的云鼎实验室安全整改的**非 schema 部分**（hook fail-open 可见化、retry 重试、test-prompts-v3、独立审计/演进文档、pmu_guard/setup/_meta）。redflags.py 分类器保留全部 ③ 豁免（代码注释 / 否定语境 / 窄否定 / 自有路径），蜜罐探针 34 条、34 条规则全覆盖、FP 率 2.6%。1.3.0 的 43 探针 schema 因与 ③ 豁免冲突且覆盖更弱而未采纳（改留本地解耦 schema）。详细变更见 CHANGELOG [1.4.0]。
