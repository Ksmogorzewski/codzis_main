"""API panelu partnera (REST API v1, proxy /{proxy+}) na routerze Powertools.

Logowanie (infra/api.tf): z Google - token puli Cognito partnerów (nagłówek X-Id-Token, sprawdza go
API Gateway), samoobsługa: konto Google = konto organizatora (partnerId = sub, nazwa = imię i nazwisko
z Google); bez Google - klucz API partnera z Terraforma (partnerId = apiKeyId). Patrz routes/__init__.py.

    GET  /me                       profil partnera: saldo kredytów, koszt ogłoszenia, opcje formularza
                                   (pierwsze wywołanie zakłada rekord z kredytami startowymi)
    GET  /events                   ostatnie zgłoszenia partnera (events.py)
    POST /events                   nowe ogłoszenie: walidacja, -1 kredyt, kolejka taggera, presigned POST zdjęcia
    GET  /payments                 ostatnie płatności partnera (payments.py)
    POST /payments                 {"package": id} -> płatność pending + redirectUrl (mock bramki)
    GET  /payments/{id}            podgląd płatności
    POST /payments/{id}/confirm    rozliczenie: dodaje kredyty (raz; ponownie -> 409)
    POST /payments/{id}/cancel     anulowanie płatności pending

Pliki: handler.py (złożenie aplikacji), routes/ (trasy per domena + partner z żądania), schemas.py (modele
wejścia i wyjścia, walidacja formularza), events.py (ogłoszenia), payments.py (płatności),
store.py (klienty AWS, rekord partnera, transakcje i kredyty), config.py (zmienne środowiskowe).
"""

from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

from codzis_common.app import create_app
from routes import events, me, payments

app = create_app(APIGatewayRestResolver)
app.include_router(me.router)
app.include_router(events.router)
app.include_router(payments.router)


def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    return app.resolve(_with_proxy_path(event), context)


def _with_proxy_path(event: dict[str, Any]) -> dict[str, Any]:
    """Trasę wyznacza `pathParameters.proxy` (część adresu po stage'u, np. "payments/abc/confirm"), jak przed
    refaktorem. `path` zależy od drogi żądania (domyślny adres API Gateway: "/me", własna domena z mapowaniem:
    z prefiksem), więc Powertools dostaje kopię zdarzenia z `path` = "/" + proxy bez skrajnych "/"."""
    proxy = (event.get("pathParameters") or {}).get("proxy") or ""
    return {**event, "path": "/" + proxy.strip("/")}
