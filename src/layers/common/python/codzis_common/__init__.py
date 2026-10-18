"""Wspólny kod Lambd API (klient, partner), wdrażany jako Lambda Layer (infra/layers.tf).

W Lambdzie warstwa jest w /opt/python, więc import to `from codzis_common.http import ...`.
Moduły: http (błędy, body, odpowiedź JSON, handle_request: catch-all 500 + log dostępu),
aws (AWS_CONFIG: timeouty i ponawianie dla boto3).
Tylko biblioteka standardowa i botocore (jest w runtime Lambdy) - warstwa nie ma własnych zależności.
"""
