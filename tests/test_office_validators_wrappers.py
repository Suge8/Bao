import importlib
import subprocess
import sys
from pathlib import Path

pytest = importlib.import_module("pytest")

_ROOT = Path(__file__).resolve().parents[1]
_SKILLS = ("docx", "pptx", "xlsx")


def _office_dir(skill: str) -> Path:
    return _ROOT / "bao" / "skills" / skill / "scripts" / "office"


def _validate_script(skill: str) -> Path:
    return _office_dir(skill) / "validate.py"


def _purge_validator_modules() -> None:
    for name in list(sys.modules):
        if name == "validators" or name.startswith("validators."):
            _ = sys.modules.pop(name, None)
        if name == "office_validators" or name.startswith("office_validators."):
            _ = sys.modules.pop(name, None)


def _import_validators_for_skill(skill: str):
    _purge_validator_modules()
    office_dir = _office_dir(skill)
    office_dir_text = str(office_dir)
    sys.path.insert(0, office_dir_text)
    try:
        return importlib.import_module("validators")
    finally:
        try:
            sys.path.remove(office_dir_text)
        except ValueError:
            pass


@pytest.mark.parametrize("skill", _SKILLS)
def test_validate_help_runs_for_each_skill(skill: str) -> None:
    result = subprocess.run(
        [sys.executable, str(_validate_script(skill)), "--help"],
        capture_output=True,
        text=True,
    )
    combined = f"{result.stdout}\n{result.stderr}".lower()
    assert result.returncode == 0
    assert "usage: validate.py" in combined


@pytest.mark.parametrize("skill", _SKILLS)
def test_validators_wrappers_bind_local_schemas(skill: str) -> None:
    validators = _import_validators_for_skill(skill)
    local_schemas = (_office_dir(skill) / "schemas").resolve()

    docx_validator = validators.DOCXSchemaValidator(_office_dir(skill), None, False)
    pptx_validator = validators.PPTXSchemaValidator(_office_dir(skill), None, False)

    assert docx_validator.schemas_dir.resolve() == local_schemas
    assert pptx_validator.schemas_dir.resolve() == local_schemas
    assert hasattr(validators, "RedliningValidator")


def test_import_all_skills_in_one_process_without_cross_pollution() -> None:
    imported_from: list[Path] = []

    for skill in _SKILLS:
        validators = _import_validators_for_skill(skill)
        module_file_text = getattr(validators, "__file__", None)
        assert module_file_text is not None
        module_file = Path(module_file_text).resolve()
        imported_from.append(module_file)
        assert f"/{skill}/scripts/office/validators/__init__.py" in module_file.as_posix()

        local_schemas = (_office_dir(skill) / "schemas").resolve()
        assert (
            validators.DOCXSchemaValidator(_office_dir(skill), None, False).schemas_dir.resolve()
            == local_schemas
        )

    assert len(set(imported_from)) == 3
