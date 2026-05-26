import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained .next/standalone (minimal server.js + traced
  // node_modules) so the Docker image needs neither a full npm install nor
  // `next start`. See node_modules/next/dist/docs/.../config/.../output.md.
  output: "standalone",
};

export default nextConfig;
