"""Smoke tests: verify every declared dependency is importable."""

import importlib

import pytest

# fmt: off
PACKAGES = [
    "pyoxigraph",
    "rdflib",
    "pyshacl",
    "pgmpy",
    "dowhy",
    "langgraph",
    "pydantic_ai",
    "pydantic_settings",
    "pyreadstat",
    "morph_kgc",
    "openai",
]
# fmt: on


@pytest.mark.parametrize("package", PACKAGES)
def test_import(package: str) -> None:
    """Import the package and assert it exposes __version__ or __name__."""
    mod = importlib.import_module(package)
    assert hasattr(mod, "__version__") or hasattr(mod, "__name__"), (
        f"{package} has neither __version__ nor __name__"
    )
