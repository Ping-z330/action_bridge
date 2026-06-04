"use client";

import { FormEvent, useMemo, useState } from "react";

import { fetchAgentTraces, runAgentDebug } from "../lib/api";
import { AgentTraceLogItem } from "../lib/types";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function stringifyFilters(filters: Record<string, unknown>) {
  const entries = Object.entries(filters);
  if (entries.length === 0) return "无参数";
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(" / ");
}

function getIntentLabel(intent: string) {
  const labels: Record<string, string> = {
    query_tasks: "查询任务",
    summarize_project: "总结项目",
    update_task_status: "更新状态",
    confirm_create_task: "确认创建任务",
    confirm_update_task_deadline: "确认修改截止时间",
    confirm_update_task_owner: "确认修改负责人",
    fallback_help: "帮助兜底",
    unhandled: "未处理",
  };
  return labels[intent] ?? intent;
}

export function AgentDebugPanel({ traces: initialTraces }: { traces: AgentTraceLogItem[] }) {
  const [traces, setTraces] = useState(initialTraces);
  const [activeTraceId, setActiveTraceId] = useState<number | null>(initialTraces[0]?.id ?? null);
  const [message, setMessage] = useState("查看未完成任务");
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const activeTrace = useMemo(
    () => traces.find((trace) => trace.id === activeTraceId) ?? traces[0],
    [activeTraceId, traces]
  );

  const stats = useMemo(
    () => ({
      total: traces.length,
      executed: traces.filter((trace) => trace.tool_executed).length,
      dangerous: traces.filter((trace) => trace.dangerous).length,
      confirmation: traces.filter((trace) => trace.requires_confirmation).length,
    }),
    [traces]
  );

  async function handleDebugRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage) {
      setRunStatus("请输入一条自然语言指令。");
      return;
    }

    setIsRunning(true);
    setRunStatus("Agent 正在执行...");
    try {
      const result = await runAgentDebug(trimmedMessage);
      const latestTraces = await fetchAgentTraces();
      setTraces(latestTraces);
      setActiveTraceId(result.trace_id ?? latestTraces[0]?.id ?? null);
      setRunStatus(`执行完成：${getIntentLabel(result.intent_name)}，${result.handled ? "已处理" : "未处理"}`);
    } catch (error) {
      setRunStatus(error instanceof Error ? error.message : "Agent 调试运行失败");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section className="debug-page">
      <div className="debug-hero">
        <div>
          <p className="section-label">Agent Trace</p>
          <h1>Agent 执行调试面板</h1>
          <p>输入一句自然语言，观察它如何经过 Memory、意图识别、任务引用解析、工具调用和最终回复。</p>
        </div>
      </div>

      <form className="debug-runner work-card" onSubmit={handleDebugRun}>
        <div>
          <h2>调试运行</h2>
          <p>这里调用的是和飞书消息相同的 Agent Graph，适合快速验证自然语言理解效果。</p>
        </div>
        <div className="debug-runner-controls">
          <input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="例如：把第二个任务负责人改成测试同学"
          />
          <button type="submit" disabled={isRunning}>
            {isRunning ? "运行中..." : "运行 Agent"}
          </button>
        </div>
        {runStatus ? <p className="debug-run-status">{runStatus}</p> : null}
      </form>

      <div className="debug-stat-grid">
        <div className="debug-stat-card">
          <span>Trace 总数</span>
          <strong>{stats.total}</strong>
        </div>
        <div className="debug-stat-card">
          <span>已调用工具</span>
          <strong>{stats.executed}</strong>
        </div>
        <div className="debug-stat-card">
          <span>危险操作</span>
          <strong>{stats.dangerous}</strong>
        </div>
        <div className="debug-stat-card">
          <span>需要确认</span>
          <strong>{stats.confirmation}</strong>
        </div>
      </div>

      {traces.length === 0 ? (
        <div className="work-card debug-empty">
          <h2>暂无 Agent 执行记录</h2>
          <p>在上方输入自然语言并运行，或者在飞书里发送任务指令后，这里会展示 Agent 的执行过程。</p>
        </div>
      ) : (
        <div className="debug-layout">
          <aside className="debug-list work-card">
            <div className="debug-list-heading">
              <h2>最近执行</h2>
              <span>{traces.length} 条</span>
            </div>
            {traces.map((trace) => (
              <button
                key={trace.id}
                className={`debug-list-item ${activeTrace?.id === trace.id ? "active" : ""}`}
                type="button"
                onClick={() => setActiveTraceId(trace.id)}
              >
                <span>#{trace.id} · {getIntentLabel(trace.intent_name)}</span>
                <strong>{trace.message || "空消息"}</strong>
                <em>{formatDateTime(trace.created_at)}</em>
              </button>
            ))}
          </aside>

          {activeTrace ? (
            <article className="debug-detail work-card">
              <div className="debug-detail-header">
                <div>
                  <p className="section-label">Trace #{activeTrace.id}</p>
                  <h2>{getIntentLabel(activeTrace.intent_name)}</h2>
                </div>
                <span className={`debug-badge ${activeTrace.dangerous ? "danger" : "safe"}`}>
                  {activeTrace.dangerous ? "写操作" : "安全查询"}
                </span>
              </div>

              <div className="debug-step-grid">
                <section className="debug-step">
                  <span>1. 原始输入</span>
                  <p>{activeTrace.message || "无"}</p>
                </section>
                <section className="debug-step">
                  <span>2. Memory 归一化</span>
                  <p>{activeTrace.normalized_message || "无归一化结果"}</p>
                </section>
                <section className="debug-step">
                  <span>3. 意图识别</span>
                  <p>{activeTrace.intent_name}</p>
                  <small>{stringifyFilters(activeTrace.intent_filters)}</small>
                </section>
                <section className="debug-step">
                  <span>4. 工具路由</span>
                  <p>{activeTrace.tool_name || "未命中工具"}</p>
                  <small>
                    来源：{activeTrace.tool_source || "无"} / 类型：{activeTrace.tool_category || "无"}
                  </small>
                </section>
                <section className="debug-step">
                  <span>5. 执行策略</span>
                  <p>{activeTrace.tool_executed ? "已执行工具" : "未执行工具"}</p>
                  <small>{activeTrace.requires_confirmation ? "需要用户确认" : "无需确认"}</small>
                </section>
                <section className="debug-step">
                  <span>6. 最终回复</span>
                  <p>{activeTrace.response_message || "无回复内容"}</p>
                </section>
              </div>
            </article>
          ) : null}
        </div>
      )}
    </section>
  );
}
