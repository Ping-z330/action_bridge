import Link from "next/link";
import { AppShell } from "../components/AppShell";
import { fetchActionItems, fetchMeetings } from "../lib/api";
import { ActionItemListItem, MeetingListItem } from "../lib/types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function StatCard({ label, value, color = "" }: { label: string; value: number | string; color?: string }) {
  return (
    <div className="debug-stat-card">
      <span>{label}</span>
      <strong style={color ? { color } : undefined}>{value}</strong>
    </div>
  );
}

function EmptyState() {
  return (
    <section className="work-card" style={{ textAlign: "center", padding: "3rem 2rem" }}>
      <p style={{ fontSize: "3rem", margin: "0 0 1rem" }}>🚀</p>
      <h2 style={{ marginBottom: "0.5rem" }}>欢迎使用 ActionBridge</h2>
      <p style={{ color: "#868e96", maxWidth: 500, margin: "0 auto 1.5rem", lineHeight: 1.7 }}>
        这是一个基于 A2A 架构的多 Agent 项目管理系统。
        每个成员拥有私有 AI 助手，中央 Agent 持有项目依赖图，自动发现风险并预警。
      </p>
      <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
        <Link className="primary-link" href="/meetings/new" style={{ padding: "12px 24px", fontSize: "1rem" }}>
          ① 创建会议，AI 解析行动项
        </Link>
        <Link className="primary-link" href="/demo" style={{ padding: "12px 24px", fontSize: "1rem", background: "#2b8a3e" }}>
          ② 模拟多 Agent 协作
        </Link>
        <Link className="secondary-link" href="/agent-debug" style={{ padding: "12px 24px", fontSize: "1rem" }}>
          ③ 查看 Agent 决策链
        </Link>
      </div>
      <p style={{ color: "#adb5bd", fontSize: "0.85rem", marginTop: "1.5rem" }}>
        还没有数据？先从第 ① 步开始——粘贴一段会议记录，AI 会自动提取行动项和负责人。
      </p>
    </section>
  );
}

export default async function HomePage() {
  const meetings = await fetchMeetings().catch(() => [] as MeetingListItem[]);
  const actionItems = await fetchActionItems().catch(() => [] as ActionItemListItem[]);

  // Show empty state when no data
  if (meetings.length === 0 && actionItems.length === 0) {
    return (
      <AppShell active="meetings">
        <section className="debug-hero">
          <div>
            <p className="section-label">ActionBridge · A2A 项目管理系统</p>
            <h1>项目执行全景</h1>
            <p>
              每个成员拥有私有 AI 助手，中央 Agent 持有项目依赖图。
              AI 监控进度、发现风险、主动预警——人做最终决策。
            </p>
          </div>
        </section>
        <EmptyState />
      </AppShell>
    );
  }

  // Calculate dashboard stats
  const total = actionItems.length;
  const completed = actionItems.filter((i) => i.status === "completed").length;
  const inProgress = actionItems.filter((i) => i.status === "in_progress").length;
  const pending = actionItems.filter((i) => i.status === "pending").length;
  const failed = actionItems.filter((i) => i.status === "failed").length;
  const overdue = actionItems.filter((i) => i.due_status === "overdue").length;
  const dueToday = actionItems.filter((i) => i.due_status === "due_today").length;
  const completionRate = total > 0 ? Math.round((completed / total) * 100) : 0;

  // Member stats
  const ownerMap = new Map<string, { total: number; completed: number }>();
  actionItems.forEach((item) => {
    if (!item.owner_name || item.owner_name === "Pending confirmation") return;
    const entry = ownerMap.get(item.owner_name) || { total: 0, completed: 0 };
    entry.total++;
    if (item.status === "completed") entry.completed++;
    ownerMap.set(item.owner_name, entry);
  });
  const members = Array.from(ownerMap.entries())
    .map(([name, stats]) => ({ name, ...stats, rate: Math.round((stats.completed / stats.total) * 100) }))
    .sort((a, b) => b.rate - a.rate);

  return (
    <AppShell active="meetings">
      {/* Hero section */}
      <section className="debug-hero">
        <div>
          <p className="section-label">ActionBridge · A2A 项目管理系统</p>
          <h1>项目执行全景</h1>
          <p>
            每个成员拥有私有 AI 助手，中央 Agent 持有项目依赖图。
            AI 监控进度、发现风险、主动预警——人做最终决策。
          </p>
          <div style={{ marginTop: 12, display: "flex", gap: 10 }}>
            <Link className="primary-link" href="/demo">
              模拟多 Agent 协作
            </Link>
            <Link className="primary-link" href="/agent-debug" style={{ background: "#2b8a3e" }}>
              Agent 调试面板
            </Link>
            <Link className="secondary-link" href="/tasks">
              任务看板
            </Link>
          </div>
        </div>
      </section>

      {/* Stats grid */}
      <div className="debug-stat-grid">
        <StatCard label="任务总数" value={total} />
        <StatCard label="完成率" value={`${completionRate}%`} color={completionRate === 100 ? "#2b8a3e" : completionRate > 50 ? "#1971c2" : "#e8590c"} />
        <StatCard label="进行中" value={inProgress} />
        <StatCard label="待处理" value={pending} />
        <StatCard label="有风险/阻塞" value={failed} color={failed > 0 ? "#c92a2a" : ""} />
        <StatCard label="已逾期" value={overdue} color={overdue > 0 ? "#c92a2a" : ""} />
        <StatCard label="今日到期" value={dueToday} color={dueToday > 0 ? "#e8590c" : ""} />
        <StatCard label="已完成" value={completed} color="#2b8a3e" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        {/* Member activity */}
        <section className="work-card">
          <h2>成员活跃度</h2>
          {members.length === 0 ? (
            <p style={{ color: "#868e96" }}>暂无成员数据</p>
          ) : (
            <table className="work-table">
              <thead>
                <tr>
                  <th>成员</th>
                  <th>任务数</th>
                  <th>完成率</th>
                  <th>活跃度</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.name}>
                    <td>{m.name}</td>
                    <td>{m.total}</td>
                    <td>{m.rate}%</td>
                    <td>
                      <span
                        className={`status-chip ${m.rate === 100 ? "status-completed" : m.total === 0 ? "status-risk" : "status-progress"}`}
                      >
                        {m.rate === 100 ? "已完成" : m.total === 0 ? "无更新" : "进行中"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Risk alerts */}
        <section className="work-card">
          <h2>风险概览</h2>
          {overdue === 0 && failed === 0 ? (
            <div style={{ padding: "2rem 0", textAlign: "center" }}>
              <p style={{ fontSize: "2rem", margin: 0 }}>✅</p>
              <p style={{ color: "#868e96" }}>当前无风险项。项目状态健康。</p>
            </div>
          ) : (
            <ul className="plain-list">
              {overdue > 0 && (
                <li>🔴 {overdue} 个任务已逾期——建议立即确认进度</li>
              )}
              {failed > 0 && (
                <li>🟡 {failed} 个任务标记为有风险/阻塞</li>
              )}
              {dueToday > 0 && (
                <li>📌 {dueToday} 个任务今日到期——建议当天完成确认</li>
              )}
            </ul>
          )}
        </section>
      </div>

      {/* Quick create meeting */}
      <section className="work-card" style={{ marginTop: "1rem" }}>
        <h2>快速操作</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <Link className="primary-link" href="/meetings/new">+ 新建会议（AI 解析）</Link>
          <Link className="secondary-link" href="/agent-debug">Agent 调试</Link>
        </div>
      </section>

      {/* Meeting history (kept for backward compat) */}
      {meetings.length > 0 && (
        <section className="work-card" style={{ marginTop: "1rem" }}>
          <h2>最近会议 / 项目 ({meetings.length})</h2>
          <table className="work-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>任务数</th>
                <th>待处理</th>
                <th>已完成</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {meetings.slice(0, 8).map((m) => (
                <tr key={m.id}>
                  <td>
                    <Link href={`/meetings/${m.id}`} prefetch={false}>
                      {m.title}
                    </Link>
                  </td>
                  <td>{m.action_count}</td>
                  <td>{m.pending_count}</td>
                  <td>{m.completed_count}</td>
                  <td>
                    <span className={`status-chip ${m.closure_status === "closed" ? "status-completed" : "status-pending"}`}>
                      {m.closure_status === "closed" ? "已闭环" : "进行中"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </AppShell>
  );
}
