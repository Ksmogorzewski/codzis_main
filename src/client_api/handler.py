"""API portalu klienta (HTTP API + JWT authorizer Cognito, payload 2.0).

    GET    /api/me          profil zalogowanego użytkownika (pierwsze wywołanie zakłada rekord i dane konta;
                            kopiuje z tokenu e-mail, imię -> displayName, nazwisko -> familyName)
    PUT    /api/me          {"birthDate"} -> dane konta (account.py); imię i nazwisko zostają bez zmian. Przy
                            wypełnionej ankiecie przelicza też preferencje (przedział wieku z daty urodzenia)
    POST   /api/me/photo    {"contentType"} -> {"key", "upload": {"url", "fields"}} (presigned POST do S3)
    PUT    /api/me/photo    {"key"} -> wgrane zdjęcie staje się zdjęciem profilowym (poprzednie usuwamy)
    DELETE /api/me/photo    -> profil bez zdjęcia
    GET    /api/onboarding  pytania onboardingu (onboarding.py)
    PUT    /api/profile     {"answers": {...}} -> walidacja, preferencje (+ przedział wieku z account.birthDate),
                            zapis w tabeli users

Odpowiedź tras /api/me = GET /api/me: m.in. "name" (imię), "familyName" (nazwisko - tylko dla właściciela),
"account": {"birthDate", "photoUrl"}.

Eksploruj, zapisy i Popularne (logika: events.py, DynamoDB: store.py). Karta (`Card`) = karta
rekomendacji z src/recommender_api/present.py bez reason/reasonSource/score, za to z
`saves` (liczba zapisanych) i `saved` (czy ja):

    GET    /api/events?when=today|tomorrow|weekend|week|date&date=RRRR-MM-DD&cat=sport|kultura|rekreacja
                       &district=&free=1&indoor=1&q=&limit=60 (maks. 200)
           -> {"when", "window": {"from", "to"}, "total", "items": [Card]}  (od najbliższego startu)
    GET    /api/events/stats?ids=a,b,c (maks. 100)   -> {"<id>": {"saves", "saved"}}
    GET    /api/events/{id}             -> Card + {"text" (bez HTML), "occurrences", "importedAt"}; 404
    PUT    /api/events/{id}/save        -> {"saved": true, "saves"}  (idempotentnie; 404 gdy brak wydarzenia)
    DELETE /api/events/{id}/save        -> {"saved": false, "saves"} (idempotentnie)
    GET    /api/events/{id}/attendees   -> {"saves", "saved", "people": [{"userId", "name", "isMe", "isFriend"}]}
                                           (najpierw ja, potem znajomi, potem reszta - w grupach najnowsi
                                           najpierw; isFriend tylko dla wydarzeń z nadchodzącym terminem,
                                           inaczej false; maks. 100 najnowszych; bez imienia "Ktoś"; nigdy e-maili;
                                           userId = sub z Cognito, dane testowe "seed-<n>" - tożsamość osoby)
    GET    /api/popular                 -> {"window": {"from", "to"}, "items": [Card]}
                                           (dziś + 6 dni, saves > 0, malejąco, maks. 20)
    GET    /api/me/events               -> {"items": [Card + {"past", "savedAt"}]}  zakładka „Twoje”: moje zapisy
                                           (saved = true; najpierw nadchodzące od najbliższego terminu, potem
                                           minione - past = true, slot = ostatni termin - od najświeższego;
                                           maks. 100 najnowszych zapisów; bez wydarzeń wygasłych z codzis-events)

Czat ekipy (logika i DynamoDB: crews.py): zapisani na wydarzenie łączą się w ekipy do 4 osób, każda ma
własny czat; wypisanie z wydarzenia = wyjście z ekipy. Wiadomość = {"id", "kind" ("user" | komunikat
Wodzireja: "welcome", "joined", "left", "full"), "userId", "name", "text" (tylko "user"), "sentAt", "isMe"}:

    GET    /api/events/{id}/crew?after=<sentAt>  (zapisani, imię) -> {"crew", "capacity", "members": [{"userId",
                                       "name", "isMe"}], "messageCount", "icebreaker", "answered", "messages",
                                       "cursor"}; pierwsze wejście dołącza do ekipy z wolnym miejscem (albo
                                       zakłada nową), każde oznacza wiadomości jako przeczytane; bez after -
                                       najnowsze 200, z after - nowe (z 15 s zapasu, powtórki pomija front);
                                       answered = czy już coś napisałem (lodołamacz odblokowuje czat);
                                       400 fields ["after"] przy złym after
    POST   /api/events/{id}/crew/messages (zapisani, imię) {"text"} -> {"message"}; 1-500 znaków po
                                       oczyszczeniu (400 fields ["text"]), 429 {"code": "too_fast"} częściej niż co 1 s
    GET    /api/me/crews              -> {"items": [{"eventId", "title", "crew", "capacity", "members",
                                       "messageCount", "unread", "last": Wiadomość bez id | null}], "unread"}
                                       (plakietki: moje zapisy, w których mam ekipę; wydarzenia od najnowszego zapisu)
    Błędy: 404 brak wydarzenia, 409 {"code": "not_attending"} bez zapisu na wydarzenie, 409 name_required.

Imię widoczne dla innych (zapisy, zaproszenia, znajomi, podgląd kodu) składa profiles.display_name: imię + inicjał
nazwiska („Ola K.”, nazwisko opcjonalne przy rejestracji); pełnego nazwiska nie oddajemy nikomu.

Znajomi (logika i DynamoDB: friends.py). Akcje oznaczone (imię) bez imienia w tokenie i w users ->
409 {"code": "name_required"}. Czasy createdAt/since: ISO 8601 UTC. userId = sub z Cognito (nigdy e-mail):

    GET    /api/friends (imię)             -> {"code": "WAW-XXXXXX", "friends": [{"userId", "name", "since"}],
                                              "incoming": [{"userId", "name", "createdAt"}], "outgoing": [...]}
                                              (pierwsze wywołanie zakłada kod; znajomi alfabetycznie,
                                              zaproszenia najnowsze najpierw, wygasłe po 30 dniach pominięte)
    POST   /api/friends/code (imię)        -> {"code"}  nowy kod (stary przestaje działać; znajomi
                                              i oczekujące zaproszenia zostają)
    GET    /api/friends/code/{code}        -> {"userId", "name"}  do kogo należy kod (wpis "byle jak":
                                              "waw 7k2p9x" = "WAW-7K2P9X"); 404 zły kod, 400 własny kod
    POST   /api/friends/invite (imię)      {"code"} -> {"status": "pending" | "friends", "userId", "name"}
                                              ("friends": już znajomi albo ta osoba już mnie zaprosiła -
                                              automatyczna akceptacja); 404, 400 jak wyżej
    PUT    /api/friends/requests/{userId} (imię) -> {"status": "friends"}  akceptacja; 404 brak zaproszenia
    DELETE /api/friends/requests/{userId}  -> {}  ciche odrzucenie (zapraszający dalej widzi "oczekuje")
    DELETE /api/friends/{userId}           -> {}  usunięcie znajomości u obu stron; własne id -> 400
    GET    /api/friends/going              -> {"items": [Card + {"friends": [Friend]}], "byEvent": {eventId: [Friend]}}
                                              Friend = {"userId", "name"}; nadchodzące zapisy znajomych (od teraz;
                                              bez zajęć bez terminu); karty od najbliższego startu, maks. 60;
                                              byEvent - wszystkie; znajomi po imieniu, potem po userId
    Błędy: 404 zły kod (+1 do limitu), 429 {"code": "too_many_attempts"} po 10 złych kodach w godzinę
    (także dobre kody do końca okna), 409 {"code": "friend_limit"} przy 50 znajomych.

Token weryfikuje API Gateway; tu korzystamy już tylko z jego claims (ID token Cognito).
Po zapisaniu profilu i przy logowaniu rekomender w tle liczy zestawy na dziś, jutro i weekend
(GET /api/recommendations obsługuje osobna Lambda: src/recommender_api).

Budowa (AWS Lambda Powertools): ten plik tylko składa aplikację - `create_app` z codzis_common (format błędów,
404, serializacja JSON, linia logu dostępu) + routery z routes/ (me.py: /api/me, /api/onboarding, /api/profile;
events.py: Eksploruj i Popularne; saves.py: zapisy „idę” i /api/me/events; friends.py: znajomi; crews.py: czat
ekipy). Wejście (ścieżka, query, body) przez modele Pydantic w schemas.py; logika i DynamoDB w modułach domeny
(profiles.py, account.py, onboarding.py, events.py, store.py, friends.py, crews.py). Nowa trasa: model
w schemas.py -> funkcja w routes/<domena>.py -> test -> trasa w infra/client_api.tf (test_routes_registered
pilnuje zgodności).
"""

from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

import crews
import friends
import profiles
import routes.crews
import routes.events
import routes.friends
import routes.me
import routes.saves
import store
from codzis_common.app import create_app
from profiles import ONBOARDING_VERSION, lambda_client, users
from schemas import PATH_ID

# Obiekty, do których sięgają testy (client_api.store, client_api.users…) - te same, których używają trasy.
# Do podmiany w testach bierz moduł (np. client_api.profiles.lambda_client), nie nazwę zaimportowaną tutaj.
__all__ = [
    "ONBOARDING_VERSION",
    "PATH_ID",
    "app",
    "crews",
    "friends",
    "handler",
    "lambda_client",
    "profiles",
    "store",
    "users",
]

app = create_app(APIGatewayHttpResolver)
for _router in (
    routes.me.router,
    routes.events.router,
    routes.saves.router,
    routes.friends.router,
    routes.crews.router,
):
    app.include_router(_router)


def handler(event: dict[str, Any], context: LambdaContext) -> dict[str, Any]:
    """Punkt wejścia Lambdy (Terraform: handler.handler)."""
    return app.resolve(event, context)
