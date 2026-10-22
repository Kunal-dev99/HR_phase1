import type { NextConfig } from "next";
import {
  PHASE_PRODUCTION_BUILD,
  PHASE_PRODUCTION_SERVER,
} from "next/constants";

// D-22: same-origin proxy to the backend; no CORS.
const BACKEND_URL = (process.env.BACKEND_URL || "http://localhost:8000").replace(
  /\/+$/,
  "",
);

export default function config(phase: string): NextConfig {
  // D-21: the dev principal picker must never reach a production build or server.
  if (
    (phase === PHASE_PRODUCTION_BUILD || phase === PHASE_PRODUCTION_SERVER) &&
    process.env.NEXT_PUBLIC_DEV_AUTH === "true"
  ) {
    throw new Error(
      "D-21: NEXT_PUBLIC_DEV_AUTH=true is not allowed in a production build or production server start. Unset it (dev principal picker is dev-only).",
    );
  }

  return {
    cacheComponents: true,
    partialPrefetching: true,
    turbopack: {
      rules: {
        "*.css": {
          loaders: ["@tailwindcss/turbopack"],
          as: "*.css",
        },
      },
    },
    async rewrites() {
      return [
        { source: "/api/v1/:path*", destination: `${BACKEND_URL}/api/v1/:path*` },
        { source: "/healthz", destination: `${BACKEND_URL}/healthz` },
      ];
    },
  };
}
