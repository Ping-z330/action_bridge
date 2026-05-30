import Link from "next/link";
import { ReactNode } from "react";

type NavKey = "meetings" | "tasks" | "history";

const NAV_ITEMS = [
  { key: "meetings", label: "会议处理", href: "/" },
  { key: "tasks", label: "任务结果", href: "/tasks" },
  { key: "history", label: "历史记录", href: "/history" },
] satisfies Array<{ key: NavKey; label: string; href: string }>;

export function AppShell({ active, children }: { active: NavKey; children: ReactNode }) {
  return (
    <div className="app-frame">
      <aside className="side-nav">
        <div className="side-brand">
          <div className="brand-mark">A</div>
          <div>
            <p className="brand-title">ActionBridge</p>
            <p className="brand-subtitle">会议执行闭环工作台</p>
          </div>
        </div>

        <nav className="nav-list" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.key}
              className={`nav-item ${active === item.key ? "active" : ""}`}
              href={item.href}
              prefetch={false}
            >
              {item.label}
            </Link>
          ))}
          <a className="nav-item">我的任务</a>
          <a className="nav-item">消息提醒</a>
          <a className="nav-item">设置管理</a>
        </nav>

        <div className="side-footer">
          <a className="nav-item">帮助中心</a>
          <a className="nav-item">收起</a>
        </div>
      </aside>

      <main className="work-main">
        <header className="work-topbar">
          <div className="top-tabs">
            {NAV_ITEMS.map((item) => (
              <Link
                key={item.key}
                className={`top-tab ${active === item.key ? "active" : ""}`}
                href={item.href}
                prefetch={false}
              >
                {item.label}
              </Link>
            ))}
          </div>
          <div className="user-block">
            <span className="top-icon">?</span>
            <span className="top-icon">!</span>
            <span className="avatar">张</span>
            <div>
              <p className="user-name">张三</p>
              <p className="user-role">产品部</p>
            </div>
          </div>
        </header>

        {children}
      </main>
    </div>
  );
}
