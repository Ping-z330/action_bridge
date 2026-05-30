import Link from "next/link";

import { AppShell } from "../components/AppShell";
import { MeetingForm } from "../components/MeetingForm";
import { fetchMeeting, fetchMeetings } from "../lib/api";
import { Meeting } from "../lib/types";

function getStatusLabel(status: string) {
  return status === "completed" ? "已完成" : "待处理";
}

function getStatusClass(status: string) {
  return status === "completed" ? "status-completed" : "status-pending";
}

function ResultPreview({ meeting }: { meeting?: Meeting }) {
  return (
    <section className="work-card result-column">
      <div className="work-card-header">
        <div>
          <p className="step-title">2. AI 整理结果</p>
          <p className="header-note">生成后会停留在当前页面，右侧直接展示本次会议的整理结果。</p>
        </div>
        {meeting ? <span className="ok-dot">已就绪</span> : null}
      </div>

      {meeting ? (
        <div className="result-stack">
          <section className="result-block">
            <h3>会议摘要</h3>
            <p>{meeting.summary}</p>
          </section>

          <section className="result-block">
            <h3>关键决策</h3>
            {meeting.decisions.length > 0 ? (
              <ul className="plain-list">
                {meeting.decisions.map((decision) => (
                  <li key={decision}>{decision}</li>
                ))}
              </ul>
            ) : (
              <p>暂无明确决策。</p>
            )}
          </section>

          <section className="result-block">
            <h3>行动项</h3>
            <table className="work-table">
              <thead>
                <tr>
                  <th>任务目标</th>
                  <th>负责人</th>
                  <th>截止时间</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {meeting.action_items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.title}</td>
                    <td>{item.owner_name}</td>
                    <td>{item.deadline}</td>
                    <td>
                      <span className={`status-chip ${getStatusClass(item.status)}`}>
                        {getStatusLabel(item.status)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="result-block">
            <h3>风险与关注点</h3>
            <ul className="plain-list">
              <li>请确认负责人和截止时间是否完整。</li>
              <li>未完成行动项会参与后续跟进提醒。</li>
            </ul>
          </section>

          <div className="action-bar">
            <Link className="secondary-link" href={`/meetings/${meeting.id}`} prefetch={false}>
              查看详情
            </Link>
            <Link className="primary-link" href="/tasks" prefetch={false}>
              查看任务结果
            </Link>
          </div>
        </div>
      ) : (
        <div className="empty-result">
          <p className="empty-title">等待会议输入</p>
          <p>左侧生成第一条会议纪要后，这里会展示摘要、关键决策和行动项。</p>
        </div>
      )}
    </section>
  );
}

export default async function HomePage({
  searchParams,
}: {
  searchParams?: { meetingId?: string };
}) {
  const meetings = await fetchMeetings().catch(() => []);
  const selectedMeetingId = searchParams?.meetingId ?? meetings[0]?.id?.toString();
  const selectedMeeting = selectedMeetingId ? await fetchMeeting(selectedMeetingId).catch(() => undefined) : undefined;

  return (
    <AppShell active="meetings">
      <section className="workspace-board">
        <MeetingForm />
        <ResultPreview meeting={selectedMeeting} />
      </section>
    </AppShell>
  );
}
