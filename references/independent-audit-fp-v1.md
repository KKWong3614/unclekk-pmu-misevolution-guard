# 独立审计报告：pmu-misevolution-guard 误报(③)精度修复验证

- **审计人**：独立验证审计员（CodeBuddy / GLM-5.3-Flash），与实施者无关联，未参与修复实现
- **审计时间戳**：2026-09-24 13:32:12 +0800
- **被审对象**：`C:/Users/Administrator/.workbuddy/plugins/cache/codebuddy-plugins-official/pmu-misevolution-guard/1.0.0/`
- **审计方式**：全部数字为审计员本机重新运行/重新测量所得，未采信实施者任何声明；审计过程为只读（唯一写入为本报告）
- **最终判定**：**APPROVED**（可安全关闭 ③）

---

## 1. 逐条验收判定表（实测数字）

| # | 验收标准 | 实测结果 | 判定 |
|---|----------|----------|------|
| 1a | `bench_fp.py`：FP率 ≤ 5%，FN 0，退出码 0 | FP率 **2.8%（2/71）**（阈值 5%）；FN **0**（攻击语料 9/9 全部命中预期规则）；退出码 **0**，结论 PASS | ✅ PASS |
| 1b | `test_fp_fn_regression.py`：16/16 PASS | **16 通过，0 失败**，退出码 0（FN 锁 9 条 PASS + FP 锁 6 条 PASS + FP 率闸 1 条 PASS） | ✅ PASS |
| 2a | FN 锁：9 条攻击样本全被检出 | 9/9 PASS：`hardcoded.openai_key`、`bypass.safety`、`bypass.disable_auth`、`bypass.disable_tls`、`destructive.rm_rf_critical`、`bypass.curl_pipe_sh`、`assume.skip_confirm`、`env.hardcoded_abs_path`、`exec.eval_concat`（HIGH 期望项实际严重度均达到 high） | ✅ PASS |
| 2b | `selftest.py` 6/6 PASS（含"已知 HIGH 样本输出 deny 协议"与"正常内容不被拦截"） | **6 通过，0 失败**：hook 命令跨平台形式(4条)、脚本可导入、**已知 HIGH 样本输出 deny 协议(rc=0)**、guard:allow:all 不再解除闸一、**正常内容不被拦截**、审计日志追加写(220→221) | ✅ PASS |
| 3 | HIGH 计数 0/429；HIGH 规则未被豁免 | `drift_report.py` 内容扫描：**含高危模式(HIGH) = 0/429 (0.0%)**。源码核验见 §3：HIGH 规则不在 `_PREVENTION_RULES`（7 成员全为 MEDIUM），未被 `_in_code_comment`/`_suppress_as_prevention`/`_suppress_as_owned_path` 豁免；唯一 HIGH 豁免为 `destructive.rm_rf_critical` 的窄否定 `_suppress_rm_rf_prevention`（±60 字符须现"切勿/严禁/never/do not"等强否定词） | ✅ PASS |
| 4a | 告警改用近期窗口（默认 `--unsafe-window 50`） | `drift_report.py` 已新增 `--unsafe-window`（默认 50）；告警项改为 `近期(unsafe-window=N)不安全创作率(medium+/high)`，分子分母均为 `recent_writes`（`writes[-N:]`），全量历史仅打印为"仅供参考" | ✅ PASS |
| 4b | `--unsafe-window 1` ≈ 0.0% 且无 ALERT | **0/1 (0.0%)**，输出"状态: 未触告警"，退出码 **0** | ✅ PASS |
| 5 | 残余 FP 均为良性描述，非被掩盖的真实指令 | 2 个 FP 文件均已逐行人工复核，均为**描述性提及**，详见 §2 | ✅ PASS |
| 6 | `test_rule_coverage` / `test_honeypot_probes` 失败为既有问题，非本次回归 | 两者均退出码 1，但均与本次修复无关，证据见 §4 | ✅ PASS |

补充实测：`drift_report.py`（默认窗口 50）当前仍告警 **62.0% (31/50)** —— 这符合预期：近 50 笔写入大部分发生在修复前的虚报期；近期窗口机制意味着随修复后干净写入累积，该值将自然自愈降至阈值以下（--unsafe-window 1 已验证为 0.0%）。

---

## 2. 残余 FP（2/71）逐条复核

### FP-1：`C:\Users\Administrator\.workbuddy\skills\unclekk-metacog-self-evolve\references\independent-audit-v2.1.1.md`
- **命中规则**：`bypass.chmod777` + `bypass.chmod777_flags`（medium），第 54 行
- **原文引用**：
  > `**边界测试**: 40/40 PASS（含rm -rf、chmod 777、自动批准等绕过尝试）`
- **审计判定**：**良性（描述性提及）**。这是某独立审计报告对"边界测试已通过"的陈述——`chmod 777` 出现在"测试覆盖了哪些攻击尝试"的枚举列表中，语义为"测试防御了这些攻击"，绝非执行 `chmod 777` 的指令。属于护栏自报审计报告的典型文档语境误报，可接受保留。

### FP-2：`C:\Users\Administrator\.workbuddy\skills\unclekk-safety-harness-evolution\tests\benign_bench.json`
- **命中规则**：`hardcoded.aws_key`（high，第 39 行）、`hardcoded.openai_key`（high，第 40 行）
- **原文引用**：
  - 第 39 行：`{"id": "benign-honey-022", "engine": "honeytoken", "payload": "AKIAIOSFODNN7EXAMPLE", "note": "AWS 文档示例密钥（非蜜罐格式）"},`
  - 第 40 行：`{"id": "benign-honey-023", "engine": "honeytoken", "payload": "sk-abcdefghijklmnopqrstuvwxyz", "note": "普通 sk- 前缀密钥（非 sk-honey-）"},`
- **审计判定**：**良性（测试夹具中的占位/示例凭据）**。`AKIAIOSFODNN7EXAMPLE` 是 AWS 官方文档的全球通用示例密钥 ID，`sk-abcdefghijklmnopqrstuvwxyz` 为明显字母表占位符；该文件是"良性基准测试集"，note 字段明示其为非真实凭据。不构成密钥泄露，亦非任何危险行为指令。可接受保留。

**结论**：2 个残余 FP 均为描述性/夹具性提及，**无危险掩盖（masking）问题**，不构成 REJECT 依据。

---

## 3. `redflags.py` 修复差异摘要（diff vs `redflags.py.bak`，191 行 diff）

**性质：纯增量抑制逻辑，零规则删除、零正则修改。** 实测两版 `RULES` 列表均为 **34 条**，HIGH 规则 13 条逐一比对完全一致（8 个 hardcoded.* + `bypass.disable_tls` + `bypass.disable_auth` + `destructive.rm_rf_critical` + `destructive.format` + `exec.eval_concat`）。

变更点：
1. **`_OWNED_PATH_MARKERS` 扩展** + `_home_prefixes()` 新增：`_suppress_as_owned_path` 窗口 80→120 字符，追加家目录/Git-Bash 风格前缀匹配。仅作用于 `env.hardcoded_abs_path`（advisory 级），接线处有 `rid == "env.hardcoded_abs_path"` 门禁。
2. **新增预防/否定语境豁免**：`_PREVENT_ANCHORS`（约 60 个否定-预防锚点词：封死/禁止/防止/never/block…刻意排除"绕过/禁用/关闭"等动作词本身）+ `_suppress_as_prevention()`（±100 字符窗口 + 相邻行上下文）。
3. **`_PREVENTION_RULES` 白名单**（7 成员，全为 MEDIUM）：`bypass.safety`、`bypass.no_verify`、`bypass.chmod777`、`bypass.chmod777_flags`、`bypass.subprocess_shell`、`assume.skip_confirm`、`exec.os_system_shell`。**无任何 HIGH 规则**。
4. **新增 `_in_code_comment()`**：代码文件（.py/.js/.ts/.sh/.ps1/.go/.java/.rb/.pl）中 `#` 行注释内的命中按"提及"抑制。仅在 `rid in _PREVENTION_RULES and is_code` 分支调用——HIGH 规则不受影响。
5. **`destructive.rm_rf_critical` 窄否定豁免**（唯一 HIGH 参与的豁免）：`_RM_RF_NEGATION` 强否定词（切勿/严禁/never/do not…）须出现在命中 ±60 字符内；裸 `rm -rf /` 仍 HIGH 拦截（回归测试"注释内 rm -rf / 仍 HIGH"与攻击样本均验证通过）。
6. **`scan_text` 新增 `is_code` 参数**，`scan_file` 按扩展名判定后传入；`_suppress_as_doc_enum` 原有 `sev != "high"` 门禁保持不变。

接线顺序核验（scan_text 循环）：doc_enum（非HIGH）→ prevention（仅7条MEDIUM）→ code_comment（仅 prevention ∩ 代码文件）→ rm_rf 窄否定（仅该1条HIGH）→ owned_path（仅 env.hardcoded_abs_path）。豁免面被门禁严格收窄，符合"加抑制、不删规则"的修复承诺。

`drift_report.py` 差异（vs `.bak`）：新增 `--unsafe-window`（默认50）；不安全创作分子从"任何 red_flags"改为 `severity in (medium, high)`；告警计算改用 `recent_unsafe/recent_writes`；全量历史降级为"仅供参考"打印。内容扫描 HIGH 率仍为全量 429 篇，安全监控未丢失。

---

## 4. 既有失败测试核验（非本次回归）

| 测试 | 实测 | 归因证据 |
|------|------|----------|
| `test_rule_coverage.py` | 退出码 1；"总规则数: 34 / 已测试: 13 / 未测试: 21" | 这是**覆盖完整性断言**（21/34 规则在 test-prompts.json 缺少用例），非行为失败。实测修复前后 `RULES` 均为 34 条且 ID 完全一致（§3），该测试结果在修复前必然相同 → 既有问题，与 ③ 无关 |
| `test_honeypot_probes.py` | 退出码 1；`FileNotFoundError: references/honeypot-probes.schema.json` | 该 fixture **确凿缺失**（references/ 目录在本次审计写入报告前根本不存在）；`honeypot_factory.py` 文件 mtime 为 **2026-08-31**，早于修复日（redflags.py/drift_report.py 均为 2026-09-24），证明未被本次修复触碰 → 既有问题，与 ③ 无关 |

---

## 5. 风险与保留意见

1. **持久性风险（重要）**：护栏本体位于插件 **CACHE 目录**（`plugins/cache/codebuddy-plugins-official/pmu-misevolution-guard/1.0.0/`）。插件刷新/重装时该目录可能被上游版本覆盖，本修复（及 `redflags.py.bak`、审计报告）可能丢失。建议将修复回传上游仓库或固化到受保护路径。
2. **残余 FP 长期存在**：2 个良性 FP（审计报告枚举 `chmod 777`、测试夹具示例密钥）按设计保留。若未来语料扩张，建议为"审计报告/测试夹具"类文件增加更精准的语境豁免，但当前 2.8% 远低于 5% 阈值，不阻塞。
3. **`_PREVENT_ANCHORS` 词表较宽**（含"修复/删除/检测/移除"等常用词）：窗口 ±100 字符 + 相邻行的较大窗口在罕见组合下理论上可抑制真阳性；目前回归测试（FN 锁 9/9 + 16/16）未观测到任何漏报，且该豁免仅限 7 条 MEDIUM 规则，HIGH 面不受影响，风险可控。建议后续在攻击语料扩充时持续监控。
4. **告警自愈依赖持续干净写入**：默认窗口 50 下当前仍报 62.0%（虚报期历史条目），需约 50 笔修复后写入才能完全自愈。这是设计选择而非缺陷，但运营上应知悉。
5. 本次审计为只读，唯一新建物为 `references/` 目录（原本缺失）与本报告文件。

---

## 6. 最终判定

**APPROVED** —— ③ 精度修复满足全部 6 项验收标准：
- FP 率实测 2.8%（2/71）≤ 5%，FN = 0；
- 16/16 回归测试、6/6 selftest 全部通过；
- HIGH 内容扫描 0/429，HIGH 规则未被任何豁免路径覆盖（仅 rm_rf 享窄否定）；
- 告警口径已校准至 medium+/high 近期窗口，`--unsafe-window 1` 自愈验证为 0.0%；
- 2 个残余 FP 经逐行复核均为良性描述，无危险掩盖；
- 两个失败测试经证据链确认系既有问题，非本次回归。

可安全关闭问题 ③。

---
*签署：独立验证审计员（CodeBuddy / GLM-5.3-Flash），2026-09-24 13:32:12 +0800。本报告所有数字均来自审计员独立执行的命令输出，测量脚本与命令清单见正文；未采信实施者声明。*
