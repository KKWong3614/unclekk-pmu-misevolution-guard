# 审计日志格式（Audit Log）

> 本文件由护栏**自动维护**，无需手动编辑。
> 位置：`audit/audit-log.jsonl`（随本 skill 一起）。
> `write_gate.py`(post 模式) 在每次"经验固化"文件写入后追加一行；`reuse_gate.py`
> 在复用拦截时读取它判断血缘风险。

---

## 字段定义（与代码实现一致）

| 字段 | 类型 | 说明 | 取值 |
|---|---|---|---|
| `ts` | string | ISO 8601 时间戳（本地时区自动派生，见 `write_gate.now_iso()`） | `2026-08-27T11:00:00+08:00` |
| `phase` | string | 事件阶段 | `write` / `reuse` |
| `skill` | string | 技能 / 记忆名（由路径推断） | `auto-send-report` |
| `path` | string | 被写入文件的绝对路径 | `.../skills/auto-send-report/SKILL.md` |
| `outcome_ok` | bool | 任务结果是否达成 | `true` / `false` |
| `red_flags` | array | 命中的危险模式 ID（来自 `redflags.py`） | `["hardcoded.openai_key","env.hardcoded_abs_path"]` |
| `severity` | string | 本次命中最高严重度 | `low` / `medium` / `high` |
| `lineage_risk` | string | 血缘风险等级（复用期评估依据） | `low` / `medium` / `high` |
| `repaired` | bool | 是否做了局部修复 | `true` / `false` |
| `retired` | bool | 该技能是否已退役 | `true` / `false` |
| `carryover_harm` | bool | 是否造成跨会话 / 跨任务危害 | `true` / `false` |
| `utility` | null/float | 效用评分（预留） | `null` |

---

## red_flags ID 词表（来自 `scripts/redflags.py`，代码客观判定）

HIGH（写入期硬拦 / 复用期高危）：
```
hardcoded.openai_key         OpenAI 格式硬编码密钥 (sk-...)
hardcoded.aws_key           AWS Access Key (AKIA...)
hardcoded.github_pat        GitHub Personal Access Token
hardcoded.slack_token       Slack Token
hardcoded.private_key       私钥块
bypass.disable_tls          关闭 TLS 校验 (verify=false / insecure=true)
bypass.disable_auth        关闭鉴权 (auth=false / DISABLE_AUTH)
destructive.rm_rf_critical  关键路径递归删除 (rm -rf / 或 ~ 或 C:\ 等)
destructive.format          格式化磁盘
exec.eval_concat           eval 外部/不可信字符串
```

MEDIUM（仅告警 + 记入审计，不硬拦）：
```
bypass.safety / bypass.no_verify / bypass.chmod777 / bypass.curl_pipe_sh
destructive.git_reset_hard / destructive.sql_drop / exec.os_system_shell
assume.skip_confirm / env.hardcoded_abs_path
```

LOW：
```
pref.temp_to_default        临时偏好泛化为长期默认（永远/默认...）
```

---

## 示例（2 行：写入含高危密钥被记录 → 复用被拦截）

```json
{"ts":"2026-08-27T11:00:00+08:00","phase":"write","skill":"auto-send-report","path":"C:/Users/Administrator/.workbuddy/skills/auto-send-report/SKILL.md","outcome_ok":true,"red_flags":["hardcoded.openai_key"],"severity":"high","lineage_risk":"high","repaired":false,"retired":false,"carryover_harm":false,"utility":null}
{"ts":"2026-08-27T15:30:00+08:00","phase":"reuse","skill":"auto-send-report","path":"","outcome_ok":false,"red_flags":["hardcoded.openai_key"],"severity":"high","lineage_risk":"high","repaired":false,"retired":true,"carryover_harm":true,"utility":0.1}
```

> 该日志是"不自知"解药的数据底座：漂移自查（`drift_report.py`）直接读它算不安全创作率
> 与 carryover 趋势。即使某次危险写入绕过了闸一（如历史遗留技能），闸二在复用前、闸三在
> 每日快照时仍能发现并告警。
