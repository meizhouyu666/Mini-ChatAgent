# Agent Context Compression Design

## Goal

在当前最小 Agent Runtime 上补齐一套更稳的 context 管理方案，使其在多轮对话、工具追问、纯对话追问、上下文压缩后仍能保持较好的连续性。

本设计明确遵循以下约束：

- `thoughts` 不进入长期记忆
- 不做用户画像
- 压缩后的上下文采用分 slot 结构
- 事实摘要优先走规则抽取，作为硬兜底
- 对话摘要可由模型生成，以保留语义连续性

## Scope

本次设计覆盖：

- session 内 context 的组织结构
- 压缩触发条件
- slot 提取规则
- prompt 注入顺序
- 压缩失败时的兜底行为
- 需要补充的测试方向

本次不覆盖：

- 用户画像
- 跨 session 共享记忆
- 向量检索 / RAG
- 长期持久化存储设计
- thoughts / chain-of-thought 存储

## Context Structure

压缩后的 session context 固定拆成三层：

### 1. Fact Summary

只保存可稳定抽取和复用的硬信息，不保存内部推理。

首版只做最小槽位：

- `todos`
- `tool_result_conclusions`
- `current_task`
- `explicit_commitments`

说明：

- `todos`：当前 session 中已记录的待办事项
- `tool_result_conclusions`：工具执行后已经确认的结论性信息，如“计算结果是 8”“天气是晴，25C”
- `current_task`：当前用户正在推进的主要任务目标
- `explicit_commitments`：Agent 已明确答应做但尚未完成或刚完成的动作

### 2. Dialogue Summary

只保存对话层面的语义连续性信息。

首版摘要内容应包括：

- 最近主要讨论主题
- 当前轮追问所指向的对象
- 代词或省略表达的解析结果
- 用户当前最关心的未完结问题

不应包括：

- thoughts
- 原始大段工具输出
- 不确定的推测性信息

### 3. Recent Messages

保留最近若干轮原始消息，作为短窗口高保真上下文。

消息类型：

- `user`
- `assistant`
- `tool`

recent window 的目的不是长期存档，而是让模型在压缩之后仍能看到最近具体措辞、最近工具结果和最近问答细节。

## Prompt Assembly Order

每次调用 LLM 时，prompt 组装顺序固定为：

1. `system_prompt`
2. `fact_summary`
3. `dialogue_summary`
4. `structured_state`
5. `recent_messages`
6. `current_user_input`
7. `tool_definitions`

设计理由：

- 先给 system 和摘要，帮助模型先建立全局语境
- 再给 structured state，让硬事实与运行态结构对齐
- recent messages 放在靠后位置，便于模型优先关注最新语境
- 当前用户输入必须放在最近消息之后，作为本轮最强信号
- tool definitions 放在最后，方便模型直接参照 schema 决策

## Compression Trigger Policy

压缩采用双触发机制：

### Trigger A: Message Count Hard Limit

当消息总量超过固定阈值时，强制进入压缩。

目的：

- 保证不会无限膨胀
- 在任何模型下都可稳定工作

### Trigger B: Prompt Budget Soft Limit

在组装 prompt 后，估算其大小；若接近预算上限，则进行二次压缩。

目的：

- 更贴近真实运行时的 token 限制
- 避免虽然消息轮数不多，但某些 tool result 很长导致 prompt 超预算

推荐策略：

- 先用消息数做第一层硬保护
- 再用 prompt 预算做第二层软保护

## Compression Flow

当触发压缩时，处理顺序如下：

1. 选出要保留的 `recent_messages`
2. 对较旧消息做规则抽取，更新 `fact_summary`
3. 基于较旧消息和当前 fact summary，让模型生成 `dialogue_summary`
4. 删除已经被压缩的旧消息，仅保留 recent window
5. 后续 prompt 读取 `fact_summary + dialogue_summary + recent_messages`

### Why This Order

- recent messages 先切出来，避免压缩器误伤最近关键上下文
- 事实摘要先落地，保证即使模型摘要不稳定，也不会丢硬事实
- 对话摘要最后生成，可以参考已经提炼过的事实摘要

## Fact Extraction Rules

事实摘要使用规则提取，作为首版硬兜底。

### todos

来源：

- `todo` 工具 state
- `todo` 工具返回结果

规则：

- 去重
- 保留最近状态
- 删除动作暂不支持，首版只考虑 add/list

### tool_result_conclusions

来源：

- `tool` 消息
- 可识别的工具类型

规则：

- `calculator`：记录最近计算结论
- `search` / `weather`：只保留结论，不保留原始大段返回
- 仅保留“可被追问引用”的结论

示例：

- “计算结果是 8”
- “北京天气为晴，25C”

### current_task

来源：

- 最近若干条 user message
- 最近 assistant 的明确任务确认

规则：

- 取当前 session 里最主要、仍在推进的目标
- 如果用户主题明显切换，则覆盖旧任务
- 如果只是围绕同一任务追问，则保持不变

### explicit_commitments

来源：

- assistant message 中明确承诺执行的动作

规则：

- 只记录明确承诺，例如“我会帮你整理成周报结构”
- 已完成且不再需要追踪的承诺可以被后续压缩淘汰

## Dialogue Summary Generation

对话摘要交给 LLM 生成，但要有严格范围。

摘要输入：

- 被压缩掉的旧消息
- 最新 `fact_summary`

摘要目标：

- 最近主要话题是什么
- 当前追问指向哪个对象或结论
- 哪些代词、省略语需要恢复
- 用户目前在继续推进什么

输出要求：

- 简短
- 不超过固定长度
- 不引入新事实
- 不保留 thoughts

可接受示例：

- “用户先记录了写周报的待办，随后追问待办列表；当前围绕同一任务继续确认待办状态。”
- “用户先查询天气，再基于天气结果继续追问是否需要带伞；当前主题仍是天气场景。”

## Failure Handling

### 如果规则抽取失败

- 不阻塞主流程
- 保留旧 `fact_summary`
- 记录 trace

### 如果对话摘要模型生成失败

- 不阻塞主流程
- 保留旧 `dialogue_summary`
- recent messages 窗口略扩大一档，补偿摘要缺失

### 如果二次压缩后仍超预算

- 继续裁剪 recent messages
- facts 不删
- dialogue summary 不删
- thoughts 仍不注入

## Trace Expectations

需要新增或明确以下 trace 事件：

- `compression_started`
- `fact_summary_updated`
- `dialogue_summary_updated`
- `compression_skipped`
- `compression_failed`
- `prompt_budget_exceeded`

trace 里可以记录：

- 触发原因
- 压缩前后消息数量
- fact summary 是否变更
- dialogue summary 是否变更

不记录：

- thoughts 原文

## Testing Strategy

首批补充测试应覆盖：

### Fact Summary

- todo 被正确保留到 fact summary
- tool 结论被正确提炼
- current task 在主题切换时更新
- explicit commitments 在后续压缩后仍可追踪

### Dialogue Summary

- 压缩后仍能支持“刚才那个结果”“这件事继续做”类追问
- 代词所指在常见场景下可恢复

### Triggering

- 仅消息数超限时触发压缩
- 仅预算超限时触发压缩
- 双条件都满足时仍稳定执行一次压缩流程

### Failure Paths

- 模型摘要失败时 recent window 扩大兜底
- fact extractor 出错时不影响主链路

## Recommended First Implementation Slice

第一阶段只做：

- `fact_summary` 结构
- `dialogue_summary` 字段
- 双触发压缩入口
- facts 规则抽取
- dialogue summary 的 LLM 生成接口
- prompt 组装顺序调整

先不做：

- 更复杂的实体抽取
- 用户画像
- 跨 session 共享记忆
- 自适应多档摘要策略

## Acceptance Bar

若要认为这部分达标，应满足：

- 压缩后 todo / 当前任务 / 结论性工具结果不丢
- 纯对话追问命中率明显优于当前仅 recent messages 的方案
- thoughts 未进入长期记忆
- 超过阈值时压缩行为稳定可解释
- 测试能覆盖主链路与失败兜底
