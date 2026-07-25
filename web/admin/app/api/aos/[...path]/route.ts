import { NextRequest, NextResponse } from 'next/server';
import { verifySession, SESSION_COOKIE } from '@/lib/session';

// 单创OS 商户后台 —— AOS 内核反向代理（网关层鉴权门控）
// 对齐 AGENTS.md §5「能力即路由，权限即边界」：
//   1. 公开路由白名单（/status）免登录，人人可探活；
//   2. 其余受保护路由校验网关 session，无效即 401；
//   3. 校验通过 → 网关统一注入内部 AOS_API_KEY 转发后端，前端不持任何系统密钥。
const BACKEND = process.env.AOS_BACKEND_URL || 'http://127.0.0.1:8000';
const PUBLIC_PATHS = new Set(['status']);

type Ctx = { params: { path?: string[] } };

async function proxy(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const segments = ctx.params.path ?? [];
  const path = segments.join('/');

  // ── 受保护路由门控：绝不信任前端携带的任何系统密钥 ──
  if (!PUBLIC_PATHS.has(path)) {
    const token = req.cookies.get(SESSION_COOKIE)?.value;
    const session = verifySession(token);
    if (!session) {
      return NextResponse.json(
        { error: 'Unauthorized', detail: '缺少有效会话，请先 POST /api/auth/login' },
        { status: 401, headers: { 'WWW-Authenticate': 'Bearer realm="AOS Gateway"' } }
      );
    }
  }

  const target = `${BACKEND}/api/${path}${req.nextUrl.search}`;

  const headers: Record<string, string> = {};
  const contentType = req.headers.get('content-type');
  if (contentType) headers['content-type'] = contentType;

  // 权限即边界：网关统一注入内部 API Key，前端不持有系统密钥
  const apiKey = process.env.AOS_API_KEY;
  if (apiKey) headers['x-api-key'] = apiKey;

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
