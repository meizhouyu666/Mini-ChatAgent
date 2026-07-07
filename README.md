# Minimal Agent MVP

一个从零实现的最小可用 Agent Runtime，不依赖现成 Agent 框架，主目标是把核心 loop、session、tool calling 和基础 context 管理跑通。

## Features

- 自研 agent loop：接收输入、决定回复或调工具、继续循环直到返回结果
- 严格 JSON 协议：模型输出只适配我们自己的 runtime JSON，不依赖厂商 function calling
- 工具注册机制：内置 `calculator`、`search`、`todo`
- session 隔离：不同窗口上下文互不影响
- 内存态 context 管理：保留最近消息、结构化事实摘要、对话摘要
- 双触发压缩：支持消息条数阈值和 prompt 预算阈值
- 基础 trace：记录 LLM 请求、工具调用、压缩过程和异常
- 单元测试覆盖核心链路

## Context Compression

- Prompt 按 slot 组装：`system_prompt`、`fact_summary`、`dialogue_summary`、`state`、`recent_messages`、`latest_user_message`、`tools`
- `fact_summary` 只保留稳定硬信息：`todos`、`tool_result_conclusions`、`current_task`、`explicit_commitments`
- `dialogue_summary` 只保留对话连续性，不写入内部推理 `thoughts`
- 压缩触发后仅保留 recent window，旧消息内容通过 facts + dialogue summary 续接
- Trace 会记录 `prompt_budget_exceeded`、`compression_started`、`fact_summary_updated`、`dialogue_summary_updated`

## Run Tests

```bash
python -m unittest discover -s tests -v
```

## Run CLI Demo

```bash
python -m agent_mvp.cli
```

默认优先接真实模型，但仍坚持 strict JSON 协议。如果要配置 OpenAI-compatible 接口：

```bash
set AGENT_BASE_URL=https://your-openai-compatible-endpoint
set AGENT_API_KEY=your_api_key
set AGENT_MODEL=your_model_name
set AGENT_TIMEOUT_SECONDS=30
python -m agent_mvp.cli
```

当前真实模型接入方式：

- 走普通 chat completions
- 通过 prompt 约束模型输出严格 JSON
- 先做一次响应清洗，再交给 `ResponseParser` 校验
- 如首轮输出不合法，可做一次 repair 重试

## Project Structure

```text
agent_mvp/
  __init__.py
  cli.py
  context_compression.py
  llm.py
  parser.py
  real_llm.py
  runtime.py
  sessions.py
  tools.py
  trace.py
  types.py
tests/
  test_cli.py
  test_context_compression.py
  test_llm.py
  test_parser.py
  test_runtime.py
  test_strict_json_llm.py
  test_tools.py
docs/
  tech-plan.md
```

## Notes

- 当前 session、todo、trace 都优先存在本地内存
- 外部系统能力先通过接口预留，不强依赖接入
- 核心目标是先保证主链路可运行，再逐步增强真实环境适配
