Action Bridge → Agent 能力深化方案

目标

从"意图识别→路由工具"升级为"Agent自主选择工具链"

当前问题

现在的流程是：用户消息 → 意图识别（规则+LLM） → 路由到固定工具 → 执行。Agent 没有真正"决定"调用哪个工具，只是分类到预定义意图。

核心改动

1. 真正的 Tool Calling
- 不用意图识别了，直接把工具描述（含参数 schema）给 LLM
- LLM 自己决定：需要调工具吗？调哪个？传什么参数？
- 技术点：OpenAI function calling / Anthropic tool use，让模型输出 tool_calls 而不是意图标签
1. 多步工具链
- 一个用户请求可能需要多次工具调用（先查任务→发现没有→创建）
- Agent 自动编排顺序，不是硬编码的 A→B
- 技术点：ReAct 循环 — Thought → Action → Observation → Thought → Action → ... → Final Answer
1. Agent 决策准确率评估
- 记录每次 Agent 决策：调了什么工具、传了什么参数、结果对不对
- 标注一批测试用例，算准确率
- 技术点：用 trace 系统（你已经有了）生成评估数据集
1. 砍掉（瘦身业务）
- 前端任务看板的复杂 UI（保留核心功能）
- 历史统计图表页面
- 把重心放在 agent-debug 面板上——这反而是面试时能演示的东西

不动的部分（你已有的、好的就别改）

- 确认门控（write 操作的 pending confirmation 机制）
- Agent trace 可观测系统
- 飞书集成
- 记忆别名系统
