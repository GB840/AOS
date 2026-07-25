'use client';

import { useEffect, useState } from 'react';
import { getStatus, getFabric, chat, type AosStatus, type FabricInfo } from '@/lib/aos-client';

export default function AdminHome() {
  const [status, setStatus] = useState<AosStatus | null>(null);
  const [fabric, setFabric] = useState<FabricInfo | null>(null);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [reply, setReply] = useState('');

  useEffect(() => {
    getStatus()
      .then(setStatus)
      .catch((e) => setErr(String(e)));
    getFabric()
      .then(setFabric)
      .catch(() => {});
  }, []);

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

  return (
    <main className="container">
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
