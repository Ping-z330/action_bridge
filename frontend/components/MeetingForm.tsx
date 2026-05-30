"use client";

import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const ACCEPTED_TEXT_TYPES = [".txt", ".md", ".vtt", ".srt"];

function getTitleFromFileName(fileName: string) {
  return fileName.replace(/\.[^/.]+$/, "").trim();
}

export function MeetingForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [inputMode, setInputMode] = useState<"text" | "file">("text");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError(null);
    setInputMode("file");

    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!ACCEPTED_TEXT_TYPES.includes(extension)) {
      setError("当前版本仅支持 txt、md、vtt、srt 文本文件。");
      event.target.value = "";
      return;
    }

    try {
      const content = await file.text();
      const trimmedContent = content.trim();

      if (!trimmedContent) {
        setError("文件内容为空，请重新选择会议记录文件。");
        event.target.value = "";
        return;
      }

      setTranscript(trimmedContent);
      setSelectedFileName(file.name);

      if (!title.trim()) {
        setTitle(getTitleFromFileName(file.name));
      }
    } catch {
      setError("文件读取失败，请确认文件是 UTF-8 文本格式。");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
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
      router.push(`/?meetingId=${meeting.id}`);
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
          <p className="header-note">粘贴会议记录或上传文本文件，AI 会生成结构化纪要并在右侧展示。</p>
        </div>
      </div>

      <div className="segmented-control" aria-label="输入方式">
        <button
          className={inputMode === "text" ? "active" : ""}
          type="button"
          onClick={() => setInputMode("text")}
        >
          粘贴文本
        </button>
        <button
          className={inputMode === "file" ? "active" : ""}
          type="button"
          onClick={() => setInputMode("file")}
        >
          上传文件
        </button>
      </div>

      {inputMode === "file" ? (
        <label className="file-upload-box">
          <input accept={ACCEPTED_TEXT_TYPES.join(",")} type="file" onChange={handleFileChange} />
          <strong>{selectedFileName || "选择会议记录文件"}</strong>
          <span>支持 txt、md、vtt、srt。上传后会自动填入下方会议记录。</span>
        </label>
      ) : null}

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

      <p className="form-footnote">生成后不会跳离当前页面，右侧会直接展示整理结果。</p>
    </form>
  );
}
