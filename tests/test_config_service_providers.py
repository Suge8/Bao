from __future__ import annotations

import json
from pathlib import Path

from tests._config_service_testkit import load_service


def test_get_providers_preserves_config_order_and_hides_internal_fields(tmp_path: Path) -> None:
    config_text = """{
  "providers": {
    "late": {
      "type": "openai",
      "apiKey": "sk-late",
      "order": 5
    },
    "early": {
      "type": "openai",
      "apiKey": "sk-early",
      "extraHeaders": {
        "x-test": "1"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  }
}"""
    svc, _ = load_service(tmp_path, config_text)

    providers = svc.getProviders()
    assert [provider["name"] for provider in providers] == ["late", "early"]
    assert providers[0] == {
        "name": "late",
        "type": "openai",
        "apiKey": "sk-late",
        "apiBase": "",
    }
    assert "order" not in providers[1]
    assert "extraHeaders" not in providers[1]


def test_save_full_providers_object_with_dotted_name_and_comments(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments

    config_text = (
        "{\n"
        "  // provider config\n"
        '  "providers": {\n'
        '    "openaiCompatible": {\n'
        '      "type": "openai",\n'
        '      "apiKey": "sk-old",\n'
        '      "apiBase": "https://api.openai.com/v1"\n'
        "    }\n"
        "  },\n"
        '  "agents": {\n'
        '    "defaults": {\n'
        '      "model": "openai/gpt-4o"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    svc, cfg = load_service(tmp_path, config_text)

    ok = svc.save(
        {
            "providers": {
                "foo.bar": {
                    "type": "openai",
                    "apiKey": "sk-new",
                    "apiBase": "https://api.example.com/v1",
                }
            }
        }
    )
    assert ok is True

    written = cfg.read_text(encoding="utf-8")
    assert "// provider config" in written
    assert '// "provider-name": {' in written
    assert '//   "extraHeaders": {},' in written
    data = json.loads(_strip_comments(written))
    assert data["providers"]["foo.bar"]["apiKey"] == "sk-new"
    assert "order" not in data["providers"]["foo.bar"]


def test_save_providers_preserves_explicit_ui_order_for_numeric_names(tmp_path: Path) -> None:
    from app.backend.jsonc_patch import _strip_comments

    config_text = """{
  "providers": {
    "alpha": {
      "type": "openai",
      "apiKey": "sk-alpha"
    },
    "beta": {
      "type": "openai",
      "apiKey": "sk-beta"
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  }
}"""
    svc, cfg = load_service(tmp_path, config_text)

    ok = svc.save(
        {
            "providers": [
                {"name": "2", "value": {"type": "openai", "apiKey": "sk-two"}},
                {"name": "10", "value": {"type": "openai", "apiKey": "sk-ten"}},
                {"name": "1", "value": {"type": "openai", "apiKey": "sk-one"}},
            ]
        }
    )
    assert ok is True

    data = json.loads(_strip_comments(cfg.read_text(encoding="utf-8")))
    assert list(data["providers"].keys()) == ["2", "10", "1"]


def test_save_provider_named_provider_name_still_injects_template_comment(tmp_path: Path) -> None:
    config_text = """{
  "providers": {},
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o"
    }
  }
}"""
    svc, cfg = load_service(tmp_path, config_text)

    ok = svc.save(
        {
            "providers": {
                "provider-name": {
                    "type": "openai",
                    "apiKey": "sk-real",
                }
            }
        }
    )
    assert ok is True

    written = cfg.read_text(encoding="utf-8")
    assert '// "provider-name": {' in written
    assert '"provider-name": {' in written
    assert written.count('// "provider-name": {') == 1
