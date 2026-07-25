// 单创OS 商户后台 —— 登录端点（网关层转发后端 /api/auth/token，签发 session）
// 对齐 AGENTS.md §5「权限即边界」：网关不存用户密码，凭据直交后端换取 JWT，
// session 仅持有后端签发的 JWT（HMAC 签名防篡改），前端不持系统密钥。
import { NextRequest, NextResponse } from 'next/server';
import { signSession, SESSION_COOKIE, SESSION_MAX_AGE } from '@/lib/session';

const BACKEND = process.env.AOS_BACKEND_URL || 'http://127.0.0.1:8000';

export async function POST(req: NextRequest) {
  if (!process.env.AUTH_SECRET) {
    return NextResponse.json(
      { ok: false, error: '服务端未配置 AUTH_SECRET，无法签发会话' },
      { status: 500 }
    );
  }

  let body: { username?: string; password?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: '请求体非法' }, { status: 400 });
  }
  const username = (body.username ?? '').trim();
  const password = body.password ?? '';
  if (!username || !password) {
    return NextResponse.json({ ok: false, error: '用户名或密码不能为空' }, { status: 400 });
  }

  // 转发后端换 JWT（诚实边界：网关不做本地凭据判断，全部交给后端鉴权服务）
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/auth/token`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username, password }),
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    return NextResponse.json(
      { ok: false, error: '后端鉴权服务不可用（请确认 AOS API 已启动）' },
      { status: 502 }
    );
  }

  if (upstream.status === 401) {
    return NextResponse.json({ ok: false, error: '用户名或密码错误' }, { status: 401 });
  }
  if (!upstream.ok) {
    return NextResponse.json({ ok: false, error: `后端鉴权异常 (${upstream.status})` }, { status: 502 });
  }

  const data = await upstream.json().catch(() => null);
  const accessToken = data?.access_token;
  if (!accessToken) {
    return NextResponse.json({ ok: false, error: '后端未返回 access_token' }, { status: 502 });
  }

  const token = signSession(username, accessToken);
  const res = NextResponse.json({ ok: true, user: username });
  res.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_MAX_AGE,
  });
  return res;
}
