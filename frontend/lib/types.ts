// 单个行动项的基础结构。
// 常用于会议详情页里的行动项编辑列表。
export type ActionItem = {
  id: number;
  title: string;
  owner_name: string;

  // deadline 是展示用的截止时间文本。
  // deadline_date/deadline_time 是前端表单更容易编辑的结构化日期和时间。
  deadline: string;
  deadline_date: string;
  deadline_time: string;

  // 任务状态，例如 pending、in_progress、completed、failed。
  status: string;
};

// 行动项列表项，比 ActionItem 多了来源会议和到期风险信息。
// /tasks 页面和飞书任务查询结果常用这个结构。
export type ActionItemListItem = ActionItem & {
  meeting_id: number;
  meeting_title: string;

  // due_status 是机器可判断的到期状态，例如 overdue、due_today、completed。
  // due_status_label 是页面直接展示给用户看的中文文案。
  due_status: string;
  due_status_label: string;
  created_at: string;
};

// 单个会议详情。
// GET /api/meetings/{id} 返回这个结构。
export type Meeting = {
  id: number;
  title: string;
  raw_transcript: string;
  summary: string;
  decisions: string[];
  created_at: string;

  // 这个会议解析出来的所有行动项。
  action_items: ActionItem[];
};

// 会议列表项。
// GET /api/meetings 返回这个结构，用于首页/历史页列表。
export type MeetingListItem = {
  id: number;
  title: string;
  summary: string;
  created_at: string;

  // 下面这些字段是后端提前算好的统计数据，前端直接展示即可。
  action_count: number;
  pending_count: number;
  completed_count: number;
  due_today_count: number;
  overdue_count: number;

  // open 表示还有未完成行动项；closed 表示会议行动项已全部完成。
  closure_status: string;
};

// 一次跟进扫描里，某个会议的提醒结果。
export type FollowUpRunItem = {
  meeting_id: number;
  meeting_title: string;
  reminder_count: number;
  reminder_types: string[];
  status: string;
  message: string;
};

// POST /api/follow-ups/run 的返回结构。
// 用于“批量跟进”按钮展示扫描和发送结果。
export type FollowUpRunResponse = {
  scanned_meetings: number;
  total_candidates: number;
  total_sent: number;
  results: FollowUpRunItem[];
};

// Agent 执行 trace。
// /agent-debug 页面用它展示 Agent 如何理解消息、路由工具、是否需要确认。
export type AgentTraceLogItem = {
  id: number;
  chat_id: string;
  source: string;

  // 用户原始消息，以及经过 Memory/别名归一化后的消息。
  message: string;
  normalized_message: string;

  // Agent 识别出来的意图和过滤条件。
  intent_name: string;
  intent_filters: Record<string, unknown>;

  // Agent 选择执行的工具信息。
  tool_name: string;
  tool_source: string;
  tool_category: string;
  tool_executed: boolean;

  // dangerous/requires_confirmation 用来说明是否属于危险写操作。
  dangerous: boolean;
  requires_confirmation: boolean;

  // 最终回复给用户的文本。
  response_message: string;
  created_at: string;
};

// Web 调试页手动运行 Agent 后的返回结构。
export type AgentDebugRunResponse = {
  handled: boolean;
  intent_name: string;
  message: string;

  // trace_id 可用来在 trace 列表中定位本次运行记录。
  trace_id: number | null;
};
