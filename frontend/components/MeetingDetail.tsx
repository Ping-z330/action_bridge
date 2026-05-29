"use client";

import { useState } from "react";

import { ActionItem, FollowUpRunResponse, Meeting } from "../lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const STATUS_OPTIONS = [
  { value: "pending", label: "待处理" },
  { value: "in_progress", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
];

function getStatusLabel(status: string) {
  return STATUS_OPTIONS.find((option) => option.value === status)?.label ?? status;
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

type EditableActionItems = Record<
  number,
  {
    owner_name: string;
    deadline: string;
    status: string;
  }
>;

function buildEditableState(items: ActionItem[]): EditableActionItems {
  return Object.fromEntries(
    items.map((item) => [
      item.id,
      {
        owner_name: item.owner_name,
        deadline: item.deadline,
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

export function MeetingDetail({ meeting }: { meeting: Meeting }) {
  const [sendStatus, setSendStatus] = useState<string | null>(null);
  const [followUpStatus, setFollowUpStatus] = useState<string | null>(null);
  const [batchFollowUpStatus, setBatchFollowUpStatus] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
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
    setSaveStatus("正在保存行动项...");

    const response = await fetch(`${API_BASE}/api/action-items/${actionItemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      setSaveStatus(errorBody?.detail ?? "行动项保存失败。");
      return;
    }

    const updatedMeeting: Meeting = await response.json();
    setActionItems(updatedMeeting.action_items);
    setEditableItems(buildEditableState(updatedMeeting.action_items));
    setSaveStatus("行动项已更新。");
  }

  function updateField(actionItemId: number, field: "owner_name" | "deadline" | "status", value: string) {
    setEditableItems((current) => ({
      ...current,
      [actionItemId]: {
        ...current[actionItemId],
        [field]: value,
      },
    }));
  }

  return (
    <div className="grid">
      <section className="panel stack">
        <span className="pill">会议摘要</span>
        <h1>{meeting.title}</h1>
        <p>{meeting.summary}</p>
      </section>

      <section className="panel stack">
        <span className="pill">会议结论</span>
        <ul>
          {meeting.decisions.map((decision) => (
            <li key={decision}>{decision}</li>
          ))}
        </ul>
      </section>

      <section className="panel stack">
        <span className="pill">行动项</span>
        {actionItems.map((item) => (
          <div key={item.id} className="panel stack">
            <strong>{normalizeActionTitle(item.title, item.owner_name)}</strong>
            <label className="stack">
              <span>负责人</span>
              <input
                value={editableItems[item.id]?.owner_name ?? item.owner_name}
                onChange={(event) => updateField(item.id, "owner_name", event.target.value)}
              />
            </label>
            <label className="stack">
              <span>截止时间</span>
              <input
                value={editableItems[item.id]?.deadline ?? item.deadline}
                onChange={(event) => updateField(item.id, "deadline", event.target.value)}
              />
            </label>
            <label className="stack">
              <span>状态</span>
              <select
                value={editableItems[item.id]?.status ?? item.status}
                onChange={(event) => updateField(item.id, "status", event.target.value)}
                style={{ padding: "12px 14px", borderRadius: 12, border: "1px solid var(--border)" }}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <p>当前状态：{getStatusLabel(editableItems[item.id]?.status ?? item.status)}</p>
            <button className="secondary" onClick={() => handleActionItemSave(item.id)}>
              保存行动项
            </button>
          </div>
        ))}
        {saveStatus ? <p>{saveStatus}</p> : null}
      </section>

      <section className="panel stack">
        <span className="pill">同步与通知</span>
        <button onClick={handleFeishuSend}>发送到飞书</button>
        <button className="secondary" onClick={handleFollowUpSend}>
          发送当前会议跟进提醒
        </button>
        <button className="secondary" onClick={handleBatchFollowUpRun}>
          运行批量跟进
        </button>
        <p style={{ margin: 0, color: "var(--muted-foreground)" }}>
          批量跟进会扫描全部会议中今天到期或已逾期、且尚未完成的行动项，并统一发送提醒。
        </p>
        {sendStatus ? <p>{sendStatus}</p> : null}
        {followUpStatus ? <p>{followUpStatus}</p> : null}
        {batchFollowUpStatus ? <p>{batchFollowUpStatus}</p> : null}
      </section>
    </div>
  );
}
