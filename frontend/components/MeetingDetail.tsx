"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ActionItem, FollowUpRunResponse, Meeting } from "../lib/types";

// 后端 API 地址。没有配置环境变量时，默认连接本地 FastAPI。
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// 行动项状态下拉框选项。
// value 是后端保存的真实状态值，label 是页面展示文案。
const STATUS_OPTIONS = [
  { value: "pending", label: "待处理" },
  { value: "in_progress", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "有风险" },
];

// 清理行动项标题里的固定英文前缀和重复负责人。
// 例如 "Action: 张三 修复问题" 会尽量显示成更干净的任务标题。
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

// 页面编辑状态的结构。
// key 是行动项 ID，value 是这个行动项当前表单里的可编辑字段。
type EditableActionItems = Record<
  number,
  {
    owner_name: string;
    deadline: string;
    deadline_date: string;
    deadline_time: string;
    status: string;
  }
>;

// 单个行动项保存按钮的状态。
type SaveState = "idle" | "saving" | "saved" | "error";

// 把后端返回的 action_items 转成页面表单需要的编辑状态。
function buildEditableState(items: ActionItem[]): EditableActionItems {
  return Object.fromEntries(
    items.map((item) => [
      item.id,
      {
        owner_name: item.owner_name,
        deadline: item.deadline,
        deadline_date: item.deadline_date,
        deadline_time: item.deadline_time,
        status: item.status,
      },
    ])
  );
}

// 批量跟进接口返回的是统计数据，这里把它格式化成页面提示文案。
function formatBatchFollowUpStatus(result: FollowUpRunResponse) {
  if (result.total_candidates === 0) {
    return "本次没有扫描到需要提醒的行动项。";
  }

  return `已扫描 ${result.scanned_meetings} 个会议，命中 ${result.total_candidates} 条待提醒行动项，成功发送 ${result.total_sent} 条。`;
}

// 根据保存状态切换按钮文字。
function getSaveButtonText(state: SaveState) {
  if (state === "saving") return "保存中...";
  if (state === "saved") return "已保存";
  if (state === "error") return "重试";
  return "保存";
}

export function MeetingDetail({ meeting }: { meeting: Meeting }) {
  const router = useRouter();

  // 飞书发送、跟进、批量跟进、保存行动项后的状态提示文案。
  const [sendStatus, setSendStatus] = useState<string | null>(null);
  const [followUpStatus, setFollowUpStatus] = useState<string | null>(null);
  const [batchFollowUpStatus, setBatchFollowUpStatus] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  // 每个行动项保存按钮自己的状态，例如 saving/saved/error。
  const [saveStates, setSaveStates] = useState<Record<number, SaveState>>({});

  // actionItems 是当前页面展示的行动项列表。
  // editableItems 是表单里的可编辑副本，用户输入时先改它，点保存后再提交给后端。
  const [actionItems, setActionItems] = useState<ActionItem[]>(meeting.action_items);
  const [editableItems, setEditableItems] = useState<EditableActionItems>(buildEditableState(meeting.action_items));

  // 把当前会议摘要发送到飞书。
  async function handleFeishuSend() {
    setSendStatus("正在准备飞书推送...");

    const response = await fetch(`${API_BASE}/api/meetings/${meeting.id}/send-feishu`, {
      method: "POST",
    });

    if (!response.ok) {
      setSendStatus("飞书推送准备失败。");
      return;
    }

    const result = await response.json();
    setSendStatus(result.message);
  }

  // 给当前会议发送一次跟进提醒。
  async function handleFollowUpSend() {
    setFollowUpStatus("正在发送当前会议的跟进提醒...");

    const response = await fetch(`${API_BASE}/api/meetings/${meeting.id}/follow-up`, {
      method: "POST",
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      setFollowUpStatus(errorBody?.detail ?? "跟进提醒发送失败。");
      return;
    }

    const result = await response.json();
    setFollowUpStatus(result.message);
  }

  // 手动触发全局批量跟进扫描。
  // 后端会找出所有今日到期/逾期且未完成的任务并发送提醒。
  async function handleBatchFollowUpRun() {
    setBatchFollowUpStatus("正在运行批量跟进...");

    const response = await fetch(`${API_BASE}/api/follow-ups/run`, {
      method: "POST",
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      setBatchFollowUpStatus(errorBody?.detail ?? "批量跟进运行失败。");
      return;
    }

    const result: FollowUpRunResponse = await response.json();
    setBatchFollowUpStatus(formatBatchFollowUpStatus(result));
  }

  // 保存单个行动项的编辑结果。
  // 它会 PATCH 到后端，成功后用后端返回的最新会议数据刷新页面状态。
  async function handleActionItemSave(actionItemId: number) {
    const payload = editableItems[actionItemId];

    // 先把当前行动项按钮切到 saving 状态。
    setSaveStatus(null);
    setSaveStates((current) => ({ ...current, [actionItemId]: "saving" }));

    const response = await fetch(`${API_BASE}/api/action-items/${actionItemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      setSaveStatus(errorBody?.detail ?? "行动项保存失败。");
      setSaveStates((current) => ({ ...current, [actionItemId]: "error" }));
      return;
    }

    const updatedMeeting: Meeting = await response.json();

    // 用后端返回的新 action_items 覆盖本地列表和表单状态。
    setActionItems(updatedMeeting.action_items);
    setEditableItems(buildEditableState(updatedMeeting.action_items));
    setSaveStatus("行动项已更新。");
    setSaveStates((current) => ({ ...current, [actionItemId]: "saved" }));

    // 刷新 Next.js 当前路由，让服务端组件也拿到最新数据。
    router.refresh();

    // saved 状态只短暂展示，1.4 秒后恢复普通按钮文案。
    window.setTimeout(() => {
      setSaveStates((current) => ({ ...current, [actionItemId]: "idle" }));
    }, 1400);
  }

  // 更新某个行动项表单字段。
  // 注意这里只改前端 editableItems，不会立刻写数据库。
  function updateField(
    actionItemId: number,
    field: "owner_name" | "deadline" | "deadline_date" | "deadline_time" | "status",
    value: string
  ) {
    // 用户重新编辑后，把保存按钮从 saved/error 恢复成普通状态。
    setSaveStates((current) => ({ ...current, [actionItemId]: "idle" }));
    setEditableItems((current) => ({
      ...current,
      [actionItemId]: {
        ...current[actionItemId],
        [field]: value,
      },
    }));
  }

  return (
    <section className="work-card result-column">
      <div className="work-card-header">
        <div>
          <p className="step-title">AI 整理结果</p>
          <p className="header-note">{meeting.title}</p>
        </div>
        <span className="ok-dot">{actionItems.length} 个行动项</span>
      </div>

      <div className="result-stack">
        <section className="result-block">
          <h3>会议摘要</h3>
          <p>{meeting.summary}</p>
        </section>

        <section className="result-block">
          <h3>关键决策</h3>
          <ul className="plain-list">
            {meeting.decisions.map((decision) => (
              <li key={decision}>{decision}</li>
            ))}
          </ul>
        </section>

        <section className="result-block">
          <h3>行动项</h3>
          <div className="result-stack">
            {actionItems.map((item, index) => {
              // 当前行动项表单里的临时值，优先读 editableItems。
              const currentStatus = editableItems[item.id]?.status ?? item.status;
              const currentDate = editableItems[item.id]?.deadline_date ?? "";
              const currentTime = editableItems[item.id]?.deadline_time ?? "";

              // saveState 决定这一行保存按钮的样式和文案。
              const saveState = saveStates[item.id] ?? "idle";

              return (
                <div key={item.id} className={`action-edit-row action-save-${saveState}`}>
                  <div className="action-index">{index + 1}</div>
                  <div className="action-edit-main">
                    <div className="action-card-header">
                      <div className="action-title-group">
                        <span className="task-id-badge">#{item.id}</span>
                        <p className="action-title">{normalizeActionTitle(item.title, item.owner_name)}</p>
                      </div>
                      {!currentDate ? <span className="action-warning">需要补充截止日期</span> : null}
                    </div>
                    <div className="action-edit-grid">
                      <label className="action-field">
                        <span>负责人</span>
                        <input
                          value={editableItems[item.id]?.owner_name ?? item.owner_name}
                          onChange={(event) => updateField(item.id, "owner_name", event.target.value)}
                        />
                      </label>
                      <label className="action-field">
                        <span>截止日期</span>
                        <input
                          type="date"
                          value={currentDate}
                          onChange={(event) => updateField(item.id, "deadline_date", event.target.value)}
                        />
                      </label>
                      <label className="action-field">
                        <span>截止时间</span>
                        <input
                          type="time"
                          value={currentTime}
                          onChange={(event) => updateField(item.id, "deadline_time", event.target.value)}
                        />
                      </label>
                      <label className="action-field">
                        <span>状态</span>
                        <select value={currentStatus} onChange={(event) => updateField(item.id, "status", event.target.value)}>
                          {STATUS_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                  </div>
                  <button
                    className="secondary action-save-button"
                    disabled={saveState === "saving"}
                    onClick={() => handleActionItemSave(item.id)}
                  >
                    {getSaveButtonText(saveState)}
                  </button>
                </div>
              );
            })}
          </div>
        </section>

        <section className="result-block">
          <h3>同步与通知</h3>
          <div className="action-bar">
            <button onClick={handleFeishuSend}>发送摘要</button>
            <button className="secondary" onClick={handleFollowUpSend}>
              当前会议跟进
            </button>
            <button className="secondary" onClick={handleBatchFollowUpRun}>
              批量跟进
            </button>
          </div>
          {saveStatus ? <p className="status-message">{saveStatus}</p> : null}
          {sendStatus ? <p className="status-message">{sendStatus}</p> : null}
          {followUpStatus ? <p className="status-message">{followUpStatus}</p> : null}
          {batchFollowUpStatus ? <p className="status-message">{batchFollowUpStatus}</p> : null}
        </section>
      </div>
    </section>
  );
}
