'use client';

import { useEffect, useState } from 'react';
import { getStatus, runTask, type AosStatus } from '@/lib/aos-client';

export default function TenantHome() {
  const [status, setStatus] = useState<AosStatus | null>(null);
  const [capability, setCapability] = useState('content.marketing_video');
  const [payload, setPayload] = useState('{\n  "topic": "护眼科普短视频"\n}');
  const [result, setResult] = useState('');
  const [err, setErr] = useState('');

  // 登录态
  const [authed, setAuthed] = useState(false);
  const [user, setUser] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginErr, setLoginErr] = useState('');

  useEffect(() => {
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

  async function onRun() {
    setResult('');
    setErr('');
    try {
      const parsed = JSON.parse(payload);
      const data = (await runTask({ capability, payload: parsed })) as unknown;
      setResult(JSON.stringify(data, null, 2));
    } catch (e) {
      setErr(String(e));
    }
  }

  const ok = status?.ok || status?.status === 'ok';

  if (!authed) {
    return (
      <main className="container">
        <section className="card">
          <h2>工作台登录</h2>
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
            默认凭据 tenant / changeme（见 .env TENANT_USERNAME / TENANT_PASSWORD，生产请改）
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>单创OS · 自用工作台</h2>
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
        <h2>派发任务（经网关 /api/aos/v1/run_task）</h2>
        <label style={{ fontSize: 14, color: '#666', display: 'block', marginBottom: 6 }}>
          能力（capability）
        </label>
        <input value={capability} onChange={(e) => setCapability(e.target.value)} />
        <label style={{ fontSize: 14, color: '#666', display: 'block', margin: '12px 0 6px' }}>
          Payload（JSON）
        </label>
        <textarea rows={5} value={payload} onChange={(e) => setPayload(e.target.value)} />
        <button onClick={onRun}>派发</button>
        {result ? <pre style={{ marginTop: 12 }}>{result}</pre> : null}
      </section>
    </main>
  );
}
