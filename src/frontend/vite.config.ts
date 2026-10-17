import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dwie aplikacje w jednym projekcie:
//   vite --mode client   -> portal klienta WarsawNow (waw-out.pl), dev: http://localhost:8000
//   vite --mode partner  -> panel organizatora (partner.waw-out.pl), dev: http://localhost:8001
// config.js nie jest bundlowany: generuje go Terraform (S3), lokalnie scripts/frontend-dev.sh.
const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig(({ mode }) => {
  const app = mode === "partner" ? "partner" : "client";
  const root = here(`./${app}`);

  return {
    root,
    publicDir: `${root}/public`,
    plugins: [react()],
    build: {
      outDir: here(`./dist/${app}`),
      emptyOutDir: true,
      rolldownOptions: {
        // mock-pay.html: osobna strona "bramki płatności" (adres zwraca API: /mock-pay.html?id=...)
        input: app === "partner"
          ? { main: `${root}/index.html`, mockPay: `${root}/mock-pay.html` }
          : { main: `${root}/index.html` },
      },
    },
    server: app === "partner"
      ? {
          port: 8001,
          strictPort: true,
          // API partnera jest za CloudFront pod /api (ta sama domena co strona)
          proxy: { "/api": { target: process.env.PARTNER_ORIGIN || "https://partner.waw-out.pl", changeOrigin: true } },
        }
      : { port: 8000, strictPort: true }, // localhost:8000 jest na liście adresów powrotu Cognito
  };
});
