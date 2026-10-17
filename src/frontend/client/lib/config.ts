// Konfiguracja runtime z config.js (Terraform: local.client_app_config w infra/client_site.tf)
export type ClientConfig = {
  region: string;
  userPoolId: string;
  clientId: string;
  cognitoDomain: string; // np. warsawnow.auth.eu-central-1.amazoncognito.com
  googleEnabled: boolean;
  apiUrl: string;
  partnerPortal: string;
};

export const config = (): ClientConfig => window.APP_CONFIG as ClientConfig;
