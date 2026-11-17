import type { NextConfig } from "next";

// The browser only ever talks to this app's own origin; /api is forwarded to FastAPI. Same
// origin means the session cookie just works, with no CORS setup.
const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default config;
