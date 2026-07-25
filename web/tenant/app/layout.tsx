import './globals.css';
import type { ReactNode } from 'react';

export const metadata = {
  title: '单创OS · 自用工作台',
  description: '单创OS 自用工作台 / 租户后台（Node 网关 + Python 微服务）',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="header">
          <h1>单创OS · 自用工作台</h1>
          <span style={{ fontSize: 13, color: '#666' }}>Node 网关 + Python 微服务</span>
        </header>
        {children}
      </body>
    </html>
  );
}
