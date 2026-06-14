import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  devIndicators: false,

  // Next.js 16 uses Turbopack by default. Pin the workspace root to THIS
  // directory. Without this, Turbopack auto-infers the root and intermittently
  // climbs to the parent (d:\Mini_Project), where it then fails to resolve
  // `tailwindcss` ("Can't resolve 'tailwindcss' in 'd:\Mini_Project'") because
  // node_modules only exists under frontend/. Pinning the root makes the dev
  // server resolve packages from frontend/ deterministically.
  turbopack: {
    root: path.resolve(__dirname),
    resolveAlias: {},
  },
};

export default nextConfig;
