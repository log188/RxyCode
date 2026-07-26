# 开源对标移植笔记（问题 1-6 修复依据）

> 原则：GitHub 前 20 高星 agent 已解决的问题直接移植适配（copy-adapt），不自写。
> 对标仓库：google-gemini/gemini-cli（Apache-2.0，唯一同栈 Ink+React 头部项目，本地检出于 `.refs/gemini-cli/packages/cli/src/ui`）。
> openai/codex 现行 TUI 为 Rust/Ratatui，代码不可直接移植，仅借鉴其"单渲染 tick 批量合并"思想。
> 许可证处理：移植范式与关键片段的文件头保留 `Copyright 2025 Google LLC / SPDX-License-Identifier: Apache-2.0` 出处注释。

## 1. 光标定位（问题 1/2）

- **Gemini CLI 做法**：`components/InputPrompt.tsx` + `components/shared/text-buffer.ts`。
  **不写任何原生 ANSI 光标定位序列**。光标是 Ink 渲染树内的"反色字符"（`chalk.inverse(char)`），
  由 `text-buffer` 的 `visualCursor [row, col]`（按 grapheme/宽字符计算的视觉坐标）决定反色哪个字符。
  原生光标整局隐藏。因此不存在"ANSI 写入与 Ink 帧竞态"问题——这正是我们
  `InputBox.tsx` 用 `setTimeout(0)` 写 `\x1b[{row};{col}H` 导致光标落到"设置"状态栏后/高一行的根因。
- **移植决策**：RxyCode 保留原生细光标是刻意设计（见 `CursorInput.tsx` 注释），完全换反色块光标属于大改。
  折中移植：保留原生光标，但**放弃 setTimeout(0) 竞态写入**，改为 Gemini 范式的"渲染后同步定位"
  ——在 Ink 输出完成后（`useEffect` 帧后 + Ink `Static` 稳定）一次性写光标序列；
  几何计算收敛到 `layout.ts` 单一来源，修 off-by-one。

## 2. Static 历史区 / 动态区分离 + 防闪屏（问题 3/4）

- **Gemini CLI 做法**：`components/MainContent.tsx:308-322`（非 alt-buffer 传统流）：
  - `<Static key={historyRemountKey} items=[header, ...staticHistoryItems, ...lastResponseHistoryItems]>` 提交历史；
  - **pending（流式中）items 渲染在 Static 之外**，且用 `availableTerminalHeight`（`uiState.constrainHeight` 时）约束高度，
    动态区**永不超过终端高度** → Ink 重绘区域小、不闪屏；
  - 每条历史 `HistoryItemDisplay` 均 memo；`key=historyRemountKey` 全量重挂载仅在终端 resize 时发生。
- **我们的差距**：`ChatPanel.tsx` 动态区无高度约束（长流式内容整块重绘）；
  `ThinkingMessage` 内部 80ms `setInterval` spinner 独立高频重渲染整个 thinking 面板（含全部内容行）。
- **移植要点**：
  - 动态区加高度约束（尾部裁剪，只渲染最后 N 行），对标 `constrainHeight`/`MAX_GEMINI_MESSAGE_LINES`；
  - spinner 与内容分离：spinner 仅在标题行组件内动画，内容行组件 memo 后不随 spinner 帧重渲染。

## 3. 流式合并节流（问题 4/6）

- **Gemini CLI 做法**：`hooks/useGeminiStream.ts` — stream 事件先累积，
  经固定节拍统一 flush（单渲染 tick）；`static` 区仅在条目定稿时追加。
  Codex（Rust）同思想：per-frame coalescing。
- **移植落点（后端为主）**：`api_server.py StreamTUI` 按类型累加 + 时间片冲刷（~70ms time-based coalescing，
  无定时器线程：新 chunk 到达时若距上次 flush>70ms 才发事件；离散事件 tool_call/plan/step/final/error 前强制 flush 保序）。
  `write_tool_result` SSE 截断（4KB/60 行），全量仍写 recorder/history。

## 4. thinking 折叠（问题 5）

- **Gemini CLI 做法**：thought 摘要仅显示在 `LoadingIndicator`（`currentLoadingPhrase`），
  完整推理不默认灌入历史；展开由用户显式触发（ctrl+t 对应 `setShowFullThought` 类交互）。
- **移植落点**：前端 `ChatPanel.tsx` `showExpand = !done || expanded` 改为受 `expanded` 控制；
  后端 `/thinking` 开关升级为**事件门控**：关闭时 `write_reasoning` 不进 SSE（仍写 recorder），
  内部独白 progress 一并抑制——这同时消除"后端极速灌内部内容"（问题 6 用户可见面）。
