// Next.js 配置 —— 单创OS 自用工作台 / 租户后台（Node 网关层）
// 同 web/admin：前端不直接连大模型，所有 /api/aos/* 经本 Node 网关转发到 Python AOS 内核。
const BACKEND = process.env.AOS_BACKEND_URL || 'http://127.0.0.1:8000';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: '/api/aos/:path*', destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
