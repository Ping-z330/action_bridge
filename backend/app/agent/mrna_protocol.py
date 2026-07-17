"""mRNA Protocol: Message Relay for Networked Agents.

Agent-to-Agent 通信协议。个人助手（PersonalAssistant）将成员的进度汇报
转成结构化消息，通过 mRNA 传递给中央项目 Agent（CentralAgent）。

取名为 mRNA 是因为个人助手像 mRNA 一样把"基因信息"（成员状态）
从个人端转录并传递到中央系统。

This is NOT a network protocol — personal assistants and the central agent
share the same process space. mRNA is a data contract, not a transport.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ── 协议结构 ────────────────────────────────────────────────

@dataclass
class mRNAEnvelope:
    """A structured message from one agent to another."""
    sender_agent_id: str       # "personal:zhangsan" | "central:project-1"
    receiver_agent_id: str     # "central:project-1"  | "personal:zhangsan"
    message_type: str          # "task_update" | "status_report" | "alert_ack" | "query"
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ── 消息类型常量 ─────────────────────────────────────────────

MSG_TASK_UPDATE = "task_update"        # 成员完成/更新了一个任务
MSG_STATUS_REPORT = "status_report"    # 成员做了进度汇报（未绑定具体任务）
MSG_ALERT_ACK = "alert_ack"           # 负责人确认/处理了一个预警
MSG_RISK_QUERY = "risk_query"         # 负责人主动查询项目风险


# ── mRNA 路由器 ──────────────────────────────────────────────

class mRNAHub:
    """Central hub that routes mRNA messages between agents.

    All agents register here. When one agent sends a message,
    the hub delivers it to the receiver's mailbox (an in-memory list).
    """

    def __init__(self):
        self._mailboxes: dict[str, list[mRNAEnvelope]] = {}
        self._sent_messages: list[mRNAEnvelope] = []

    def register_agent(self, agent_id: str) -> None:
        """Register an agent so it can receive messages."""
        if agent_id not in self._mailboxes:
            self._mailboxes[agent_id] = []

    def send(self, envelope: mRNAEnvelope) -> None:
        """Deliver a message to the receiver's mailbox."""
        if envelope.receiver_agent_id not in self._mailboxes:
            self._mailboxes[envelope.receiver_agent_id] = []
        self._mailboxes[envelope.receiver_agent_id].append(envelope)
        self._sent_messages.append(envelope)

    def poll(self, agent_id: str) -> list[mRNAEnvelope]:
        """Get and clear all pending messages for an agent."""
        messages = list(self._mailboxes.get(agent_id, []))
        self._mailboxes[agent_id] = []
        return messages

    def get_all_sent(self) -> list[mRNAEnvelope]:
        """Return all messages ever sent through this hub (for debugging)."""
        return list(self._sent_messages)


# 模块级单例 — 项目内所有 Agent 共享同一个 hub
_default_hub: mRNAHub | None = None


def get_mrna_hub() -> mRNAHub:
    global _default_hub
    if _default_hub is None:
        _default_hub = mRNAHub()
    return _default_hub
