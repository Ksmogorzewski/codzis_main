"""Wspólny kod Lambd API (klient, partner), wdrażany jako Lambda Layer (infra/layers.tf).

W Lambdzie warstwa jest w /opt/python, więc import to `from codzis_common.app import ...`.
Moduły:
- app: fabryka aplikacji na Powertools (router, logger JSON z correlation_id, obsługa błędów),
- aws: AWS_CONFIG (timeouty i ponawianie dla boto3),
- http: błędy, body, odpowiedź JSON; stare `handle_request`/`response` zostają tylko na czas
  wdrożenia (okno deploy), do usunięcia w kolejnym PR.
Zależność: warstwa Lambda Powertools (z Pydantic) oraz botocore z runtime Lambdy;
warstwa nie ma własnych zależności.
"""
