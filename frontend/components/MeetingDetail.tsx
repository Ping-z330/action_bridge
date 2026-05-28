"use client";

import { useState } from "react";

import { Meeting } from "../lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

function getStatusLabel(status: string) {
  switch (status) {
    case "pending":
      return "待处理";
    case "completed":
      return "已完成";
    case "running":
      return "处理中";
    case "failed":
      return "失败";
    default:
      return status;
  }
}

export function MeetingDetail({ meeting }: { meeting: Meeting }) {
  const [sendStatus, setSendStatus] = useState<string | null>(null);

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
        {meeting.action_items.map((item) => (
          <div key={item.id} className="panel">
            <strong>{item.title}</strong>
            <p>负责人：{item.owner_name}</p>
            <p>截止时间：{item.deadline}</p>
            <p>状态：{getStatusLabel(item.status)}</p>
          </div>
        ))}
      </section>

      <section className="panel stack">
        <span className="pill">同步与通知</span>
        <button onClick={handleFeishuSend}>发送到飞书</button>
        {sendStatus ? <p>{sendStatus}</p> : null}
      </section>
    </div>
  );
}
