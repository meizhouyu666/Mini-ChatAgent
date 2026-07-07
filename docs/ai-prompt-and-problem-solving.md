# AI Prompt 与问题解决记录

本文档记录两类内容：

1. 本次题目中，用户对 AI 的关键输入要求
2. 基于这些要求，在实现过程中识别并解决的问题

目标不是记录项目内部 prompt 的版本演进，而是把这次 AI 协作过程本身整理成可提交材料。

## 1. 用户给 AI 的关键输入要求

### 1.1 总目标

用户给出的题目目标是：

- 从零实现一个最小可用 Agent
- 不能依赖现成 agent framework 完成主流程
- 核心 Agent Runtime 需要自行实现

对应约束包括：

- 需要有基本 loop
- 需要有至少三个工具
- 需要有工具注册机制和 Schema
- 需要有 session 管理
- 需要有 context 管理与压缩
- 需要有 trace / 执行日志
- 需要构建测试用例

原始prompt
使用 CodingKit 处理这道 AI Coding 面试题。

当前目标：先做需求分析和简版技术方案，不要写代码。
因为没有时间要求，所以我会根据要求提出我对agent runtime和context管理的实现要求



请先判断复杂度，并按最小 MVP 思路输出以下内容：
1. 需求理解
2. MVP 边界
3. 明确哪些功能先不做
4. 核心数据结构设计
5. 核心处理流程
6. 项目目录结构
7. 测试用例清单
8. 后续真实环境接入的扩展点

要求：
- 优先保证核心链路可运行
- 使用最小实现思路
- 存储优先用本地内存
- 外部系统先预留接口，不强依赖
- 文档先生成简版技术方案，不要过度展开

题目如下：
Vibe coding题目：从零实现一个最小可用 Agent
要求1：从零完成
  不能依赖现有agent框架（langgraph/openhands/openclaw）完成主流程，
  允许使用任何 AI 工具辅助开发，但核心 Agent Runtime 需要自行实现。

要求2：实现基本循环
Loop大致步骤
  Step one 接收用户输入
  Step two 判断是直接回复，还是调用工具
  Step three 调用工具
  Step four 根据工具结果判断是继续loop，还是返回结果给用户
工具相关
    至少实现三个工具
      calculator
      search（可 mock）
      read_docs / todo / weather（可自定义）
  
  需实现工具注册机制（每个工具包含名称、描述、参数 Schema），LLM 基于 Schema 自主决策调用。需实现 LLM 输出的解析逻辑，提取思考过程、工具调用或最终答案。
session管理
  用户 A 开了窗口 1：让 Agent 查天气记待办
  用户 A 开了窗口 2：让 Agent 写周报记待办
  这两个窗口应该是独立的session，用户A可以随时接着窗口1/2和继续聊，彼此不会影响。
context的有效管理
  最大轮次限制
  用户持续的对话，要能记住之前的状态。
  能支持追问
    纯对话追问
    带着工具的追问
  要如何实现？哪些信息要塞入context更合适？
    用户输入、工具执行结果、Agent 思考过程等，自行判断。
  context过长要有基础的压缩，复杂的压缩不用在这里实现。
额外要求
  基本异常处理
  工具调用trace或执行日志

要求3: 测试用例构建
  构建测试用例，来测试以上功能

### 1.2 第一阶段要求：先做需求分析和简版技术方案

用户先要求：

- 先判断复杂度
- 按最小 MVP 思路输出需求理解、边界、数据结构、处理流程、目录结构、测试清单、扩展点
- 不要过度展开
- 先不要写代码

这一阶段的核心输入是：

- 优先保证核心链路可运行
- 存储优先用本地内存
- 外部系统先预留接口，不强依赖

### 1.3 对模型调用方式的明确要求

用户后续明确要求：

- 不直接用真实厂商 function calling
- 只让真实模型输出严格适配本项目 agent runtime 的 JSON

这条要求决定了：

- 不能把工具调用控制外包给模型厂商协议
- 必须自行定义 agent 输出 JSON 协议
- 必须自行实现 JSON 解析和工具调度

### 1.4 对整体 MVP 的检查和补齐要求

在完成初版后，用户要求：

- 检查当前 MVP 与题目预期的达成度
- 对缺口继续补齐

这意味着工作方式不是一次性写完，而是：

- 先把最小链路做出来
- 再按需求逐条检查缺口
- 再补关键偏差

### 1.5 对 context / memory 的明确要求

用户对上下文管理提出了几个关键约束：

- `thoughts` 的上下文管理是期望的一部分
- 但内部推理过程不应该进入 LTM
- 纯对话追问要考虑压缩和注入后的表现
- 这部分需要进一步完善

随后在多轮确认中，用户又进一步明确：

- 用户画像暂时不在本次实现范围内
- 事实信息先做最小 slot 范围
- 要符合 slot prompt 拼接逻辑
- 具体流程由 AI 自主决策即可

这些输入直接决定了：

- 长期上下文不能存 `thoughts`
- context compression 必须拆 slot，而不是只做一段 summary
- 第一阶段不做 persona / profile

### 1.6 对事实 slot 范围的选择

在讨论 slot 设计时，用户通过多轮选择给出了明确偏好：

- 先做最小实现
- 暂不考虑扩展
- 用户画像不纳入本次范围

最终收敛出来的事实 slot 范围是：

- `todos`
- `tool_result_conclusions`
- `current_task`
- `explicit_commitments`

### 1.7 对 Git 与交付的要求

用户后续明确要求：

- 把项目连接到指定 GitHub 仓库
- 收口并推送到远端
- 最终材料需要包含：
  - 代码链接
  - 终端或网页操作录屏
  - README
  - AI Prompt 与问题解决记录

### 1.8 对 README 的最终要求

用户明确说明 README 需要覆盖：

- 运行方式
- 系统设计
- memory 的召回时机
- memory 的放置方式说明

### 1.9 对本文件的最终要求

用户最后又明确纠偏：

- “AI Prompt 与问题解决记录”不是写项目内部 prompt 的演进
- 应该写：
  - 用户给 AI 的 prompt / 指令
  - 对应解决的问题
  - 项目遇到的问题解决记录

这也是本文档当前采用的组织方式。

## 2. 用户输入要求与实现决策的对应关系

这一部分把“用户如何要求”和“最终如何落地”对应起来。

### 2.1 要求：核心 Agent Runtime 必须自行实现

对应实现：

- 自行实现 `AgentRuntime`
- 自行实现 loop 控制
- 自行实现工具注册、工具校验、工具调度
- 自行实现 session store
- 自行实现 parser 和 strict JSON 协议

解决的问题：

- 满足题目“不能依赖现成 agent framework 完成主流程”的硬要求

### 2.2 要求：真实模型也不能直接走厂商 function calling

对应实现：

- 真实模型走普通 OpenAI-compatible `chat/completions`
- 用 prompt 约束输出严格 JSON
- 本地 parser 负责解析
- runtime 决定是否调工具

解决的问题：

- 工具调用控制权回到本项目 runtime
- mock 模型与真实模型路径可以统一

### 2.3 要求：`thoughts` 不进长期记忆

对应实现：

- `thought` 字段仍允许出现在模型输出里
- 但不写入 `fact_summary`
- 不写入 `dialogue_summary`
- 不写入压缩后的长期上下文

解决的问题：

- 兼顾调试可见性和长期记忆边界

### 2.4 要求：支持纯对话追问和工具追问

对应实现：

- context 不是只留 recent messages
- 拆成：
  - `fact_summary`
  - `dialogue_summary`
  - `recent_messages`

解决的问题：

- 工具状态追问不只依赖最近窗口
- 纯对话追问不只依赖长历史原文

### 2.5 要求：slot prompt 拼接逻辑要明确

对应实现：

真实模型请求中的 slot 结构固定为：

1. `system_prompt`
2. `fact_summary`
3. `dialogue_summary`
4. `structured_state`
5. `recent_messages`
6. `current_user_input`
7. `tool_definitions`

解决的问题：

- prompt 结构不再混乱
- 压缩后的 memory 能以固定方式召回

### 2.6 要求：默认改成接入真实模型

对应实现：

- 读取 `.env`
- 若 `base_url + api_key + model` 存在，则默认启用真实模型
- 缺失时回退到本地 `HeuristicLLM`

解决的问题：

- CLI 默认行为从“本地 mock 优先”调整为“真实模型优先”

## 3. 项目实现过程中遇到的问题与解决记录

### 3.1 问题：Session 需要支持多窗口隔离

背景：

- 题目明确要求同一用户的窗口 1 / 窗口 2 独立

解决方式：

- 使用 `session_id` 作为隔离键
- `InMemorySessionStore` 按 `session_id` 保存独立 `Session`

结果：

- 两个窗口的 todos、messages、state 不会互相污染

### 3.2 问题：仅用 recent messages 无法稳定支持长对话

背景：

- 一旦消息窗口裁剪，只保留 recent messages 会丢失旧任务、旧结论和较早语义连续性

解决方式：

- 加入 `fact_summary`
- 加入 `dialogue_summary`
- recent messages 只保留局部上下文窗口

结果：

- 长对话追问稳定性明显提升

### 3.3 问题：context compression 做完后，真实模型路径没有真正吃到新 slot

背景：

- runtime 已经能构造 `fact_summary`、`dialogue_summary`、`recent_messages`
- 但真实模型请求最初仍然只发旧字段

这是一个真实的实现偏差。

解决方式：

- 调整真实模型 prompt 结构
- 将真实模型 user payload 改为 slot 化上下文
- 在 system prompt 中增加 slot 使用约束
- 增加“不要假设隐藏 thoughts / 历史”的限制
- 补测试验证真实请求已带上新 slot

结果：

- runtime 设计和真实模型调用路径对齐

### 3.4 问题：纯对话追问需要兜底，但不应过度复杂化

背景：

- 用户明确要求考虑压缩与注入后的纯对话追问表现
- 同时又要求保持最小 MVP

解决方式：

- 不引入复杂的长期记忆系统
- 第一阶段只用：
  - `fact_summary`
  - `dialogue_summary`
  - `recent_messages`
- 通过 message-count 和 prompt-budget 双触发做基础压缩

结果：

- 满足题目要求
- 没把实现范围扩到 RAG / profile / 持久化

### 3.5 问题：README 出现编码污染，不适合最终提交

背景：

- 原 README 在实现过程中出现乱码
- 已经不适合作为交付材料

解决方式：

- 重写 README
- 直接按照最终提交要求重组内容
- 补足运行方式、系统设计、memory 召回和放置说明

结果：

- README 可以直接交付

### 3.6 问题：提交材料不只需要代码，还需要 AI 协作记录

背景：

- 最终题目要求不仅看代码，还看过程材料

解决方式：

- README 负责项目说明
- 单独补一份 AI Prompt 与问题解决记录
- 把用户输入要求和项目问题解决过程整理成文档

结果：

- 交付材料更完整

## 4. 本次 AI 协作的工作方式总结

从这次对话看，AI 不是独立随意发挥，而是在一组逐步收紧的用户约束下实现项目。

工作顺序基本是：

1. 先按要求做最小 MVP 分析
2. 再按要求实现基础 runtime
3. 再按要求检查整体达成度
4. 再按要求补 context compression
5. 再按要求补真实模型 slot prompt 对齐
6. 最后按要求补交付文档

这套过程本身，也是本题“使用 AI 协作完成开发”的一部分证据。

## 5. 当前边界

本次实现仍然是 MVP，有意未做：

- 持久化数据库
- 用户画像
- 向量检索 / RAG
- 复杂压缩策略
- 多模型路由
- 外部真实 search / weather 接入
- thoughts 存储与可视化

这些未做项不是遗漏，而是基于用户给出的“MVP 优先、核心链路优先、先不扩展”的输入约束主动收住的范围。
