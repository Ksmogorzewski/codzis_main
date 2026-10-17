"""Wspólne narzędzia testów backendu (importowane przez conftest.py, więc env ustawia się pierwsze).

Każda Lambda ma własny katalog i własny moduł `handler`, importowany tak jak w Lambdzie
(`import handler`, `from onboarding import ...`). Dlatego handler ładujemy funkcją `load_lambda`:
czyści wcześniej załadowane moduły Lambd z `sys.modules` i importuje z właściwego katalogu.
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
    names = set()
    for directory in (CLIENT_API_DIR, API_DIR):
        names.update(p.stem for p in directory.glob("*.py"))
    return names


def load_lambda(directory: Path, module: str = "handler") -> ModuleType:
    """Importuje świeży moduł Lambdy z `directory` (jak w runtime: katalog w sys.path)."""
    for name in _lambda_module_names():
        sys.modules.pop(name, None)
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
