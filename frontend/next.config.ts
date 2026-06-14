import type { NextConfig } from "next";

// Resolve THIS directory (the frontend project) robustly across both CJS and ESM
// config loaders. `__dirname` is undefined when Next loads next.config.ts as ESM;
// in that case `path.resolve(__dirname)` throws and Next silently falls back to
// its default config — which then auto-infers the workspace root as the git repo
// root (d:\Mini_Project) and fails to resolve `tailwindcss` there. start_gridmind
// always launches `next dev` with cwd = frontend/, so process.cwd() is a reliable
// fallback.
const frontendRoot =
  typeof __dirname !== "undefined" ? __dirname : process.cwd();

// Surface the resolved root once at startup so misconfiguration is visible in
// frontend.log instead of manifesting as a cryptic tailwindcss resolve error.
console.log("[next.config] turbopack.root =", frontendRoot);

const nextConfig: NextConfig = {
  devIndicators: false,

  // Next.js 16 uses Turbopack by default. Pin the workspace root to the frontend
  // dir so Turbopack never climbs to the parent (d:\Mini_Project) — where it
  // can't resolve `tailwindcss` because node_modules only exists under frontend/.
  turbopack: {
    root: frontendRoot,
    resolveAlias: {},
  },
};

export default nextConfig;
