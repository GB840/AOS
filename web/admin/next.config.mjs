// Next.js 配置 —— 单创OS 商户后台（Node 网关层）
// 关键原则（对齐 AGENTS.md §5「能力即路由，权限即边界」+ TS/Node 综述「禁止前端直连」）：
//   前端永远不直接连大模型 / Python 微服务，所有 /api/aos/* 请求经本 Node 网关转发到
//   Python AOS 内核（FastAPI，默认 http://127.0.0.1:8000）。密钥与鉴权只在网关侧处理。
const BACKEND = process.env.AOS_BACKEND_URL || 'http://127.0.0.1:8000';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: '/api/aos/:path*', destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
