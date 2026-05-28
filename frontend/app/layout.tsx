import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ActionBridge",
  description: "会议纪要到执行闭环 Agent MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
