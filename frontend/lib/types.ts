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
