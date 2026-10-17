variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "project" {
  type    = string
  default = "codzis"
}

variable "domain_name" {
  description = "Główna (kanoniczna) domena portalu, np. waw-out.pl. DNS u zewnętrznego operatora (home.pl)"
  type        = string
}

variable "domain_aliases" {
  description = "Dodatkowe nazwy portalu na tym samym certyfikacie i CloudFront, np. [\"www.waw-out.pl\"]"
  type        = list(string)
  default     = []
}

variable "partners" {
  description = "Nazwy partnerów - każdy dostaje własny klucz API (= login do portalu)"
  type        = set(string)
  default     = ["demo"]
}

variable "event_cost_credits" {
  description = "Ile kredytów kosztuje dodanie jednego ogłoszenia"
  type        = number
  default     = 1
}

variable "starter_credits" {
  description = "Kredyty na start dla nowego partnera (przy pierwszym logowaniu)"
  type        = number
  default     = 0
}

variable "currency" {
  type    = string
  default = "PLN"
}

variable "credit_packages" {
  description = "Pakiety kredytów do kupienia (mock bramka)"
  type = map(object({
    name    = string
    credits = number
    price   = number
  }))
  default = {
    starter  = { name = "Start", credits = 1, price = 19 }
    standard = { name = "Standard", credits = 5, price = 79 }
    pro      = { name = "Pro", credits = 12, price = 149 }
  }
}

variable "max_photo_mb" {
  description = "Maksymalny rozmiar zdjęcia (MB)"
  type        = number
  default     = 5
}

variable "api_rate_limit" {
  description = "Średnia liczba żądań/s (na klucz i na cały stage)"
  type        = number
  default     = 5
}

variable "api_burst_limit" {
  type    = number
  default = 10
}

variable "api_daily_quota" {
  description = "Limit żądań dziennie na klucz API (bezpiecznik kosztowy)"
  type        = number
  default     = 1000
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "worker_min_messages" {
  description = "Od ilu wiadomości w kolejce dispatcher uruchamia tagger (1 = przy każdej wiadomości)"
  type        = number
  default     = 1
}

variable "worker_check_minutes" {
  description = "Co ile minut dispatcher sprawdza kolejkę (1 min = ~43 tys. wywołań Lambdy/mies., w darmowym limicie)"
  type        = number
  default     = 1
}

variable "importer_schedule_enabled" {
  description = "Czy EventBridge ma uruchamiać importer w ECS. dane.um.warszawa.pl odrzuca IP AWS - do czasu rozwiązania import robi scripts/import-local.sh"
  type        = bool
  default     = true
}

variable "importer_schedule" {
  description = "Jak często importer pobiera dane z API UM Warszawy (zbiory odświeżają się co 2 h)"
  type        = string
  default     = "rate(2 hours)"
}

variable "importer_image_tag" {
  type    = string
  default = "latest"
}

variable "raw_snapshot_retention_days" {
  description = "Ile dni trzymać surowe odpowiedzi API w S3 (podgląd / ponowne przetworzenie)"
  type        = number
  default     = 30
}

variable "worker_image_tag" {
  type    = string
  default = "latest"
}

variable "event_categories" {
  description = "Kategorie w formularzu partnera - nazwy jak w API UM Warszawy (do weryfikacji z ich słownikiem)"
  type        = list(string)
  default     = ["Kultura", "Sport", "Rekreacja", "Edukacja", "Dla dzieci"]
}

locals {
  # Dzielnice jak w polu localization[].name z API UM Warszawy
  warsaw_districts = [
    "Bemowo", "Białołęka", "Bielany", "Mokotów", "Ochota", "Praga-Południe",
    "Praga-Północ", "Rembertów", "Śródmieście", "Targówek", "Ursus", "Ursynów",
    "Wawer", "Wesoła", "Wilanów", "Włochy", "Wola", "Żoliborz",
  ]
}

# --- portal klienta (WarsawNow) ---

variable "client_domain_name" {
  description = "Domena portalu klienta. Subdomena, bo home.pl nie ma rekordu ALIAS dla domeny głównej (wystarczy CNAME)"
  type        = string
  default     = "portal.waw-out.pl"
}

variable "client_domain_aliases" {
  description = "Dodatkowe nazwy portalu klienta na tym samym certyfikacie i CloudFront"
  type        = list(string)
  default     = []
}

variable "client_dev_origins" {
  description = "Adresy lokalnego developmentu (callback logowania + CORS API), np. scripts/client-dev.sh"
  type        = list(string)
  default     = ["http://localhost:8000"]
}

variable "partner_dev_origins" {
  description = "Adresy lokalnego developmentu panelu organizatora (CORS uploadu zdjęć), np. npm run dev:partner"
  type        = list(string)
  default     = ["http://localhost:8001"]
}

variable "cognito_domain_prefix" {
  description = "Prefiks Hosted UI Cognito: https://<prefix>.auth.<region>.amazoncognito.com (unikalny w regionie)"
  type        = string
  default     = "warsawnow"
}

variable "google_client_id" {
  description = "OAuth client ID z Google Cloud Console; puste = logowanie tylko e-mailem"
  type        = string
  default     = ""
}

variable "google_maps_embed_key" {
  description = "Klucz Google Maps Embed API (mapa z trasą komunikacją w szczegółach wydarzenia); puste = sam link do Map Google. Trafia do publicznego config.js, więc w Google Cloud ogranicz go do Maps Embed API i domen portalu"
  type        = string
  default     = ""
}

variable "google_client_secret" {
  description = "OAuth client secret z Google Cloud Console (trafia do state'u Terraforma)"
  type        = string
  default     = ""
  sensitive   = true
}

# --- rekomendacje (RAG) ---

variable "recommender_image_tag" {
  description = "Tag obrazu rekomendera w ECR; Lambda dostaje jego aktualny digest przy każdym apply"
  type        = string
  default     = "latest"
}

variable "recommender_memory_mb" {
  description = "Pamięć Lambdy rekomendera (od niej zależy CPU). Model ~0,5 GB; nowe konta AWS mają limit 3008 MB"
  type        = number
  default     = 3008
}

variable "recommender_refresh_minutes" {
  description = "Co ile minut odświeżać indeks rekomendacji (embeddingi liczone tylko dla nowych eventów)"
  type        = number
  default     = 30
}

variable "recommender_precompute_schedule" {
  description = "Kiedy liczyć zestawy na dziś, jutro i weekend dla aktywnych użytkowników (UTC; 3:00 = 5:00 latem, 4:00 zimą)"
  type        = string
  default     = "cron(0 3 * * ? *)"
}

variable "recommender_precompute_active_days" {
  description = "Nocne przeliczenie obejmuje osoby zalogowane w ciągu tylu ostatnich dni"
  type        = number
  default     = 14
}

variable "recommender_results_max_age_hours" {
  description = "Po ilu godzinach zapisany zestaw liczy się od nowa (żeby złapać nowe eventy)"
  type        = number
  default     = 12
}

variable "recommender_keep_warm" {
  description = "Wywołanie co 5 min, żeby model był w pamięci (zimny start z torchem trwa kilkanaście sekund)"
  type        = bool
  default     = true
}

variable "recommender_llm_enabled" {
  description = "Czy DeepSeek układa kolejność i pisze uzasadnienia (false = ranking wektorowy + reguły)"
  type        = bool
  default     = true
}

locals {
  client_domains        = concat([var.client_domain_name], var.client_domain_aliases)
  client_origins        = [for d in local.client_domains : "https://${d}"]
  client_app_urls       = concat([for o in local.client_origins : "${o}/"], [for o in var.client_dev_origins : "${o}/"])
  google_enabled        = var.google_client_id != ""
  cognito_hosted_domain = "${var.cognito_domain_prefix}.auth.${var.region}.amazoncognito.com"

  # rozszerzenie pliku -> Content-Type (strony na S3)
  content_types = {
    html = "text/html; charset=utf-8"
    js   = "application/javascript; charset=utf-8"
    css  = "text/css; charset=utf-8"
    jpg  = "image/jpeg"
    png  = "image/png"
    svg  = "image/svg+xml"
    ico  = "image/x-icon"
    webp = "image/webp"
    # manifest PWA portalu klienta (src/frontend/client/public)
    webmanifest = "application/manifest+json"
  }
}
