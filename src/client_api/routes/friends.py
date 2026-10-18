"""Trasy znajomych: /api/friends (+ /code, /code/{code}, /invite, /requests/{userId}, /{userId}, /going).

Logika i DynamoDB: friends.py; imię do akcji (409 name_required bez imienia): profiles.require_name."""

from aws_lambda_powertools.event_handler.router import APIGatewayHttpRouter

import events
import friends
import profiles
import store
from codzis_common.app import parse_input
from routes import common
from schemas import InviteBody

GOING_LIMIT = 60

router = APIGatewayHttpRouter()


@router.get("/api/friends")
def get_friends() -> dict:
    """Moja zakładka Znajomi: kod (pierwszy raz losowany), znajomi i zaproszenia."""
    user = common.claims(router)
    friends.get_or_create_code(user["sub"], profiles.require_name(user))
    return friends.overview(user["sub"], common.epoch())


@router.post("/api/friends/code")
def post_code() -> dict:
    user = common.claims(router)
    return {"code": friends.regenerate_code(user["sub"], profiles.require_name(user))}


@router.get("/api/friends/code/<code>")
def get_code(code: str) -> dict:
    user_id = common.claims(router)["sub"]
    return friends.preview(user_id, common.path_id(code), common.epoch())


@router.post("/api/friends/invite")
def post_invite() -> dict:
    user = common.claims(router)
    code = parse_input(InviteBody, common.body(router), "Podaj kod znajomego").code  # przed imieniem (409)
    return friends.invite(user["sub"], profiles.require_name(user), code, common.epoch())


@router.put("/api/friends/requests/<userId>")
def put_request(userId: str) -> dict:
    user = common.claims(router)
    from_id = common.path_id(userId)
    return friends.accept(user["sub"], profiles.require_name(user), from_id, common.epoch())


@router.delete("/api/friends/requests/<userId>")
def delete_request(userId: str) -> dict:
    user_id = common.claims(router)["sub"]
    friends.decline(user_id, common.path_id(userId))
    return {}


@router.delete("/api/friends/<userId>")
def delete_friend(userId: str) -> dict:
    user_id = common.claims(router)["sub"]
    friends.remove(user_id, common.path_id(userId))
    return {}


@router.get("/api/friends/going")
def get_going() -> dict:
    """„Znajomi idą”: nadchodzące zapisy znajomych (≤ 50 zapytań GSI byUser) + mapa wydarzenie -> znajomi.

    Znajomi jako {"userId", "name"} (po imieniu, potem po userId) - dwie „Ole” to dwie osoby.
    """
    user = common.claims(router)
    now = common.now()
    going: dict[str, list[dict[str, str]]] = {}
    for friend_id, name in friends.friend_ids(user["sub"]).items():
        for row in store.my_saves(friend_id):
            going.setdefault(row["eventId"], []).append({"userId": friend_id, "name": name})
    known = store.all_events()
    upcoming = [(known[i], events.next_slot(known[i], now=now)) for i in going if i in known]
    page = [(item, slot) for item, slot in upcoming if slot and common.upcoming(slot)]
    page.sort(key=lambda pair: (events.slot_sort_key(pair[1]), events.plain_text(pair[0].get("title"))))
    by_event = {item["id"]: sorted(going[item["id"]], key=_friend_order) for item, _ in page}
    cards = common.cards(user, page[:GOING_LIMIT])
    return {"items": [card | {"friends": by_event[card["id"]]} for card in cards], "byEvent": by_event}


def _friend_order(friend: dict[str, str]) -> tuple[str, str]:
    return (friend["name"].casefold(), friend["userId"])
