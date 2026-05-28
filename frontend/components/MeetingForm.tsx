"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function MeetingForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, transcript }),
      });

      if (!response.ok) {
        throw new Error("创建会议失败");
      }

      const meeting = await response.json();
      router.push(`/meetings/${meeting.id}`);
      router.refresh();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "发生未知错误");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="panel stack" onSubmit={handleSubmit}>
      <div>
        <span className="pill">新建会议</span>
        <h2>把会议记录整理成行动项</h2>
        <p>粘贴会议 transcript 后，ActionBridge 会先生成一版摘要、结论和后续待办，帮助你快速进入执行阶段。</p>
      </div>
      <label className="stack">
        <span>会议标题</span>
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：每周产品同步会" required />
      </label>
      <label className="stack">
        <span>会议记录</span>
        <textarea
          value={transcript}
          onChange={(event) => setTranscript(event.target.value)}
          placeholder={"讨论了上线阻塞项\nDecision: Beta 版本延期到周五上线\nAction: 前端更新落地页文案"}
          required
        />
      </label>
      {error ? <p style={{ color: "#b91c1c", margin: 0 }}>{error}</p> : null}
      <button type="submit" disabled={submitting}>
        {submitting ? "创建中..." : "创建会议"}
      </button>
    </form>
  );
}
