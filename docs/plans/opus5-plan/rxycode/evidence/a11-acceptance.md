# A11 验收记录：文档与死代码清理

日期：2026-08-06 ｜ 执行：subagent-driven development（superpowers）｜ 卡：`docs/plans/opus5-plan/rxycode/PHASE-A-MODEL-ADAPTATION-LAYER.md` §A11（依赖 A1-A10，均完成）

## 完成判据对照

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| 1 | providers.md 存在，含新增 provider 说明 | ✅ | `docs/modules/providers.md`：13 字段表逐字核对 model_capabilities.py、解析顺序（显式>matches>兜底）、新增流程（§5 锚点）、**三条设计约束 §2.2**、常见问题（issues #2 + 实测踩坑） |
| 2 | 配置及模型文档更新 | ✅ | config.md（模型条目字段 + api_key 优先级 + 能力覆盖）+ core.md（LLM 构造路径 A6/A8/A9 能力门） |
| 3 | core/config.py 遗留代码删除/废弃 | ✅ | LLMConfig 删除 + AppConfig.llm 级联 + 文件头废弃注记 + core/README.md 同步；git grep 零代码引用 |
| 4 | §12.1 + README 同步 2026-08-01 扩展 | ✅ | §3.2 Phase A 行（已完成 2026-08-06）；两处模型清单 → 8 家族；3 周 → ≈1 周 |

## 验收命令输出

```powershell
git grep -nE "LLMConfig|core\.config" -- "*.py"   # 仅 core/config.py 注释 + core/README.md 说明，零代码引用
python -c "import RxyCode.RxyCode1_1_0.core.config as c; print([n for n in dir(c) if n.endswith('Config')])"
# ['AppConfig', 'ExecutorConfig', 'MemoryConfig'] —— 无 LLMConfig，import 正常
python -m pytest tests -q --timeout=600           # 9972 passed, 3 skipped（1 flaky 时序测试重跑通过，与改动无关）
python -m evals.cli run --backend agent --compare-baseline evals\baselines\latest-agent.json
# 基线已重建为 19 任务套件：17/19 = 89.5%（a05d35c）
# gate-a11：GATE: PASS (pass rate 94.7% >= baseline 89.5%)，18/19
```

## 实现 commit

- `79cfcee` refactor(config): remove dead LLMConfig (A11) and sync core README
- `0eace3f` docs: providers module doc, config model fields, core LLM path, index registration (A11)
- `c08820e` docs(plans): mark Phase A complete and sync model list (A11)
- `a05d35c` chore(evals): rebuild baseline on 19-task suite (17/19)
- `df866cf` docs(plans): mark A11 completion criteria done with evidence
- `e9cXXXX`（审计整改）providers.md §2.2 约束小节 + 判据措辞修正

## 深度耦合核查（C1-C4）闭环

- C1 core/README.md LLMConfig 示例同步 ✅
- C2 AppConfig.llm 级联删除（全库 `\.llm` 零命中）✅
- C3 AGENTS.md 模块索引注册 providers 行 ✅
- C4 17/19 任务基线错配 → 重建 19 任务基线（89.5%）→ gate-a11 同套件对比无误报 ✅

## 证据文件

- `artifacts/gate-a11.log`（GATE: PASS 94.7%）、`evals/results/gate-a11.json`（18/19）
- `evals/baselines/latest-agent.json`（19 任务基线 17/19，a05d35c 入库）
- SDD 报告：`docs/superpowers/sdd/a11-docs-config-cleanup/task-{1,2,3}-report.md` + 各审查包

## 待用户裁定

- **docs/plans/ 跟踪策略**：并行进程 d8089da 曾将 docs/plans/ 移出 git（gitignore + 移除索引）；c08820e 用 -f 仅回注 3 个执行相关文件。选项：① 维持现状（3 文件入库，其余本地）② 全量回注 docs/plans ③ 完全不入库。
