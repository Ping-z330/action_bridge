"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { MeetingListItem } from "../lib/types";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function getClosureLabel(status: string) {
  return status === "closed" ? "已完成闭环" : "执行中";
}

function getClosureClass(status: string) {
  return status === "closed" ? "status-completed" : "status-progress";
}

export function HistoryRecords({ meetings }: { meetings: MeetingListItem[] }) {
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

  const stats = useMemo(
    () => ({
      total: meetings.length,
      actionCount: meetings.reduce((sum, meeting) => sum + meeting.action_count, 0),
      pendingCount: meetings.reduce((sum, meeting) => sum + meeting.pending_count, 0),
      closedCount: meetings.filter((meeting) => meeting.closure_status === "closed").length,
    }),
    [meetings]
  );

  return (
    <section className="history-page">
      <div className="history-hero">
        <div>
          <p className="section-label">历史记录</p>
          <h1>会议处理记录库</h1>
          <p>沉淀每次会议的 AI 整理结果，方便回溯摘要、行动项和执行闭环状态。</p>
        </div>
        <Link className="primary-link" href="/">
          新增会议纪要
        </Link>
      </div>

      <div className="history-stat-grid">
        <div className="task-stat-card">
          <span>累计会议</span>
          <strong>{stats.total}</strong>
        </div>
        <div className="task-stat-card">
          <span>行动项总数</span>
          <strong>{stats.actionCount}</strong>
        </div>
        <div className="task-stat-card">
          <span>未完成行动项</span>
          <strong>{stats.pendingCount}</strong>
        </div>
        <div className="task-stat-card">
          <span>已完成闭环</span>
          <strong>{stats.closedCount}</strong>
        </div>
      </div>

      <div className="work-card history-list-card">
        <div className="history-toolbar">
          <div>
            <h2>会议记录</h2>
            <p>按时间倒序展示已处理会议。</p>
          </div>
          <input
            className="history-search"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索会议标题或摘要"
          />
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
                    <span className={`status-chip ${getClosureClass(meeting.closure_status)}`}>
                      {getClosureLabel(meeting.closure_status)}
                    </span>
                  </div>
                  <p>{meeting.summary}</p>
                  <div className="history-meta">
                    <span>创建时间：{formatDateTime(meeting.created_at)}</span>
                    <span>行动项：{meeting.action_count}</span>
                    <span>未完成：{meeting.pending_count}</span>
                    <span>已完成：{meeting.completed_count}</span>
                  </div>
                </div>

                <div className="history-actions">
                  <Link className="secondary-link" href={`/meetings/${meeting.id}`}>
                    查看详情
                  </Link>
                  <Link className="primary-link" href="/tasks">
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
