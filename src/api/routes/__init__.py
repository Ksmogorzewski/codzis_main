"""Trasy API partnera: jeden `router` (Powertools `APIGatewayRouter`) na domenę; składa je `handler.py`.

Ścieżki względem stage'a REST API ("/me", nie "/api/me"); parametr ścieżki jak w logu dostępu (`<id>` -> "{id}").
Trasa: partner (`current_partner`) -> wejście przez model (`schemas`) -> logika domeny -> dict albo (dict, status).
Błędy: `raise ApiError(...)`; resztę (500, 404, log dostępu) robi `codzis_common.app`.
"""

from aws_lambda_powertools.event_handler.router import APIGatewayRouter

from config import PARTNERS
from schemas import Partner

GOOGLE_PARTNER_NAME = "Organizator"  # konto Google bez imienia i nazwiska
MAX_PARTNER_NAME = 100


def current_partner(router: APIGatewayRouter) -> Partner:
    """Partner bieżącego żądania. API Gateway wpuszcza tylko żądania z ważnym tokenem albo kluczem.

    Z Google (autoryzator Cognito puli partnerów): partnerId = `sub`, nazwa = imię i nazwisko z tokenu.
    Bez Google: partnerId = id klucza API, nazwa z PARTNERS (Terraform) albo samo id."""
    request_context = router.current_event.raw_event["requestContext"]
    claims = (request_context.get("authorizer") or {}).get("claims")
    if claims:
        # Nazwa podpisuje ogłoszenia w portalu klienta; e-maila z tokenu nigdzie nie kopiujemy.
        name = " ".join(str(claims.get("name") or "").split())[:MAX_PARTNER_NAME]
        return {"partnerId": claims["sub"], "partnerName": name or GOOGLE_PARTNER_NAME}
    key_id = request_context["identity"]["apiKeyId"]
    return {"partnerId": key_id, "partnerName": PARTNERS.get(key_id, key_id)}
