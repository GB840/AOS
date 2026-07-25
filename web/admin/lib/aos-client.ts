// 单创OS 商户后台 —— AOS 内核 Typed Client
// 所有调用都走同源的 /api/aos/*（由 Next 网关转发到 Python 微服务），绝不直连大模型。

export const AOS_API_BASE = '/api/aos';

export interface AosStatus {
  status?: string;
  ok?: boolean;
  version?: string;
  [key: string]: unknown;
}

export interface FabricInfo {
  adapters?: Array<{ name: string; capability: string }>;
  [key: string]: unknown;
}

export async function getStatus(): Promise<AosStatus> {
  const res = await fetch(`${AOS_API_BASE}/status`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`AOS /status -> ${res.status}`);
  return (await res.json()) as AosStatus;
}

export async function getFabric(): Promise<FabricInfo> {
  const res = await fetch(`${AOS_API_BASE}/fabric`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`AOS /fabric -> ${res.status}`);
  return (await res.json()) as FabricInfo;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  stream?: boolean;
}

export async function chat(req: ChatRequest): Promise<unknown> {
  const res = await fetch(`${AOS_API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stream: false, ...req }),
  });
  if (!res.ok) throw new Error(`AOS /chat -> ${res.status}`);
  return await res.json();
}
