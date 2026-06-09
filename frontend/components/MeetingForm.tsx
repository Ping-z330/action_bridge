"use client";

// 会议输入表单组件，支持粘贴文本和上传文件两种输入方式，提交后会调用后端 API 创建会议并展示结果。

import { useRouter } from "next/navigation";
import { ChangeEvent, FormEvent, useState } from "react";

// API_BASE 从环境变量读取，默认为 http://localhost:8000
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
// 目前仅支持这些文本文件格式，后续可以根据需要扩展
const ACCEPTED_TEXT_TYPES = [".txt", ".md", ".vtt", ".srt"];

function getTitleFromFileName(fileName: string) {
  // 用上传文件名自动推导会议标题，去掉最后一个扩展名。
  return fileName.replace(/\.[^/.]+$/, "").trim();
}

export function MeetingForm() {
  // 这些 useState 是页面表单的本地状态：标题、正文、输入方式、文件名、提交中、错误提示。
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [inputMode, setInputMode] = useState<"text" | "file">("text");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // handleFileChange 处理文件输入，读取文件内容并填入会议记录文本框，同时根据文件名自动生成会议标题（如果标题框为空的话）
  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    // 获取用户选择的文件，如果没有选择文件就直接返回
    const file = event.target.files?.[0];
    if (!file) return;

    setError(null);
    setInputMode("file");

    // 检查文件类型是否受支持，如果不支持就提示错误并清空输入
    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!ACCEPTED_TEXT_TYPES.includes(extension)) {
      setError("当前版本仅支持 txt、md、vtt、srt 文本文件。");
      event.target.value = "";
      return;
    }

    // 尝试读取文件内容，如果读取失败或内容为空就提示错误并清空输入
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

  // handleSubmit 处理表单提交，调用后端 API 创建会议，并在成功后跳转到会议详情页
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // 阻止表单默认提交行为，改为使用 JavaScript 处理提交逻辑
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    // 调用后端 API 创建会议，如果成功就跳转到会议详情页，如果失败就显示错误信息
    try {
      const response = await fetch(`${API_BASE}/api/meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, transcript }),
      });

      // 如果响应状态不是 2xx，就尝试从响应体中解析错误信息并抛出异常，如果解析失败就抛出一个通用错误
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "创建会议失败");
      }

      // 成功创建会议后，从响应体中获取会议 ID，并使用 Next.js 的路由功能跳转到会议详情页，同时刷新页面以加载新会议数据
      const meeting = await response.json();
      router.push(`/?meetingId=${meeting.id}`);
      router.refresh();
    } catch (submitError) {
      // 出现错误时，检查错误对象是否是 Error 实例，如果是就显示其消息，否则显示一个通用错误提示
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
