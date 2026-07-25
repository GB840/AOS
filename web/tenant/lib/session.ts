// 单创OS 自用工作台 —— 网关层会话（HMAC 自签，零额外依赖）
// 对齐 AGENTS.md §5「权限即边界」：前端只持签名 session，系统密钥(AOS_API_KEY)仅存于网关 env。
import crypto from 'crypto';

export const SESSION_COOKIE = 'aos_tenant_session';
export const SESSION_MAX_AGE = 60 * 60 * 8; // 8 小时

interface SessionPayload {
  sub: string;
  exp: number; // unix 秒
  jwt?: string; // 后端 /api/auth/token 签发的 JWT，网关转发时注入 Authorization
}

function b64url(buf: Buffer): string {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function b64urlJson(obj: unknown): string {
  return b64url(Buffer.from(JSON.stringify(obj), 'utf-8'));
}
function fromB64url(s: string): Buffer {
  const pad = s.length % 4 === 0 ? '' : '='.repeat(4 - (s.length % 4));
  return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/') + pad, 'base64');
}

/** 恒定时间字符串比较，防计时侧信道。 */
export function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

/** 签发会话令牌。AUTH_SECRET 缺失时抛错（fail-fast，诚实拒绝）。 */
export function signSession(sub: string, jwt?: string): string {
  const secret = process.env.AUTH_SECRET;
  if (!secret) throw new Error('AUTH_SECRET 未配置');
  const payload: SessionPayload = {
    sub,
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE,
    jwt,
  };
  const body = b64urlJson(payload);
  const sig = crypto.createHmac('sha256', secret).update(body).digest('hex');
  return `${body}.${sig}`;
}

/** 校验会话令牌，返回 payload 或 null（过期/篡改/缺失均返回 null）。 */
export function verifySession(token: string | undefined): SessionPayload | null {
  const secret = process.env.AUTH_SECRET;
  if (!token || !secret) return null;
  const parts = token.split('.');
  if (parts.length !== 2) return null;
  const [body, sig] = parts;
  const expect = crypto.createHmac('sha256', secret).update(body).digest('hex');
  const a = Buffer.from(sig);
  const b = Buffer.from(expect);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;
  try {
    const payload = JSON.parse(fromB64url(body).toString('utf-8')) as SessionPayload;
    if (!payload.exp || payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}
