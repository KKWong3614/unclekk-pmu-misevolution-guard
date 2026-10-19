#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""触发机制扩展测试（1.2.15 新增）。

覆盖：is_guarded_path 对 skills 全目录任意文件触发 / hermes skills 任意文件触发 /
普通代码目录放行 / SkillManage 入参解析（名字、命名空间名、绝对路径、未知名放行）/
write_gate post 模式对 skill 目录做全目录扫描并聚合命中。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from redflags import is_guarded_path  # noqa: E402
from write_gate import resolve_skill_path  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name}")


# ===== A. is_guarded_path 扩展 =====
A = [
    # (路径, 期望, 说明)
    (r"C:/Users/user/.workbuddy/skills/some-skill/SKILL.md", True, "skills/SKILL.md"),
    (r"C:/Users/user/.workbuddy/skills/some-skill/scripts/helper.py", True, "skills 内任意 .py"),
    (r"C:/Users/user/.workbuddy/skills/some-skill/references/faq.md", True, "skills 内 references"),
    (r"C:/Users/user/.workbuddy/skills/some-skill/_meta.json", True, "skills 内 _meta.json"),
    (r"C:/Users/user/.workbuddy/skills/@user_48f048de/any-skill/CHANGELOG.md", True, "命名空间子目录任意文件"),
    (r"C:/Users/user/.hermes/skills/my-skill/scripts/run.py", True, "hermes skills 任意文件"),
    (r"C:/Users/user/.workbuddy/memory/2026-08-31.md", True, "memory 目录"),
    (r"C:/Users/user/dev/project/main.py", False, "普通代码"),
    (r"C:/Users/user/Desktop/notes.txt", False, "桌面文件"),
    (r"C:/Windows/system32/notepad.exe", False, "系统文件"),
    ("", False, "空路径"),
]
for p, want, note in A:
    got = is_guarded_path(p)
    check(f"is_guarded_path[{note}] = {want}", got == want)

# ===== B. resolve_skill_path（SkillManage 入参解析）=====
# 自包含：在临时目录构造一个真实存在的技能绝对路径，避免依赖本机已装技能
_res_base = tempfile.mkdtemp(prefix="wb_resolve_")
_res_skill = os.path.join(_res_base, ".workbuddy", "skills", "cos-vectors")
os.makedirs(_res_skill)
B = [
    (_res_skill, True, "绝对路径（存在）"),
    (r"C:/no/such/path", False, "绝对路径（不存在）"),
]
for s, want, note in B:
    r = resolve_skill_path(s)
    check(f"resolve[{note}]", (r != "") == want)
shutil.rmtree(_res_base, ignore_errors=True)

# 名字形态（存在 cos-vectors 技能 → 非空）
r = resolve_skill_path("cos-vectors")
check("resolve[名字形态] 定位到现有技能", r != "" and "cos-vectors" in r.replace("\\", "/"))
r2 = resolve_skill_path("user:cos-vectors")
check("resolve[命名空间形态] 剥前缀定位", r2 != "" and r2 == r)
r3 = resolve_skill_path("no-such-skill-xyz")
check("resolve[未知技能] 返回空（放行）", r3 == "")

# ===== C. write_gate post 模式对 skill 目录全目录扫描 =====
# 构造"技能资产"形态目录：<tmp>/.workbuddy/skills/testskill/
# 含 SKILL.md（安全）+ scripts/leak.py（高危密钥）→ post 扫目录应聚合出 HIGH。
# 说明：目录必须落在守卫路径内（/.workbuddy/skills/ 或 /.hermes/skills/），
# 否则 is_guarded_path 按设计放行（普通目录不拦）。
base = tempfile.mkdtemp(prefix="wb_skills_")
skill_dir = os.path.join(base, ".workbuddy", "skills", "testskill")
os.makedirs(os.path.join(skill_dir, "scripts"))
with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
    f.write("# 测试技能\n正常描述\n")
with open(os.path.join(skill_dir, "scripts", "leak.py"), "w", encoding="utf-8") as f:
    f.write("key = 'sk-FAKETESTKEY00000000000000'\n")

# 用真实 write_gate.py 跑 post 模式（stdin JSON 指向技能目录）
wg = os.path.join(HERE, "write_gate.py")
payload = json.dumps({"tool_name": "SkillManage", "tool_input": {"skill": skill_dir}})
proc = subprocess.run([sys.executable, wg, "--mode", "post"],
                      input=payload, capture_output=True, text=True, timeout=30)
# 清理临时目录
for root, _dirs, files in os.walk(base, topdown=False):
    for fn in files:
        os.unlink(os.path.join(root, fn))
    for d in _dirs:
        try:
            os.rmdir(os.path.join(root, d))
        except OSError:
            pass
try:
    os.rmdir(base)
except OSError:
    pass
# post 模式对 HIGH 命中输出 systemMessage 提醒（不拦截）
out = proc.stdout or ""
check("post 模式目录扫描输出 HIGH 提醒", "高危" in out and "leak.py" in out)

print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
