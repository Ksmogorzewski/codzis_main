"""Standard zdjęć wydarzeń i ich przetwarzanie (tagger to jedyny zapisujący codzis-events).

Standard v2 (VERSION): WebP 3:2 (jak pole plakatu na karcie i nagłówek szczegółów), do 1200×800 px, jakość 82,
sRGB, bez metadanych. Z jednego źródła zawsze ten sam plik:
  - proporcje od 4:3 do 16:9 -> zdjęcie wypełnia kadr (z brzegu znika najwyżej 8%: przy 4:3 z góry i z dołu, przy
    16:9 z boków), w rozdzielczości najwyżej 2× źródła: miniatura UM 360×270 -> 720×480, dalej skaluje przeglądarka,
  - inne proporcje (plakat pionowy, kwadrat, 5:4, panorama) -> całe zdjęcie, powiększone najwyżej 2×, na jednolitym
    polu 3:2 w średnim kolorze brzegu zdjęcia (pole najmniejsze, w którym zdjęcie się mieści; plakat na jednolitym
    tle przechodzi w nie bez widocznej krawędzi; płaski kolor, bez rozmyć - jak w kierunku „Plakat”) - z kadru nic
    nie znika, więc tekst na plakatach zostaje czytelny,
  - po skalowaniu lekkie wyostrzenie; kolory z profilu ICC źródła (np. Display P3 z telefonu) przeliczone na sRGB;
    przezroczystość na jasnym papierze; animacja = pierwsza klatka; obrót według EXIF.
Historia: v1 - małe zdjęcia (większość z API UM to miniatury 360×270 / 400×265) stały na środku pola 1200×800,
jak w ramce; v2 - wypełniają kadr.

Plik: s3://<PHOTOS_BUCKET>/photos/events/<VERSION>/<sha1 adresu źródła>.webp, publicznie pod
<PHOTOS_BASE_URL>/photos/events/<VERSION>/… (CloudFront panelu, jak zdjęcia profilowe). W rekordzie: imageUrl = nasz
plik, sourceImageUrl = źródło. Ten sam adres źródła = ten sam plik (drugi raz go nie liczymy).

Kiedy: tagger przy każdym zapisie wydarzenia (run_task.write); istniejące wydarzenia jednorazowo przebiegiem po
tabeli: `python -m tagger.images` (scripts/resize-images.sh). Zmiana standardu = nowy VERSION (nowe klucze)
i ten sam przebieg.

Pobieramy tylko https z publicznych adresów (bez sieci wewnętrznej), do 15 MB i 25 Mpx po dekodowaniu (duże JPEG
dekodują się od razu zmniejszone). Nieudane zdjęcie nie zatrzymuje zapisu wydarzenia: zostaje adres źródłowy (front
i tak pokaże plakat, gdy zdjęcie nie działa). Zdjęcie usunięte u źródła (404/410) to nie błąd przebiegu.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import ipaddress
import logging
import math
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from botocore.exceptions import ClientError
from PIL import Image, ImageCms, ImageFilter, ImageOps, ImageStat

log = logging.getLogger("tagger.images")

VERSION = "v2"
WIDTH, HEIGHT = 1200, 800
QUALITY = 82
FILL_RANGE = (4 / 3, 16 / 9)  # proporcje źródła, przy których zdjęcie wypełnia kadr 3:2
MAX_UPSCALE = 2.0
MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 25_000_000
TIMEOUT_S = 15
PAPER = (248, 248, 245)  # --card z portalu: tło pod przezroczystymi PNG
PREFIX = f"photos/events/{VERSION}/"
USER_AGENT = "WarsawNow-images/1 (+https://portal.waw-out.pl)"

# Limit pikseli (pamięć zadania: 512 MB w ECS) sprawdza _decode po zmniejszeniu JPEG przy dekodowaniu, zamiast
# ostrzeżeń i DecompressionBombError Pillow już przy otwarciu pliku (odrzucałby zdjęcia z aparatów).
Image.MAX_IMAGE_PIXELS = None
_SRGB = ImageCms.createProfile("sRGB")


# --------------------------------------------------------------------------- obraz


def render(data: bytes) -> bytes:
    """Bajty zdjęcia (JPEG, PNG, WebP, GIF…) -> WebP w standardzie. ValueError, gdy to nie obraz albo za duży."""
    try:
        image = _decode(data)
    except (OSError, ValueError) as e:
        raise ValueError(f"to nie jest obsługiwany obraz: {e}") from e
    out = io.BytesIO()
    _compose(image).save(out, "WEBP", quality=QUALITY, method=6)
    return out.getvalue()


def _decode(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as source:
        source.seek(0)  # animacja: pierwsza klatka
        # JPEG dekoduje się od razu w skali 1/2…1/8 (nadal co najmniej 2× kadru): mniej pamięci i czasu
        source.draft("RGB", (WIDTH * 2, HEIGHT * 2))
        if source.width * source.height > MAX_PIXELS:
            raise ValueError(f"za duży: {source.width}×{source.height} px")
        return _flatten(_to_srgb(ImageOps.exif_transpose(source)))


def _to_srgb(image: Image.Image) -> Image.Image:
    """Kolory według profilu ICC źródła -> sRGB (bez tego po zdjęciu metadanych np. Display P3 by zmatowiało)."""
    icc = image.info.get("icc_profile")
    if not icc or image.mode not in ("RGB", "RGBA", "CMYK"):
        return image
    try:
        profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        converted = ImageCms.profileToProfile(
            image, profile, _SRGB, outputMode="RGBA" if image.mode == "RGBA" else "RGB"
        )
    except (ImageCms.PyCMSError, OSError, ValueError):  # uszkodzony profil: kolory jak w pliku
        return image
    return converted if converted is not None else image


def _flatten(image: Image.Image) -> Image.Image:
    """RGB bez przezroczystości: kanał alfa na jasnym papierze, reszta trybów (P, CMYK, L…) wprost do RGB."""
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        paper = Image.new("RGB", rgba.size, PAPER)
        paper.paste(rgba, mask=rgba.getchannel("A"))
        return paper
    return image.convert("RGB")


def _compose(image: Image.Image) -> Image.Image:
    width, height = image.size
    if FILL_RANGE[0] - 0.01 <= width / height <= FILL_RANGE[1] + 0.01:
        # wypełnia kadr: przycięcie do 3:2, najwyżej 2× źródła i najwyżej 1200×800 (szerokość podzielna przez 3)
        out_width = int(min(WIDTH, min(width, height * 3 / 2) * MAX_UPSCALE)) // 3 * 3
        return _sharpen(ImageOps.fit(image, (out_width, out_width * 2 // 3), Image.Resampling.LANCZOS))
    scale = min(WIDTH / width, HEIGHT / height, MAX_UPSCALE)
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    # najmniejsze pole 3:2, w którym zdjęcie się mieści (małe źródło nie ląduje na środku wielkiego pola)
    frame_width = min(WIDTH, math.ceil(max(size[0], math.ceil(size[1] * 3 / 2)) / 3) * 3)
    frame = Image.new("RGB", (frame_width, frame_width * 2 // 3), _edge_color(image))
    frame.paste(
        _sharpen(image.resize(size, Image.Resampling.LANCZOS)),
        ((frame.width - size[0]) // 2, (frame.height - size[1]) // 2),
    )
    return frame


def _edge_color(image: Image.Image) -> tuple[int, ...]:
    """Średni kolor brzegu zdjęcia: pierścień 1 px na kopii zmniejszonej do 32×32."""
    small = image.resize((32, 32), Image.Resampling.BOX)
    ring = Image.new("L", small.size, 255)
    ring.paste(0, (1, 1, 31, 31))
    return tuple(round(v) for v in ImageStat.Stat(small, ring).mean)


def _sharpen(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))


# --------------------------------------------------------------------------- pobieranie


def check_url(url: str) -> str:
    """Tylko https z publicznego adresu (bez localhost, sieci prywatnej, adresów metadanych) -> url albo ValueError."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("zdjęcie tylko przez https")
    try:
        addresses = {str(info[4][0]) for info in socket.getaddrinfo(parts.hostname, parts.port or 443)}
    except OSError as e:
        raise ValueError(f"nie znamy hosta: {parts.hostname}") from e
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise ValueError(f"adres niepubliczny: {parts.hostname}")
    return url


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """Przekierowanie też musi prowadzić na publiczny https (inaczej omijałoby check_url)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_CheckedRedirect)


def download(url: str) -> bytes:
    """Zdjęcie spod publicznego https, najwyżej MAX_BYTES. ValueError przy kłopocie z adresem albo rozmiarem."""
    request = urllib.request.Request(check_url(url), headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    with _opener.open(request, timeout=TIMEOUT_S) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("zdjęcie większe niż 15 MB")
    return data


# --------------------------------------------------------------------------- pliki w S3


def key_for(source_url: str) -> str:
    """Klucz pliku w standardzie: wersja standardu + skrót adresu źródła (ten sam adres = ten sam plik)."""
    return f"{PREFIX}{hashlib.sha1(source_url.encode('utf-8')).hexdigest()[:24]}.webp"


class S3Images:
    """Pliki w buckecie zdjęć (photos/events/<wersja>/…), serwowane przez CloudFront panelu pod /photos/*."""

    def __init__(self, bucket: str, base_url: str, client: Any = None) -> None:
        import boto3  # dopiero tutaj: testy czystych funkcji nie potrzebują AWS

        self.bucket = bucket
        self.base_url = base_url.rstrip("/")
        self.s3 = client or boto3.client("s3")

    @classmethod
    def from_env(cls) -> S3Images | None:
        bucket, base_url = os.environ.get("PHOTOS_BUCKET"), os.environ.get("PHOTOS_BASE_URL")
        if not bucket or not base_url:
            log.warning("Bez PHOTOS_BUCKET / PHOTOS_BASE_URL - zdjęcia zostają w źródłowej postaci")
            return None
        return cls(bucket, base_url)

    def url(self, key: str) -> str:
        return f"{self.base_url}/{key}"

    def owns(self, url: str) -> bool:
        """Czy to już nasz plik w bieżącym standardzie."""
        return url.startswith(f"{self.base_url}/{PREFIX}")

    def exists(self, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put(self, key: str, data: bytes) -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType="image/webp",
            CacheControl="public, max-age=31536000, immutable",  # klucz zmienia się razem ze źródłem i standardem
        )


# --------------------------------------------------------------------------- rekordy


def ensure(source_url: str, store: S3Images, fetch: Callable[[str], bytes] = download) -> tuple[str, bool]:
    """Plik w standardzie dla źródła -> (publiczny adres, czy policzony teraz). Wyjątek, gdy się nie udało."""
    key = key_for(source_url)
    if store.exists(key):
        return store.url(key), False
    store.put(key, render(fetch(source_url)))
    return store.url(key), True


def source_of(record: dict, store: S3Images) -> str | None:
    """Adres źródła zdjęcia: zapisany sourceImageUrl, a bez niego imageUrl (o ile to nie nasz plik)."""
    source = record.get("sourceImageUrl") or record.get("imageUrl")
    if not isinstance(source, str) or not source or store.owns(source):
        return None
    return source


def normalize_image(record: dict, store: S3Images | None, fetch: Callable[[str], bytes] = download) -> dict:
    """Rekord ze zdjęciem w standardzie: imageUrl = nasz plik, sourceImageUrl = źródło. Bez zdjęcia, bez
    magazynu albo po błędzie - rekord bez zmian (zdjęcie to dodatek, wydarzenie zapisujemy i tak)."""
    if store is None:
        return record
    source = source_of(record, store)
    if source is None:
        return record
    try:
        url, _ = ensure(source, store, fetch)
    except Exception as e:  # zdjęcie nie może zatrzymać zapisu wydarzenia
        log.warning("Zdjęcie wydarzenia %s zostaje źródłowe: %s", record.get("id"), e)
        return record
    return {**record, "imageUrl": url, "sourceImageUrl": source}


def backfill(
    table: Any,
    store: S3Images,
    *,
    workers: int = 8,
    limit: int | None = None,
    dry_run: bool = False,
    fetch: Callable[[str], bytes] = download,
) -> Counter[str]:
    """Przebieg po całej tabeli wydarzeń: zdjęcia do standardu i nowe adresy w rekordach (UpdateItem).

    dry_run: tylko pobranie i przeliczenie (rozmiary w logu), bez zapisu plików i rekordów."""
    items = _scan(table)
    todo = [(item, source) for item in items if (source := source_of(item, store))][:limit]
    stats: Counter[str] = Counter(events=len(items), with_photo=len(todo))

    def one(pair: tuple[dict, str]) -> str:
        item, source = pair
        try:
            if dry_run:
                data = render(fetch(source))
                log.info("%s: %d KB", item["id"], len(data) // 1024)
                return "sprawdzone"
            url, created = ensure(source, store, fetch)
            if item.get("imageUrl") != url or item.get("sourceImageUrl") != source:
                # klient, nie zasób boto3: klienta można dzielić między wątkami
                table.meta.client.update_item(
                    TableName=table.name,
                    Key={"id": item["id"]},
                    UpdateExpression="SET imageUrl = :url, sourceImageUrl = :source",
                    # wydarzenie wygasło (TTL) w trakcie przebiegu: nie wskrzeszamy go samym zdjęciem
                    ConditionExpression="attribute_exists(id)",
                    ExpressionAttributeValues={":url": url, ":source": source},
                )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return "wygasło w trakcie"
            log.warning("Zdjęcie wydarzenia %s bez zmian: %s", item["id"], e)
            return "błąd"
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return "brak u źródła"  # zdjęcie usunięte w UM - to nie nasz błąd, front pokaże plakat
            log.warning("Zdjęcie wydarzenia %s bez zmian: %s", item["id"], e)
            return "błąd"
        except Exception as e:
            log.warning("Zdjęcie wydarzenia %s bez zmian: %s", item["id"], e)
            return "błąd"
        return "przeliczone" if created else "z gotowego pliku"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        stats.update(pool.map(one, todo))
    return stats


def _scan(table: Any) -> list[dict]:
    params: dict[str, Any] = {
        "ProjectionExpression": "id, imageUrl, sourceImageUrl",
    }
    found: list[dict] = []
    while True:
        page = table.scan(**params)
        found.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            return found
        params["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zdjęcia wszystkich wydarzeń do standardu (jednorazowo / po zmianie).")
    ap.add_argument("--limit", type=int, default=None, help="tylko pierwsze N wydarzeń ze zdjęciem")
    ap.add_argument("--dry-run", action="store_true", help="bez zapisu: pobranie, przeliczenie i rozmiary")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    import boto3

    store = S3Images.from_env()
    if store is None:
        return 1
    table = boto3.resource("dynamodb").Table(os.environ["DYNAMODB_TABLE"])
    stats = backfill(table, store, workers=args.workers, limit=args.limit, dry_run=args.dry_run)
    log.info("Zdjęcia %s: %s", VERSION, dict(stats))
    return 0 if not stats.get("błąd") else 2


if __name__ == "__main__":
    sys.exit(main())
