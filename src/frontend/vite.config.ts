import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type PluginOption } from "vite";

// Dwie aplikacje w jednym projekcie:
//   vite --mode client   -> portal klienta WarsawNow (waw-out.pl), dev: http://localhost:8000
//   vite --mode partner  -> panel organizatora (partner.waw-out.pl), dev: http://localhost:8001
// config.js nie jest bundlowany: generuje go Terraform (S3), lokalnie scripts/frontend-dev.sh.
const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

// Portal klienta: trasy plikowe TanStack Router (generuje client/routeTree.gen.ts) i Tailwind 4.
// Panel partnera zostaje bez zmian (zwykły CSS, routing na hashu ręcznie).
const clientPlugins = (): PluginOption[] => [
  // Musi być przed pluginem React.
  tanstackRouter({
    target: "react",
    autoCodeSplitting: true,
    routesDirectory: here("./client/routes"),
    generatedRouteTree: here("./client/routeTree.gen.ts"),
  }),
  react(),
  tailwindcss(),
];

export default defineConfig(({ mode }) => {
  const app = mode === "partner" ? "partner" : "client";
  const root = here(`./${app}`);

  return {
    root,
    publicDir: `${root}/public`,
    plugins: app === "client" ? clientPlugins() : [react()],
    // "@/..." = katalog źródeł portalu klienta (client/); partner używa ścieżek względnych.
    resolve: { alias: { "@": here("./client") } },
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
