"""Wspólne narzędzia testów backendu (importowane przez conftest.py, więc env ustawia się pierwsze).

Każda Lambda ma własny katalog i własny moduł `handler`, importowany tak jak w Lambdzie
(`import handler`, `from onboarding import ...`). Dlatego handler ładujemy funkcją `load_lambda`:
czyści wcześniej załadowane moduły Lambd z `sys.modules` (także pakiety, np. `routes` i `routes.*`, które
client-api i API partnera mają pod tą samą nazwą) i importuje z właściwego katalogu.
Import musi nastąpić wewnątrz `mock_aws()`, bo klienty boto3 powstają na poziomie modułu.
"""

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
CLIENT_API_DIR = SRC / "client_api"
API_DIR = SRC / "api"

# Fałszywe dane AWS: testy nigdy nie mogą trafić do prawdziwego konta.
for _name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"):
    os.environ.pop(_name, None)
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "eu-central-1"
os.environ["AWS_REGION"] = "eu-central-1"

DISTRICTS = ["Mokotów", "Śródmieście", "Wola"]


def _lambda_module_names() -> set[str]:
    """Moduły (`schemas`, `profiles`…) i pakiety (`routes`) z katalogów Lambd API."""
    names: set[str] = set()
    for directory in (CLIENT_API_DIR, API_DIR):
        names.update(p.stem for p in directory.glob("*.py"))
        names.update(p.parent.name for p in directory.glob("*/__init__.py"))
    return names


def forget_lambda_modules() -> None:
    """Usuwa z `sys.modules` moduły Lambd API razem z modułami pakietów (`routes.me`…)."""
    names = _lambda_module_names()
    for name in [n for n in sys.modules if n.split(".", 1)[0] in names]:
        del sys.modules[name]


def load_lambda(directory: Path, module: str = "handler") -> ModuleType:
    """Importuje świeży moduł Lambdy z `directory` (jak w runtime: katalog w sys.path)."""
    forget_lambda_modules()
    path = str(directory)
    sys.path.insert(0, path)
    try:
        return importlib.import_module(module)
    finally:
        sys.path.remove(path)


def taxonomy() -> dict[str, list[str]]:
    """Opcje taksonomii taggera (tagger/prompt.py -> DIMENSIONS) - kontrakt z ankietą i formularzem partnera.

    Ładujemy sam plik (bez tagger/__init__.py, który potrzebuje zależności taggera)."""
    spec = importlib.util.spec_from_file_location("tagger_prompt", REPO / "tagger" / "prompt.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name: dim["options"] for name, dim in module.DIMENSIONS.items()}
