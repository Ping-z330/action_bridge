import Link from "next/link";

import { MeetingListItem } from "../lib/types";

export function MeetingList({ meetings }: { meetings: MeetingListItem[] }) {
  return (
    <section className="panel stack">
      <div>
        <span className="pill">历史记录</span>
        <h2>最近会议</h2>
      </div>
      <div className="stack">
        {meetings.length === 0 ? (
          <p style={{ margin: 0 }}>还没有会议记录，先从左侧表单创建第一条吧。</p>
        ) : (
          meetings.map((meeting) => (
            <Link key={meeting.id} href={`/meetings/${meeting.id}`} className="panel">
              <strong>{meeting.title}</strong>
              <p>{meeting.summary}</p>
            </Link>
          ))
        )}
      </div>
    </section>
  );
}
