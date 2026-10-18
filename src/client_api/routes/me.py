"""Trasy profilu: /api/me (+ /api/me/photo), /api/onboarding, /api/profile (dane: profiles.py, account.py)."""

from aws_lambda_powertools.event_handler.router import APIGatewayHttpRouter

import account
import events
import profiles
from codzis_common.app import ApiError, parse_input
from onboarding import public_steps, validate_answers
from routes import common
from schemas import MeBody, PhotoBody, PhotoUploadBody, ProfileBody

ANSWERS_ERROR = "Niepoprawne lub brakujące odpowiedzi"
ME_ERROR = "Niepoprawne dane profilu"
PHOTO_TYPE_ERROR = "Zdjęcie musi być w formacie JPG, PNG albo WebP"
PHOTO_KEY_ERROR = "Nie znaleźliśmy wgranego zdjęcia, spróbuj ponownie"

router = APIGatewayHttpRouter()


@router.get("/api/me")
def get_me() -> dict:
    return profiles.login(common.claims(router))


@router.put("/api/me")
def put_me() -> dict:
    """Data urodzenia w profilu (imię i nazwisko zostają z rejestracji albo Google); przy wypełnionej ankiecie
    przelicza też preferencje (przedział wieku) - profiles.update_account."""
    user_id = common.claims(router)["sub"]
    body = parse_input(MeBody, common.body(router), ME_ERROR)
    today = events.warsaw_today(common.now())
    values, errors = account.validate(body.model_dump(), today)
    if errors:
        raise ApiError(400, ME_ERROR, fields=errors)
    return profiles.update_account(user_id, values, today)


@router.post("/api/me/photo")
def post_photo() -> dict:
    """Formularz uploadu zdjęcia prosto do S3; profil zmienia dopiero PUT /api/me/photo."""
    user_id = common.claims(router)["sub"]
    body = parse_input(PhotoUploadBody, common.body(router), PHOTO_TYPE_ERROR)
    return account.upload_form(user_id, body.contentType)


@router.put("/api/me/photo")
def put_photo() -> dict:
    user_id = common.claims(router)["sub"]
    key = parse_input(PhotoBody, common.body(router), PHOTO_KEY_ERROR).key
    if not (account.own_photo_key(key, user_id) and account.uploaded(key)):
        raise ApiError(400, PHOTO_KEY_ERROR, fields=["key"])
    current = profiles.account_of(user_id)
    me = profiles.save_account(user_id, account.with_photo(current, key))
    if current.get("photoKey") != key:
        account.delete_file(current.get("photoKey"))
    return me


@router.delete("/api/me/photo")
def delete_photo() -> dict:
    user_id = common.claims(router)["sub"]
    current = profiles.account_of(user_id)
    me = profiles.save_account(user_id, account.with_photo(current, None))
    account.delete_file(current.get("photoKey"))
    return me


@router.get("/api/onboarding")
def get_onboarding() -> dict:
    return {"version": profiles.ONBOARDING_VERSION, "steps": public_steps(profiles.STEPS)}


@router.put("/api/profile")
def put_profile() -> dict:
    user_id = common.claims(router)["sub"]
    body = parse_input(ProfileBody, common.body(router), ANSWERS_ERROR)
    answers, errors = validate_answers(body.answers, profiles.STEPS)
    if errors:
        raise ApiError(400, ANSWERS_ERROR, fields=errors)
    return profiles.save_answers(user_id, answers, events.warsaw_today(common.now()))
