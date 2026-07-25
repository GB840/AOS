// 单创OS 商户后台 —— 登录端点（网关层签发 session）
// 诚实边界：demo 用 env 凭据做本地校验；生产应改为转发后端 /api/auth/token 或查 DB/OIDC。
import { NextRequest, NextResponse } from 'next/server';
import { signSession, SESSION_COOKIE, SESSION_MAX_AGE, safeEqual } from '@/lib/session';

const USER = process.env.AUTH_USERNAME || 'admin';
const PASS = process.env.AUTH_PASSWORD || 'changeme';

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

  const userOk = safeEqual(body.username ?? '', USER);
  const passOk = safeEqual(body.password ?? '', PASS);
  if (!userOk || !passOk) {
    return NextResponse.json({ ok: false, error: '用户名或密码错误' }, { status: 401 });
  }

  const token = signSession(USER);
  const res = NextResponse.json({ ok: true, user: USER });
  res.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_MAX_AGE,
  });
  return res;
}
