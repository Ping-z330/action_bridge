"""本地工具适配器：把项目工具函数包装成带 JSON Schema 的 AgentTool。

每个工具都有 parameters_schema，LLM Function Calling 会根据这些 schema
自主决定调哪个工具、传什么参数。不再需要 intent 分类器。
"""

from app.agent.tool_contracts import AgentTool, AgentToolAdapter
from app.agent import tools as agent_tools


# ── 工具注册名常量 ───────────────────────────────────────────

QUERY_TASKS = "query_tasks"
SUMMARIZE_PROJECT = "summarize_project"
UPDATE_TASK_STATUS = "update_task_status"
CREATE_TASK = "create_task"
UPDATE_TASK_DEADLINE = "update_task_deadline"
UPDATE_TASK_OWNER = "update_task_owner"
ANALYZE_RISK = "analyze_risk"
QUERY_MEMBER_ACTIVITY = "query_member_activity"
CREATE_ALERT = "create_alert"
GENERATE_PROGRESS_REPORT = "generate_progress_report"


class LocalAgentToolAdapter(AgentToolAdapter):
    name = "local_agent_tools"
    source = "local"

    def list_tools(self) -> list[AgentTool]:
        return [
            # ── 读操作：查询 ──
            AgentTool(
                name=QUERY_TASKS,
                description="查询项目中的任务列表，可按状态、负责人、关键词、到期状态过滤",
                handler=agent_tools.filter_tasks,
                source=self.source,
                category="task_query",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "failed", "blocked"],
                            "description": "任务状态筛选",
                        },
                        "owner": {
                            "type": "string",
                            "description": "负责人姓名，支持模糊匹配",
                        },
                        "keyword": {
                            "type": "string",
                            "description": "项目关键词或任务标题关键词",
                        },
                        "due_status": {
                            "type": "string",
                            "enum": ["due_today", "overdue", "upcoming"],
                            "description": "到期状态筛选",
                        },
                        "open_only": {
                            "type": "boolean",
                            "description": "是否只看未完成任务",
                        },
                    },
                },
            ),
            AgentTool(
                name=QUERY_MEMBER_ACTIVITY,
                description="查询项目成员的活跃度：最近更新时间、更新次数、负责的任务完成情况",
                handler=agent_tools.query_member_activity,
                source=self.source,
                category="task_query",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "项目 ID",
                        },
                        "member_name": {
                            "type": "string",
                            "description": "成员姓名，不填则返回所有成员",
                        },
                    },
                },
            ),

            # ── 读操作：分析/报告 ──
            AgentTool(
                name=SUMMARIZE_PROJECT,
                description="汇总项目进度：完成率、各状态任务数量、到期风险统计、进度判断结论",
                handler=agent_tools.summarize_project_progress,
                source=self.source,
                category="task_report",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "项目关键词",
                        },
                    },
                    "required": ["keyword"],
                },
            ),
            AgentTool(
                name=ANALYZE_RISK,
                description="分析项目风险：扫描逾期任务、长期未更新任务、依赖链影响，生成风险评分和预警列表",
                handler=agent_tools.analyze_project_risk,
                source=self.source,
                category="task_report",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "项目 ID",
                        },
                    },
                    "required": ["project_id"],
                },
            ),
            AgentTool(
                name=GENERATE_PROGRESS_REPORT,
                description="生成项目进度报告：包含完成率、成员活跃度、风险列表、关键路径状态",
                handler=agent_tools.generate_progress_report,
                source=self.source,
                category="task_report",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "项目 ID",
                        },
                    },
                    "required": ["project_id"],
                },
            ),

            # ── 写操作：状态更新（可直接执行） ──
            AgentTool(
                name=UPDATE_TASK_STATUS,
                description="更新任务状态。状态必须是: pending(待处理), in_progress(进行中), completed(已完成), failed(有风险), blocked(阻塞)",
                handler=agent_tools.execute_status_update_tool,
                source=self.source,
                category="task_write",
                dangerous=True,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "action_item_id": {
                            "type": "integer",
                            "description": "任务编号",
                        },
                        "target_status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "failed", "blocked"],
                            "description": "目标状态",
                        },
                    },
                    "required": ["action_item_id", "target_status"],
                },
            ),

            # ── 写操作：需要用户确认 ──
            AgentTool(
                name=CREATE_TASK,
                description="创建新任务。需要用户确认后才会真正创建。",
                handler=agent_tools.execute_create_task_tool,
                source=self.source,
                category="task_write",
                dangerous=True,
                requires_confirmation=True,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "任务标题",
                        },
                        "owner_name": {
                            "type": "string",
                            "description": "负责人姓名",
                        },
                        "deadline": {
                            "type": "string",
                            "description": "截止时间，可以是自然语言如'明天下午''下周五'",
                        },
                    },
                    "required": ["title", "owner_name", "deadline"],
                },
            ),
            AgentTool(
                name=UPDATE_TASK_DEADLINE,
                description="修改任务截止时间。需要用户确认。",
                handler=agent_tools.execute_deadline_update_tool,
                source=self.source,
                category="task_write",
                dangerous=True,
                requires_confirmation=True,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "action_item_id": {
                            "type": "integer",
                            "description": "任务编号",
                        },
                        "target_deadline": {
                            "type": "string",
                            "description": "新的截止时间",
                        },
                    },
                    "required": ["action_item_id", "target_deadline"],
                },
            ),
            AgentTool(
                name=UPDATE_TASK_OWNER,
                description="修改任务负责人。需要用户确认。",
                handler=agent_tools.execute_owner_update_tool,
                source=self.source,
                category="task_write",
                dangerous=True,
                requires_confirmation=True,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "action_item_id": {
                            "type": "integer",
                            "description": "任务编号",
                        },
                        "target_owner_name": {
                            "type": "string",
                            "description": "新的负责人姓名",
                        },
                    },
                    "required": ["action_item_id", "target_owner_name"],
                },
            ),
            AgentTool(
                name=CREATE_ALERT,
                description="创建项目预警。当发现风险时调用此工具通知负责人。",
                handler=agent_tools.create_project_alert,
                source=self.source,
                category="task_write",
                dangerous=True,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {
                            "type": "integer",
                            "description": "项目 ID",
                        },
                        "alert_type": {
                            "type": "string",
                            "enum": ["overdue", "no_update", "blocked", "dependency_chain"],
                            "description": "预警类型",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "warning", "info"],
                            "description": "严重程度",
                        },
                        "message": {
                            "type": "string",
                            "description": "预警内容",
                        },
                    },
                    "required": ["project_id", "alert_type", "severity", "message"],
                },
            ),
        ]
