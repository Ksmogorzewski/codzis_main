import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./client", import.meta.url)) } },
  test: {
    include: ["{client,partner,shared}/**/*.test.ts"],
    exclude: ["**/node_modules/**", "client/routeTree.gen.ts"],
    environment: "node",
  },
});
