# PUBLISHING REPORT

**Skill**: unclekk-pmu-misevolution-guard
**Version**: 1.2.1
**Publish Date**: 2026-08-29
**Status**: ✅ Ready for Publication (after independent re-audit remediation)

---

## Summary

- **Round-1 baseline score**: 56.8/100
- **Round-1 optimized score**: 88.5/100
- **Independent re-audit (2026-08-29)**: found 3 new P0 + 7 P1 + 15 P2 + 8 suggestions
- **Remediation**: ALL items fixed in v1.2.1 (3×P0 / 7×P1 / 15×P2 / 8 suggestions)
- **Test prompts**: 16/16 passing (100%)

---

## Files Packaged

```
unclekk-pmu-misevolution-guard/
├── .gitignore              # Git ignore rules (now tracks hooks.json / package.json)
├── CHANGELOG.md            # Version history (documents 1.2.0 + 1.2.1 remediation)
├── LICENSE                 # MIT License
├── README.md               # Usage documentation
├── SKILL.md                # Main skill definition (v1.2.1)
├── package.json            # Package metadata (v1.2.1)
├── hooks/
│   └── hooks.json          # Event-driven hook config (cross-platform python3 -c)
├── scripts/
│   ├── redflags.py         # 34 detection rules (HIGH 13 / MEDIUM 19 / LOW 2)
│   ├── write_gate.py       # Gate 1: write-phase block + append-only audit
│   ├── reuse_gate.py       # Gate 2: reuse-phase lineage block
│   ├── drift_report.py     # Gate 3: drift self-check (text + --json)
│   ├── test_redflags.py    # 16 regression/leak-coverage test cases
│   └── selftest.py         # Install-time self-check (catches silent failures)
├── references/
│   ├── audit-log.md        # Audit log JSONL format
│   ├── audit-report-v2.md  # Historical audit snapshot (marked superseded)
│   └── red-flags.md        # Dangerous-pattern catalog
├── test-prompts.json       # 16 test cases
├── sync-to-cache.ps1       # Regenerate cache instance (Windows)
├── sync-to-cache.sh        # Regenerate cache instance (Linux)
└── audit/                  # Audit log dir (created at runtime)
```

> **Note**: `results.tsv` / `dim8-test-results.json` were removed (stale Darwin artifacts) and are no longer packaged.

---

## Verification Results

### File Integrity
- ✅ All core files present and tracked by git (incl. `hooks/hooks.json`, `package.json`)
- ✅ No `__pycache__` or temporary files (`.sync-log.txt` removed)
- ✅ `hooks.json` is valid JSON; all 4 hook commands are shell-agnostic `python3 -c` form

### Code Quality
- ✅ 34 detection rules (8 hardcoded keys + 9 bypass + 6 destructive + 7 dynamic_exec + 4 misc)
- ✅ Cross-platform hooks (existence check inside Python, fail-open on any error)
- ✅ Append-only audit log (each write appends a JSONL line with fsync; history preserved)
- ✅ Local timezone handling (`datetime.now(timezone.utc).astimezone()`)

### Test Coverage
- ✅ 16/16 test prompts passing (100%) — covers key detection, bypass expressions, leak samples (IEX / base64|sh / git push --force / os.popen / eval), and `rm -rf ./` regression
- ✅ `python3 scripts/selftest.py` passes: hook parseable, scripts importable, deny protocol correct, audit appends, `guard:allow:all` rejected, benign content allowed

### Security (post-remediation)
- ✅ **P0-1 fixed**: `guard:allow:all` rejected; `hardcoded_secret` never allow-listed; allowed HIGH hits still audited + warned
- ✅ **P0-2 fixed**: audit log append-only (was overwriting → history loss)
- ✅ **P0-3 fixed**: hook commands no longer depend on POSIX `[ -f ]`; run via `python3 -c`
- ✅ **P1-1 fixed**: `write_gate`/`reuse_gate` wrapped in try/except → exit 0 (never DoS)
- ✅ **P1-5 fixed**: `hooks.json` / `package.json` no longer git-ignored (no more dist-level silent failure)

---

## Known Follow-ups (not blocking publish)

- Cache instance version label (`plugin.json`) still reads `1.0.0` and points to a third-party repo URL; the cache is a **derived artifact** regenerated via `sync-to-cache.*` after a host restart. Real source of truth is this git repo.
- `sync-to-cache.*` hardcode the current machine's user path (by design, they are operational helpers for this machine; the `env.hardcoded_abs_path` rule flags such paths only in *skill content*, not in dev scripts).

---

## Installation

```bash
# WorkBuddy
cp -r unclekk-pmu-misevolution-guard ~/.workbuddy/plugins/

# Hermes Agent
cp -r unclekk-pmu-misevolution-guard ~/.hermes/skills/
```

After install, run `python3 scripts/selftest.py` to confirm hooks fire.

---

## License

MIT License - Free for commercial and non-commercial use.

---

**Report Generated**: 2026-08-29T10:30:00+08:00
**Auditor**: Independent Third-Party re-audit + remediation (v1.2.1)
