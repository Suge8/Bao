import importlib
import sys
from pathlib import Path

_SHARED_OFFICE = Path(__file__).resolve().parents[4] / "_office_shared" / "scripts" / "office"
if str(_SHARED_OFFICE) not in sys.path:
    sys.path.insert(0, str(_SHARED_OFFICE))

_shared_mod = importlib.import_module("office_validators")
_SharedDOCXSchemaValidator = getattr(_shared_mod, "DOCXSchemaValidator")
_SharedPPTXSchemaValidator = getattr(_shared_mod, "PPTXSchemaValidator")
RedliningValidator = getattr(_shared_mod, "RedliningValidator")

_LOCAL_SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"


class DOCXSchemaValidator(_SharedDOCXSchemaValidator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schemas_dir = _LOCAL_SCHEMAS_DIR


class PPTXSchemaValidator(_SharedPPTXSchemaValidator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.schemas_dir = _LOCAL_SCHEMAS_DIR


__all__ = [
    "DOCXSchemaValidator",
    "PPTXSchemaValidator",
    "RedliningValidator",
]
