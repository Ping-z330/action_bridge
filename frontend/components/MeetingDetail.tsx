"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ActionItem, FollowUpRunResponse, Meeting } from "../lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const STATUS_OPTIONS = [
  { value: "pending", label: "待处理" },
  { value: "in_progress", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "有风险" },
];

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

type SaveState = "idle" | "saving" | "saved" | "error";

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

function formatBatchFollowUpStatus(result: FollowUpRunResponse) {
  if (result.total_candidates === 0) {
    return "本次没有扫描到需要提醒的行动项。";
  }

  return `已扫描 ${result.scanned_meetings} 个会议，命中 ${result.total_candidates} 条待提醒行动项，成功发送 ${result.total_sent} 条。`;
}

function getSaveButtonText(state: SaveState) {
  if (state === "saving") return "保存中...";
  if (state === "saved") return "已保存";
  if (state === "error") return "重试";
  return "保存";
}

export function MeetingDetail({ meeting }: { meeting: Meeting }) {
  const router = useRouter();
  const [sendStatus, setSendStatus] = useState<string | null>(null);
  const [followUpStatus, setFollowUpStatus] = useState<string | null>(null);
  const [batchFollowUpStatus, setBatchFollowUpStatus] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [saveStates, setSaveStates] = useState<Record<number, SaveState>>({});
  const [actionItems, setActionItems] = useState<ActionItem[]>(meeting.action_items);
  const [editableItems, setEditableItems] = useState<EditableActionItems>(buildEditableState(meeting.action_items));

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

  async function handleActionItemSave(actionItemId: number) {
    const payload = editableItems[actionItemId];
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
    setActionItems(updatedMeeting.action_items);
    setEditableItems(buildEditableState(updatedMeeting.action_items));
    setSaveStatus("行动项已更新。");
    setSaveStates((current) => ({ ...current, [actionItemId]: "saved" }));
    router.refresh();

    window.setTimeout(() => {
      setSaveStates((current) => ({ ...current, [actionItemId]: "idle" }));
    }, 1400);
  }

  function updateField(
    actionItemId: number,
    field: "owner_name" | "deadline" | "deadline_date" | "deadline_time" | "status",
    value: string
  ) {
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
              const currentStatus = editableItems[item.id]?.status ?? item.status;
              const currentDate = editableItems[item.id]?.deadline_date ?? "";
              const currentTime = editableItems[item.id]?.deadline_time ?? "";
              const saveState = saveStates[item.id] ?? "idle";

              return (
                <div key={item.id} className={`action-edit-row action-save-${saveState}`}>
                  <div className="action-index">{index + 1}</div>
                  <div className="action-edit-main">
                    <div className="action-card-header">
                      <p className="action-title">{normalizeActionTitle(item.title, item.owner_name)}</p>
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
