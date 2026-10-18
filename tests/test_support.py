"""tests/support.load_lambda: przed importem czyści moduły obu Lambd API, także pakiet routes (routes.*)."""

import sys
from types import ModuleType

import pytest

from tests.support import forget_lambda_modules

LAMBDA_MODULES = ["handler", "schemas", "profiles", "store", "routes", "routes.me", "routes.common"]


def test_forget_lambda_modules_clears_modules_and_route_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in LAMBDA_MODULES:
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    forget_lambda_modules()
    assert [name for name in LAMBDA_MODULES if name in sys.modules] == []
    assert "json" in sys.modules and "pytest" in sys.modules  # inne moduły zostają
