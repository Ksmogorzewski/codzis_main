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
