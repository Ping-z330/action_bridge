"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AppShell } from "../../../components/AppShell";

export default function NewMeetingPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !transcript.trim()) {
      setError("请填写会议标题和内容");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
      const res = await fetch(`${apiBase}/api/meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim(), transcript: transcript.trim() }),
      });
      if (!res.ok) throw new Error("创建失败");
      const meeting = await res.json();
      router.push(`/meetings/${meeting.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell active="meetings">
      <section className="debug-hero">
        <div>
          <p className="section-label">会议纪要 → AI 解析</p>
          <h1>新建会议</h1>
          <p>粘贴会议记录，AI 自动提取摘要、决策和行动项。</p>
        </div>
      </section>

      <form className="work-card" onSubmit={handleSubmit} style={{ maxWidth: 700 }}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontWeight: 600, display: "block", marginBottom: 6 }}>会议标题</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：每周产品同步会"
            style={{ width: "100%", padding: "10px 14px", fontSize: "1rem", borderRadius: 6, border: "1px solid #dee2e6" }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontWeight: 600, display: "block", marginBottom: 6 }}>会议记录</label>
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder={`粘贴会议记录...\n\n示例：\n讨论官网改版上线风险。\nAction: 前端同学周五前修复移动端适配问题\nAction: 后端下周三前完成 API 性能优化\nAction: 测试同学补充回归用例`}
            rows={10}
            style={{ width: "100%", padding: "10px 14px", fontSize: "0.95rem", borderRadius: 6, border: "1px solid #dee2e6", resize: "vertical", fontFamily: "inherit" }}
          />
        </div>
        {error && <p style={{ color: "#c92a2a", marginBottom: 12 }}>{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="primary-link"
          style={{ border: "none", cursor: "pointer", fontSize: "1rem", padding: "10px 24px" }}
        >
          {loading ? "AI 正在解析..." : "创建会议"}
        </button>
      </form>
    </AppShell>
  );
}
