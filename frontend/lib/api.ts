import { ActionItemListItem, AgentDebugRunResponse, AgentTraceLogItem, Meeting, MeetingListItem } from "./types";

// 这个模块封装了前端与后端 API 交互的函数，包括获取会议列表、获取会议详情、获取行动项列表、获取智能体调试日志以及运行智能体调试等功能。
// 每个函数都使用 fetch API 来发送 HTTP 请求，并根据响应状态处理错误情况。

// API_BASE是后端API的基础URL，默认值是http://localhost:8000，
// 但可以通过环境变量NEXT_PUBLIC_API_BASE进行覆盖，以适应不同的部署环境。
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// 自定义错误类，用于在获取会议详情时遇到404错误时抛出，方便前端进行特定的错误处理。
export class MeetingNotFoundError extends Error {
  constructor(id: string) {
    super(`Meeting ${id} not found`);
    this.name = "MeetingNotFoundError";
  }
}

// fetchMeetings函数用于获取会议列表
export async function fetchMeetings(): Promise<MeetingListItem[]> {
  const response = await fetch(`${API_BASE}/api/meetings`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to fetch meetings");
  }
  return response.json();
}

// fetchMeeting函数用于获取特定会议的详情
export async function fetchMeeting(id: string): Promise<Meeting> {
  const response = await fetch(`${API_BASE}/api/meetings/${id}`, { cache: "no-store" });
  if (response.status === 404) {
    throw new MeetingNotFoundError(id);
  }
  if (!response.ok) {
    throw new Error("Failed to fetch meeting");
  }
  return response.json();
}

// fetchActionItems函数用于获取行动项列表
export async function fetchActionItems(): Promise<ActionItemListItem[]> {
  const response = await fetch(`${API_BASE}/api/action-items`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to fetch action items");
  }
  return response.json();
}

// fetchAgentTraces函数用于获取智能体调试日志列表
export async function fetchAgentTraces(): Promise<AgentTraceLogItem[]> {
  const response = await fetch(`${API_BASE}/api/agent/traces`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to fetch agent traces");
  }
  return response.json();
}

// runAgentDebug函数用于运行智能体调试，接受一个消息字符串和一个可选的聊天ID参数，发送POST请求到后端API，并返回调试结果。
export async function runAgentDebug(message: string, chatId = "debug-web"): Promise<AgentDebugRunResponse> {
  const response = await fetch(`${API_BASE}/api/agent/debug-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, chat_id: chatId }),
  });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(errorBody?.detail ?? "Failed to run agent debug");
  }
  return response.json();
}
