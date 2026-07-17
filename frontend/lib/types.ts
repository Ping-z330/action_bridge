// ── Project models ────────────────────────────────────────

export type Project = {
  id: number;
  name: string;
  description: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
};

export type Member = {
  id: number;
  project_id: number;
  name: string;
  chat_id: string;
  role: string;
  last_active_at: string;
  created_at: string;
};

export type Alert = {
  id: number;
  project_id: number;
  alert_type: "overdue" | "no_update" | "blocked" | "dependency_chain";
  severity: "critical" | "warning" | "info";
  message: string;
  status: "active" | "acknowledged" | "resolved";
  acknowledged_by: string;
  created_at: string;
  resolved_at: string | null;
};

// ── Task models ────────────────────────────────────────────

export type ActionItem = {
  id: number;
  title: string;
  owner_name: string;
  deadline: string;
  deadline_date: string;
  deadline_time: string;
  status: string;
};

export type ActionItemListItem = ActionItem & {
  meeting_id: number;
  meeting_title: string;
  due_status: string;
  due_status_label: string;
  created_at: string;
};

// ── Meeting models (kept for backward compatibility) ───────

export type Meeting = {
  id: number;
  title: string;
  raw_transcript: string;
  summary: string;
  decisions: string[];
  created_at: string;
  action_items: ActionItem[];
};

export type MeetingListItem = {
  id: number;
  title: string;
  summary: string;
  created_at: string;
  action_count: number;
  pending_count: number;
  completed_count: number;
  due_today_count: number;
  overdue_count: number;
  closure_status: string;
};

// ── Agent trace models ─────────────────────────────────────

export type AgentStep = {
  thought: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  tool_result: string;
  tool_error: string;
};

export type AgentTraceLogItem = {
  id: number;
  chat_id: string;
  source: string;
  message: string;
  normalized_message: string;
  intent_name: string;
  intent_filters: Record<string, unknown>;
  tool_name: string;
  tool_source: string;
  tool_category: string;
  tool_executed: boolean;
  dangerous: boolean;
  requires_confirmation: boolean;
  response_message: string;
  steps_json?: string;  // JSON string of AgentStep[]
  created_at: string;
};

export type AgentDebugRunResponse = {
  handled: boolean;
  intent_name: string;
  message: string;
  trace_id: number | null;
  steps?: AgentStep[];  // ReAct steps for debug panel
};

// ── Risk / Report models ───────────────────────────────────

export type RiskAssessment = {
  task_id: number;
  task_title: string;
  risk_type: string;
  severity: string;
  description: string;
  impacted_task_ids: number[];
};

export type ProjectRiskReport = {
  project_id: number;
  risk_score: number;
  total_tasks: number;
  overdue_count: number;
  no_update_count: number;
  blocked_count: number;
  risks: RiskAssessment[];
  conclusion: string;
};

export type ProjectHealth = {
  project_id: number;
  total_tasks: number;
  completed: number;
  in_progress: number;
  pending: number;
  failed: number;
  completion_rate: number;
  member_count: number;
  active_alert_count: number;
  alerts: Alert[];
};

// ── mRNA trace models ─────────────────────────────────────────

export type mRNAEnvelope = {
  sender_agent_id: string;
  receiver_agent_id: string;
  message_type: string;
  payload: Record<string, unknown>;
  timestamp: string;
};

// ── Old types kept for backward compat ─────────────────────

export type FollowUpRunItem = {
  meeting_id: number;
  meeting_title: string;
  reminder_count: number;
  reminder_types: string[];
  status: string;
  message: string;
};

export type FollowUpRunResponse = {
  scanned_meetings: number;
  total_candidates: number;
  total_sent: number;
  results: FollowUpRunItem[];
};
