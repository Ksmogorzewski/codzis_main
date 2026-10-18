"""Trasy czatu ekipy: /api/events/{id}/crew (+ /messages), /api/me/crews (logika i DynamoDB: crews.py).

Czat jest tylko dla zapisanych na wydarzenie (409 not_attending); imię do dołączenia i pisania: profiles.require_name.
"""

from aws_lambda_powertools.event_handler.router import APIGatewayHttpRouter

import crews
import events
import profiles
import store
from codzis_common.app import ApiError, parse_input
from routes import common
from schemas import CrewQuery, MessageBody

MY_CREWS_LIMIT = 100  # jak moje zapisy na „Twoje”
EVENT_NOT_FOUND = "Nie znaleziono wydarzenia"
AFTER_ERROR = "Niepoprawny parametr after"

router = APIGatewayHttpRouter()


@router.get("/api/events/<id>/crew")
def get_crew(id: str) -> dict:
    """Czat mojej ekipy (front pyta co kilka sekund z ?after= = cursor z poprzedniej odpowiedzi); pierwsze
    wejście dołącza do ekipy z wolnym miejscem."""
    user = common.claims(router)
    event_id = common.path_id(id, EVENT_NOT_FOUND)
    after = parse_input(CrewQuery, common.query(router), AFTER_ERROR).after
    name = profiles.require_name(user, "Podaj imię, zanim dołączysz do ekipy")
    event = _attended_event(user["sub"], event_id)
    return crews.open_chat(event_id, event, user["sub"], name, after, common.now())


@router.post("/api/events/<id>/crew/messages")
def post_message(id: str) -> dict:
    user = common.claims(router)
    event_id = common.path_id(id, EVENT_NOT_FOUND)
    text = parse_input(MessageBody, common.body(router), crews.TEXT_ERROR).text
    name = profiles.require_name(user, "Podaj imię, zanim napiszesz do ekipy")
    event = _attended_event(user["sub"], event_id)
    return crews.send(event_id, event, user["sub"], name, text, common.now())


@router.get("/api/me/crews")
def get_my_crews() -> dict:
    """Plakietki czatów: moje ekipy na wydarzenia, na które jestem zapisany (bez wydarzeń wygasłych)."""
    user_id = common.claims(router)["sub"]
    known = store.all_events()
    ids = [row["eventId"] for row in store.my_saves(user_id) if row["eventId"] in known][:MY_CREWS_LIMIT]
    found = crews.summaries(user_id, ids)
    items = [{"eventId": i, "title": events.plain_text(known[i].get("title"))} | found[i] for i in ids if i in found]
    return {"items": items, "unread": sum(item["unread"] for item in items)}


def _attended_event(user_id: str, event_id: str) -> dict:
    """Wydarzenie czatu (z pamięci, a świeżo dodane - z tabeli); czat jest tylko dla zapisanych."""
    event = store.all_events().get(event_id) or store.get_event(event_id)
    if not event:
        raise ApiError(404, EVENT_NOT_FOUND)
    if not store.is_saved(event_id, user_id):
        raise ApiError(409, "Czat jest tylko dla zapisanych na wydarzenie", code="not_attending")
    return event
