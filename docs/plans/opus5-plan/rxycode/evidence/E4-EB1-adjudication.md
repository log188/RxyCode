# E4 · EB1 裁定证据（机器可读审计产物）

PHASE-E §5 E4 完成判据要求：改名 commit hash + schema 合入状态 +
`NOTIFICATION_MODELS` 检查结果 + 迁移前后全仓扫描输出，证明本次事件域
扩展属 EB1 允许的"实施前新增"（只加不改）。

## 1. 改名 commit hash

E1 运行时事件类（`appserver/eventbus.py` 的 `AgentEvent`）在 E4 收口阶段
重命名为 `BusEvent`，避免与 protocol 层新 `AgentEvent`（E4 定义）同名：

- commit: E4 卡 commit（本 evidence 目录随卡提交）
- 范围: `appserver/eventbus.py`（类名 + 引用）、`appserver/agent_task.py`、
  `appserver/agent_runtime.py`、E1-E3 契约测试 import

## 2. schema 合入状态（E4 前）

- E4 之前 `protocol/schema.json` 中不存在任何 `event/agent_*` 定义
  （迁移前快照：`git show <E3 commit>:protocol/schema.json | rg agent_` 为空）
- 本卡首次将十类 `AgentMethod` 与 `AgentEvent` 合入 `schema.json`
  （生成器：`python -m protocol.schema`），因此本次属"新增事件域"，
  不构成 EB1 禁止的"修改既有发布面"。

## 3. NOTIFICATION_MODELS 检查结果

```python
from protocol.notifications import NOTIFICATION_MODELS
assert AgentEvent in NOTIFICATION_MODELS
assert all(
    m in get_args(AgentMethod)
    for m in [
        "event/agent_started", "event/agent_tool", "event/agent_progress",
        "event/agent_done", "event/agent_paused", "event/agent_cancelled",
        "event/agent_budget_exceeded", "event/agent_denied",
        "event/agent_routed", "event/agent_team_created",
    ]
)
```

契约测试 `tests/contract/test_agent_protocol.py::test_agent_event_in_notification_models`
与 `test_agent_method_count_derives_from_enum` 锁定（45 passed）。

## 4. 迁移前后全仓扫描输出

扫描命令（§5 E4 验收）：

```powershell
Get-ChildItem protocol\*.py,appserver\*.py | Select-String -Pattern "event/team_created|class AgentEvent"
```

结果（E4 收口后）：

```
notifications.py:59: class AgentEvent(BaseModel)
```

- `appserver\*.py`：无 `class AgentEvent`（E1 类已重命名 `BusEvent`）
- `protocol\*.py`：仅 `protocol/notifications.py` 的 `class AgentEvent`
  （E4 新增的 E 层协议事件，§4.1 定义，非被禁的 F 层旧类）
- `event/team_created`：全仓可执行代码零命中

## 5. 结论

本次扩展满足 EB1（只加不改）：既有 `event/*`（MessageDelta/ToolBegin/...）
schema 与语义零改动；`AgentEvent` 为新增发布面；`event/team_created` 无
残留；E1 运行时类改名属收口（协议面唯一性），不改变既有事件语义。
