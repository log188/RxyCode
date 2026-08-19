# RL8 · X10 clean-room retest (2026-08-19)

Exclusive worktree: `D:\agent-demo\RxyCode\RxyCode-fix2`
Branch: `fix2`
Commit before/after: `a064678` / `a064678`
Dirty files before/after: `0` / `0`
RM1: no concurrent `pytest` at start.

Command:

```
python -m pytest tests -q --tb=line
```

Result: **completed** in 671.15s (0:11:11).

```
38 failed, 12011 passed, 3 skipped, 371 warnings, 5 errors
```

`fake_mcp_server` count, sampled every 30s from 2026-08-19T03:56:28+08:00 through the run: **every sample was `count=1`**. Peak = 1. No 23s accumulation to 30.

Verdict **(a)**: the X10 hang/pile-up did not reproduce after RL7. The remaining failures are pricing/session/RL5-gate items, not a stuck suite.

PHASE-G-CONFLICT-AUDIT.md X10 updated in the local plan tree (gitignored `docs/plans/`).
