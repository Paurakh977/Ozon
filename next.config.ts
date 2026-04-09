import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  serverExternalPackages: ["@llamaindex/liteparse"],
  output: "standalone",
};

export default nextConfig;
