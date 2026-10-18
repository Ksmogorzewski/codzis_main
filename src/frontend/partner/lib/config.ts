// Konfiguracja runtime z config.js (Terraform: local.partner_app_config w infra/website.tf)
export type CreditPackage = { name: string; credits: number; price: number };

export type PartnerConfig = {
  apiUrl: string; // "/api" - API za CloudFront, ta sama domena
  maxPhotoMb: number;
  eventCost: number;
  currency: string;
  packages: Record<string, CreditPackage>;
  categories: string[];
  districts: string[];
  clientPortal?: string;
  // Logowanie Google: Hosted UI puli Cognito partnerów (infra/partner_auth.tf); puste = logowanie kluczem API
  cognitoDomain?: string;
  clientId?: string;
};

export const config = (): PartnerConfig => window.APP_CONFIG as PartnerConfig;

export const sortedPackages = () =>
  Object.entries(config().packages)
    .map(([id, p]) => ({ id, ...p }))
    .sort((a, b) => a.credits - b.credits);
