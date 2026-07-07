# Minimal Agent MVP Tech Plan

## Current Scope

- 单进程、单机、内存态运行
- 文本输入输出
- 自研 Agent Runtime
- 工具注册与调度
- session 隔离
- 基础 context 压缩
- 本地 trace 记录

## Core Modules

- `runtime.py`
  - 负责主循环、最大 loop 控制、错误兜底、调用 parser / tools / session
- `llm.py`
  - 提供 `ScriptedLLM` 供测试使用
  - 提供 `HeuristicLLM` 供离线演示使用
- `tools.py`
  - 负责工具定义、Schema 校验、工具注册和实际执行
- `sessions.py`
  - 负责内存 session 生命周期
- `trace.py`
  - 负责记录 `llm_request`、`llm_response`、`tool_called`、`error`
- `parser.py`
  - 负责解析结构化 LLM 输出

## Context Strategy

- 保留当前 session 的 `summary + recent messages + state`
- 当消息数超过阈值时，把较早的消息折叠进 `summary`
- `todo` 作为结构化 state 存在 `session.state`

## Extension Points

- 真实 LLM Provider
  - 在 `llm.py` 中新增 provider adapter
- 外部工具接入
  - 在 `tools.py` 中新增 tool class 并注册
- 持久化 session
  - 将 `InMemorySessionStore` 替换为 Redis / DB store
- 持久化 trace
  - 将 `InMemoryTraceLogger` 替换为文件、数据库或 observability 平台
- 更复杂 context 管理
  - 引入 token budgeting、分层摘要、检索增强
