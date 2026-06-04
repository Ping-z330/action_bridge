from app.agent.tool_contracts import AgentTool, AgentToolAdapter
from app.agent.tools import (
    execute_create_task_tool,
    execute_deadline_update_tool,
    execute_owner_update_tool,
    execute_status_update_tool,
    filter_tasks,
    summarize_project_progress,
)


QUERY_TASKS = "query_tasks"
SUMMARIZE_PROJECT = "summarize_project"
UPDATE_TASK_STATUS = "update_task_status"
CREATE_TASK = "create_task"
UPDATE_TASK_DEADLINE = "update_task_deadline"
UPDATE_TASK_OWNER = "update_task_owner"


class LocalAgentToolAdapter(AgentToolAdapter):
    name = "local_agent_tools"
    source = "local"

    def list_tools(self) -> list[AgentTool]:
        return [
            AgentTool(
                name=QUERY_TASKS,
                description="Filter action items by status, due status, owner, or project keyword.",
                handler=filter_tasks,
                source=self.source,
                category="task_query",
            ),
            AgentTool(
                name=SUMMARIZE_PROJECT,
                description="Summarize project progress from action items and a project keyword.",
                handler=summarize_project_progress,
                source=self.source,
                category="task_report",
            ),
            AgentTool(
                name=UPDATE_TASK_STATUS,
                description="Update an action item's status.",
                handler=execute_status_update_tool,
                source=self.source,
                category="task_write",
                dangerous=True,
            ),
            AgentTool(
                name=CREATE_TASK,
                description="Create a manual action item from an agent-confirmed task.",
                handler=execute_create_task_tool,
                source=self.source,
                category="task_write",
                dangerous=True,
                requires_confirmation=True,
            ),
            AgentTool(
                name=UPDATE_TASK_DEADLINE,
                description="Update an action item's deadline.",
                handler=execute_deadline_update_tool,
                source=self.source,
                category="task_write",
                dangerous=True,
                requires_confirmation=True,
            ),
            AgentTool(
                name=UPDATE_TASK_OWNER,
                description="Update an action item's owner.",
                handler=execute_owner_update_tool,
                source=self.source,
                category="task_write",
                dangerous=True,
                requires_confirmation=True,
            ),
        ]
