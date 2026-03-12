from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "app/resources/icons/vendor/icon-manifest.json"
VENDOR_DIR = ROOT / "app/resources/icons/vendor"


def _download_text(url: str) -> str:
    with urlopen(url) as response:  # noqa: S310
        return response.read().decode("utf-8")


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    for icon in manifest["starterIcons"]:
        source = sources[icon["source"]]
        raw_url = f"{source['rawBaseUrl']}/{icon['upstream']}"
        target = VENDOR_DIR / icon["local"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_download_text(raw_url), encoding="utf-8")
        print(f"synced {icon['local']} <- {raw_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
