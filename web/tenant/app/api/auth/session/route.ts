// 单创OS 自用工作台 —— 当前会话查询（不泄露签名密钥）
import { NextRequest, NextResponse } from 'next/server';
import { verifySession, SESSION_COOKIE } from '@/lib/session';

export async function GET(req: NextRequest) {
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const session = verifySession(token);
  if (!session) return NextResponse.json({ authenticated: false });
  return NextResponse.json({ authenticated: true, user: session.sub });
}
