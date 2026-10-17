import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["{client,partner,shared}/**/*.test.ts"],
    environment: "node",
  },
});
