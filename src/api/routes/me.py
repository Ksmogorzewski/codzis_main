"""GET /me - profil partnera: saldo kredytów, koszt ogłoszenia, opcje formularza."""

from aws_lambda_powertools.event_handler.router import APIGatewayRouter

from config import EVENT_COST
from routes import current_partner
from schemas import FORM_OPTIONS, Profile
from store import ensure_partner

router = APIGatewayRouter()


@router.get("/me")
def get_me() -> Profile:
    partner = current_partner(router)
    item = ensure_partner(partner)
    return Profile(**partner, credits=item["credits"], eventCost=EVENT_COST, formOptions=FORM_OPTIONS)
