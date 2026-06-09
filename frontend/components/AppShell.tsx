import Link from "next/link";
import { ReactNode } from "react";

// 页面整体布局组件，包含侧边导航栏和顶部用户信息栏，接收一个 active 属性来标识当前激活的导航项，以及 children 来渲染具体页面内容。

type NavKey = "meetings" | "tasks" | "history" | "agent-debug";

// 侧边栏和顶部 tab 共用同一份导航配置，避免两个地方维护不同链接。
const NAV_ITEMS = [
  { key: "meetings", label: "会议处理", href: "/" },
  { key: "tasks", label: "任务结果", href: "/tasks" },
  { key: "history", label: "历史记录", href: "/history" },
  { key: "agent-debug", label: "Agent 调试", href: "/agent-debug" },
] satisfies Array<{ key: NavKey; label: string; href: string }>;

export function AppShell({ active, children }: { active: NavKey; children: ReactNode }) {
  // AppShell 是所有主要页面的外壳：左侧导航 + 顶部栏 + 页面内容区域。
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
          {/* 主导航：active 用来高亮当前页面。 */}
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
            {/* 顶部 tab 和侧边栏使用同一份 NAV_ITEMS。 */}
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
