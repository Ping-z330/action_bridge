import Link from "next/link";

import { MeetingListItem } from "../lib/types";

export function MeetingList({ meetings }: { meetings: MeetingListItem[] }) {
  // 首页右侧的最近会议列表；点击会议行进入对应详情页。
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
          <>
            {/* 没有会议时展示空状态，提示用户先创建会议纪要。 */}
            <p className="helper-text">还没有会议记录，先创建第一条会议。</p>
          </>
        ) : (
          <>
            {/* 有会议时展示可点击的会议摘要列表。 */}
            {meetings.map((meeting) => (
              <Link key={meeting.id} href={`/meetings/${meeting.id}`} className="meeting-row">
                <strong>{meeting.title}</strong>
                <p>{meeting.summary}</p>
              </Link>
            ))}
          </>
        )}
      </div>
    </section>
  );
}
