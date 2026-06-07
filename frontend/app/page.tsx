import Link from "next/link";

// 首页会议处理界面，左侧是会议输入表单，右侧是会议结果预览
import { AppShell } from "../components/AppShell";
import { MeetingForm } from "../components/MeetingForm";
import { fetchMeeting, fetchMeetings } from "../lib/api";
import { Meeting } from "../lib/types";

// 这个页面会根据 URL 参数 ?meetingId= 来决定展示哪个会议的结果，如果没有参数则默认展示最新会议的结果。

// 动态渲染，每次获取最新数据
export const dynamic = "force-dynamic";
export const revalidate = 0;

// “翻译字典”，将后端返回的状态码转换为用户友好的标签
const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  in_progress: "进行中",
  completed: "已完成",
  failed: "有风险",
};

// 把英文状态转换成中文
function getStatusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

// 根据状态返回对应的 CSS 类名，用于在界面上显示不同的颜色或样式
function getStatusClass(status: string) {
  if (status === "completed") return "status-completed";
  if (status === "failed") return "status-risk";
  if (status === "in_progress") return "status-progress";
  return "status-pending";
}

// 右侧结果预览组件
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
        // 如果有会议数据，就展示摘要、决策和行动项等内容
        <div className="result-stack">

          {/* 会议摘要 */}
          <section className="result-block">
            <h3>会议摘要</h3>
            <p>{meeting.summary}</p>
          </section>

          {/* 关键决策 */}
          <section className="result-block">
            <h3>关键决策</h3>
            {meeting.decisions.length > 0 ? (
              <ul className="plain-list">
                {meeting.decisions.map((decision) => (
                  <li key={decision}>{decision}</li>
                ))}
              </ul>
            ) : (
              // 如果没有决策，就显示一个提示信息
              <p>暂无明确决策。</p>
            )}
          </section>
          
          {/* 行动项 */}
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
                {/* 行动项列表 */}
                {meeting.action_items.map((item) => (
                  // map
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
          
          {/* 风险与关注点 */}
          <section className="result-block">
            <h3>风险与关注点</h3>
            <ul className="plain-list">
              <li>请确认负责人和截止时间是否完整。</li>
              <li>未完成行动项会参与后续跟进提醒。</li>
            </ul>
          </section>
          
          {/* 操作栏 */}
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
        // 如果没有会议数据，就显示一个等待提示
        <div className="empty-result">
          <p className="empty-title">等待会议输入</p>
          <p>左侧生成第一条会议纪要后，这里会展示摘要、关键决策和行动项。</p>
        </div>
      )}
    </section>
  );
}

// 首页组件，负责获取会议列表和选定会议的详情，并将数据传递给 MeetingForm 和 ResultPreview 组件进行展示
export default async function HomePage({
  searchParams,
}: {
  searchParams?: { meetingId?: string };
}) {
  // 获取会议列表
  const meetings = await fetchMeetings().catch(() => []);
  //决定当前选中哪个会议，如果 URL 参数里有 meetingId 就选那个，否则默认选第一个会议（最新的会议）
  const selectedMeetingId = searchParams?.meetingId ?? meetings[0]?.id?.toString();
  //当前选中会议的详情数据，如果没有选中会议或获取失败则为 undefined
  const selectedMeeting = selectedMeetingId ? await fetchMeeting(selectedMeetingId).catch(() => undefined) : undefined;

  return (
    // 使用 AppShell 组件作为页面的布局框架，传入 active="meetings" 来高亮当前导航项
    <AppShell active="meetings">
      <section className="workspace-board">
        <MeetingForm />
        <ResultPreview meeting={selectedMeeting} />
      </section>
    </AppShell>
  );
}
