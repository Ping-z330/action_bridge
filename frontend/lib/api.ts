import { Meeting, MeetingListItem } from "./types";

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
