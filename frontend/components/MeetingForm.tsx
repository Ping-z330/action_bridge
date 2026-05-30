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
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "创建会议失败");
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
    <form className="work-card input-column" onSubmit={handleSubmit}>
      <div className="work-card-header">
        <div>
          <p className="step-title">1. 会议输入</p>
          <p className="header-note">粘贴会议记录后，AI 会生成结构化纪要。</p>
        </div>
      </div>

      <div className="segmented-control" aria-label="输入方式">
        <button className="active" type="button">粘贴文本</button>
        <button type="button">上传文件</button>
      </div>

      <label className="field">
        <span>会议标题 *</span>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="例如：每周产品同步会"
          required
        />
      </label>

      <label className="field">
        <span>会议记录 Transcript *</span>
        <textarea
          value={transcript}
          onChange={(event) => setTranscript(event.target.value)}
          placeholder={
            "讨论了本周上线风险和延期方案。\n前端落地页文案还没更新完成，可能影响用户转化。\n产品经理需要确认用户通知时间和文案内容。\n---\nDecision: Beta 版本延期到周五上线。\nAction: 前端同学更新落地页文案。\nNext step: 产品经理确认用户通知时间。"
          }
          required
        />
      </label>

      <p className="word-count">字数统计：{transcript.trim().length}</p>
      {error ? <p className="error-message">{error}</p> : null}

      <button className="full-button" type="submit" disabled={submitting}>
        {submitting ? "AI 整理中..." : "AI 生成会议纪要"}
      </button>

      <p className="form-footnote">AI 将自动提取会议摘要、关键决策、行动项和风险点。</p>
    </form>
  );
}
