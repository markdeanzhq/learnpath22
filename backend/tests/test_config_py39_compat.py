import importlib
import sys
from pathlib import Path

MODULES = [
    ("app.core.config", "PYTHON_BASELINE", "3.12"),
    ("app.models.sqlite_models", None, None),
    ("app.schemas.graph", None, None),
    ("app.schemas.profile", None, None),
    ("tests.test_explanation_readability", None, None),
    ("tests.test_generate_thesis_validation_evidence", None, None),
]


def test_python39_first_party_modules_import_cleanly():
    backend_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend_root))

    failures = {}
    for module_name, attr_name, expected in MODULES:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            failures[module_name] = f"{type(exc).__name__}: {exc}"
            continue
        if attr_name is not None:
            assert getattr(module, attr_name) == expected

    assert failures == {}, failures
