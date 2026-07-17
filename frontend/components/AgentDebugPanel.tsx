"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { fetchAgentTraces, runAgentDebug } from "../lib/api";
import { AgentStep, AgentTraceLogItem } from "../lib/types";

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
    update_task_status: "更新状态",
    summarize_project: "总结项目",
    analyze_risk: "风险分析",
    generate_progress_report: "进度报告",
    query_member_activity: "成员活跃度",
    create_alert: "创建预警",
    create_task: "创建任务",
    update_task_deadline: "修改截止",
    update_task_owner: "修改负责人",
    confirm_create_task: "确认创建",
    confirm_update_task_deadline: "确认改截止",
    confirm_update_task_owner: "确认改负责人",
    central_analysis: "中央分析",
    agent_response: "Agent 回复",
    fallback_help: "帮助兜底",
    unhandled: "未处理",
  };
  return labels[intent] ?? intent;
}

function getToolLabel(name: string) {
  const labels: Record<string, string> = {
    query_tasks: "查询任务",
    query_member_activity: "成员活跃度",
    summarize_project: "项目总结",
    analyze_risk: "风险分析",
    generate_progress_report: "进度报告",
    update_task_status: "更新状态",
    create_task: "创建任务",
    update_task_deadline: "修改截止",
    update_task_owner: "修改负责人",
    create_alert: "创建预警",
  };
  return labels[name] ?? name;
}

export function AgentDebugPanel({ traces: initialTraces }: { traces: AgentTraceLogItem[] }) {
  const [traces, setTraces] = useState(initialTraces);
  const [activeTraceId, setActiveTraceId] = useState<number | null>(initialTraces[0]?.id ?? null);
  const [message, setMessage] = useState("查看所有任务");
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [lastSteps, setLastSteps] = useState<AgentStep[]>([]);
  const [lastResponse, setLastResponse] = useState<string>("");
  const stepsRef = useRef<HTMLDivElement>(null);

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

  // Scroll to steps when new steps arrive
  useEffect(() => {
    if (lastSteps.length > 0 && stepsRef.current) {
      stepsRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [lastSteps]);

  async function handleDebugRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage) {
      setRunStatus("请输入一条自然语言指令。");
      return;
    }

    setIsRunning(true);
    setRunStatus("Agent 正在执行 ReAct 循环...");
    setLastSteps([]);
    setLastResponse("");
    try {
      const result = await runAgentDebug(trimmedMessage);
      const latestTraces = await fetchAgentTraces();
      setTraces(latestTraces);
      setActiveTraceId(result.trace_id ?? latestTraces[0]?.id ?? null);
      // Capture ReAct steps for live display
      if (result.steps && result.steps.length > 0) {
        setLastSteps(result.steps);
      }
      setLastResponse(result.message);
      const toolLabels = result.steps?.map((s) => getToolLabel(s.tool_name)).join(" → ") || "";
      setRunStatus(
        result.handled
          ? `✅ ${toolLabels || result.intent_name} (${result.steps?.length || 0} 步)`
          : `⚠️ ${result.message.slice(0, 60)}`
      );
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
          <p className="section-label">Agent Trace · ReAct 可观测面板</p>
          <h1>Agent 执行调试面板</h1>
          <p>
            输入自然语言 → LLM 自主选择工具链 → 执行 → 观察结果 → 再决策。
            每一步的 Thought / Tool Call / Result 都可追溯。
          </p>
        </div>
      </div>

      <form className="debug-runner work-card" onSubmit={handleDebugRun}>
        <div>
          <h2>调试运行</h2>
          <p>这里调用的是和飞书消息相同的 ReAct Agent 循环。</p>
        </div>
        <div className="debug-runner-controls">
          <input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="例如：分析项目风险"
          />
          <button type="submit" disabled={isRunning}>
            {isRunning ? "⏳ 运行中..." : "▶ 运行 Agent"}
          </button>
        </div>
        {runStatus ? <p className="debug-run-status">{runStatus}</p> : null}
      </form>

      {/* Live ReAct steps from last run */}
      {lastSteps.length > 0 && (
        <div className="work-card" ref={stepsRef} style={{ marginBottom: "1.5rem" }}>
          <h2>ReAct 步骤链 · 最近一次执行</h2>
          <div className="react-chain">
            {lastSteps.map((step, index) => (
              <div key={index} className={`react-step ${step.tool_error ? "react-step-error" : ""}`}>
                <div className="react-step-header">
                  <span className="react-step-number">Step {index + 1}</span>
                  <span className="react-step-tool">
                    {getToolLabel(step.tool_name)}
                  </span>
                  {step.tool_error && <span className="react-step-badge error">失败</span>}
                </div>
                <div className="react-step-body">
                  <div className="react-step-row">
                    <span className="react-step-label">参数</span>
                    <code>{JSON.stringify(step.tool_args, null, 2)}</code>
                  </div>
                  <div className="react-step-row">
                    <span className="react-step-label">结果</span>
                    <code className={step.tool_error ? "text-error" : ""}>
                      {step.tool_error ? step.tool_error : step.tool_result}
                    </code>
                  </div>
                </div>
                {index < lastSteps.length - 1 && (
                  <div className="react-step-arrow">↓</div>
                )}
              </div>
            ))}
          </div>
          {lastResponse && (
            <div className="react-final">
              <strong>Agent 最终回复</strong>
              <p style={{ whiteSpace: "pre-wrap" }}>{lastResponse}</p>
            </div>
          )}
        </div>
      )}

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
                  <span>3. Agent 意图 / 工具名</span>
                  <p>{getIntentLabel(activeTrace.intent_name)}</p>
                  <small>{stringifyFilters(activeTrace.intent_filters)}</small>
                </section>
                <section className="debug-step">
                  <span>4. 工具执行</span>
                  <p>{activeTrace.tool_name || "未命中工具"}</p>
                  <small>
                    {activeTrace.tool_source} / {activeTrace.tool_category}
                    {activeTrace.tool_executed ? " · 已执行" : " · 未执行"}
                  </small>
                </section>
                <section className="debug-step">
                  <span>5. 安全策略</span>
                  <p>
                    {activeTrace.dangerous ? "⚠️ 危险写操作" : "✅ 安全读操作"}
                    {activeTrace.requires_confirmation ? " · 需用户确认" : ""}
                  </p>
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
