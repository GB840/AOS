'use client';

import { useEffect, useState } from 'react';
import { getStatus, runTask, type AosStatus } from '@/lib/aos-client';

export default function TenantHome() {
  const [status, setStatus] = useState<AosStatus | null>(null);
  const [capability, setCapability] = useState('content.marketing_video');
  const [payload, setPayload] = useState('{\n  "topic": "护眼科普短视频"\n}');
  const [result, setResult] = useState('');
  const [err, setErr] = useState('');

  useEffect(() => {
    getStatus()
      .then(setStatus)
      .catch((e) => setErr(String(e)));
  }, []);

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
