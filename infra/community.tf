# Społeczność: zapisy na wydarzenia ("idę") i liczniki pod Popularne.
# Jedyny zapisujący: Lambda client-api (src/client_api/store.py) + scripts/seed_demo.py (tylko rekordy seed: true).

# Kto zapisał się na wydarzenie: get_item (czy ja), query po eventId (lista zapisanych),
# GSI byUser (na co się zapisałem - stan "Zapisano" na kartach). Źródło członków czatu.
resource "aws_dynamodb_table" "attendance" {
  name         = "${local.name}-attendance"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "eventId"
  range_key    = "userId" # sub z Cognito (seed: "seed-<n>")

  attribute {
    name = "eventId"
    type = "S"
  }

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "savedAt"
    type = "S"
  }

  global_secondary_index {
    name            = "byUser"
    hash_key        = "userId"
    range_key       = "savedAt"
    projection_type = "KEYS_ONLY"
  }

  # Deklaracje użytkowników - nie da się ich odtworzyć
  point_in_time_recovery {
    enabled = true
  }
}

# Liczba zapisanych na wydarzenie (ADD w tej samej transakcji co zapis w attendance).
# kind = "event" to stała pod GSI bySaves: top wydarzeń po liczbie zapisanych (query malejąco).
resource "aws_dynamodb_table" "event_stats" {
  name         = "${local.name}-event-stats"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "eventId"

  attribute {
    name = "eventId"
    type = "S"
  }

  attribute {
    name = "kind"
    type = "S"
  }

  attribute {
    name = "saves"
    type = "N"
  }

  global_secondary_index {
    name            = "bySaves"
    hash_key        = "kind"
    range_key       = "saves"
    projection_type = "KEYS_ONLY"
  }
}

# Znajomi (src/client_api/friends.py - tam pełny opis modelu). Jedyny zapisujący: client-api.
# Jedna tabela bez GSI, wszystko po kluczu: PK userId (sub albo "code#WAW-XXXXXX"), SK sk:
#   code (mój kod), owner (kod -> właściciel), friend#<sub> (znajomość, para rekordów),
#   in#<sub> / out#<sub> (zaproszenia, wygasają po 30 dniach), limit (złe kody, okno 1 h).
resource "aws_dynamodb_table" "friends" {
  name         = "${local.name}-friends"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "sk"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # Zaproszenia i okna limitu prób wygasają same (sekundy epoki)
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  # Znajomości użytkowników - nie da się ich odtworzyć
  point_in_time_recovery {
    enabled = true
  }
}
