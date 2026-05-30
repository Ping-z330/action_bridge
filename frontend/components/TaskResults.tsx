"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ActionItemListItem } from "../lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  in_progress: "进行中",
  completed: "已完成",
  failed: "有风险",
};

const FILTERS = [
  { value: "risk", label: "风险优先" },
  { value: "all", label: "全部" },
  { value: "pending", label: "待处理" },
  { value: "in_progress", label: "进行中" },
  { value: "failed", label: "有风险" },
  { value: "due_today", label: "今日到期" },
  { value: "overdue", label: "已逾期" },
  { value: "completed", label: "已完成" },
];

const DUE_STATUS_ORDER: Record<string, number> = {
  overdue: 1,
  due_today: 2,
  unknown: 3,
  upcoming: 4,
  completed: 5,
};

function getStatusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function getStatusClass(status: string) {
  if (status === "completed") return "status-completed";
  if (status === "failed") return "status-risk";
  if (status === "in_progress") return "status-progress";
  return "status-pending";
}

function getDueStatusClass(status: string) {
  if (status === "overdue") return "due-overdue";
  if (status === "due_today") return "due-today";
  if (status === "completed") return "status-completed";
  if (status === "unknown") return "due-unknown";
  return "due-upcoming";
}

function normalizeActionTitle(title: string, ownerName: string) {
  let normalized = title.trim();
  const prefixes = ["Action:", "Next step:", "Todo:", "Follow up:", "Follow-up:"];

  for (const prefix of prefixes) {
    if (normalized.toLowerCase().startsWith(prefix.toLowerCase())) {
      normalized = normalized.slice(prefix.length).trim();
      break;
    }
  }

  if (ownerName && normalized.startsWith(ownerName)) {
    normalized = normalized.slice(ownerName.length).trim();
  }

  return normalized || title.trim();
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDeadlineDisplay(item: ActionItemListItem) {
  if (!item.deadline_date) {
    return { date: item.deadline || "待确认", detail: "请补充日期" };
  }

  const date = new Date(`${item.deadline_date}T00:00:00+08:00`);
  const weekday = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    weekday: "short",
  }).format(date);

  return {
    date: item.deadline_date,
    detail: `${weekday} ${item.deadline_time || "18:00"}`,
  };
}

function getRiskMessage(overdue: number, dueToday: number, unknown: number) {
  if (overdue > 0) {
    return `存在 ${overdue} 个已逾期任务，请优先处理。`;
  }
  if (dueToday > 0) {
    return `今天有 ${dueToday} 个任务到期，请及时跟进。`;
  }
  if (unknown > 0) {
    return `有 ${unknown} 个任务缺少明确截止时间，建议先补全。`;
  }
  return "当前没有高风险任务，可以继续推进普通待处理事项。";
}

function getMeetingStatus(items: ActionItemListItem[]) {
  if (items.length === 0) return "暂无任务";
  if (items.every((item) => item.status === "completed")) return "已完成";
  if (items.some((item) => item.status === "failed" || item.due_status === "overdue")) return "有风险";
  if (items.some((item) => item.status === "in_progress")) return "进行中";
  return "未开始";
}

function getMeetingStatusClass(status: string) {
  if (status === "已完成") return "status-completed";
  if (status === "有风险") return "status-risk";
  if (status === "进行中") return "status-progress";
  return "status-pending";
}

function matchesFilter(item: ActionItemListItem, activeFilter: string) {
  if (activeFilter === "all") return true;
  if (activeFilter === "risk") return item.status !== "completed" && (item.status === "failed" || item.due_status !== "upcoming");
  if (activeFilter === "due_today") return item.due_status === "due_today";
  if (activeFilter === "overdue") return item.due_status === "overdue";
  return item.status === activeFilter;
}

type MeetingGroup = {
  meetingId: number;
  meetingTitle: string;
  createdAt: string;
  items: ActionItemListItem[];
  completed: number;
  total: number;
  progress: number;
  status: string;
};

export function TaskResults({ initialItems }: { initialItems: ActionItemListItem[] }) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [activeFilter, setActiveFilter] = useState("risk");
  const [keyword, setKeyword] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const stats = useMemo(
    () => ({
      total: items.length,
      pending: items.filter((item) => item.status === "pending").length,
      inProgress: items.filter((item) => item.status === "in_progress").length,
      risk: items.filter((item) => item.status === "failed" || item.due_status === "overdue").length,
      dueToday: items.filter((item) => item.due_status === "due_today").length,
      overdue: items.filter((item) => item.due_status === "overdue").length,
      unknown: items.filter((item) => item.due_status === "unknown" && item.status !== "completed").length,
      completed: items.filter((item) => item.status === "completed").length,
    }),
    [items]
  );

  const meetingGroups = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    const visibleItems = items
      .filter((item) => {
        const matchesKeyword =
          normalizedKeyword.length === 0 ||
          item.title.toLowerCase().includes(normalizedKeyword) ||
          item.owner_name.toLowerCase().includes(normalizedKeyword) ||
          item.meeting_title.toLowerCase().includes(normalizedKeyword);

        return matchesFilter(item, activeFilter) && matchesKeyword;
      })
      .sort((a, b) => {
        const dueDiff = (DUE_STATUS_ORDER[a.due_status] ?? 99) - (DUE_STATUS_ORDER[b.due_status] ?? 99);
        if (dueDiff !== 0) return dueDiff;
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      });

    const groups = new Map<number, ActionItemListItem[]>();

    for (const item of visibleItems) {
      groups.set(item.meeting_id, [...(groups.get(item.meeting_id) ?? []), item]);
    }

    return Array.from(groups.entries())
      .map(([meetingId, groupItems]): MeetingGroup => {
        const completed = groupItems.filter((item) => item.status === "completed").length;
        const total = groupItems.length;
        const status = getMeetingStatus(groupItems);

        return {
          meetingId,
          meetingTitle: groupItems[0]?.meeting_title ?? "未命名会议",
          createdAt: groupItems[0]?.created_at ?? "",
          items: groupItems,
          completed,
          total,
          progress: total === 0 ? 0 : Math.round((completed / total) * 100),
          status,
        };
      })
      .sort((a, b) => {
        const statusDiff =
          (a.status === "有风险" ? 0 : a.status === "进行中" ? 1 : a.status === "未开始" ? 2 : 3) -
          (b.status === "有风险" ? 0 : b.status === "进行中" ? 1 : b.status === "未开始" ? 2 : 3);
        if (statusDiff !== 0) return statusDiff;
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      });
  }, [activeFilter, items, keyword]);

  async function updateStatus(item: ActionItemListItem, status: string) {
    setMessage("正在更新任务状态...");

    const response = await fetch(`${API_BASE}/api/action-items/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        owner_name: item.owner_name,
        deadline: item.deadline,
        deadline_date: item.deadline_date,
        deadline_time: item.deadline_time,
        status,
      }),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      setMessage(errorBody?.detail ?? "任务状态更新失败。");
      return;
    }

    setItems((current) =>
      current.map((currentItem) =>
        currentItem.id === item.id
          ? {
              ...currentItem,
              status,
              due_status: status === "completed" ? "completed" : currentItem.due_status,
              due_status_label: status === "completed" ? "已完成" : currentItem.due_status_label,
            }
          : currentItem
      )
    );
    setMessage("任务状态已更新，历史记录会同步刷新。");
    router.refresh();
  }

  return (
    <section className="tasks-page">
      <div className="tasks-hero">
        <div>
          <p className="section-label">任务结果</p>
          <h1>会议行动项执行看板</h1>
          <p>按会议归组查看所有行动项，快速判断每个项目的完成进度、风险状态和当前负责人。</p>
        </div>
        <Link className="primary-link" href="/" prefetch={false}>
          新增会议纪要
        </Link>
      </div>

      <div className="task-stat-grid">
        <div className="task-stat-card">
          <span>全部任务</span>
          <strong>{stats.total}</strong>
        </div>
        <div className="task-stat-card">
          <span>待处理</span>
          <strong>{stats.pending}</strong>
        </div>
        <div className="task-stat-card">
          <span>进行中</span>
          <strong>{stats.inProgress}</strong>
        </div>
        <div className="task-stat-card danger-stat">
          <span>有风险</span>
          <strong>{stats.risk}</strong>
        </div>
        <div className="task-stat-card">
          <span>已完成</span>
          <strong>{stats.completed}</strong>
        </div>
      </div>

      <div className={`risk-banner ${stats.overdue > 0 ? "risk-banner-danger" : ""}`}>
        {getRiskMessage(stats.overdue, stats.dueToday, stats.unknown)}
      </div>

      <div className="work-card task-table-card">
        <div className="task-toolbar">
          <div className="task-filters">
            {FILTERS.map((filter) => (
              <button
                key={filter.value}
                className={activeFilter === filter.value ? "active" : ""}
                type="button"
                onClick={() => setActiveFilter(filter.value)}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <input
            className="task-search"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索任务、负责人或来源会议"
          />
        </div>

        {message ? <p className="status-message">{message}</p> : null}

        {meetingGroups.length === 0 ? (
          <div className="empty-result">
            <p className="empty-title">暂无匹配任务</p>
            <p>可以回到会议处理页生成新的会议纪要，或切换筛选条件查看其它任务。</p>
          </div>
        ) : (
          <div className="meeting-task-groups">
            {meetingGroups.map((group) => (
              <section className="meeting-task-card" key={group.meetingId}>
                <div className="meeting-task-header">
                  <div>
                    <div className="meeting-title-row">
                      <h2>{group.meetingTitle}</h2>
                      <span className={`status-chip ${getMeetingStatusClass(group.status)}`}>{group.status}</span>
                    </div>
                    <p>
                      创建时间：{group.createdAt ? formatDateTime(group.createdAt) : "待确认"} · 任务进度：
                      {group.completed}/{group.total}
                    </p>
                  </div>
                  <Link className="secondary-link" href={`/meetings/${group.meetingId}`} prefetch={false}>
                    查看会议
                  </Link>
                </div>

                <div className="meeting-progress">
                  <div className="meeting-progress-meta">
                    <span>完成率 {group.progress}%</span>
                    <span>{group.total - group.completed} 项待推进</span>
                  </div>
                  <div className="meeting-progress-track">
                    <span style={{ width: `${group.progress}%` }} />
                  </div>
                </div>

                <table className="work-table task-table">
                  <thead>
                    <tr>
                      <th>任务目标</th>
                      <th>负责人</th>
                      <th>截止时间</th>
                      <th>到期风险</th>
                      <th>状态</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.items.map((item) => {
                      const deadlineDisplay = formatDeadlineDisplay(item);
                      return (
                        <tr key={item.id}>
                          <td className="task-title-cell">{normalizeActionTitle(item.title, item.owner_name)}</td>
                          <td>{item.owner_name}</td>
                          <td>
                            <div className="deadline-display">
                              <strong>{deadlineDisplay.date}</strong>
                              <span>{deadlineDisplay.detail}</span>
                            </div>
                          </td>
                          <td>
                            <span className={`status-chip ${getDueStatusClass(item.due_status)}`}>
                              {item.due_status_label}
                            </span>
                          </td>
                          <td>
                            <select
                              className="task-status-select"
                              value={item.status}
                              onChange={(event) => updateStatus(item, event.target.value)}
                            >
                              <option value="pending">待处理</option>
                              <option value="in_progress">进行中</option>
                              <option value="failed">有风险</option>
                              <option value="completed">已完成</option>
                            </select>
                          </td>
                          <td>
                            <div className="table-actions">
                              {item.status === "completed" ? (
                                <button className="secondary" type="button" onClick={() => updateStatus(item, "pending")}>
                                  设为待处理
                                </button>
                              ) : (
                                <button type="button" onClick={() => updateStatus(item, "completed")}>
                                  标记完成
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </section>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
