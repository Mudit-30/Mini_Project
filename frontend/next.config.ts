import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,

  // Next.js 16 uses Turbopack by default.
  // Resolve packages from the frontend directory explicitly so the
  // tailwindcss resolution never climbs up to the project root.
  turbopack: {
    resolveAlias: {},
  },
};

export default nextConfig;
