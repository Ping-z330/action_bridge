# ActionBridge

ActionBridge 是一个“会议纪要到执行闭环”的办公协作 Agent MVP。它可以把会议文本解析成结构化摘要、关键决策和行动项，并通过 Web 工作台、任务看板、历史归档、飞书机器人和轻量 Agent 能力，持续推进会议后的执行过程。

## 项目定位

这个项目不是单纯的 AI 聊天 Demo，而是面向研发、产品、测试、运营等团队的会议执行工具：

- 降低会议后手动整理纪要、拆任务和跟进状态的成本。
- 将行动项沉淀到系统中，统一管理负责人、截止时间和任务状态。
- 通过飞书机器人接收会议纪要、查询任务、更新任务、总结项目进度。
- 通过任务结果页和历史记录页形成可追踪、可回溯的执行闭环。

## 核心功能

- 会议纪要输入：支持 Web 粘贴文本和上传 `.txt`、`.md`、`.vtt`、`.srt` 文本文件。
- LLM 解析：调用 DeepSeek/OpenAI-compatible API 生成摘要、决策和行动项。
- 规则兜底：未配置 LLM 或调用失败时，使用规则解析保证本地演示可用。
- 行动项管理：支持编辑负责人、截止日期、截止时间和任务状态。
- 任务结果页：按会议分组展示任务，支持状态筛选、搜索、进度条和风险优先。
- 历史记录页：展示会议归档、整体执行情况和完成率环形图。
- 飞书机器人：支持 Webhook 机器人和自建应用机器人。
- 飞书上下文回复：私聊触发回复私聊，群聊触发回复原群，后台发送和自动提醒发送默认群。
- 轻量 Agent：支持自然语言创建任务、查询任务、更新任务状态、总结项目进度和查看帮助。
- LLM 意图兜底：规则无法识别时，可调用 LLM 将口语化消息转成结构化意图；LLM 只负责理解，实际执行仍走确认机制。
- LangGraph 编排：将 Memory、任务上下文、意图识别、任务引用解析、工具执行和响应生成串成可维护的 Agent 执行流。
- Tool Registry：通过工具注册表管理查询、总结、更新、创建等工具，并标记工具来源、类型、危险级别和是否需要确认。
- 结构化 Memory：支持项目别名、成员别名和团队术语映射，让 Agent 能理解团队内部说法。
- Agent 调试面板：支持查看 Agent Trace，并在网页中直接输入自然语言运行 Agent，观察意图识别、工具路由和最终回复。
- 自动跟进：支持扫描今日到期/逾期未完成任务，发送飞书跟进提醒，并识别用户回复更新状态。
- 事件去重：基于飞书 `event_id/message_id` 做数据库级幂等去重，避免重复回调导致重复创建或重复发送。

## 功能流程

```mermaid
flowchart TD
    A[会议纪要来源] --> A1[Web 粘贴/上传]
    A --> A2[飞书 /meeting]
    A --> A3[飞书固定命令]
    A --> A4[飞书自然语言]

    A1 --> B[FastAPI /api/meetings]
    A2 --> C[飞书事件入口 /api/feishu/events]
    A3 --> C
    A4 --> C

    C --> C0[feishu_event_router 解析 payload]
    C0 --> C00{challenge / ignored?}
    C00 -->|challenge| C01[返回 challenge]
    C00 -->|ignored| C02[返回 ignored]
    C00 -->|继续| C1{事件是否重复}
    C1 -->|是| C2[忽略 duplicated]
    C1 -->|否| D{消息类型?}

    D -->|/meeting| BG[后台创建会议]
    BG --> B
    D -->|/tasks /task /done /help /remember /memory /forget /bind-channel| E[feishu_command_handler 固定命令处理]
    D -->|跟进回复 #12 完成/进行中/有风险| E
    D -->|普通文本| G0[feishu_event_guard 判断是否处理]

    G0 --> P0{是否有待确认操作?}
    P0 -->|确认/取消| P1[orchestrator 执行或取消 Pending Action]
    P0 -->|修改待确认字段| P2[更新 Pending Payload 并重发确认卡片]
    P0 -->|普通自然语言| F0[Memory 别名归一化]

    F0 --> F[规则意图识别]
    F --> FLLM{规则是否识别?}
    FLLM -->|是| FR[LangGraph 结构化意图路由]
    FLLM -->|否| FLLM2[LLM 意图兜底]
    FLLM2 --> FR

    B --> G[LLM 或规则解析]
    G --> G1[会议摘要]
    G --> G2[关键决策]
    G --> G3[行动项]

    G1 --> H[(SQLite)]
    G2 --> H
    G3 --> H

    FR --> F1[查询任务 / 最近任务上下文]
    FR --> F2[更新任务状态]
    FR --> F3[总结项目进度]
    FR --> F4[帮助说明]
    FR --> F5[创建任务]
    FR --> F6[修改负责人/截止时间]

    F5 --> P3[保存 Pending Create]
    F6 --> P4[保存 Pending Update]
    P3 --> L
    P4 --> L
    P1 --> H
    P2 --> L

    E --> H
    F1 --> H
    F2 --> H
    F3 --> H

    H --> I[Web 首页/详情页]
    H --> J[任务结果页 /tasks]
    H --> K[历史记录页 /history]
    H --> L[飞书卡片回复]

    H --> M[auto_follow_up_scheduler 定时触发]
    M --> M1[follow_up_service 扫描今日到期/逾期任务]
    M1 --> L
    M --> L
    L --> N[用户回复完成/进行中/有风险]
    N --> H
    H --> PC[project_channel_service 项目群绑定同步]
    PC --> L
```

## 页面说明

```text
/                    会议处理工作台
/meetings/[id]       会议详情与行动项编辑
/tasks               任务结果页 / 执行看板
/history             历史记录页 / 归档统计
/agent-debug         Agent 调试面板 / Trace 查看与手动运行
```

- 会议处理工作台：输入会议标题和会议记录，生成摘要、决策和行动项。
- 会议详情页：查看完整会议结果，编辑行动项负责人、截止时间和状态。
- 任务结果页：按会议分组管理所有行动项，判断每个会议/项目的执行进度。
- 历史记录页：沉淀会议归档，展示整体执行情况、完成率和风险数量。
- Agent 调试面板：查看最近 Agent 执行记录，也可以直接输入自然语言测试 Agent 识别和工具路由。

## 技术架构

```mermaid
flowchart TD
    subgraph Frontend[Next.js 前端]
        F0[AppShell 导航壳]
        F1[MeetingForm]
        F2[MeetingDetail]
        F3[TaskResults]
        F4[HistoryRecords]
        F5[AgentDebugPanel]
        F6[lib/api.ts / lib/types.ts]
    end

    subgraph Backend[FastAPI 后端]
        B1[api/routes.py 路由入口]
        B2[meeting_service 会议与行动项]
        B3[parser_service 会议解析]
        B4[feishu_event_service Payload 提取]
        B5[feishu_event_router 事件分流]
        B6[feishu_command_handler 固定命令]
        B7[feishu_event_guard 处理范围判断]
        B8[feishu_delivery / feishu_service 飞书发送]
        B9[follow_up_service / auto_follow_up_scheduler 跟进提醒]
        B10[deadline_service / due_status_service 时间与风险]
        B11[project_channel_service 项目群绑定]
    end

    subgraph Agent[轻量 Agent]
        A1[agent/graph.py LangGraph 执行流]
        A2[agent/orchestrator.py 飞书 Agent 编排]
        A3[agent/service.py 规则意图识别]
        A4[agent/llm_intent_service.py LLM 意图兜底]
        A5[agent/task_reference_resolver.py 任务引用解析]
        A6[agent/tool_registry.py 工具注册表]
        A7[agent/tools.py 工具执行]
        A8[agent/confirmed_intents.py 确认后执行]
        A9[pending_agent_action_service Pending 确认]
        A10[memory_service.py 结构化 Memory]
        A11[agent_task_context_service 最近任务上下文]
        A12[agent_trace_service Trace 记录]
    end

    subgraph DB[SQLite 数据库]
        D1[meetings]
        D2[action_items]
        D3[tasks]
        D4[follow_up_logs]
        D5[feishu_event_logs]
        D6[memory_aliases]
        D7[pending_agent_actions]
        D8[agent_trace_logs]
        D9[agent_task_contexts]
        D10[project_channels]
    end

    subgraph External[外部服务]
        E1[DeepSeek API]
        E2[Feishu OpenAPI]
        E3[Feishu Webhook]
    end

    F0 --> F6
    F1 --> F6
    F2 --> F6
    F3 --> F6
    F4 --> F6
    F5 --> F6
    F6 --> B1

    B1 --> B2
    B1 --> B5
    B5 --> B4
    B5 --> B7
    B5 --> B6
    B5 --> A2
    B6 --> B2
    B6 --> B8
    A2 --> A1
    A1 --> A3
    A1 --> A4
    A1 --> A5
    A1 --> A6
    A6 --> A7
    A7 --> B2
    A2 --> A8
    A2 --> A9
    A2 --> A10
    A2 --> A11
    A1 --> A12

    B2 --> B3
    B2 --> B8
    B2 --> B10
    B9 --> B8
    B9 --> B10
    B6 --> B11
    B11 --> B8

    B3 --> E1
    A4 --> E1
    B8 --> E2
    B8 --> E3

    B2 --> D1
    B2 --> D2
    B2 --> D3
    B9 --> D4
    B5 --> D5
    A10 --> D6
    A9 --> D7
    A12 --> D8
    A11 --> D9
    B11 --> D10
```

## 代码结构

```text
ActionBridge/
  backend/
    app/
      agent/
        confirmed_intents.py          用户确认后真正执行创建/修改任务
        graph.py                     LangGraph Agent 执行流
        orchestrator.py              飞书 Agent 回复编排与确认机制
        service.py                   轻量 Agent 意图识别与编排
        llm_intent_service.py         LLM 意图识别兜底
        task_reference_resolver.py    解析“第一个任务/12 号任务”等引用
        response_builder.py           Agent 回复文案构造
        tool_registry.py             Agent 工具注册表
        tool_adapters.py             本地工具适配器，预留 MCP/外部工具接入形态
        tool_contracts.py            AgentTool / AgentToolRegistry 契约
        tools.py                     任务查询、状态更新、项目总结工具
        schemas.py                   AgentIntent / AgentResponse / 进度总结结构
      api/routes.py                  API 路由入口
      core/config.py                 环境变量配置
      core/time.py                   时间工具
      db/session.py                  数据库连接
      db/base.py                     模型注册
      db/migrations.py               SQLite 轻量迁移
      models/                        SQLAlchemy 数据模型（会议、行动项、Trace、Memory、Pending、项目群绑定等）
      schemas/                       请求/响应结构（会议、任务、行动项、Trace、Memory、跟进等）
      services/agent_task_context_service.py 最近任务上下文，用于“第一个/第二个任务”引用
      services/agent_trace_service.py Agent Trace 记录与查询
      services/auto_follow_up_scheduler.py 自动跟进定时调度
      services/deadline_service.py   截止时间解析、标准化和展示文本
      services/due_status_service.py 到期状态/风险判断
      services/feishu_command_handler.py 飞书固定命令处理
      services/feishu_delivery.py    飞书发送能力封装工具箱
      services/feishu_event_guard.py 飞书消息处理范围判断与过滤
      services/feishu_event_log_service.py 飞书事件去重和处理状态记录
      services/feishu_event_router.py 飞书事件解析、分类和分流
      services/feishu_event_service.py 飞书 payload 字段提取和命令解析
      services/feishu_service.py     飞书卡片生成与发送
      services/follow_up_service.py  未完成任务扫描、提醒和回复记录
      services/meeting_service.py    会议、行动项、飞书发送业务逻辑
      services/memory_service.py     结构化 Memory 别名管理
      services/parser_service.py     LLM/规则解析会议纪要
      services/pending_agent_action_service.py Agent 待确认操作管理
      services/project_channel_service.py 项目关键词与飞书群绑定/同步
    tests/                           后端自动化测试
  frontend/
    app/page.tsx                     首页会议处理
    app/tasks/page.tsx               任务结果页
    app/history/page.tsx             历史记录页
    app/meetings/[id]/page.tsx       会议详情页
    app/agent-debug/page.tsx         Agent 调试面板
    components/AppShell.tsx          全局导航与页面壳
    components/MeetingForm.tsx       会议输入表单和文件上传
    components/MeetingDetail.tsx     会议详情与行动项编辑
    components/TaskResults.tsx       任务结果页看板
    components/HistoryRecords.tsx    历史记录统计
    components/AgentDebugPanel.tsx   Agent Trace 与手动运行面板
    components/MeetingList.tsx       会议列表组件
    lib/api.ts                       前端 API 请求
    lib/types.ts                     TypeScript 类型
    styles/                          页面样式
```

## 后端 API

```text
POST  /api/meetings                    创建会议并解析纪要
GET   /api/meetings                    获取历史会议列表
GET   /api/meetings/{meeting_id}       获取会议详情
GET   /api/action-items                获取全部行动项
PATCH /api/action-items/{id}           更新行动项负责人、截止时间、状态
POST  /api/meetings/{id}/send-feishu   发送飞书会议摘要
POST  /api/meetings/{id}/follow-up     发送当前会议跟进提醒
POST  /api/follow-ups/run              批量扫描未完成任务并提醒
GET   /api/agent/traces                获取最近 Agent 执行 Trace
POST  /api/agent/debug-run             在 Web 调试面板中手动运行 Agent
POST  /api/feishu/events               飞书消息事件入口
POST  /api/feishu/card-callback        预留飞书卡片回调入口
```

## 飞书机器人使用

### 1. 事件订阅地址

本地开发需要先用 ngrok、cpolar 等工具把后端暴露到公网。

飞书事件订阅 Request URL：

```text
https://你的公网域名/api/feishu/events
```

飞书第一次校验时会发送 `challenge`，后端会原样返回。

### 2. 固定命令

```text
/help
```

查看 ActionBridge 使用帮助。

```text
/meeting 会议标题
会议正文...
```

创建会议，调用 LLM/规则解析会议纪要，并回复会议摘要卡片。

```text
/tasks
```

查询当前未完成任务列表。

```text
/task 12
```

查询任务 ID 为 12 的单个任务详情。

```text
/done 12
```

把任务 ID 为 12 的行动项标记为已完成。

```text
/remember 官网 = 官网改版
/remember project 官网 = 官网改版
/remember 张三 = 前端同学
```

项目群绑定：

```text
/bind-channel 官网改版
```

在某个飞书群里发送后，会把“官网改版”绑定到当前群。之后匹配该项目的任务完成时，机器人会把完成状态同步到该群。

记住团队内部别名。之后用户说“官网进度怎么样”，Agent 会先归一化为“官网改版进度怎么样”。

```text
/memory
```

查看当前已记住的别名。

```text
/forget 官网
```

删除一条别名记忆。

### 3. 自然语言 Agent 示例

任务查询：

```text
帮我看看今天到期的任务
逾期任务有哪些
前端同学负责的任务
官网改版相关任务
```

任务状态更新：

```text
把 12 号任务标记完成
12 号任务已完成
把 8 号任务改成进行中
9 号任务有风险
把 6 号任务改回待处理
```

截止时间修改：

```text
把 12 号任务延期到周五
把 8 号任务截止时间改成明天下午
把 6 号任务改到下周三前
```

修改截止时间会先进入确认流程。回复 `确认` 后才会更新任务，回复 `取消` 会放弃修改。

确认前可以继续修正，例如先说“把 12 号任务延期到周五”，机器人请求确认后，再说“改成下周一”，机器人会更新待确认内容。

负责人修改：

```text
把 12 号任务负责人改成测试同学
把 8 号任务转给产品经理
12 号任务交给前端同学负责
```

修改负责人同样会先进入确认流程。回复 `确认` 后才会更新任务，回复 `取消` 会放弃修改。

确认前也可以继续修正负责人，例如先说“把 12 号任务负责人改成测试同学”，再说“换成产品经理”。

如果任务 ID 不存在，机器人会回复“没有找到任务”的提示卡片，并引导你使用 `/tasks` 或 `/task 任务ID` 检查。

跟进提醒回复：

```text
完成了 #12
#12 还在进行中
#12 有风险
```

机器人会根据回复更新任务状态，并记录一条跟进回复日志。

任务创建：

```text
帮我加一个任务，前端同学周五前完成登录页联调
创建任务：设计同学 明天下午 产出首页 banner 图
新增行动项：产品经理 周三前 确认上线公告文案
```

如果缺少负责人或截止时间，机器人会先回复补充提示，不会直接创建任务。

信息完整时，机器人会先发送确认卡片。回复 `确认` 后才会真正创建任务，回复 `取消` 会放弃本次创建请求。

项目进度总结：

```text
官网改版进度怎么样
官网改版有哪些风险
总结一下官网改版项目
```

帮助：

```text
帮助
你能做什么
怎么使用
```

Memory 示例：

```text
/remember 官网 = 官网改版
官网进度怎么样
```

LLM 兜底示例：

```text
12 这个事情先别给前端了，测试同学来跟
```

当规则无法识别这类口语化表达时，LLM 会尝试转成结构化意图，例如修改负责人。后端会校验字段，并继续走确认流程。

### 4. 回复范围

```text
飞书私聊触发：回复私聊
飞书群聊触发：回复原群
Web 后台点击发送：发送默认群
自动跟进提醒：发送默认群
```

### 5. 飞书发送方式

系统优先使用自建应用机器人发送卡片：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_DEFAULT_CHAT_ID=oc_xxx
```

如果没有配置自建应用机器人，则回退到 Webhook 机器人：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id
```

## 环境变量

在项目根目录创建 `.env`，可参考 `.env.example`。

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
ACTIONBRIDGE_PARSER_PROVIDER=deepseek

FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-id
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_DEFAULT_CHAT_ID=oc_xxx

ACTIONBRIDGE_AUTO_FOLLOW_UP_ENABLED=false
ACTIONBRIDGE_AUTO_FOLLOW_UP_HOUR=10
ACTIONBRIDGE_AUTO_FOLLOW_UP_MINUTE=0
ACTIONBRIDGE_AUTO_FOLLOW_UP_POLL_SECONDS=30
```

注意：`.env` 包含密钥，不能提交到 GitHub。

## 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

后端地址：

```text
http://localhost:8000
```

Swagger 文档：

```text
http://localhost:8000/docs
```

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：

```text
http://localhost:3000
```

## 测试

后端测试：

```bash
python -m pytest backend/tests
```

前端构建：

```bash
cd frontend
npm run build
```

当前测试覆盖：

- 会议创建和详情查询
- LLM/规则解析兜底
- 行动项更新
- 任务结果页 API
- 历史记录统计
- 截止日期与到期风险判断
- 飞书卡片 payload
- 飞书 `/meeting`、`/tasks`、`/task`、`/done`、`/help`、`/bind-channel` 指令
- 飞书 `/remember`、`/memory`、`/forget` Memory 指令
- 飞书自然语言任务创建确认、截止时间修改确认、负责人修改确认、任务查询、任务更新、项目进度总结
- 待确认操作上下文修正，例如“改成下周一”“换成产品经理”
- LLM 意图识别兜底与 JSON 结构校验
- 飞书任务不存在友好提示
- 飞书跟进提醒回复状态更新与日志记录
- Agent Memory 别名归一化
- 飞书事件数据库级幂等去重
- 自动跟进扫描

## 演示流程

1. 启动后端和前端。
2. 打开 `http://localhost:3000`，粘贴会议纪要或上传文本文件。
3. 点击“AI 生成会议纪要”，查看整理结果。
4. 进入会议详情页，编辑行动项负责人、截止日期、截止时间和状态。
5. 进入 `/tasks`，查看按会议分组的任务执行看板。
6. 进入 `/history`，查看会议归档、整体执行情况和完成率。
7. 在飞书中发送 `/help`，查看机器人能力说明。
8. 在飞书中发送 `/meeting` 消息，验证机器人自动创建会议并发布卡片。
9. 在飞书中发送 `/tasks` 或自然语言查询任务。
10. 在飞书中发送 `/done 任务ID` 或自然语言更新任务状态。
11. 在飞书中发送“官网改版进度怎么样”，查看项目进度总结卡片。
12. 在飞书中发送 `/remember 官网 = 官网改版`，再发送“官网进度怎么样”，验证 Memory 归一化。
13. 在飞书中发送“帮我加一个任务，前端同学周五前完成登录页联调”，机器人会先请求确认。
14. 回复“确认”后，验证任务被创建并出现在任务结果页；回复“取消”则放弃创建。
15. 在飞书中发送“把 12 号任务延期到周五”，机器人会先请求确认，确认后更新截止时间。
16. 在飞书中发送“把 12 号任务负责人改成测试同学”，机器人会先请求确认，确认后更新负责人。
17. 在项目群发送 `/bind-channel 官网改版`，绑定项目关键词和当前群。
18. 私聊机器人发送 `/done 任务ID`，验证任务完成状态同步到绑定群。
19. 运行 `/api/follow-ups/run` 或开启自动跟进，收到提醒后回复“完成了 #任务ID”，验证任务状态自动更新。
20. 打开 `http://localhost:3000/agent-debug`，查看飞书消息产生的 Agent Trace。
21. 在 Agent 调试面板中输入“把第二个任务负责人改成测试同学”，点击“运行 Agent”，观察意图识别、工具路由和确认策略。

## 当前能力总结

- 已实现会议纪要结构化解析。
- 已实现行动项负责人、截止日期、截止时间和状态管理。
- 已实现任务结果页和历史记录页。
- 已实现飞书 Webhook 和自建应用机器人发送卡片。
- 已实现飞书 `/meeting` 消息事件接入。
- 已实现飞书 `/tasks` 查询未完成任务。
- 已实现飞书 `/task 任务ID` 查询单个任务详情。
- 已实现飞书 `/done 任务ID` 标记任务完成。
- 已实现飞书 `/help` 帮助卡片。
- 已实现飞书 `/bind-channel 项目关键词` 绑定项目同步群。
- 已实现飞书 `/remember`、`/memory`、`/forget` 结构化 Memory。
- 已实现飞书私聊/群聊上下文感知回复。
- 已实现轻量 Agent 自然语言任务查询。
- 已实现轻量 Agent 自然语言任务创建确认机制。
- 已实现轻量 Agent 自然语言截止时间修改确认机制。
- 已实现轻量 Agent 自然语言负责人修改确认机制。
- 已实现待确认操作的上下文修正。
- 已实现轻量 Agent 自然语言任务状态更新。
- 已实现 LLM 意图识别兜底，LLM 只输出结构化意图，不直接执行数据库操作。
- 已实现飞书任务不存在友好提示。
- 已实现轻量 Agent 项目进度总结。
- 已实现轻量 Agent 基于 Memory 的别名归一化。
- 已实现 LangGraph Agent 执行流，将 Memory、上下文加载、意图识别、工具执行和响应生成串联起来。
- 已实现 MCP-ready Tool Registry，支持工具元数据、危险操作标记和确认策略标记。
- 已实现 Agent Trace 调试日志，记录输入、归一化、意图、工具、执行策略和最终回复。
- 已实现 Agent Debug Run，可在网页中手动输入自然语言并运行 Agent。
- 已实现飞书事件数据库级去重。
- 已实现负责人私聊完成任务后，按项目关键词同步完成状态到绑定群。
- 已实现自动扫描未完成任务、飞书跟进提醒和提醒回复状态更新。

## 后续规划

- 完善权限控制：区分负责人、成员和只读用户，限制危险操作的执行范围。
- 优化通知策略：支持提前提醒、重复提醒、只提醒负责人和风险升级。
- 优化长文本展示：列表卡片截断、详情卡片展示完整内容。
- 增强 Memory，支持按类型分组展示、自然语言记忆和更细粒度的作用域。
- 将 LLM 解析和飞书发送异步化，引入任务队列。
- 从 SQLite 升级到 PostgreSQL，适配更真实的多人协作场景。
- 后续如需扩展办公系统，可在现有 Tool Registry 基础上新增 MCP/飞书文档/日历适配器。

## 简历描述参考

ActionBridge 是一个会议执行闭环 Agent MVP，基于 FastAPI、Next.js、SQLite、DeepSeek API、LangGraph 和飞书机器人集成，实现会议纪要结构化解析、行动项生成、任务状态跟进、历史归档、飞书消息接入、上下文感知回复、自然语言任务创建确认、截止时间修改确认、负责人修改确认、LLM 意图识别兜底、Tool Registry 工具治理、Agent Trace 调试面板、任务查询/更新、项目进度总结、自动提醒和提醒回复状态更新，帮助团队降低会议后整理与执行跟进成本。
