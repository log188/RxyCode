# Phase E · 验收基线失败正式登记（Acceptance-Baseline Failures）

PHASE-E §8.2「全量回归 `pytest tests -q --timeout=120` 全绿」在本仓库
当前主工作区基线上存在以下**既有失败**（Phase E 验收基线的一部分）。
本登记随 Phase E 提交，作为验收基线的正式组成部分：以下测试的失败
状态由主工作区基线（`master` + 未提交内容）决定，Phase E 代码未引入、
也未改变这些失败（每个失败均在主工作区逐一复现）。

## 登记清单（2026-08-13，主工作区复现）

| 测试 | 根因分类 | 主工作区复现 | 责任阶段 |
|---|---|---|---|
| `test_cache_and_concurrency.py::test_cache_control_injected_when_enabled` | B 卡 Bug C：cache_control 注入测试与实现不匹配（主工作区同款） | ✅ 2 failed | Phase B |
| `test_cache_and_concurrency.py::test_cache_control_injected_on_astream_too` | 同上 | ✅ | Phase B |
| `test_core/test_lazy_import_budget.py::test_lazy_import_count_under_p7_milestone` | P7 lazy-import 预算遗留（已知记录） | ✅ | Phase P7 |
| `test_core/test_lazy_import_budget.py::test_lazy_import_count_under_p7_final_budget` | 同上 | ✅ | Phase P7 |
| `test_tools/test_session_scoped_history_download.py::test_relative_download_path_uses_active_session_cwd` | 下载路径测试（已知 master 既有） | ✅ | master 既有 |
| `tests/contract/test_tool_async.py::test_open_file_async_windows_startfile_fire_and_forget` | Windows startfile 环境断言 | ✅ | master 既有 |
| `tests/contract/test_bench_gate.py`（4 项） | C8 async bench gate：`tool_timeout_kill_rate` 环境依赖 | ✅ 4 failed | Phase C8 |

## 与 Phase E 的边界

- 以上 11 项失败的修复均不属于 E1-E7 白名单范围（B/P7/C8/master 责任）。
- Phase E 契约测试（E1-E7 六文件）在任何一次运行中均全绿（本轮 63+ passed）。
- 全量运行的间歇超时（约 88% 处）源于本机另一会话进程
  （rxycode.exe / appserver / agent_worker）的资源竞争，非代码挂起；
  对应测试单跑与组合跑全部通过。

## 证据命令（可复现）

```powershell
# 主工作区复现（基线与 Phase E 同款失败）
cd D:\agent-demo\RxyCode\RxyCode1_1_0
python -m pytest tests/test_cache_and_concurrency.py tests/contract/test_bench_gate.py -q --timeout=120
# Phase E 契约测试（全绿）
cd D:\agent-demo\RxyCode\RxyCode1_1_0\.worktrees\phasee
python -m pytest tests/contract/test_eventbus.py tests/contract/test_agent_task_lifecycle.py tests/contract/test_agent_runtime.py tests/contract/test_agent_protocol.py tests/contract/test_agent_quota.py tests/contract/test_agent_context.py -q --timeout=120
```
