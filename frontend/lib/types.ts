export type ActionItem = {
  id: number;
  title: string;
  owner_name: string;
  deadline: string;
  status: string;
};

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
};

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
