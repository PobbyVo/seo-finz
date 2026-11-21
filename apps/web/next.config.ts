import type { NextConfig } from 'next';

const apiInternalUrl = process.env.FINZ_API_INTERNAL_URL || 'http://127.0.0.1:8000';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  experimental: {
    // Prevent Next.js dev proxy from timing out at 30s during AI analysis / Gemini fallback tests
    proxyTimeout: 120_000,
  },
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiInternalUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
