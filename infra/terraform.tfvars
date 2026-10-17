# Plik jest w repo - bez sekretów. google_client_id/secret wpisuj do secrets.auto.tfvars (ignorowany przez git).
domain_name    = "partner.waw-out.pl"
domain_aliases = []
partners       = ["demo"]

# dane.um.warszawa.pl blokuje IP AWS -> import lokalnie: scripts/import-local.sh
importer_schedule_enabled = false

# portal klienta (WarsawNow)
client_domain_name    = "portal.waw-out.pl"
client_domain_aliases = []
