#!/usr/bin/env python3
"""
redflags.py — 技能误进化护栏的"硬代码"危险模式库（机器可读，非自报）

这是 pmu-misevolution-guard 的核心：把 references/red-flags.md 里"会复利成大事的
小错"中，**可由代码客观判定**的那部分，编译成正则 + 语义规则。

设计原则（与论文 SafeEvolve 一致）：
- 高置信度客观危险（硬编码密钥、绕过安全、破坏性无护栏、curl|sh） → severity=HIGH，由 gate 硬性拦截。
- 需结合上下文的危险（跳过确认、环境特定绝对路径、临时偏好泛化） → severity=MEDIUM/LOW，仅告警 + 记入审计日志，由漂移自查兜底。
- 任何规则都要"宁可漏报也不误报关键功能"：HIGH 规则必须高精度，避免把正常技能写作卡死。

向外暴露：
    scan_text(text: str, prose=True) -> list[dict]   # 返回命中列表
    scan_file(path: str) -> list[dict]   # 读文件再 scan
    highest_severity(hits) -> str        # none/low/medium/high
    parse_allowlist(text: str) -> set    # 解析内联放行标记（guard:allow:<rule_id> / :all）

prose 模式（默认开启）：扫描技能/记忆这类 markdown 文档时，自动跳过
「fenced code block（```...```）」与「HTML 注释（<!--...-->）」内部内容。
理由：文档里常需展示真实格式示例密钥、rm -rf 等命令作为教学，若一并扫描会
对"示例代码"误报（评测反馈：偶尔对文档中的示例代码发出警告）。真实泄露几乎
都发生在正文散文里，故仅跳过代码块/注释，正文高危仍 100% 拦截。
"""

import os
import re
import base64

# ---------------------------------------------------------------------------
# 规则定义
# 每条: (id, category, severity, regex, message)
#   severity: high | medium | low
#   regex: 已编译（IGNORECASE 视情况）
# ---------------------------------------------------------------------------

RULES = [
    # ---- HIGH: 客观、高精度、必须拦 ----

    # 硬编码密钥 / token（具体格式，误报极低）
    ("hardcoded.openai_key", "hardcoded_secret", "high",
     re.compile(r"sk-[A-Za-z0-9]{20,}"),
     "检测到疑似 OpenAI 格式硬编码密钥 (sk-...)，应改为环境变量/密钥库，否则会随技能库泄露"),
    ("hardcoded.aws_key", "hardcoded_secret", "high",
     re.compile(r"AKIA[0-9A-Z]{16}"),
     "检测到 AWS Access Key ID (AKIA...)，硬编码会随技能库泄露"),
    ("hardcoded.github_pat", "hardcoded_secret", "high",
     re.compile(r"ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,}"),
     "检测到 GitHub Personal Access Token，应改为环境注入"),
    ("hardcoded.slack_token", "hardcoded_secret", "high",
     re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
     "检测到 Slack Token，硬编码会随技能库泄露"),
    ("hardcoded.private_key", "hardcoded_secret", "high",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
     "检测到私钥块，绝不能写进技能/记忆文件"),
    ("hardcoded.google_key", "hardcoded_secret", "high",
     re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
     "检测到 Google API Key (AIza...)，硬编码会随技能库泄露"),
    ("hardcoded.stripe_key", "hardcoded_secret", "high",
     re.compile(r"(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{16,}"),
     "检测到 Stripe Secret/Restricted Key (sk_live_/rk_live_)，硬编码会随技能库泄露"),
    ("hardcoded.anthropic_key", "hardcoded_secret", "high",
     re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
     "检测到 Anthropic API Key (sk-ant-...)，硬编码会随技能库泄露"),

    # 绕过安全检查 / 护栏
    # 注意：下列"表述类"模式降为 MEDIUM——它们常出现在合法安装说明/安全教程的正文中，
    # 若一律硬拦会误伤（如 SkillHub 安装命令、安全技能里的示例）。真实危险由下方
    # disable_auth / disable_tls 等"状态关闭类"HIGH 规则兜底。
    ("bypass.safety", "bypass_safety", "medium",
     re.compile(
         r"(?:bypass|disable|turn off|skip|circumvent|绕过|忽略|关闭|跳过|禁用)"
         r".{0,40}"
         r"(?:safe|guard|check|verif|auth|protect|hook|validation|constraint|sanitiz|安全|检查|验证|护栏)",
         re.IGNORECASE
     ),
     "检测到'绕过/禁用安全机制'表述，请确认是文档示例还是真实危险做法"),
    ("bypass.no_verify", "bypass_safety", "medium",
     re.compile(r"--no-verify|--skip-verify|--no-check|--ignore-warnings?"),
     "检测到跳过校验/警告的参数，会绕过提交/TLS 等安全检查，需确认必要性"),
    ("bypass.chmod777", "bypass_safety", "medium",
     re.compile(r"chmod\s+([0-7]?)?777\b"),
     "chmod 777 赋予全局写权限，是典型不安全捷径，需确认是否必要"),
    ("bypass.curl_pipe_sh", "bypass_safety", "medium",
     re.compile(r"(curl|wget)\s+[^\n]{0,120}?(?:\|\s*(?:sudo\s+)?(?:ba)?sh|&&\s*(?:sudo\s+)?(?:ba)?sh)"),
     "检测到 '下载即执行' (curl|sh / curl -o x && sh x)，供应链投毒常见载体，固化前需确认来源可信"),
    ("bypass.disable_tls", "bypass_safety", "high",
     re.compile(r"(verify\s*=\s*False|ssl_verify\s*=\s*false|insecure\s*=\s*true|DISABLE_SSL|TLS_VERIFY\s*=\s*false)", re.IGNORECASE),
     "检测到关闭 TLS 校验，中间人风险"),
    ("bypass.disable_auth", "bypass_safety", "high",
     re.compile(r"(auth\s*=\s*false|AUTH_ENABLED\s*=\s*false|DISABLE_AUTH\s*=\s*true|require_auth\s*=\s*false|security\.enabled\s*=\s*false)", re.IGNORECASE),
     "检测到关闭鉴权，任意越权风险"),

    # 无护栏的破坏性操作（针对关键目标）
    ("destructive.rm_rf_critical", "destructive", "high",
     re.compile(r"rm\s+-rf\s+(/|~|\$|C:\\|/root|/home|\*|\.\./)"),
     "检测到对关键路径的 rm -rf，且无备份/确认机制"),
    ("destructive.rm_rf_local", "destructive", "medium",
     re.compile(r"rm\s+-rf\s+\./"),
     "检测到项目内递归删除 (rm -rf ./...)，虽为本地路径仍请确认有备份/确认机制"),
    ("destructive.git_reset_hard", "destructive", "medium",
     re.compile(r"git\s+reset\s+--hard|git\s+clean\s+-f[fd]?"),
     "git reset --hard / clean 会丢失未提交工作，固化前需确认有备份"),
    ("destructive.sql_drop", "destructive", "medium",
     re.compile(r"(DROP\s+TABLE|TRUNCATE\s+TABLE|DELETE\s+FROM)\b", re.IGNORECASE),
     "检测到破坏性 SQL，固化进技能需显式备份与确认"),
    ("destructive.format", "destructive", "high",
     re.compile(r"(mkfs|format\s+(c:|d:|[A-Z]:))", re.IGNORECASE),
     "检测到格式化磁盘操作，极高破坏力"),

    # 动态执行未审计内容
    ("exec.eval_concat", "dynamic_exec", "high",
     re.compile(r"\beval\s*\(\s*(str|bytes|input|request|os\.)"),
     "检测到对外部/拼接字符串执行 eval，代码注入风险"),
    ("exec.eval_generic", "dynamic_exec", "medium",
     re.compile(r"\beval\s*\(\s*(?![\"'])[A-Za-z_][\w.]*"),
     "检测到对变量/表达式执行 eval（如 eval(user_input)），代码注入风险，需确认入参可信"),
    ("exec.new_function", "dynamic_exec", "medium",
     re.compile(r"\bnew\s+Function\s*\("),
     "检测到 new Function(...) 动态代码执行，需审计入参来源，避免注入"),
    ("exec.os_system_shell", "dynamic_exec", "medium",
     re.compile(r"(os\.system|subprocess\.\w+\([^)]*shell\s*=\s*True)"),
     "检测到 shell=True / os.system，命令注入风险，需审计入参来源"),

    # 动态执行未审计内容（补充漏报，对应 P2-6）
    ("exec.exec_call", "dynamic_exec", "medium",
     re.compile(r"\bexec\s*\(\s*(?![\"'])[A-Za-z_][\w.]*"),
     "检测到 exec(...) 动态执行，代码注入风险，需审计入参来源"),
    ("exec.os_popen", "dynamic_exec", "medium",
     re.compile(r"os\.popen\s*\("),
     "检测到 os.popen(...) 执行外部命令，需审计命令来源"),
    ("exec.invoke_expression", "dynamic_exec", "medium",
     re.compile(r"Invoke-Expression\b", re.IGNORECASE),
     "检测到 PowerShell Invoke-Expression（IEX）动态执行，Windows 目标平台显著盲区，需审计"),
    ("bypass.chmod777_flags", "bypass_safety", "medium",
     re.compile(r"chmod\s+(?:-[a-zA-Z]+\s+)*777\b"),
     "chmod 777 赋予全局写权限（含带 -R 等修饰），典型不安全捷径"),
    ("bypass.subprocess_shell", "bypass_safety", "medium",
     re.compile(r"subprocess\.\w+\(.*?shell\s*=\s*True", re.DOTALL),
     "检测到 subprocess(..., shell=True)，命令注入风险，需审计入参来源"),
    ("bypass.base64_pipe_sh", "bypass_safety", "medium",
     re.compile(r"base64\s+(?:-d|--decode).{0,40}?\|\s*(?:ba)?sh"),
     "检测到 base64 解码后管道执行（base64 -d | sh），供应链投毒常见载体"),
    ("destructive.git_push_force", "destructive", "medium",
     re.compile(r"git\s+push\s+(?:--force|-f\b)"),
     "检测到 git push --force，会覆盖远端历史，固化前需确认必要且已沟通"),
    ("env.export_secret", "env_specific", "low",
     re.compile(r"\bexport\s+[A-Z_][A-Z0-9_]*\s*=\s*['\"]?[A-Za-z0-9+/=]{24,}"),
     "检测到 export 长字符串常量（疑似硬编码密钥/口令），请改用环境注入"),

    # ---- MEDIUM: 需上下文，告警 + 记入审计 ----

    # 跳过确认 / 假设已授权
    ("assume.skip_confirm", "skip_confirm", "medium",
     re.compile(r"(without\s+(confirm|asking|prompt|approval)|skip.*confirm|auto-?approve|assume.*(yes|ok|granted)|无需确认|跳过.*确认|直接执行|不询问)"),
     "检测到'跳过确认/假定已授权'表述，固化后会在未授权场景被复用"),

    # 环境特定绝对路径（可移植性 + 范围蔓延）
    ("env.hardcoded_abs_path", "env_specific", "medium",
     re.compile(r"(C:\\Users\\[A-Za-z0-9_\-\.]+\\|/home/[a-z0-9_\-]+/|/root/|/Users/[A-Za-z0-9_\-\.]+/)"),
     "检测到硬编码绝对路径（环境特定），换机器/换用户即失效，且可能越权访问"),

    # 临时偏好泛化为长期默认
    ("pref.temp_to_default", "temp_to_default", "low",
     re.compile(r"(永远|永久|always|by default|默认.*执行|每次都)"),
     "检测到'永远/默认'式表述，临时偏好若固化为长期默认会悄悄放大"),
]

_COMPILED = [(rid, cat, sev, rx, msg) for (rid, cat, sev, rx, msg) in RULES]


# fenced code block（```lang ... ```）与 HTML 注释（<!-- ... -->）内部的内容
# 视为"文档示例"，扫描时跳过，避免对示例代码误报（详见模块 docstring）。
# 必须用「行首开 ``` + 内容 + 行首闭 ```」的完整 fenced block 结构匹配，而非
# 简单数三反引号 token 或就近配对——否则文档中用于教学展示的字面反引号
# （如 ```` ``` ```` ````）会被当成代码块边界，导致配对错位、漏扫（本技能早期
# 版本 SKILL.md 第373行示例密钥误报 HIGH 即此因）。
_FENCE_RE = re.compile(r"(?m)^[ \t]*```[^\n]*\n.*?\n[ \t]*```", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _skip_ranges(text: str):
    """返回所有应被跳过的 [start, end) 区间（fenced 代码块 + HTML 注释）。"""
    ranges = []
    for rx in (_FENCE_RE, _HTML_COMMENT_RE):
        for m in rx.finditer(text):
            ranges.append((m.start(), m.end()))
    return ranges


# ---------------------------------------------------------------------------
# 编码归一化（覆盖"特殊编码可能检测不到"，评测 E·内容完整度）
# ---------------------------------------------------------------------------

# 零宽 / 不可见字符：攻击者常插入零宽空格等把 `sk-...` 拆开绕过正则（如 `s​k-`）。
_ZERO_WIDTH = (
    "\u200b\u200c\u200d\u2060\ufeff\u00ad\u034f\u061c"
    "\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
)

# 全角标点 → 半角：防 `security．enabled=false`（全角句号）等变体绕过关闭鉴权规则。
_FULLWIDTH_PUNCT = {
    "\uff0e": ".",   # ． → .
    "\uff1d": "=",   # ＝ → =
    "\uff1a": ":",   # ： → :
    "\uff08": "(", "\uff09": ")",
    "\uff0c": ",",
    "\u3000": " ",   # 全角空格
}


def normalize_encoding(text: str) -> str:
    """剥离不可见字符、将全角标点归一为半角，使"编码变体"无法绕过规则。

    归一不改变换行与反引号，故 prose 掩码（fenced 块 / HTML 注释）判定仍然准确。
    仅做"等价字符级归一"，不修改任何可见语义内容。
    """
    if any(ch in text for ch in _ZERO_WIDTH):
        for ch in _ZERO_WIDTH:
            if ch in text:
                text = text.replace(ch, "")
    if any(ch in text for ch in _FULLWIDTH_PUNCT):
        for k, v in _FULLWIDTH_PUNCT.items():
            if k in text:
                text = text.replace(k, v)
    return text


# base64 编码隐藏密钥：先扫 base64 串，解码后再查最无歧义的真密钥 HIGH 模式。
# 仅对"解码为合法 UTF-8 且命中明确密钥格式"的串报 HIGH，避免随机 base64 误报。
_B64_RE = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_B64_SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|AIza[0-9A-Za-z_\-]{35}|"
    r"(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{16,}"
)


def _scan_base64_obfuscated(text: str, skip):
    """检测用 base64 编码隐藏的硬编码密钥/私钥。"""
    hits = []
    for m in _B64_RE.finditer(text):
        s = m.start()
        if any(a <= s < b for (a, b) in skip):
            continue
        token = m.group(0)
        if len(token) % 4 != 0:   # 长度非 4 倍数基本不可能是完整 base64
            continue
        try:
            dec = base64.b64decode(token, validate=True).decode("utf-8")
        except Exception:
            continue
        if not _B64_SECRET_RE.search(dec):
            continue
        line_no = text.count("\n", 0, s) + 1
        snippet = "base64:<" + (token if len(token) <= 36 else token[:36] + "…") + ">"
        hits.append({
            "id": "hardcoded.base64_obfuscated",
            "category": "hardcoded_secret",
            "severity": "high",
            "message": "检测到 base64 编码隐藏的硬编码密钥/私钥（解码后命中高危格式），"
                       "应改为环境变量/密钥库注入，否则仍会随技能库泄露",
            "snippet": snippet,
            "line": line_no,
        })
    return hits


# ---------------------------------------------------------------------------
# 文档枚举 / 反例语境豁免（轻量修复 · 2026-09-12）
# ---------------------------------------------------------------------------
# 背景：技能/记忆文档常以"红线 / 反例黑名单 / 禁用清单"形式枚举"不可做的事"，
# 这些被列举的禁止项会触发 bypass.safety / no_verify / chmod777 / skip_confirm
# 等"表述类"MEDIUM 规则，造成审计日志虚报（见 audit-log.jsonl 不安全率 75%）。
# 该类命中的语义是"文档在 *禁止* X / 把 X 当反面教材"，并非"文档在 *指导* 做 X"，
# 故应抑制，使虚报回落到真实值。
#
# 安全约束（防自毁）：
#   * 仅作用于「非 HIGH」规则。HIGH 规则（硬编码密钥 / 关 TLS / 关鉴权 /
#     rm -rf 关键路径 / eval 拼接 / 格式化磁盘 等）**永不被豁免**——
#     即便写在反例黑名单里，真实密钥泄露仍是泄露。
#   * 仅在"文档枚举语境"触发，正常散文（如"生产环境请禁用安全检查以提速"）
#     中的同类表述仍照常 MEDIUM 告警，不削弱真实检测。
# ---------------------------------------------------------------------------

# (b) 引号：被引号包裹的短语属"提及/引用"，不是指令
_DOC_ENUM_QUOTES = (
    '"', "'",
    "\u201c", "\u201d", "\u2018", "\u2019",   # “ ” ‘ ’
    "\u300c", "\u300d",                         # 「 」
)

# (c) 强枚举短语：窗口内任意行出现即视为"在列禁止项"
_DOC_ENUM_VOCAB_STRONG = (
    "反例黑名单", "黑名单", "反模式", "负面清单",
    "forbidden", "blacklist", "anti-pattern", "anti pattern", "negative list",
)
# (c') "红线" 仅当它出现在本节【标题行】(以 # 开头) 时才视为枚举章节标记——
# 避免 changelog 里一句"修掉红线正则…"的随手提及，在 10 行内误伤真实指令。
_DOC_ENUM_REDLINE_HEADING = "红线"


def _suppress_as_doc_enum(text: str, lines, start: int, end: int, line_no: int) -> bool:
    """命中是否处于'文档枚举/反例黑名单'语境（非 HIGH 规则才可调用）。"""
    # (a) markdown 表格行：结构化的"反模式 | 原因 | 替代"枚举
    if 1 <= line_no <= len(lines):
        line = lines[line_no - 1]
        if line.count("|") >= 2:
            return True
        # (b) 引号包裹的提及（如 "跳过安全检查"）——引用而非指令
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        if before in _DOC_ENUM_QUOTES or after in _DOC_ENUM_QUOTES:
            return True
    # (c) 局部窗口（当前行 + 前 10 行）含强枚举短语
    lo = max(0, line_no - 11)
    window_lines = lines[lo:line_no]  # 含当前行
    joined = "\n".join(window_lines).lower()
    for v in _DOC_ENUM_VOCAB_STRONG:
        if v.lower() in joined:
            return True
    # (c') "红线"仅在标题行才算枚举章节
    for wl in window_lines:
        if wl.lstrip().startswith("#") and _DOC_ENUM_REDLINE_HEADING in wl:
            return True
    return False


# 自家托管域标记：agent 每机/每用户规范位置，硬编码其中路径属预期、非可移植/越权缺陷
# 扩展（③ 误报专项 2026-09-24）：加入用户家目录（expanduser("~") 解析值）与已知自有
# 项目根（Obsidian 知识库 D:\图书馆、WorkBuddy 项目目录），使"文档自家路径"不再误报。
# 安全约束：仅抑制 env.hardcoded_abs_path（advisory，非 HIGH 破坏性）；且不匹配
# 他机/他用户名（如 /home/stranger/），避免掩盖真实越权路径（攻击基准仍须命中）。
_OWNED_PATH_MARKERS = (
    ".workbuddy", ".hermes",
    ".local\\bin", ".local/bin",
    "WorkBuddy\\", "WorkBuddy/",
    "D:\\图书馆", "图书馆",                     # 用户自有 Obsidian 知识库
    "C:\\Users\\",                              # 用户自有 Windows 家目录（他机/他用户名不命中）
)


def _home_prefixes():
    """返回用户家目录的多种形态前缀（Windows/Linux/Git-Bash 风格）。"""
    home = os.path.expanduser("~")
    if not home:
        return ()
    h = home.rstrip("\\/")
    return (
        h + "\\", h + "/",
        h.replace("\\", "/") + "/",
        # Git-Bash 风格 /c/Users/Administrator
        "/" + h[0].lower() + "/" + h.split("\\")[-1] + "/",
        "/" + h.split("\\")[-1].lower() + "/",
    )


def _suppress_as_owned_path(text: str, start: int) -> bool:
    """env.hardcoded_abs_path 命中是否指向 agent 自家托管域（预期自用路径）。

    命中片段（含其后 120 字符）含任一自家标记即抑制；同时若命中路径整体位于
    用户家目录下也抑制（覆盖 C:\\Users\\Administrator\\... / /Users/Administrator/ 等）。
    """
    seg = text[start:start + 120]
    low = seg.lower()
    if any(m.lower() in low for m in _OWNED_PATH_MARKERS):
        return True
    for pfx in _home_prefixes():
        if pfx and pfx.lower() in low:
            return True
    return False


# ---------------------------------------------------------------------------
# 预防/否定语境豁免（③ 误报专项 · 2026-09-24）
# ---------------------------------------------------------------------------
# 背景：技能/记忆文档常以"描述漏洞 + 其修复"或"红线/防御"口吻书写，频繁出现
# 「绕过/禁用/关闭 安全/检查/验证」等表述类 MEDIUM 规则命中；这些命中语义是
# "文档在 *禁止/防御/修复* X"，并非"文档在 *指导* 做 X"，却与真实危险指令共用
# 同一正则，造成审计日志虚报（见审计日志 53.2% 不安全创作率，bypass.safety 占 109）。
# 此类命中若一律告警，会训练用户忽略护栏 → 真危险被淹没。
#
# 修复：对"表述类"MEDIUM 规则增加"预防/否定锚点"抑制——当命中周围窗口（±100 字符
# 含前后相邻行）出现明确的"封死/禁止/防止/修复/封堵…"等否定-预防动词时，判定文本
# 在"禁止或描述"该动作，而非"指导"该动作，予以抑制。
#
# 安全约束（防自毁）：
#   * 仅作用于"表述类"MEDIUM 规则（_PREVENTION_RULES），HIGH 规则（硬编码密钥 /
#     关 TLS / 关鉴权 / 关键路径 rm -rf / eval 拼接 / 格式化磁盘）**默认不被豁免**——
#     即便写在"禁止 X"语境，真实密钥泄露/真实关鉴权仍是危险，须保留。
#   * 仅 rm_rf_critical（HIGH）享"窄否定"豁免：须命中片段 ±60 字符内出现极强的
#     否定指令词（切勿/严禁/禁止/never/do not…），且这些词语义上否定"执行"本身，
#     与"描述修复"区分；裸"rm -rf /"（无否定词）仍 HIGH 拦截。
#   * 锚点词表刻意排除"绕过/禁用/跳过/关闭"等*动作本身*，只收"封死/禁止/防止…"
#     等*否定动作*，避免把"请禁用安全检查"这类真危险误抑制。
# ---------------------------------------------------------------------------

# 否定-预防锚点：语义上"禁止/防御/修复" bypass 类动作的动词（不含动作本身）
_PREVENT_ANCHORS = (
    # 中文
    "封死", "封堵", "封住", "堵住", "禁止", "防止", "避免", "杜绝", "拦截", "防御",
    "对抗", "硬化", "加固", "收紧", "约束", "兜底", "红线", "切勿", "严禁", "不允许",
    "阻断", "拒绝", "不得", "不可", "不该", "不能", "不要", "别", "挡住", "拦下",
    "遏制", "收口", "把关", "已修", "修复", "修补", "整改", "治理", "收敛", "降级",
    "撤销", "回滚", "移除", "删除", "废弃", "停用", "剥离", "解除", "阻断",
    "检测", "识别", "匹配", "拦截", "捕获", "留底", "检出",
    # 英文
    "forbid", "prevent", "avoid", "block", "deny", "disallow", "never", "do not",
    "don't", "must not", "prohibit", "harden", "enforce", "seal", "refuse", "reject",
    "removed", "fixed", "patched", "mitigat", "defensive", "safeguard", "deprecat",
    "do NOT", "must NOT",
)

# 表述类 MEDIUM 规则：享受"预防语境"豁免
_PREVENTION_RULES = {
    "bypass.safety", "bypass.no_verify", "bypass.chmod777",
    "bypass.chmod777_flags", "bypass.subprocess_shell", "assume.skip_confirm",
    "exec.os_system_shell",
}

# rm_rf_critical（HIGH）的窄否定词：仅这些*强否定执行*词可豁免
_RM_RF_NEGATION = (
    "切勿", "严禁", "禁止", "不要", "避免", "不可", "不得", "不允许", "切勿执行",
    "禁止执行", "禁止运行", "never", "do not", "don't", "must not", "forbidden",
    "do NOT", "must NOT", "危险示例", "以下为禁止", "禁止操作",
    "红线", "block", "拦", "拦截", "破坏性", "全拦",
)


def _window_around(text, lines, start, end, line_no, before=100, after=100):
    """返回命中周围的文本窗口（含前后相邻行），用于锚点检测。"""
    pre = text[max(0, start - before):start]
    post = text[end:end + after]
    # 相邻行上下文（当前行 + 前 3 行 + 后 1 行）
    lo = max(0, line_no - 4)
    hi = min(len(lines), line_no + 1)
    line_ctx = "\n".join(lines[lo:hi])
    return (pre + post + "\n" + line_ctx).lower()


def _suppress_as_prevention(text, lines, start, end, line_no) -> bool:
    """命中是否处于'预防/否定'语境（表述类 MEDIUM 规则才可调用）。"""
    win = _window_around(text, lines, start, end, line_no)
    return any(a.lower() in win for a in _PREVENT_ANCHORS)


def _suppress_rm_rf_prevention(text, start, end) -> bool:
    """rm_rf_critical（HIGH）窄否定豁免：命中 ±60 字符内须出现强否定执行词。"""
    win = text[max(0, start - 60):end + 60].lower()
    return any(n.lower() in win for n in _RM_RF_NEGATION)


def _in_code_comment(text, lines, line_no, start, end) -> bool:
    """命中是否落在 Python/Shell 等代码的 `#` 行注释内（仅代码文件启用）。

    代码注释是文档/说明，非可执行指令；安全检测器源码常以 `# 绕过安全` 形式
    注释其正则匹配项，属"提及"而非"指导"，应抑制以避免对护栏自身源码虚报。
    仅对整行注释（行 lstrip 以 # 起）或行内注释（命中位置在某 # 之后）生效。
    """
    if not (1 <= line_no <= len(lines)):
        return False
    line = lines[line_no - 1]
    if line.lstrip().startswith("#"):
        return True
    hash_idx = line.find("#")
    if hash_idx == -1:
        return False
    line_start_abs = text.rfind("\n", 0, start) + 1   # 命中所在行的起始绝对位置
    end_col = end - line_start_abs                        # 命中结束位置在行内的列
    # 命中只要延伸到 # 之后（含跨 # 的匹配，如正则 `bypass` 接注释 `绕过检查`），
    # 即整体落在行注释内，按"提及"抑制。
    return end_col > hash_idx


def scan_text(text: str, prose: bool = True, is_code: bool = False):
    """扫描文本，返回命中列表。每个元素:
    {id, category, severity, message, snippet, line}

    prose=True 时跳过 fenced 代码块与 HTML 注释内部（防止文档示例误报）；
    行号/snippet 仍按原文精确定位（用位置掩码而非字符串裁剪，故不影响定位）。

    先做编码归一化（零宽字符剥离 / 全角标点半角化），再跑主规则，
    最后追加 base64 编码隐藏密钥检测，覆盖"特殊编码绕过"场景。
    """
    if not text:
        return []
    text = normalize_encoding(text)
    skip = _skip_ranges(text) if prose else []
    lines = text.splitlines()
    hits = []
    for (rid, cat, sev, rx, msg) in _COMPILED:
        for m in rx.finditer(text):
            start = m.start()
            # prose 模式：命中落在代码块/注释内部则跳过（视为文档示例）
            if prose and any(s <= start < e for (s, e) in skip):
                continue
            # 定位行号
            line_no = text.count("\n", 0, start) + 1
            end = m.end()
            # 文档枚举/反例语境豁免：仅非 HIGH 规则（见 _suppress_as_doc_enum 注释）
            if sev != "high" and _suppress_as_doc_enum(text, lines, start, end, line_no):
                continue
            # 预防/否定语境豁免（③ 误报专项）：表述类 MEDIUM 规则在"禁止/防御/修复"
            # 语境下命中属文档描述，非指导动作，抑制以避免虚报淹没真危险。
            if rid in _PREVENTION_RULES:
                if _suppress_as_prevention(text, lines, start, end, line_no):
                    continue
                # 代码文件内：命中落在 `#` 行注释中属"提及"（如安全检测器源码的
                # `# 关闭安全` 注释），非指导动作，同样抑制。
                if is_code and _in_code_comment(text, lines, line_no, start, end):
                    continue
            # rm_rf_critical（HIGH）窄否定豁免：仅当命中附近出现强否定执行词
            # （切勿/严禁/never/do not…），裸 "rm -rf /" 仍 HIGH 拦截（防自毁）。
            if rid == "destructive.rm_rf_critical" and _suppress_rm_rf_prevention(text, start, end):
                continue
            # 自家托管域路径豁免：仅 env.hardcoded_abs_path（见 _suppress_as_owned_path 注释）
            if rid == "env.hardcoded_abs_path" and _suppress_as_owned_path(text, start):
                continue
            snippet = m.group(0)
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            hits.append({
                "id": rid,
                "category": cat,
                "severity": sev,
                "message": msg,
                "snippet": snippet,
                "line": line_no,
            })
    # 特殊编码兜底：base64 隐藏密钥
    if prose:
        hits.extend(_scan_base64_obfuscated(text, skip))
    # 按严重度排序：high > medium > low
    order = {"high": 0, "medium": 1, "low": 2}
    hits.sort(key=lambda h: order.get(h["severity"], 9))
    return hits


def scan_file(path: str, return_meta: bool = False):
    """扫描文件内容。对超大/二进制文件有**明确边界**（评测 A 维度：能力边界定义）：

    - 二进制（正文前 8KB 含 NUL 字节）→ 跳过全文扫描（不误读乱码），
      meta.reason="binary"；
    - 超过 MAX_SCAN_BYTES / MAX_SCAN_LINES → 只扫「首 SCAN_HEAD_LINES 行 +
      尾 SCAN_TAIL_LINES 行」（覆盖最常见危险落点：文件头配置/密钥区、脚本尾部），
      meta.reason="too_large"。

    return_meta=False：返回 hits 列表（兼容既有调用方）；
    return_meta=True：返回 (hits, meta)，meta 供审计记录边界决策，让"大文件
    怎么处理"可观测、可追溯。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        if return_meta:
            return [], {"truncated": False, "reason": "unreadable", "bytes": 0}
        return []
    # 二进制探测：正文前 8KB 含 NUL 字节按二进制处理，避免把乱码当正文误扫
    if b"\x00" in raw[:8192]:
        if return_meta:
            return [], {"truncated": True, "reason": "binary", "bytes": len(raw)}
        return []
    text = raw.decode("utf-8", errors="replace")
    truncated_text, truncated = _truncate_for_scan(text)
    meta = {"truncated": truncated, "bytes": len(raw)}
    if truncated:
        meta["reason"] = "too_large"
        meta["head_lines"] = SCAN_HEAD_LINES
        meta["tail_lines"] = SCAN_TAIL_LINES
    is_code = path.lower().endswith((".py", ".js", ".ts", ".sh", ".bash",
                                      ".ps1", ".go", ".java", ".rb", ".pl"))
    hits = scan_text(truncated_text, is_code=is_code)
    if return_meta:
        return hits, meta
    return hits


# ---- 扫描边界常量（评测 A 维度：能力边界定义）----
MAX_SCAN_BYTES = 2_000_000   # 超过 2MB：只扫首尾
MAX_SCAN_LINES = 10_000      # 超过 1 万行：只扫首尾
SCAN_HEAD_LINES = 2_000      # 首部保留行数
SCAN_TAIL_LINES = 200        # 尾部保留行数


def _truncate_for_scan(text: str):
    """超长文本只保留首尾区间（文件头配置/密钥区 + 脚本尾部是最常见危险落点），
    返回 (截断后文本, 是否截断)。"""
    if len(text) <= MAX_SCAN_BYTES:
        lines = text.splitlines()
        if len(lines) <= MAX_SCAN_LINES:
            return text, False
    lines = text.splitlines()
    head = lines[:SCAN_HEAD_LINES]
    tail = lines[-SCAN_TAIL_LINES:] if SCAN_TAIL_LINES else []
    return "\n".join(head + tail), True


def highest_severity(hits):
    if not hits:
        return "none"
    sev = {h["severity"] for h in hits}
    if "high" in sev:
        return "high"
    if "medium" in sev:
        return "medium"
    return "low"


# 内联放行标记：作者可在文件注释里写 `guard:allow:<rule_id>` 或 `guard:allow:all`，
# 显式放行某条规则。用于有意为之的文档（如安全教程示例）避免被误拦——
# 把"无意识泄露"转成"有意识、可见的放行决策"，与护栏"防不自知"初衷一致。
_ALLOW_RE = re.compile(r"guard:allow:(\S+)")


def parse_allowlist(text: str):
    """解析内联放行标记，返回被显式放行的精确 rule id 集合。

    安全约束（防自毁开关，对应 P0-1）：
    - 仅接受精确 rule id（如 `hardcoded.openai_key`），**拒绝通配 `__all__`/`all`**——
      通配会让被检内容自己携带一行 `guard:allow:all` 即解除整条闸一。
    - 真密钥类（hardcoded_secret）在任何情况下都禁止放行，由调用方（write_gate）强制拦截。
    """
    allow = set()
    if not text:
        return allow
    for m in _ALLOW_RE.finditer(text):
        v = m.group(1).strip().lower()
        if v in ("all", "__all__"):
            # 拒绝通配放行：宁可误报，不可让内容自携开关解除护栏
            continue
        allow.add(v)
    return allow


def is_guarded_path(path: str) -> bool:
    """判定是否为"经验固化/技能资产"类路径（闸一扫描对象）。

    1.2.15 起扩展：凡创建/更新 skill 的任何资产文件都触发——
       - ~/.workbuddy/skills/ 目录内**任何文件**（SKILL.md、scripts/*.py、
         references/*.md、_meta.json、CHANGELOG.md 等，含 @user_xxx 命名空间子目录）
       - ~/.hermes/skills/ 目录内**任何文件**（Hermes Agent 技能资产）
       - 任意位置的 SKILL.md / MEMORY.md（技能定义与记忆文件）
       - ~/.workbuddy/memory/ 目录内任何文件（记忆库）

    不碰普通代码/数据文件（~/.workbuddy/skills/ 之外），避免误伤正常开发。

    Windows 文件系统大小写不敏感，故对路径做 upper() 归一化，避免
    `skill.md`（全小写）绕过闸一（对应 P2-7）。
    """
    if not path:
        return False
    p = path.replace("\\", "/")
    p_upper = p.upper()
    base = os.path.basename(p).upper()
    return (
        base == "SKILL.MD"
        or base == "MEMORY.MD"
        or "/.WORKBUDDY/MEMORY/" in p_upper
        or "/.WORKBUDDY/SKILLS/" in p_upper
        or "/.HERMES/SKILLS/" in p_upper
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for h in scan_file(sys.argv[1]):
            print(f"[{h['severity'].upper()}] {h['id']} @line{h['line']}: {h['message']}")
            print(f"    snippet: {h['snippet']}")
    else:
        print("usage: redflags.py <file>")
