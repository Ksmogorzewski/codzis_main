"""Standard zdjęć wydarzeń (tagger/images.py): obraz w standardzie, adresy źródeł, rekordy i przebieg po tabeli.

S3 i DynamoDB na atrapach moto, pobieranie zdjęć podmienione (bez sieci).
"""

import io
import socket
import urllib.error
import urllib.request
from collections import Counter
from email.message import Message

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from PIL import Image, ImageCms

from tagger import images
from tagger.images import HEIGHT, PAPER, PREFIX, WIDTH, S3Images, backfill, check_url, key_for, normalize_image, render

BUCKET = "test-photos"
BASE = "https://partner.example.pl"
UM = "https://um.warszawa.pl/documents/1/2/plakat.png"
OTHER = "https://um.warszawa.pl/documents/1/3/zajecia.jpg"
RED, BLUE, BEIGE = (200, 30, 30), (30, 60, 200), (232, 214, 186)


def picture(
    size: tuple[int, int], color: tuple[int, ...] = RED, *, mode: str = "RGB", fmt: str = "PNG", **save
) -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, fmt, **save)
    return out.getvalue()


def encoded(image: Image.Image, fmt: str = "PNG", **save) -> bytes:
    out = io.BytesIO()
    image.save(out, fmt, **save)
    return out.getvalue()


def opened(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def pixel(image: Image.Image, xy: tuple[int, int]) -> tuple[int, ...]:
    value = image.convert("RGB").getpixel(xy)
    assert isinstance(value, tuple)
    return value


def near(value: tuple[int, ...], color: tuple[int, ...], tolerance: int = 16) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(value, color, strict=True))


def ringed(size: tuple[int, int], ring: int = 12) -> bytes:
    """Niebieskie zdjęcie w czerwonej ramce: widać, ile zostało z brzegów i gdzie zaczyna się pole wokół."""
    image = Image.new("RGB", size, RED)
    image.paste(BLUE, (ring, ring, size[0] - ring, size[1] - ring))
    return encoded(image)


class Source:
    """Atrapa pobierania: zwraca obraz (albo rzuca błąd) i zapamiętuje, o co proszono."""

    def __init__(self, data: bytes | None = None, failing: tuple[str, ...] = (), missing: tuple[str, ...] = ()) -> None:
        self.data = data or picture((1500, 1000))
        self.failing = failing
        self.missing = missing
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self.failing:
            raise ValueError("zepsute")
        if url in self.missing:
            raise urllib.error.HTTPError(url, 404, "Not Found", Message(), None)
        return self.data


# --------------------------------------------------------------------------- obraz


@pytest.mark.parametrize(
    "size", [(1500, 1000), (600, 400), (360, 270), (400, 265), (1080, 1350), (3000, 500), (40, 40)]
)
def test_every_source_ends_in_the_standard(size):
    out = opened(render(picture(size, fmt="JPEG", exif=Image.Exif())))
    assert out.format == "WEBP"
    assert out.width * 2 == out.height * 3 and out.width <= WIDTH  # zawsze 3:2, najwyżej 1200×800
    assert out.mode == "RGB"
    assert not out.info.get("exif") and not out.info.get("icc_profile")  # bez metadanych


@pytest.mark.parametrize(
    ("size", "trimmed", "kept"),
    [
        ((1600, 1200), (600, 5), (4, 400)),  # 4:3: z góry i z dołu znika po 5,5%
        ((1920, 1080), (4, 400), (600, 4)),  # 16:9: z boków po 7,8%
    ],
)
def test_4_3_to_16_9_fills_the_frame(size, trimmed, kept):
    out = opened(render(ringed(size)))
    assert near(pixel(out, trimmed), BLUE)  # ta część ramki ucięta - kadr wypełniony, bez pola wokół
    assert near(pixel(out, kept), RED)
    assert near(pixel(out, (600, 400)), BLUE)


@pytest.mark.parametrize(
    ("size", "edges"),
    [
        ((1250, 1000), [(600, 4), (600, HEIGHT - 5)]),  # 5:4: pole po bokach, góra i dół całe
        ((1200, 628), [(4, 400), (WIDTH - 5, 400)]),  # okładka 1,91:1: pole nad i pod, boki całe
    ],
)
def test_outside_the_range_nothing_is_cut(size, edges):
    out = opened(render(ringed(size)))
    for edge in edges:
        assert near(pixel(out, edge), RED)  # ramka zdjęcia widoczna - nic nie ucięte
    assert near(pixel(out, (600, 400)), BLUE)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1500, 1000), (WIDTH, HEIGHT)),
        ((600, 400), (WIDTH, HEIGHT)),
        ((360, 270), (720, 480)),
        ((400, 265), (795, 530)),
    ],
)
def test_photo_resolution_is_at_most_2x_source(size, expected):
    assert opened(render(picture(size))).size == expected


def test_small_photo_fills_the_frame():
    out = opened(render(ringed((360, 270))))  # miniatura UM 4:3: kadr wypełniony, bez pola wokół
    assert out.size == (720, 480)
    assert near(pixel(out, (360, 4)), BLUE)  # góra ramki ucięta (4:3 -> 3:2)
    assert near(pixel(out, (4, 240)), RED)  # boki całe
    assert near(pixel(out, (360, 240)), BLUE)


def test_small_poster_gets_only_as_much_field_as_needed():
    out = opened(render(ringed((200, 300))))  # pionowy, 2× = 400×600 -> pole 900×600, nie 1200×800
    assert out.size == (900, 600)
    assert near(pixel(out, (100, 300)), RED)  # po bokach pole w kolorze brzegu plakatu
    assert near(pixel(out, (450, 300)), BLUE)


def test_poster_is_shown_whole():
    poster = Image.new("RGB", (1080, 1350), BLUE)
    poster.paste(RED, (0, 0, 1080, 100))  # pasek u góry i u dołu: przy kadrowaniu by zniknęły
    poster.paste(RED, (0, 1250, 1080, 1350))
    out = opened(render(encoded(poster)))
    assert near(pixel(out, (600, 20)), RED)
    assert near(pixel(out, (600, 400)), BLUE)
    assert near(pixel(out, (600, 780)), RED)
    assert not near(pixel(out, (100, 400)), BLUE)  # obok plakatu pole, nie plakat


def test_frame_continues_poster_background():
    poster = Image.new("RGB", (1080, 1350), BEIGE)  # plakat na jednolitym tle, „tekst” na środku
    poster.paste(BLUE, (200, 300, 880, 1050))
    out = opened(render(encoded(poster)))
    assert near(pixel(out, (100, 400)), BEIGE, tolerance=8)  # pole = tło plakatu, bez widocznej krawędzi
    assert near(pixel(out, (1100, 700)), BEIGE, tolerance=8)
    assert near(pixel(out, (600, 400)), BLUE)


def test_transparency_lands_on_paper():
    out = opened(render(picture((1200, 800), (0, 0, 0, 0), mode="RGBA")))
    assert near(pixel(out, (600, 400)), PAPER, tolerance=6)


def test_animation_uses_first_frame():
    frames = [Image.new("RGB", (600, 400), color) for color in (RED, BLUE)]
    data = encoded(frames[0], "GIF", save_all=True, append_images=frames[1:])
    assert near(pixel(opened(render(data)), (600, 400)), RED, tolerance=24)


def test_exif_orientation_is_applied():
    photo = Image.new("RGB", (600, 400), RED)
    photo.paste(BLUE, (300, 0, 600, 400))
    exif = Image.Exif()
    exif[0x0112] = 6  # zapisane na boku: do wyświetlenia obrót o 90° w prawo
    out = opened(render(encoded(photo, "JPEG", exif=exif, quality=95)))
    assert near(pixel(out, (600, 150)), RED, tolerance=24)  # lewa połowa trafia na górę
    assert near(pixel(out, (600, 650)), BLUE, tolerance=24)


def test_icc_profile_is_converted_or_ignored_when_broken():
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    assert near(pixel(opened(render(picture((1500, 1000), icc_profile=srgb))), (600, 400)), RED)
    assert near(pixel(opened(render(picture((1500, 1000), icc_profile=b"zepsuty"))), (600, 400)), RED)


@pytest.mark.parametrize("data", [b"", b"<html>404</html>", picture((10, 10))[:20]])
def test_not_an_image_is_rejected(data):
    with pytest.raises(ValueError):
        render(data)


def test_too_many_pixels_are_rejected(monkeypatch):
    monkeypatch.setattr(images, "MAX_PIXELS", 1000)
    with pytest.raises(ValueError):
        render(picture((100, 100)))


def test_big_jpeg_is_decoded_smaller_instead_of_rejected(monkeypatch):
    monkeypatch.setattr(images, "MAX_PIXELS", 4_000_000)  # 4800×3200 = 15 Mpx, JPEG dekoduje się w 1/2: 3,8 Mpx
    assert opened(render(picture((4800, 3200), fmt="JPEG"))).size == (WIDTH, HEIGHT)
    with pytest.raises(ValueError):
        render(picture((4800, 3200)))  # PNG nie da się zdekodować mniejszego


# --------------------------------------------------------------------------- adresy


def test_key_depends_on_source_and_standard():
    key = key_for(UM)
    assert key == key_for(UM)
    assert key != key_for(OTHER)
    assert key.startswith(PREFIX) and key.endswith(".webp")


@pytest.mark.parametrize(
    "url",
    [
        "http://um.warszawa.pl/a.jpg",
        "ftp://um.warszawa.pl/a.jpg",
        "file:///etc/passwd",
        "https:///a.jpg",
        "https://127.0.0.1/a.jpg",
        "https://10.0.0.5/a.jpg",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/a.jpg",
        "https://[fd00::1]/a.jpg",
    ],
)
def test_only_public_https(url):
    with pytest.raises(ValueError):
        check_url(url)


def test_names_must_resolve_to_public_addresses_only(monkeypatch):
    answers = {
        "um.warszawa.pl": ["93.184.215.14"],
        "wewnetrzny.example": ["10.1.2.3"],
        "mieszany.example": ["93.184.215.14", "192.168.0.10"],
    }
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in answers[host]],
    )
    assert check_url(UM) == UM
    for host in ("wewnetrzny.example", "mieszany.example"):
        with pytest.raises(ValueError):
            check_url(f"https://{host}/a.jpg")


def test_redirect_must_stay_public():
    request = urllib.request.Request(UM)
    with pytest.raises(ValueError):
        images._CheckedRedirect().redirect_request(request, None, 302, "Found", {}, "https://169.254.169.254/")


# --------------------------------------------------------------------------- pliki i rekordy


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3")
        client.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-central-1"})
        yield client


@pytest.fixture
def store(s3):
    return S3Images(BUCKET, BASE + "/", client=s3)


def keys(s3) -> list[str]:
    return [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])]


def test_photo_goes_to_the_standard_file(store, s3):
    record = {"id": "um-1", "title": "Plakat", "imageUrl": UM}
    fetch = Source()

    out = normalize_image(record, store, fetch)

    assert out["imageUrl"] == f"{BASE}/{key_for(UM)}"
    assert out["sourceImageUrl"] == UM
    assert out["title"] == "Plakat"
    assert record["imageUrl"] == UM  # wejściowy rekord bez zmian
    assert fetch.calls == [UM]
    head = s3.head_object(Bucket=BUCKET, Key=key_for(UM))
    assert head["ContentType"] == "image/webp"
    assert "immutable" in head["CacheControl"]
    body = s3.get_object(Bucket=BUCKET, Key=key_for(UM))["Body"].read()
    assert opened(body).size == (WIDTH, HEIGHT)


def test_same_source_is_rendered_once(store):
    fetch = Source()
    first = normalize_image({"id": "um-1", "imageUrl": UM}, store, fetch)
    second = normalize_image({"id": "um-2", "imageUrl": UM}, store, fetch)
    again = normalize_image(first, store, fetch)  # ponowny zapis już przeliczonego rekordu

    assert fetch.calls == [UM]
    assert second["imageUrl"] == again["imageUrl"] == first["imageUrl"]
    assert again["sourceImageUrl"] == UM


def test_own_file_without_source_is_left_alone(store):
    record = {"id": "um-1", "imageUrl": f"{BASE}/{PREFIX}abc.webp"}
    fetch = Source()
    assert normalize_image(record, store, fetch) == record
    assert fetch.calls == []


@pytest.mark.parametrize("fetch", [Source(failing=(UM,)), Source(data=b"<html>404</html>")])
def test_failed_photo_keeps_the_source(store, s3, fetch):
    record = {"id": "um-1", "imageUrl": UM}
    assert normalize_image(record, store, fetch) == record
    assert keys(s3) == []


def test_without_store_or_photo_nothing_changes(store):
    record = {"id": "um-1", "imageUrl": UM}
    assert normalize_image(record, None) is record
    assert normalize_image({"id": "um-2"}, store, Source()) == {"id": "um-2"}


def test_store_from_env(monkeypatch):
    monkeypatch.delenv("PHOTOS_BUCKET", raising=False)
    monkeypatch.delenv("PHOTOS_BASE_URL", raising=False)
    assert S3Images.from_env() is None
    monkeypatch.setenv("PHOTOS_BUCKET", BUCKET)
    monkeypatch.setenv("PHOTOS_BASE_URL", BASE + "/")
    store = S3Images.from_env()
    assert store is not None and store.url("k") == f"{BASE}/k"


def test_access_denied_is_not_a_missing_file():
    """Bez s3:ListBucket brak pliku daje 403 - to błąd uprawnień (infra/worker.tf), nie „pliku nie ma”."""

    class Forbidden:
        def head_object(self, **_):
            raise ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")

    with pytest.raises(ClientError):
        S3Images(BUCKET, BASE, client=Forbidden()).exists("photos/events/v1/x.webp")


# --------------------------------------------------------------------------- przebieg po tabeli


@pytest.fixture
def table(s3):
    events = boto3.resource("dynamodb").create_table(
        TableName="test-events",
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    for item in (
        {"id": "um-a", "title": "A", "imageUrl": UM},
        {"id": "um-b", "title": "B", "imageUrl": OTHER},
        {"id": "um-c", "title": "C"},
        {"id": "um-d", "title": "D", "imageUrl": UM},  # to samo zdjęcie co um-a
    ):
        events.put_item(Item=item)
    return events


def item(table, event_id: str) -> dict:
    return table.get_item(Key={"id": event_id})["Item"]


def test_backfill_updates_records_and_reuses_files(table, store, s3):
    fetch = Source(failing=(OTHER,))

    stats = backfill(table, store, workers=1, fetch=fetch)

    assert stats == Counter({"events": 4, "with_photo": 3, "przeliczone": 1, "z gotowego pliku": 1, "błąd": 1})
    for event_id in ("um-a", "um-d"):
        assert item(table, event_id)["imageUrl"] == f"{BASE}/{key_for(UM)}"
        assert item(table, event_id)["sourceImageUrl"] == UM
    assert item(table, "um-a")["title"] == "A"  # reszta rekordu bez zmian
    assert item(table, "um-b") == {"id": "um-b", "title": "B", "imageUrl": OTHER}
    assert item(table, "um-c") == {"id": "um-c", "title": "C"}
    assert keys(s3) == [key_for(UM)]

    # drugi przebieg: gotowe pliki, ponawia tylko to, co się nie udało
    fetch.calls.clear()
    again = backfill(table, store, workers=1, fetch=fetch)
    assert again == Counter({"events": 4, "with_photo": 3, "z gotowego pliku": 2, "błąd": 1})
    assert fetch.calls == [OTHER]


def test_backfill_dry_run_writes_nothing(table, store, s3):
    stats = backfill(table, store, dry_run=True, fetch=Source(failing=(OTHER,)))
    assert stats == Counter({"events": 4, "with_photo": 3, "sprawdzone": 2, "błąd": 1})
    assert keys(s3) == []
    assert item(table, "um-a") == {"id": "um-a", "title": "A", "imageUrl": UM}


def test_backfill_counts_photos_missing_at_source_apart(table, store):
    stats = backfill(table, store, workers=1, fetch=Source(missing=(OTHER,)))
    assert stats["brak u źródła"] == 1 and not stats["błąd"]  # 404 u źródła: kod wyjścia 0
    assert item(table, "um-b")["imageUrl"] == OTHER


def test_backfill_limit(table, store):
    stats = backfill(table, store, limit=1, fetch=Source())
    assert stats["with_photo"] == 1 and stats["przeliczone"] == 1


def test_backfill_does_not_revive_expired_event(table, store):
    data = picture((1500, 1000))

    def fetch_while_expiring(url: str) -> bytes:
        for event_id in ("um-a", "um-b", "um-d"):  # TTL usuwa wydarzenia w trakcie przebiegu
            table.delete_item(Key={"id": event_id})
        return data

    stats = backfill(table, store, workers=1, fetch=fetch_while_expiring)

    assert stats["wygasło w trakcie"] == 3
    assert [i["id"] for i in table.scan()["Items"]] == ["um-c"]


def test_main_needs_photos_config(monkeypatch):
    monkeypatch.delenv("PHOTOS_BUCKET", raising=False)
    assert images.main([]) == 1
