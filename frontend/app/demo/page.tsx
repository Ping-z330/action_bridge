"use client";

import { useEffect, useState, useRef } from "react";
import { AppShell } from "../../components/AppShell";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type mRNAEntry = {
  sender: string;
  receiver: string;
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
};

type ProjectStatus = {
  total_tasks: number;
  completed: number;
  in_progress: number;
  pending: number;
  failed: number;
  completion_rate: number;
  risk_score: number;
  risk_conclusion: string;
  risks: Array<{ task_id: number; title: string; severity: string; description: string }>;
  members: Array<{ name: string; total: number; completed: number; failed: number; completion_rate: number }>;
};

function MRNABadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    task_update: "#2b8a3e",
    status_report: "#1971c2",
    alert_ack: "#e8590c",
    risk_query: "#c92a2a",
  };
  const labels: Record<string, string> = {
    task_update: "任务更新",
    status_report: "状态汇报",
    alert_ack: "预警确认",
    risk_query: "风险查询",
  };
  return (
    <span style={{
      background: colors[type] || "#868e96",
      color: "#fff",
      padding: "2px 8px",
      borderRadius: 4,
      fontSize: "0.75rem",
      fontWeight: 700,
    }}>
      {labels[type] || type}
    </span>
  );
}

function RegisterMemberForm({ onRegistered }: { onRegistered: () => void }) {
  const [name, setName] = useState("");
  const [chatId, setChatId] = useState("");
  const [status, setStatus] = useState("");

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !chatId.trim()) return;
    setStatus("注册中...");
    try {
      const r = await fetch(`${API_BASE}/api/demo/register-member`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), chat_id: chatId.trim(), project_id: 1 }),
      });
      const data = await r.json();
      setStatus(`✅ ${data.member.name} 已注册 (${data.status})`);
      setName(""); setChatId("");
      onRegistered();
    } catch {
      setStatus("❌ 注册失败");
    }
  }

  return (
    <form onSubmit={handleRegister} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="姓名 (如: 张三)"
        style={{ padding: "8px 12px", borderRadius: 6, border: "1px solid #dee2e6", width: 140 }}
      />
      <input
        value={chatId}
        onChange={(e) => setChatId(e.target.value)}
        placeholder="open_id 或任意ID"
        style={{ padding: "8px 12px", borderRadius: 6, border: "1px solid #dee2e6", flex: 1, minWidth: 200 }}
      />
      <button type="submit" style={{
        padding: "8px 16px", background: "#1971c2", color: "#fff", border: "none",
        borderRadius: 6, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap",
      }}>
        注册
      </button>
      {status && <span style={{ fontSize: "0.85rem", color: "#495057", alignSelf: "center" }}>{status}</span>}
    </form>
  );
}

export default function DemoPage() {
  const [member, setMember] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [mRNAFeed, setMRNAFeed] = useState<mRNAEntry[]>([]);
  const [project, setProject] = useState<ProjectStatus | null>(null);
  const [replies, setReplies] = useState<Array<{ member: string; reply: string; steps: number }>>([]);
  const feedRef = useRef<HTMLDivElement>(null);

  // Poll project status and mRNA feed every 3 seconds
  useEffect(() => {
    fetchStatus();
    fetchMRNA();
    const id = setInterval(() => { fetchStatus(); fetchMRNA(); }, 3000);
    return () => clearInterval(id);
  }, []);

  async function fetchStatus() {
    try {
      const r = await fetch(`${API_BASE}/api/demo/project-status`);
      if (r.ok) setProject(await r.json());
    } catch {}
  }

  async function fetchMRNA() {
    try {
      const r = await fetch(`${API_BASE}/api/demo/mrna-feed`);
      if (r.ok) {
        const data = await r.json();
        setMRNAFeed(data);
        if (feedRef.current && data.length > 0) {
          feedRef.current.scrollTop = feedRef.current.scrollHeight;
        }
      }
    } catch {}
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!msg.trim()) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/demo/member-message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ member_name: member, message: msg.trim(), project_id: 1 }),
      });
      const data = await r.json();
      setReplies((prev) => [{ member, reply: data.agent_reply, steps: data.steps?.length || 0 }, ...prev.slice(0, 9)]);
      setMsg("");
      // Refresh immediately
      await fetchStatus();
      await fetchMRNA();
    } catch (e) {
      setReplies((prev) => [{ member, reply: `❌ ${String(e)}`, steps: 0 }, ...prev.slice(0, 9)]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell active="demo">
      <div className="debug-hero">
        <div>
          <p className="section-label">A2A Multi-Agent Demo</p>
          <h1>多 Agent 协作模拟</h1>
          <p>扮演不同成员向 AI 助手汇报进度，观察 Agent 间 mRNA 通信和中央风险分析。</p>
        </div>
      </div>

      {/* Member input area */}
      {/* Register member */}
      <section className="work-card" style={{ marginBottom: "1.5rem" }}>
        <h2>注册成员</h2>
        <p style={{ color: "#868e96", marginBottom: 12 }}>
          把飞书用户的 open_id 绑定到项目成员。私聊 Bot 一条消息，后端终端会显示 open_id。Demo 模式下用任意字符串即可。
        </p>
        <RegisterMemberForm onRegistered={() => { fetchStatus(); }} />
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
        <section className="work-card">
          <h2>成员进度汇报</h2>
          <p style={{ color: "#868e96", marginBottom: 16 }}>
            选择一个成员身份，输入进度更新。系统会走完整的个人助手 → mRNA → 中央 Agent 链路。
          </p>

          {/* Member selector — populated from project data */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
            {(project?.members?.length ?? 0) > 0 ? (
              project?.members.map((m) => (
                <button
                  key={m.name}
                  onClick={() => setMember(m.name)}
                  style={{
                    padding: "6px 16px",
                    borderRadius: 6,
                    border: member === m.name ? "2px solid #1971c2" : "1px solid #dee2e6",
                    background: member === m.name ? "#1971c2" : "#f1f3f5",
                    color: member === m.name ? "#fff" : "#212529",
                    fontWeight: member === m.name ? 700 : 400,
                    cursor: "pointer",
                    fontSize: "0.92rem",
                  }}
                >
                  {m.name}
                </button>
              ))
            ) : (
              <span style={{ color: "#adb5bd" }}>先创建会议，AI 解析后这里会自动出现成员</span>
            )}
          </div>

          <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
            <input
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              placeholder={member ? `以 ${member} 的身份说... (例如: 首页改版做完了)` : "先选择上方一个成员"}
              style={{ flex: 1, padding: "10px 14px", borderRadius: 6, border: "1px solid #dee2e6", fontSize: "0.95rem" }}
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !msg.trim() || !member}
              style={{
                padding: "10px 20px",
                background: "#1971c2",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontWeight: 700,
                cursor: loading ? "not-allowed" : "pointer",
                whiteSpace: "nowrap",
              }}
            >
              {loading ? "⏳" : "发送"}
            </button>
          </form>

          {/* Recent replies */}
          {replies.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <h3 style={{ fontSize: "0.85rem", color: "#868e96", marginBottom: 8 }}>最近回复</h3>
              {replies.map((r, i) => (
                <div
                  key={i}
                  style={{
                    padding: "8px 12px",
                    marginBottom: 6,
                    background: "#f8f9fa",
                    borderRadius: 6,
                    borderLeft: "3px solid #1971c2",
                  }}
                >
                  <strong style={{ fontSize: "0.8rem" }}>{r.member} 的助手</strong>
                  <span style={{ fontSize: "0.7rem", color: "#868e96", marginLeft: 8 }}>
                    {r.steps} 步 ReAct
                  </span>
                  <p style={{ margin: "4px 0 0", fontSize: "0.88rem" }}>{r.reply}</p>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* mRNA Feed */}
        <section className="work-card">
          <h2>mRNA 消息流</h2>
          <p style={{ color: "#868e96", marginBottom: 12 }}>
            Agent 间通信实时监控。每条消息代表一个 Agent 向另一个 Agent 传递结构化状态。
          </p>
          <div
            ref={feedRef}
            style={{
              maxHeight: 400,
              overflowY: "auto",
              border: "1px solid #e9ecef",
              borderRadius: 8,
              padding: 8,
            }}
          >
            {mRNAFeed.length === 0 ? (
              <p style={{ color: "#adb5bd", textAlign: "center", padding: "2rem 0" }}>
                等待第一条 Agent 间消息...
              </p>
            ) : (
              mRNAFeed.map((entry, i) => (
                <div
                  key={i}
                  style={{
                    padding: "8px 10px",
                    marginBottom: 4,
                    background: i === mRNAFeed.length - 1 ? "#e7f5ff" : "#f8f9fa",
                    borderRadius: 4,
                    fontSize: "0.82rem",
                    borderLeft: i === mRNAFeed.length - 1 ? "3px solid #1971c2" : "3px solid transparent",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <MRNABadge type={entry.type} />
                    <span style={{ color: "#868e96", fontSize: "0.7rem" }}>
                      {entry.timestamp?.slice(11, 19) || ""}
                    </span>
                  </div>
                  <div style={{ color: "#495057" }}>
                    <strong>{entry.sender}</strong> → {entry.receiver}
                  </div>
                  <div style={{ color: "#868e96", fontSize: "0.75rem", marginTop: 2 }}>
                    {JSON.stringify(entry.payload).slice(0, 120)}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      {/* Project Owner Dashboard (auto-refreshing) */}
      <section className="work-card" style={{ marginTop: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2>📊 负责人面板（实时刷新）</h2>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            {project && (
              <span style={{
                padding: "4px 12px",
                borderRadius: 20,
                fontWeight: 700,
                fontSize: "0.85rem",
                background: project.risk_score >= 50 ? "#ffe3e3" : project.risk_score >= 20 ? "#fff3bf" : "#d3f9d8",
                color: project.risk_score >= 50 ? "#c92a2a" : project.risk_score >= 20 ? "#e8590c" : "#2b8a3e",
              }}>
                风险评分: {project.risk_score}/100
              </span>
            )}
            <a href="/" style={{ fontSize: "0.85rem", color: "#1971c2" }}>查看完整仪表盘 →</a>
          </div>
        </div>

        {project ? (
          <>
            {/* Stats */}
            <div className="debug-stat-grid" style={{ marginTop: 12 }}>
              <div className="debug-stat-card"><span>总任务</span><strong>{project.total_tasks}</strong></div>
              <div className="debug-stat-card"><span>完成率</span><strong style={{ color: project.completion_rate === 100 ? "#2b8a3e" : "#1971c2" }}>{project.completion_rate}%</strong></div>
              <div className="debug-stat-card"><span>进行中</span><strong>{project.in_progress}</strong></div>
              <div className="debug-stat-card"><span>待处理</span><strong>{project.pending}</strong></div>
              <div className="debug-stat-card"><span>阻塞/风险</span><strong style={{ color: project.failed > 0 ? "#c92a2a" : "" }}>{project.failed}</strong></div>
            </div>

            {/* Members + Risks */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginTop: 16 }}>
              <div>
                <h3 style={{ fontSize: "0.9rem", marginBottom: 8 }}>成员状态</h3>
                {project.members.length === 0 ? (
                  <p style={{ color: "#868e96" }}>暂无成员数据</p>
                ) : (
                  project.members.map((m) => (
                    <div key={m.name} style={{ marginBottom: 8 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginBottom: 2 }}>
                        <span>{m.name}</span>
                        <span style={{ color: "#868e96" }}>{m.completed}/{m.total} · {m.completion_rate}%</span>
                      </div>
                      <div style={{ height: 6, background: "#e9ecef", borderRadius: 3, overflow: "hidden" }}>
                        <div style={{
                          height: "100%",
                          width: `${m.completion_rate}%`,
                          background: m.completion_rate === 100 ? "#2b8a3e" : m.completion_rate > 30 ? "#1971c2" : m.failed > 0 ? "#c92a2a" : "#fab005",
                          borderRadius: 3,
                          transition: "width 0.5s",
                        }} />
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div>
                <h3 style={{ fontSize: "0.9rem", marginBottom: 8 }}>风险列表</h3>
                {project.risks.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "1rem 0" }}>
                    <span style={{ fontSize: "2rem" }}>✅</span>
                    <p style={{ color: "#868e96" }}>暂无风险</p>
                  </div>
                ) : (
                  project.risks.map((r, i) => (
                    <div key={i} style={{
                      padding: "8px 10px",
                      marginBottom: 6,
                      borderRadius: 6,
                      background: r.severity === "critical" ? "#ffe3e3" : r.severity === "warning" ? "#fff3bf" : "#e7f5ff",
                      borderLeft: `3px solid ${r.severity === "critical" ? "#c92a2a" : r.severity === "warning" ? "#e8590c" : "#1971c2"}`,
                      fontSize: "0.85rem",
                    }}>
                      <strong>#{r.task_id}</strong> {r.title}
                      <p style={{ margin: "4px 0 0", fontSize: "0.8rem", color: "#495057" }}>{r.description}</p>
                    </div>
                  ))
                )}
              </div>
            </div>

            {project.risk_conclusion && (
              <div style={{
                marginTop: 12,
                padding: 10,
                background: "#f8f9fa",
                borderRadius: 6,
                fontSize: "0.88rem",
                color: "#495057",
              }}>
                <strong>中央 Agent:</strong> {project.risk_conclusion}
              </div>
            )}
          </>
        ) : (
          <p style={{ color: "#adb5bd", textAlign: "center", padding: "2rem" }}>
            先创建一些任务，然后用上方成员面板提交进度更新。
          </p>
        )}
      </section>
    </AppShell>
  );
}
