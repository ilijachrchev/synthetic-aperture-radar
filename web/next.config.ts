import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
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
