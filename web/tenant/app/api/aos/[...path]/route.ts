import { NextRequest, NextResponse } from 'next/server';

// 单创OS 自用工作台 —— AOS 内核反向代理（与 web/admin 同构）
// 前端只与本网关通信，由网关统一转发到 Python AOS 内核。
const BACKEND = process.env.AOS_BACKEND_URL || 'http://127.0.0.1:8000';

type Ctx = { params: { path?: string[] } };

async function proxy(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const segments = ctx.params.path ?? [];
  const path = segments.join('/');
  const target = `${BACKEND}/api/${path}${req.nextUrl.search}`;

  const headers: Record<string, string> = {};
  const contentType = req.headers.get('content-type');
  if (contentType) headers['content-type'] = contentType;
  const auth = req.headers.get('authorization') ?? req.headers.get('x-api-key');
  if (auth) headers['authorization'] = auth;

  const init: RequestInit = { method: req.method, headers };
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    init.body = await req.text();
  }

  const upstream = await fetch(target, init);
  const body = await upstream.arrayBuffer();
  const respHeaders: Record<string, string> = {};
  const ct = upstream.headers.get('content-type');
  if (ct) respHeaders['content-type'] = ct;
  return new NextResponse(body, { status: upstream.status, headers: respHeaders });
}

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
