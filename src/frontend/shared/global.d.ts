// config.js (Terraform / scripts/frontend-dev.sh) ustawia window.APP_CONFIG przed załadowaniem aplikacji
declare global {
  interface Window {
    APP_CONFIG: unknown;
  }
}

export {};
