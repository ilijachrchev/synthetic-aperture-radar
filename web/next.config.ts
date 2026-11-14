import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Files whose address changes when they do are kept by the browser for good, so a second visit asks for nothing:
  // the baked map tiles (they never change), the radar frames (the pages ask for them with the time of their bake,
  // ?v=), and the MapLibre worker (asked for with its version). The satellite pictures come from another script than
  // the bake, so they are checked with the server on every visit (the last rule wins for them).
  async headers() {
    const forever = [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }];
    return [
      { source: "/tiles/:path*", headers: forever },
      { source: "/layers/:all*(webp|png)", headers: forever },
      { source: "/maplibre/:path*", headers: forever },
      { source: "/layers/:site/optical/:file*", headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }] },
    ];
  },
  // The 2D explorer at /map is retired: its addresses open the 3D story pages. An old fire link opens the fire
  // page; every other one (water, and the two stories that have no 3D page yet) opens the flood.
  async redirects() {
    return [
      { source: "/map", has: [{ type: "query", key: "story", value: "fire" }], destination: "/fire", permanent: false },
      { source: "/map", destination: "/flood", permanent: false },
    ];
  },
  images: {
    // the hero photographs keep more detail than the default 75
    qualities: [75, 85],
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
