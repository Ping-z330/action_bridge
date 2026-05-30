import Link from "next/link";

import { MeetingListItem } from "../lib/types";

export function MeetingList({ meetings }: { meetings: MeetingListItem[] }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <span className="section-label">历史记录</span>
          <h2>最近会议</h2>
          <p>查看已解析的会议和后续行动项。</p>
        </div>
      </div>

      <div className="panel-body meeting-list">
        {meetings.length === 0 ? (
          <p className="helper-text">还没有会议记录，先创建第一条会议。</p>
        ) : (
          meetings.map((meeting) => (
            <Link key={meeting.id} href={`/meetings/${meeting.id}`} className="meeting-row">
              <strong>{meeting.title}</strong>
              <p>{meeting.summary}</p>
            </Link>
          ))
        )}
      </div>
    </section>
  );
}
