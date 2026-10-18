"""Trasy zapisów „idę”: /api/events/{id}/save, /api/events/{id}/attendees, /api/me/events (dane: store.py)."""

from aws_lambda_powertools.event_handler.router import APIGatewayHttpRouter

import events
import friends
import profiles
import store
from codzis_common.app import ApiError
from codzis_common.http import now_iso
from routes import common

MY_EVENTS_LIMIT = 100
ANONYMOUS = "Ktoś"
EVENT_NOT_FOUND = "Nie znaleziono wydarzenia"

router = APIGatewayHttpRouter()


@router.put("/api/events/<id>/save")
def put_save(id: str) -> dict:
    """Zapis na wydarzenie (kopiuje display_name z tokenu, a bez niego z users; nigdy e-mail ani pełne nazwisko).
    Ponowny zapis nic nie zmienia."""
    user = common.claims(router)
    event_id = common.path_id(id, EVENT_NOT_FOUND)
    if not store.get_event(event_id):
        raise ApiError(404, EVENT_NOT_FOUND)
    name = profiles.display_name(user) or profiles.stored_name(user["sub"])
    store.save(event_id, user["sub"], name, now_iso())
    return {"saved": True, "saves": store.saves_of(event_id)}


@router.delete("/api/events/<id>/save")
def delete_save(id: str) -> dict:
    """Wypisanie. Działa też dla wydarzeń, które już wygasły; ponowne nic nie zmienia."""
    user_id = common.claims(router)["sub"]
    event_id = common.path_id(id, EVENT_NOT_FOUND)
    store.unsave(event_id, user_id)
    return {"saved": False, "saves": store.saves_of(event_id)}


@router.get("/api/events/<id>/attendees")
def get_attendees(id: str) -> dict:
    """Lista zapisanych: userId i imię (nigdy e-maile), najnowsi najpierw."""
    me = common.claims(router)["sub"]
    event_id = common.path_id(id, EVENT_NOT_FOUND)
    rows = store.attendees(event_id)
    item = store.all_events().get(event_id) if rows else None
    # znajomi widzą tylko nadchodzące zapisy - na minionych wydarzeniach nikt nie jest oznaczony
    upcoming = item and common.upcoming(events.next_slot(item, now=common.now()))
    mine = friends.friend_ids(me) if upcoming else {}
    people = [
        {
            "userId": row["userId"],
            "name": row.get("name") or ANONYMOUS,
            "isMe": row["userId"] == me,
            "isFriend": row["userId"] in mine,
        }
        for row in rows
    ]
    people.sort(key=lambda p: 0 if p["isMe"] else 1 if p["isFriend"] else 2)  # stabilnie: w grupie najnowsi
    return {"saves": store.saves_of(event_id), "saved": store.is_saved(event_id, me), "people": people}


@router.get("/api/me/events")
def get_my_events() -> dict:
    """Zakładka „Twoje”: wydarzenia, na które jestem zapisany (GSI byUser + pamięć codzis-events)."""
    user_id = common.claims(router)["sub"]
    found = events.my_events(store.my_saves(user_id), store.all_events(), common.now(), MY_EVENTS_LIMIT)
    counts = store.saves_for(item["id"] for item, _, _ in found) if found else {}
    return {
        "items": [
            events.card(item, slot, counts[item["id"]], True) | {"past": row["past"], "savedAt": row.get("savedAt")}
            for item, slot, row in found
        ]
    }
