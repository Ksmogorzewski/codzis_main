"""Dane konta w profilu: data urodzenia i zdjęcie (src/client_api/account.py, trasy /api/me)."""

import boto3
import pytest

from tests.client_api.conftest import PHOTOS_BASE_URL, PHOTOS_BUCKET, call

GOOGLE = {
    "sub": "user-g",
    "email": "anna@example.com",
    "name": "Anna",
    "family_name": "Nowak",
    "picture": "https://lh3.googleusercontent.com/a/anna",
    "identities": '[{"providerName": "Google"}]',
}
EMAIL = {"sub": "user-1", "email": "ala@example.com", "name": "Ala"}
EMPTY = {"birthDate": None, "photoUrl": None}
ANSWERS = {
    "who": "kids",
    "vibe": ["active"],
    "discover": ["history", "guided"],
    "district": "Wola",
    "travel": "local",
    "budget": "up50",
}


def me(client_api, claims):
    status, body = call(client_api, "GET /api/me", claims=claims)
    assert status == 200
    return body


def photo_files():
    return [o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket=PHOTOS_BUCKET).get("Contents", [])]


def upload(client_api, claims, content_type="image/jpeg"):
    """Formularz z POST /api/me/photo + plik w S3, jak po presigned POST z przeglądarki."""
    status, form = call(client_api, "POST /api/me/photo", {"contentType": content_type}, claims=claims)
    assert status == 200
    boto3.client("s3").put_object(Bucket=PHOTOS_BUCKET, Key=form["key"], Body=b"zdjecie")
    return form["key"]


# --- dane konta zakładane przy pierwszym logowaniu ---


def test_google_first_login_takes_names_and_photo_from_google(client_api):
    body = me(client_api, GOOGLE)
    # imię i nazwisko z tokenu (given_name -> name, family_name), tylko do odczytu
    assert (body["name"], body["familyName"]) == ("Anna", "Nowak")
    assert body["account"] == {"birthDate": None, "photoUrl": GOOGLE["picture"]}


def test_later_logins_keep_account_set_by_user(client_api):
    me(client_api, GOOGLE)
    call(client_api, "PUT /api/me", {"birthDate": "1990-05-17"}, claims=GOOGLE)

    body = me(client_api, {**GOOGLE, "picture": "https://lh3.googleusercontent.com/a/nowe"})

    assert body["account"] == {"birthDate": "1990-05-17", "photoUrl": GOOGLE["picture"]}


def test_email_account_starts_empty(client_api):
    body = me(client_api, EMAIL)
    assert body["familyName"] is None
    assert body["account"] == EMPTY


def test_google_photo_only_over_https(client_api):
    assert me(client_api, {**GOOGLE, "picture": "http://example.com/a.jpg"})["account"] == EMPTY


# --- PUT /api/me ---


def test_put_me_saves_birth_date(client_api, users_table):
    me(client_api, EMAIL)

    status, body = call(client_api, "PUT /api/me", {"birthDate": "1990-05-17"}, claims=EMAIL)

    assert status == 200
    assert body["name"] == "Ala"
    assert body["account"] == {"birthDate": "1990-05-17", "photoUrl": None}
    assert users_table.get_item(Key={"userId": "user-1"})["Item"]["account"] == {"birthDate": "1990-05-17"}


def test_put_me_does_not_change_names(client_api, users_table):
    me(client_api, GOOGLE)

    _, body = call(client_api, "PUT /api/me", {"birthDate": None, "lastName": "Kowalska", "name": "X"}, claims=GOOGLE)

    assert (body["name"], body["familyName"]) == ("Anna", "Nowak")
    assert "lastName" not in users_table.get_item(Key={"userId": "user-g"})["Item"]["account"]


def test_put_me_empty_date_clears_it_and_keeps_photo(client_api):
    me(client_api, GOOGLE)
    call(client_api, "PUT /api/me", {"birthDate": "1990-05-17"}, claims=GOOGLE)
    _, body = call(client_api, "PUT /api/me", {"birthDate": ""}, claims=GOOGLE)
    assert body["account"] == {"birthDate": None, "photoUrl": GOOGLE["picture"]}


def test_put_me_keeps_onboarding_profile(client_api):
    me(client_api, EMAIL)
    status, saved = call(client_api, "PUT /api/profile", {"answers": ANSWERS}, claims=EMAIL)
    assert status == 200

    _, body = call(client_api, "PUT /api/me", {"birthDate": "1990-05-17"}, claims=EMAIL)

    assert body["needsOnboarding"] is False
    assert body["profile"] == saved["profile"]


@pytest.mark.parametrize("birth_date", ["2999-01-01", "1899-12-31", "17.05.1990", "1990-02-30", "19900517", 1990])
def test_put_me_rejects_bad_birth_date(client_api, birth_date):
    status, body = call(client_api, "PUT /api/me", {"birthDate": birth_date}, claims=EMAIL)
    assert status == 400
    assert body == {"error": "Niepoprawne dane profilu", "fields": ["birthDate"]}


# --- zdjęcie profilowe ---


def test_photo_upload_form_only_for_images(client_api):
    status, body = call(client_api, "POST /api/me/photo", {"contentType": "image/gif"}, claims=EMAIL)
    assert status == 400
    assert body["fields"] == ["contentType"]

    status, body = call(client_api, "POST /api/me/photo", {"contentType": "image/webp"}, claims=EMAIL)

    assert status == 200
    assert body["key"].startswith("photos/avatars/user-1/")
    assert body["key"].endswith(".webp")
    assert body["upload"]["fields"]["key"] == body["key"]
    assert body["upload"]["fields"]["Content-Type"] == "image/webp"
    assert PHOTOS_BUCKET in body["upload"]["url"]


def test_put_photo_sets_url_and_removes_previous_file(client_api):
    me(client_api, EMAIL)
    first = upload(client_api, EMAIL)
    status, body = call(client_api, "PUT /api/me/photo", {"key": first}, claims=EMAIL)
    assert status == 200
    assert body["account"]["photoUrl"] == f"{PHOTOS_BASE_URL}/{first}"

    second = upload(client_api, EMAIL, "image/png")
    _, body = call(client_api, "PUT /api/me/photo", {"key": second}, claims=EMAIL)

    assert body["account"]["photoUrl"] == f"{PHOTOS_BASE_URL}/{second}"
    assert photo_files() == [second]


def test_put_photo_rejects_foreign_or_not_uploaded_file(client_api):
    other = upload(client_api, GOOGLE)
    status, body = call(client_api, "PUT /api/me/photo", {"key": other}, claims=EMAIL)
    assert (status, body["fields"]) == (400, ["key"])

    not_uploaded = "photos/avatars/user-1/0123456789abcdef.jpg"
    status, body = call(client_api, "PUT /api/me/photo", {"key": not_uploaded}, claims=EMAIL)
    assert (status, body["fields"]) == (400, ["key"])

    status, _ = call(client_api, "PUT /api/me/photo", {"key": "../user-g/x.jpg"}, claims=EMAIL)
    assert status == 400


def test_delete_photo_removes_url_and_file(client_api):
    me(client_api, EMAIL)
    key = upload(client_api, EMAIL)
    call(client_api, "PUT /api/me/photo", {"key": key}, claims=EMAIL)

    status, body = call(client_api, "DELETE /api/me/photo", claims=EMAIL)

    assert status == 200
    assert body["account"]["photoUrl"] is None
    assert photo_files() == []


def test_deleted_google_photo_does_not_come_back_on_login(client_api):
    me(client_api, GOOGLE)
    call(client_api, "DELETE /api/me/photo", claims=GOOGLE)
    assert me(client_api, GOOGLE)["account"]["photoUrl"] is None
