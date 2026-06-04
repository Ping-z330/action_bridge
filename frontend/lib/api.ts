import { ActionItemListItem, AgentDebugRunResponse, AgentTraceLogItem, Meeting, MeetingListItem } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class MeetingNotFoundError extends Error {
  constructor(id: string) {
    super(`Meeting ${id} not found`);
    this.name = "MeetingNotFoundError";
  }
}

export async function fetchMeetings(): Promise<MeetingListItem[]> {
  const response = await fetch(`${API_BASE}/api/meetings`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to fetch meetings");
  }
  return response.json();
}

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

export async function fetchActionItems(): Promise<ActionItemListItem[]> {
  const response = await fetch(`${API_BASE}/api/action-items`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to fetch action items");
  }
  return response.json();
}

export async function fetchAgentTraces(): Promise<AgentTraceLogItem[]> {
  const response = await fetch(`${API_BASE}/api/agent/traces`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to fetch agent traces");
  }
  return response.json();
}

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
