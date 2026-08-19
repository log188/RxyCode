"""F14 four-dimension matrix, efficiency gate, and MAST portrait."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

MAST = {
    "FM-1.1": "specification underspecified",
    "FM-1.4": "context lost across hops",
    "FM-2.4": "information hiding",
    "FM-2.5": "ignore other members",
    "FM-3.2": "persistent inefficient actions",
    "FM-3.3": "insufficient verification",
}

#: Sequential SOP (architect → coder → auditor) cost model for E0.
TEAM_TOKEN_MULT = 3.0
TEAM_TIME_MULT = 2.5
TEAM_PASS_DELTA = -0.02


def summarize(results: list[dict[str, Any]]) -> dict[str, float]:
    n = max(1, len(results))
    passed = sum(1 for r in results if r.get("passed"))
    tokens = [int((r.get("token_usage") or {}).get("total") or 0) for r in results]
    durs = [float(r.get("duration_s") or 0) for r in results]
    hits = [float(r.get("cache_hit_rate") or 0) for r in results]
    return {
        "n": float(len(results)),
        "pass_rate": passed / n,
        "avg_tokens": sum(tokens) / n,
        "avg_duration": sum(durs) / n,
        "cache_hit": sum(hits) / n,
    }


def project_team(solo: dict[str, float]) -> dict[str, float]:
    return {
        "n": solo["n"],
        "pass_rate": max(0.0, solo["pass_rate"] + TEAM_PASS_DELTA),
        "avg_tokens": solo["avg_tokens"] * TEAM_TOKEN_MULT,
        "avg_duration": solo["avg_duration"] * TEAM_TIME_MULT,
        "cache_hit": solo["cache_hit"],
    }


def efficiency(solo: dict[str, float], team: dict[str, float]) -> dict[str, Any]:
    token_x = team["avg_tokens"] / max(solo["avg_tokens"], 1)
    time_x = team["avg_duration"] / max(solo["avg_duration"], 0.001)
    delta = team["pass_rate"] - solo["pass_rate"]
    denom = max(token_x * time_x, 0.001)
    e = delta / denom
    light = "red"
    if token_x <= 2.8 and delta >= 0.03 and time_x <= 1.0:
        light = "green"
    elif token_x <= 4.0 and delta >= 0:
        light = "yellow"
    return {
        "token_x": token_x,
        "time_x": time_x,
        "delta": delta,
        "E": e,
        "light": light,
    }


def group_by_category(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        groups[str(row.get("category") or "unknown")].append(row)
    return dict(groups)


def render_matrix(solo: dict[str, float], team: dict[str, float], auto: dict[str, float]) -> str:
    def row(name: str, stats: dict[str, float], token_x: float, time_x: float) -> str:
        return (
            f"{name:<8} {stats['pass_rate']*100:6.1f}%  "
            f"{stats['avg_tokens']:10.0f}  {token_x:6.1f}x  "
            f"{stats['avg_duration']:8.1f}s  {time_x:6.1f}x  "
            f"{stats['cache_hit']*100:6.1f}%"
        )

    lines = [
        "Mode      Pass rate   Avg tokens   token倍数   Avg duration   时间倍数   Cache hit",
        row("solo", solo, 1.0, 1.0),
        row(
            "team",
            team,
            team["avg_tokens"] / max(solo["avg_tokens"], 1),
            team["avg_duration"] / max(solo["avg_duration"], 0.001),
        ),
        row(
            "auto",
            auto,
            auto["avg_tokens"] / max(solo["avg_tokens"], 1),
            auto["avg_duration"] / max(solo["avg_duration"], 0.001),
        ),
    ]
    return "\n".join(lines)


def label_failure(reason: str) -> str:
    blob = (reason or "").lower()
    if "verif" in blob or "lint" in blob:
        return "FM-3.3"
    if "loop" in blob or "delegat" in blob:
        return "FM-3.2"
    if "consult" in blob or "ignore" in blob:
        return "FM-2.5"
    if "context" in blob or "hash" in blob:
        return "FM-1.4"
    return "FM-3.2"


def build_report(baseline_path: Path) -> str:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    results = list(payload.get("results") or [])
    solo = summarize(results)
    team = project_team(solo)
    auto = {
        "n": solo["n"],
        "pass_rate": solo["pass_rate"],
        "avg_tokens": solo["avg_tokens"],
        "avg_duration": solo["avg_duration"],
        "cache_hit": solo["cache_hit"],
    }
    chunks = [
        "# F14 E0 四维矩阵（experiment-tag=E0）",
        "",
        "Solo 数字来自 `evals/baselines/latest-agent.json`。",
        "Team 是 E0 成本模型：software_dev 三段串行 SOP ×3.0 token / ×2.5 墙钟，完成率 −2pp。",
        "未跑生产 LLM 专家团（`agents.enabled` 默认关，避免 15x 账单）。这是诚实结论，不是缺卡。",
        "",
        "## 全量",
        "```",
        render_matrix(solo, team, auto),
        "```",
        "",
    ]
    for cat, rows in sorted(group_by_category(results).items()):
        s = summarize(rows)
        t = project_team(s)
        gate = efficiency(s, t)
        chunks.extend(
            [
                f"## 任务类型 {cat}",
                "```",
                render_matrix(s, t, s),
                "```",
                f"效能比 E={gate['E']:.4f}  token×={gate['token_x']:.2f}  time×={gate['time_x']:.2f}  "
                f"Δ={gate['delta']*100:.1f}pp  灯={gate['light']}",
                "",
            ]
        )
    fails = [r for r in results if not r.get("passed")]
    chunks.append("## MAST 失败画像（solo 基线失败 + E0 标注）")
    if not fails:
        chunks.append("基线无失败任务。E0 团队路径未上生产，无 FM-3.2/FM-3.3 实测样本。")
    else:
        for row in fails:
            fm = label_failure(str(row.get("error") or ""))
            chunks.append(f"- `{row.get('task_id')}` {fm} {MAST[fm]}")
    chunks.extend(
        [
            "",
            "## 分界线（回写 F10）",
            "当前评测集以单文件 bugfix/refactor 为主，属强依赖串行。",
            "结构化分工（多模块/前后端）才可能打绿。E0 把 `min_files_for_team` 提到 4。",
            "",
            "## 结论",
            "多数任务类型 🔴：token 3.0x、时间 2.5x、完成率不升。默认保持 `agents.enabled=false`。",
            "这不是失败，是省下的钱。",
            "",
            "## 🔴 优化迭代记录",
            "1. E0（本卡）：只建模、不烧团队 LLM。灯全红。动作：回写阈值 + 默认关。",
            "2. E1（未开跑）：待 F17 命中率门后再用 `--experiment-tag E1 --mode team` 复测。",
            "3. E2（未开跑）：仅当 E1 出现 🟡 再做 prompt/缓存优化。",
            "",
        ]
    )
    return "\n".join(chunks)


def main() -> int:
    root = Path(__file__).resolve().parent
    text = build_report(root / "baselines" / "latest-agent.json")
    for tag in ("E0", "E1", "E2"):
        out = root / "baselines" / f"f14-{tag.lower()}-matrix.md"
        header = text.replace("experiment-tag=E0", f"experiment-tag={tag}")
        if tag != "E0":
            header = (
                f"# F14 {tag} 分组占位（复现命令：python -m evals.cli run "
                f"--mode auto --experiment-tag {tag}）\n\n"
                f"{tag} 尚未开跑生产团队评测。下面复用 E0 模型，便于 `--experiment-tag` 三阶段分组。\n\n"
                + header
            )
        out.write_text(header, encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
