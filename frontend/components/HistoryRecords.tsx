"use client";

import Link from "next/link";
import { CSSProperties, useMemo, useState } from "react";

import { ActionItemListItem, MeetingListItem } from "../lib/types";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function getClosureLabel(meeting: MeetingListItem) {
  if (meeting.overdue_count > 0) return "存在风险";
  if (meeting.closure_status === "closed") return "已完成闭环";
  return "执行中";
}

function getClosureClass(meeting: MeetingListItem) {
  if (meeting.overdue_count > 0) return "status-risk";
  return meeting.closure_status === "closed" ? "status-completed" : "status-progress";
}

function getPercent(part: number, total: number) {
  if (total === 0) return 0;
  return Math.round((part / total) * 1000) / 10;
}

type HistoryRecordsProps = {
  meetings: MeetingListItem[];
  actionItems: ActionItemListItem[];
};

export function HistoryRecords({ meetings, actionItems }: HistoryRecordsProps) {
  const [keyword, setKeyword] = useState("");

  const filteredMeetings = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();

    if (!normalizedKeyword) {
      return meetings;
    }

    return meetings.filter((meeting) => {
      return (
        meeting.title.toLowerCase().includes(normalizedKeyword) ||
        meeting.summary.toLowerCase().includes(normalizedKeyword)
      );
    });
  }, [keyword, meetings]);

  const stats = useMemo(() => {
    const actionCount = actionItems.length;
    const completedCount = actionItems.filter((item) => item.status === "completed").length;
    const inProgressCount = actionItems.filter((item) => item.status === "in_progress").length;
    const overdueCount = actionItems.filter((item) => item.status !== "completed" && item.due_status === "overdue").length;
    const pendingCount = actionItems.filter((item) => item.status === "pending").length;
    const failedCount = actionItems.filter((item) => item.status === "failed").length;

    return {
      totalMeetings: meetings.length,
      actionCount,
      completedCount,
      inProgressCount,
      overdueCount,
      pendingCount,
      failedCount,
      completedRate: getPercent(completedCount, actionCount),
      inProgressRate: getPercent(inProgressCount, actionCount),
      overdueRate: getPercent(overdueCount, actionCount),
      pendingRate: getPercent(pendingCount, actionCount),
    };
  }, [actionItems, meetings.length]);

  const ringStyle = {
    "--completed-rate": `${stats.completedRate * 3.6}deg`,
  } as CSSProperties;

  return (
    <section className="history-page">
      <section className="history-overview">
        <div className="history-overview-heading">
          <h1>整体执行情况</h1>
          <span>所有时间</span>
        </div>

        <div className="history-overview-body">
          <div className="history-metric-grid">
            <div className="history-metric-card">
              <span>会议总数</span>
              <strong>{stats.totalMeetings}</strong>
            </div>
            <div className="history-metric-card">
              <span>行动项总数</span>
              <strong>{stats.actionCount}</strong>
            </div>
            <div className="history-metric-card">
              <span>已完成</span>
              <div className="metric-value-row">
                <strong>{stats.completedCount}</strong>
                <em className="metric-up">{stats.completedRate}%</em>
              </div>
            </div>
            <div className="history-metric-card">
              <span>进行中</span>
              <div className="metric-value-row">
                <strong>{stats.inProgressCount}</strong>
                <em className="metric-info">{stats.inProgressRate}%</em>
              </div>
            </div>
            <div className="history-metric-card">
              <span>逾期</span>
              <div className="metric-value-row">
                <strong>{stats.overdueCount}</strong>
                <em className="metric-danger">{stats.overdueRate}%</em>
              </div>
            </div>
            <div className="history-metric-card">
              <span>待处理</span>
              <div className="metric-value-row">
                <strong>{stats.pendingCount}</strong>
                <em className="metric-warning">{stats.pendingRate}%</em>
              </div>
            </div>
          </div>

          <div className="history-rate-ring" style={ringStyle}>
            <div>
              <strong>{stats.completedRate}%</strong>
              <span>整体完成率</span>
            </div>
          </div>
        </div>
      </section>

      <div className="work-card history-list-card">
        <div className="history-toolbar">
          <div>
            <h2>会议记录</h2>
            <p>按时间倒序展示已处理会议。</p>
          </div>
          <div className="history-toolbar-actions">
            <input
              className="history-search"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索会议标题或摘要"
            />
            <Link className="primary-link" href="/" prefetch={false}>
              新增会议纪要
            </Link>
          </div>
        </div>

        {filteredMeetings.length === 0 ? (
          <div className="empty-result">
            <p className="empty-title">暂无会议记录</p>
            <p>可以先从会议处理页生成一条会议纪要，历史记录会自动沉淀在这里。</p>
          </div>
        ) : (
          <div className="history-record-list">
            {filteredMeetings.map((meeting) => (
              <article key={meeting.id} className="history-record">
                <div className="history-record-main">
                  <div className="history-record-title">
                    <h3>{meeting.title}</h3>
                    <span className={`status-chip ${getClosureClass(meeting)}`}>{getClosureLabel(meeting)}</span>
                  </div>
                  <p>{meeting.summary}</p>
                  <div className="history-meta">
                    <span>创建时间：{formatDateTime(meeting.created_at)}</span>
                    <span>行动项：{meeting.action_count}</span>
                    <span>未完成：{meeting.pending_count}</span>
                    <span>今日到期：{meeting.due_today_count}</span>
                    <span>已逾期：{meeting.overdue_count}</span>
                    <span>已完成：{meeting.completed_count}</span>
                  </div>
                </div>

                <div className="history-actions">
                  <Link className="secondary-link" href={`/meetings/${meeting.id}`} prefetch={false}>
                    查看详情
                  </Link>
                  <Link className="primary-link" href="/tasks" prefetch={false}>
                    查看任务
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
