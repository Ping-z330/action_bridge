import "./globals.css";
import "../styles/layout.css";
import "../styles/workspace.css";
import "../styles/detail.css";
import "../styles/history.css";
import "../styles/tasks.css";
import "../styles/debug.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ActionBridge",
  description: "会议纪要到执行闭环的办公协作 Agent MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
