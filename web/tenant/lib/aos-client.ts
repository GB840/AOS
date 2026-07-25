// 单创OS 自用工作台 —— AOS 内核 Typed Client
// 所有调用走同源 /api/aos/*（由 Next 网关转发到 Python 微服务），绝不直连大模型。

export const AOS_API_BASE = '/api/aos';

export interface AosStatus {
  status?: string;
  ok?: boolean;
  version?: string;
  [key: string]: unknown;
}

export async function getStatus(): Promise<AosStatus> {
  const res = await fetch(`${AOS_API_BASE}/status`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`AOS /status -> ${res.status}`);
  return (await res.json()) as AosStatus;
}

export interface RunTaskRequest {
  capability: string;
  payload: Record<string, unknown>;
}

export async function runTask(req: RunTaskRequest): Promise<unknown> {
  const res = await fetch(`${AOS_API_BASE}/v1/run_task`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`AOS /v1/run_task -> ${res.status}`);
  return await res.json();
}
