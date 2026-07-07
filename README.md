# Minimal Agent MVP

一个从零实现的最小可用 Agent。核心目标是不依赖现成 agent 框架，自行完成 runtime loop、tool calling、session 隔离、context 管理、基础压缩和真实模型 strict JSON 接入。

## 1. 项目概览

当前实现覆盖：

- 自研 Agent Runtime Loop
- 三个工具：`calculator`、`search`、`todo`
- Tool Registry：工具名、描述、参数 Schema 注册
- Session 隔离：不同窗口独立上下文
- 上下文管理：`recent_messages + fact_summary + dialogue_summary`
- 双触发压缩：消息数阈值、prompt 预算阈值
- Trace 记录：LLM 请求、工具调用、压缩事件、异常
- 真实模型接入：OpenAI-compatible `chat/completions`
- 严格 JSON 输出协议：不依赖厂商 function calling

## 2. 运行方式

### 2.1 环境要求

- Python 3.10+

### 2.2 安装依赖

当前项目只使用 Python 标准库，默认不需要额外安装三方依赖。

### 2.3 启动 CLI Demo

```bash
python -m agent_mvp.cli
```

启动后会先输入 `session id`，随后进入对话循环。

示例：

```text
session id> window-1
you> 帮我记个待办：写周报
you> 列出待办
you> 帮我算 2 + 2 * 3
```

### 2.4 运行测试

```bash
python -m unittest discover -s tests -v
```

## 3. 真实 LLM 配置

默认从工作区根目录 `.env` 读取配置。

支持的环境变量：

- `AGENT_BASE_URL`
- `AGENT_API_KEY`
- `AGENT_MODEL`
- `AGENT_TIMEOUT_SECONDS`

兼容别名：

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

配置示例：

```bash
set AGENT_BASE_URL=https://your-openai-compatible-endpoint
set AGENT_API_KEY=your_api_key
set AGENT_MODEL=your_model_name
set AGENT_TIMEOUT_SECONDS=30
python -m agent_mvp.cli
```

启用条件：

- 只有 `model + api_key + base_url` 都存在时，才使用真实模型
- 否则回退到本地 `HeuristicLLM`

## 4. 系统设计

### 4.1 核心模块

- `agent_mvp/runtime.py`
  - Agent 主循环
  - prompt bundle 构建
  - 工具调用与异常处理
  - context compression 触发
- `agent_mvp/tools.py`
  - Tool Registry
  - 工具 Schema 校验
  - `calculator` / `search` / `todo` 实现
- `agent_mvp/sessions.py`
  - 基于内存的 session store
- `agent_mvp/context_compression.py`
  - fact 提取
  - dialogue summary 生成入口
  - prompt budget 检测
- `agent_mvp/real_llm.py`
  - OpenAI-compatible transport
  - strict JSON prompt 约束
  - repair retry
- `agent_mvp/parser.py`
  - 解析模型输出
  - 提取 `action`、`tool_name`、`arguments`、`answer`
- `agent_mvp/trace.py`
  - 记录 trace event

### 4.2 Runtime Loop

运行流程：

1. 接收用户输入
2. 读取对应 session
3. 组装 prompt bundle
4. 调用 LLM，要求输出严格 JSON
5. 解析结果
6. 若为 `final_answer`，直接返回
7. 若为 `tool_call`，校验参数后执行工具
8. 把工具结果写回 session
9. 判断是否继续 loop，直到返回答案或达到最大轮次

### 4.3 工具机制

每个工具都包含：

- `name`
- `description`
- `input_schema`
- `run()`

LLM 不直接触发函数调用，而是根据工具定义输出 JSON：

```json
{
  "thought": "Need calculator for arithmetic",
  "action": "tool_call",
  "tool_name": "calculator",
  "arguments": {
    "expression": "2 + 2 * 3"
  }
}
```

## 5. Memory / Context 设计

### 5.1 Session 内存结构

当前 session 内包含三类上下文：

- `recent_messages`
  - 存在 `session.messages`
  - 保存最近的原始对话和工具消息窗口
- `fact_summary`
  - 保存稳定、可复用的硬信息
  - 当前字段：
    - `todos`
    - `tool_result_conclusions`
    - `current_task`
    - `explicit_commitments`
- `dialogue_summary`
  - 保存较老对话的语义连续性摘要
- `state`
  - 保存结构化运行态数据
  - 当前主要是 `todos`

明确不放入长期上下文的内容：

- `thoughts`
- chain-of-thought 原文
- 大段原始工具输出

### 5.2 Memory 召回时机

每次进入 LLM 调用前，runtime 都会从当前 session 读取上下文，并构建 slot-based prompt。

召回时机分两类：

- 正常轮次召回
  - 每一轮 `process()` 调用 LLM 前都读取：
    - `fact_summary`
    - `dialogue_summary`
    - `state`
    - `recent_messages`
    - `latest_user_message`
    - `tool_definitions`
- 压缩后的召回
  - 当旧消息被压缩后，不再把完整历史原文全部注入
  - 后续轮次主要靠：
    - `fact_summary`
    - `dialogue_summary`
    - `recent_messages`
  来恢复连续性

### 5.3 Memory 放置方式

在真实模型请求中，slot 放置为：

1. `system_prompt`
2. `fact_summary`
3. `dialogue_summary`
4. `structured_state`
5. `recent_messages`
6. `current_user_input`
7. `tool_definitions`

其中：

- `system` message 放提示约束
- `user` message 放 slot 化上下文 payload

### 5.4 压缩触发时机

当前有两个触发器：

- 消息条数超过 `max_messages_before_summary`
- prompt 体积超过 `max_prompt_chars`

压缩发生后：

- 保留 recent window
- 从旧消息中提取新的 `fact_summary`
- 基于旧消息和 facts 更新 `dialogue_summary`
- 后续 prompt 不再依赖完整长历史

## 6. 真实模型 Prompt 约束

当前真实模型不走厂商 function calling，只走普通 `chat/completions`，但通过 prompt 强约束输出严格 JSON。

约束重点：

- 只返回一个 JSON object
- 不要输出 markdown / code fence / prose
- 只能使用已注册工具
- `arguments` 必须符合 `input_schema`
- 只能根据提供的 slot 上下文决策
- 不允许假设隐藏的 `thoughts`、chain-of-thought 或未提供历史

如果首轮返回不是合法 agent JSON：

- 先做一次清洗
- 再做一次 repair retry
- 最终仍不合法则报错

## 7. Trace 与异常处理

当前会记录的关键 trace 包括：

- `llm_request`
- `llm_response`
- `tool_called`
- `prompt_budget_exceeded`
- `compression_started`
- `fact_summary_updated`
- `dialogue_summary_updated`
- `turn_completed`
- `error`

异常处理当前覆盖：

- 模型输出格式错误
- 工具不存在
- 工具参数不合法
- 工具执行错误
- 传输层错误
- 最大 loop 限制

## 8. 项目结构

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
  superpowers/
```

## 9. 提交说明

本次题目最终补充材料中：

- 代码链接：由仓库提供
- 终端或网页操作录屏：单独提交
- README：本文件
- AI Prompt 与问题解决记录：见 [docs/ai-prompt-and-problem-solving.md](/E:/meizhouyu/aicodingtest/docs/ai-prompt-and-problem-solving.md)
