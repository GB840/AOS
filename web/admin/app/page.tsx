'use client';

import { useEffect, useState } from 'react';
import { getStatus, getFabric, chat, type AosStatus, type FabricInfo } from '@/lib/aos-client';

export default function AdminHome() {
  const [status, setStatus] = useState<AosStatus | null>(null);
  const [fabric, setFabric] = useState<FabricInfo | null>(null);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [reply, setReply] = useState('');

  // 登录态
  const [authed, setAuthed] = useState(false);
  const [user, setUser] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginErr, setLoginErr] = useState('');

  useEffect(() => {
    // 探测登录态
    fetch('/api/auth/session', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        if (d.authenticated) {
          setAuthed(true);
          setUser(d.user);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!authed) return;
    getStatus()
      .then(setStatus)
      .catch((e) => setErr(String(e)));
    getFabric()
      .then(setFabric)
      .catch(() => {});
  }, [authed]);

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginErr('');
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setLoginErr(data.error || '登录失败');
        return;
      }
      setAuthed(true);
      setUser(data.user);
    } catch (e) {
      setLoginErr(String(e));
    }
  }

  async function onLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    setAuthed(false);
    setUser('');
  }

  async function onSend() {
    setReply('');
    setErr('');
    try {
      const data = (await chat({ message: msg, stream: false })) as { reply?: string };
      setReply(data.reply ?? JSON.stringify(data));
    } catch (e) {
      setErr(String(e));
    }
  }

  const ok = status?.ok || status?.status === 'ok';

  if (!authed) {
    return (
      <main className="container">
        <section className="card">
          <h2>商户后台登录</h2>
          <form onSubmit={onLogin} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input
              placeholder="用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
            <input
              type="password"
              placeholder="密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
            <button type="submit">登录</button>
          </form>
          {loginErr ? <p className="err">{loginErr}</p> : null}
          <p style={{ marginTop: 12, fontSize: 13, color: '#888' }}>
            默认凭据 admin / changeme（见 .env AUTH_USERNAME / AUTH_PASSWORD，生产请改）
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>单创OS · 商户后台</h2>
        <div style={{ fontSize: 14 }}>
          <span style={{ color: '#666', marginRight: 10 }}>{user}</span>
          <button onClick={onLogout}>登出</button>
        </div>
      </div>

      <section className="card">
        <h2>内核状态</h2>
        <p>
          <span className={`status-dot ${ok ? 'status-ok' : 'status-bad'}`} />
          {status ? `status=${status.status ?? 'unknown'} version=${status.version ?? '-'}` : '加载中…'}
        </p>
        {err ? <p className="err">{err}</p> : null}
      </section>

      <section className="card">
        <h2>已注册能力（Fabric）</h2>
        {fabric?.adapters ? (
          <pre>{JSON.stringify(fabric.adapters, null, 2)}</pre>
        ) : (
          <p>加载中…（需 Python AOS 内核通电）</p>
        )}
      </section>

      <section className="card">
        <h2>对话（经网关转发 /api/aos/chat）</h2>
        <textarea
          rows={3}
          placeholder="输入发送给 AOS 内核的消息…"
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
        />
        <button onClick={onSend}>发送</button>
        {reply ? <pre style={{ marginTop: 12 }}>{reply}</pre> : null}
      </section>
    </main>
  );
}
