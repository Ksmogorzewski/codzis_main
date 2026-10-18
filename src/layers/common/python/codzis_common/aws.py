"""Wspólna konfiguracja klientów AWS SDK (boto3) w Lambdach API.

    users = boto3.resource("dynamodb", config=AWS_CONFIG).Table(USERS_TABLE)
    sqs = boto3.client("sqs", config=AWS_CONFIG)
    s3 = boto3.client("s3", config=AWS_CONFIG.merge(Config(signature_version="s3v4")))  # własne opcje + nasze

Krótkie timeouty i maks. 2 próby łącznie (total_max_attempts; tryb "standard": ponawia błędy przejściowe
i throttling z wykładniczym odstępem). Najgorszy przypadek 2 × (1 s + 3 s) = 8 s < 10 s limitu Lambdy, żeby zawieszone
połączenie nie zjadło całego limitu Lambdy (10 s) - wtedy API Gateway zwraca pusty 502, a tak trasa
kończy się wyjątkiem i handle_request oddaje 500 z requestId.
Domyślnie boto3 czeka do 60 s na odczyt.

botocore jest w runtime Lambdy (razem z boto3), więc warstwa dalej nie ma własnych zależności.
"""

from botocore.config import Config

AWS_CONFIG = Config(connect_timeout=1, read_timeout=3, retries={"total_max_attempts": 2, "mode": "standard"})
